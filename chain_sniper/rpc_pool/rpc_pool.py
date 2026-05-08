"""
RPCPool — fault-tolerant RPC endpoint manager for ChainSniper.

Two concrete classes:
  - HttpRPCPool  — for HTTP/HTTPS endpoints
  - WssRPCPool   — for WebSocket (ws:// / wss://) endpoints

Both share the same public interface via the RPCPool base class.
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import List, Optional

import aiohttp
import websockets

from .rpc_node import RpcNode

logger = logging.getLogger(__name__)

_HEALTH_CHECK_INTERVAL = 60.0
_COOLDOWN_SECONDS = 30.0
_REQUEST_TIMEOUT = 5.0


# ------------------------------------------------------------------ #
# Base class                                                           #
# ------------------------------------------------------------------ #

class RPCPool(ABC):
    """
    Abstract base for HTTP and WebSocket RPC pools.

    Subclasses implement _validate_one() and _probe_one() for their protocol.
    """

    def __init__(self, nodes: List[RpcNode], expected_chain_id: int) -> None:
        if not nodes:
            raise RuntimeError(
                "RPCPool: no valid RPC endpoints survived chain-ID validation."
            )
        self._nodes = nodes
        self._lock = asyncio.Lock()
        self._monitor_task: Optional[asyncio.Task] = None
        self._expected_chain_id = expected_chain_id
        self._cooldown_seconds: float = _COOLDOWN_SECONDS
        self._health_check_interval: float = _HEALTH_CHECK_INTERVAL

    # ------------------------------------------------------------------ #
    # Factory (shared logic, delegates validation to subclass)            #
    # ------------------------------------------------------------------ #

    @classmethod
    async def create(
        cls,
        rpcs: List[str],
        expected_chain_id: int,
        cooldown_seconds: float = _COOLDOWN_SECONDS,
        health_check_interval: float = _HEALTH_CHECK_INTERVAL,
    ) -> "RPCPool":
        """Validate every endpoint and return a ready pool."""
        valid_nodes: List[RpcNode] = []

        results = await asyncio.gather(
            *[cls._validate_one(url, expected_chain_id) for url in rpcs],
            return_exceptions=True,
        )

        for url, result in zip(rpcs, results):
            if isinstance(result, RpcNode):
                valid_nodes.append(result)
            else:
                logger.warning("RPC rejected — %s: %s", url, result)

        pool = cls(valid_nodes, expected_chain_id)
        pool._cooldown_seconds = cooldown_seconds
        pool._health_check_interval = health_check_interval
        pool._monitor_task = asyncio.create_task(pool._health_monitor())
        logger.info(
            "%s ready with %d endpoint(s).",
            cls.__name__, len(valid_nodes),
        )
        return pool

    # ------------------------------------------------------------------ #
    # Public interface                                                     #
    # ------------------------------------------------------------------ #

    def get_rpc(self) -> str:
        """Return the URL of the fastest healthy endpoint."""
        healthy = [n for n in self._nodes if n.is_healthy]
        if not healthy:
            raise RuntimeError("all rpcs are unhealthy or in cooldown")
        healthy.sort(key=lambda n: n.latency)
        return healthy[0].url

    def mark_failed(self, url: str) -> None:
        node = self._node_by_url(url)
        if node:
            node.mark_failed(self._cooldown_seconds)
            logger.warning(
                "RPC marked failed — %s (errors=%d, dead=%s)",
                url, node.error_count, node.is_dead,
            )

    def record_success(self, url: str, elapsed_ms: float) -> None:
        node = self._node_by_url(url)
        if node:
            node.record_success(elapsed_ms)

    def stop(self) -> None:
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()

    @property
    def urls(self) -> List[str]:
        return [n.url for n in self._nodes]

    @property
    def healthy_urls(self) -> List[str]:
        return [n.url for n in self._nodes if n.is_healthy]

    @property
    def expected_chain_id(self) -> int:
        return self._expected_chain_id

    # ------------------------------------------------------------------ #
    # Abstract — protocol-specific                                        #
    # ------------------------------------------------------------------ #

    @classmethod
    @abstractmethod
    async def _validate_one(cls, url: str, expected_chain_id: int) -> RpcNode:
        """Validate a single endpoint; return RpcNode or raise."""

    @classmethod
    @abstractmethod
    async def _probe_one(cls, node: RpcNode) -> None:
        """Lightweight liveness probe used by the health monitor."""

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _node_by_url(self, url: str) -> Optional[RpcNode]:
        for node in self._nodes:
            if node.url == url:
                return node
        return None

    async def _health_monitor(self) -> None:
        while True:
            await asyncio.sleep(self._health_check_interval)
            sick = [n for n in self._nodes if not n.is_healthy]
            if not sick:
                continue
            for node in sick:
                try:
                    await self._probe_one(node)
                    node.revive()
                    logger.info("RPC revived — %s", node.url)
                except Exception as exc:
                    logger.debug("RPC still sick — %s: %s", node.url, exc)


# ------------------------------------------------------------------ #
# HTTP pool                                                            #
# ------------------------------------------------------------------ #

class HttpRPCPool(RPCPool):
    """
    RPC pool for HTTP / HTTPS endpoints.

    Example::

        pool = await HttpRPCPool.create(
            rpcs=[
                "https://bsc-dataseed1.binance.org",
                "https://bsc-dataseed2.binance.org",
            ],
            expected_chain_id=56,
        )
    """

    @classmethod
    async def _validate_one(cls, url: str, expected_chain_id: int) -> RpcNode:
        if not (url.startswith("http://") or url.startswith("https://")):
            raise ValueError(f"HttpRPCPool expects http(s):// URL, got: {url}")

        payload = {"jsonrpc": "2.0", "method": "eth_chainId", "params": [], "id": 1}
        try:
            t0 = time.monotonic()
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT),
                ) as resp:
                    data = await resp.json(content_type=None)
            elapsed = (time.monotonic() - t0) * 1000

            chain_id = int(data["result"], 16)
            if chain_id != expected_chain_id:
                raise ValueError(
                    f"chain_id mismatch: got {chain_id}, expected {expected_chain_id}"
                )

            node = RpcNode(url=url, latency=elapsed)
            logger.info("HTTP RPC accepted — %s (chain=%d, latency=%.0fms)", url, chain_id, elapsed)
            return node
        except Exception as exc:
            raise ValueError(str(exc)) from exc

    @classmethod
    async def _probe_one(cls, node: RpcNode) -> None:
        payload = {"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1}
        async with aiohttp.ClientSession() as session:
            async with session.post(
                node.url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT),
            ) as resp:
                data = await resp.json(content_type=None)
        if "error" in data:
            raise ValueError(data["error"])


# ------------------------------------------------------------------ #
# WebSocket pool                                                       #
# ------------------------------------------------------------------ #

class WssRPCPool(RPCPool):
    """
    RPC pool for WebSocket (ws:// / wss://) endpoints.

    Validation and health probes use a real WebSocket connection so the
    pool only accepts nodes that are reachable over the WS protocol.

    Example::

        pool = await WssRPCPool.create(
            rpcs=[
                "wss://bsc-ws-node.nariox.org:443",
                "wss://rpc.ankr.com/bsc/ws",
            ],
            expected_chain_id=56,
        )
    """

    @classmethod
    async def _validate_one(cls, url: str, expected_chain_id: int) -> RpcNode:
        if not (url.startswith("ws://") or url.startswith("wss://")):
            raise ValueError(f"WssRPCPool expects ws(s):// URL, got: {url}")

        payload = {"jsonrpc": "2.0", "method": "eth_chainId", "params": [], "id": 1}
        try:
            t0 = time.monotonic()
            async with asyncio.timeout(_REQUEST_TIMEOUT):
                async with websockets.connect(url) as ws:
                    await ws.send(__import__("json").dumps(payload))
                    raw = await ws.recv()
            elapsed = (time.monotonic() - t0) * 1000

            data = __import__("json").loads(raw)
            chain_id = int(data["result"], 16)
            if chain_id != expected_chain_id:
                raise ValueError(
                    f"chain_id mismatch: got {chain_id}, expected {expected_chain_id}"
                )

            node = RpcNode(url=url, latency=elapsed)
            logger.info("WSS RPC accepted — %s (chain=%d, latency=%.0fms)", url, chain_id, elapsed)
            return node
        except Exception as exc:
            raise ValueError(str(exc)) from exc

    @classmethod
    async def _probe_one(cls, node: RpcNode) -> None:
        import json
        payload = {"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1}
        async with asyncio.timeout(_REQUEST_TIMEOUT):
            async with websockets.connect(node.url) as ws:
                await ws.send(json.dumps(payload))
                raw = await ws.recv()
        data = json.loads(raw)
        if "error" in data:
            raise ValueError(data["error"])

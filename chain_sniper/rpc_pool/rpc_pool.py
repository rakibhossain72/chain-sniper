"""
RPCPool — fault-tolerant RPC endpoint manager for ChainSniper.

Supports both HTTP and WebSocket (wss://) endpoints.
"""

import asyncio
import logging
import time
from typing import List, Optional

import aiohttp

from .rpc_node import RpcNode

logger = logging.getLogger(__name__)

_HEALTH_CHECK_INTERVAL = 60.0  # seconds between background probes
_COOLDOWN_SECONDS = 30.0  # penalty window after a failure
_REQUEST_TIMEOUT = 5.0  # seconds before a validation/probe times out


class RPCPool:
    """
    Manages a pool of RPC endpoints (HTTP or WebSocket).

    Usage::

        pool = await RPCPool.create(
            rpcs=[
                "https://bsc-dataseed1.binance.org",
                "wss://bsc-ws-node.nariox.org:443",
            ],
            expected_chain_id=56,
        )
        sniper = ChainSniper(pool)

    The pool validates every endpoint on startup (chain-ID check), then
    continuously monitors unhealthy nodes in the background so they can
    recover automatically.
    """

    def __init__(self, nodes: List[RpcNode]) -> None:
        # Called internally after validation; use RPCPool.create() publicly.
        if not nodes:
            raise RuntimeError(
                "RPCPool: no valid RPC endpoints survived chain-ID validation."
            )
        self._nodes = nodes
        self._lock = asyncio.Lock()
        self._monitor_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------ #
    # Factory                                                              #
    # ------------------------------------------------------------------ #

    @classmethod
    async def create(
        cls,
        rpcs: List[str],
        expected_chain_id: int,
        cooldown_seconds: float = _COOLDOWN_SECONDS,
        health_check_interval: float = _HEALTH_CHECK_INTERVAL,
    ) -> "RPCPool":
        """
        Validate every RPC against expected_chain_id and return a ready pool.

        Raises RuntimeError if no endpoint passes validation.
        """
        valid_nodes: List[RpcNode] = []

        async with aiohttp.ClientSession() as session:
            tasks = [
                    cls._validate(session, url, expected_chain_id)
                    for url in rpcs
                ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        for url, result in zip(rpcs, results):
            if isinstance(result, RpcNode):
                valid_nodes.append(result)
            else:
                logger.warning("RPC rejected — %s: %s", url, result)

        pool = cls(valid_nodes)
        pool._cooldown_seconds = cooldown_seconds
        pool._health_check_interval = health_check_interval
        pool._monitor_task = asyncio.create_task(pool._health_monitor())
        logger.info("RPCPool ready with %d endpoint(s).", len(valid_nodes))
        return pool

    # ------------------------------------------------------------------ #
    # Public interface                                                     #
    # ------------------------------------------------------------------ #

    def get_rpc(self) -> str:
        """
        Return the URL of the fastest healthy endpoint.

        Raises RuntimeError if no healthy endpoint is available.
        """
        healthy = [n for n in self._nodes if n.is_healthy]
        if not healthy:
            raise RuntimeError("all rpcs are unhealthy or in cooldown")
        healthy.sort(key=lambda n: n.latency)
        return healthy[0].url

    def mark_failed(self, url: str) -> None:
        """Record a failure for the given URL and apply cooldown."""
        node = self._node_by_url(url)
        if node:
            node.mark_failed(self._cooldown_seconds)
            logger.warning(
                "RPC marked failed — %s (errors=%d, dead=%s)",
                url,
                node.error_count,
                node.is_dead,
            )

    def record_success(self, url: str, elapsed_ms: float) -> None:
        """Update latency moving average after a successful call."""
        node = self._node_by_url(url)
        if node:
            node.record_success(elapsed_ms)

    def stop(self) -> None:
        """Cancel the background health monitor."""
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()

    @property
    def urls(self) -> List[str]:
        return [n.url for n in self._nodes]

    @property
    def healthy_urls(self) -> List[str]:
        return [n.url for n in self._nodes if n.is_healthy]

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _node_by_url(self, url: str) -> Optional[RpcNode]:
        for node in self._nodes:
            if node.url == url:
                return node
        return None

    # ------------------------------------------------------------------ #
    # Validation                                                           #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def _validate(
        session: aiohttp.ClientSession,
        url: str,
        expected_chain_id: int,
    ) -> RpcNode:
        """
        Check chain ID via JSON-RPC.  Works for both HTTP and WSS endpoints
        (WSS URLs are translated to their HTTP counterpart for the probe).
        """
        probe_url = _to_http(url)
        payload = {
            "jsonrpc": "2.0",
            "method": "eth_chainId",
            "params": [],
            "id": 1,
        }
        try:
            t0 = time.monotonic()
            async with session.post(
                probe_url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT),
            ) as resp:
                data = await resp.json(content_type=None)
            elapsed = (time.monotonic() - t0) * 1000

            chain_id = int(data["result"], 16)
            if chain_id != expected_chain_id:
                raise ValueError(
                    f"chain_id mismatch: got {chain_id}"
                    f"expected {expected_chain_id}"
                )

            node = RpcNode(url=url)
            node.latency = elapsed
            logger.info(
                "RPC accepted — %s (chain=%d, latency=%.0fms)",
                url, chain_id, elapsed
            )
            return node

        except Exception as exc:
            raise ValueError(str(exc)) from exc

    # ------------------------------------------------------------------ #
    # Background health monitor                                            #
    # ------------------------------------------------------------------ #

    async def _health_monitor(self) -> None:
        """
        Periodically probe dead/cooldown nodes and revive them if healthy.
        Uses eth_blockNumber — lightweight and representative.
        """
        while True:
            await asyncio.sleep(self._health_check_interval)
            sick = [n for n in self._nodes if not n.is_healthy]
            if not sick:
                continue

            async with aiohttp.ClientSession() as session:
                for node in sick:
                    try:
                        await self._probe_block_number(session, node)
                        node.revive()
                        logger.info("RPC revived — %s", node.url)
                    except Exception as exc:
                        logger.debug("RPC still sick — %s: %s", node.url, exc)

    @staticmethod
    async def _probe_block_number(
        session: aiohttp.ClientSession,
        node: RpcNode,
    ) -> None:
        payload = {
            "jsonrpc": "2.0",
            "method": "eth_blockNumber",
            "params": [],
            "id": 1,
        }
        async with session.post(
            _to_http(node.url),
            json=payload,
            timeout=aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT),
        ) as resp:
            data = await resp.json(content_type=None)

        if "error" in data:
            raise ValueError(data["error"])


# ------------------------------------------------------------------ #
# Utility                                                             #
# ------------------------------------------------------------------ #


def _to_http(url: str) -> str:
    """
    Convert a WebSocket URL to its HTTP equivalent for JSON-RPC probing.

    wss://host → https://host
    ws://host  → http://host
    http(s):// → unchanged
    """
    if url.startswith("wss://"):
        return "https://" + url[6:]
    if url.startswith("ws://"):
        return "http://" + url[5:]
    return url

import asyncio
import logging
from typing import Any

from web3 import AsyncWeb3
from web3.datastructures import AttributeDict

# Defaults — overridable per-instance so callers can tune for their node latency
_BLOCK_COMPLETENESS_RETRIES = 5
_BLOCK_COMPLETENESS_INTERVAL = 0.4


class BlockFetcher:
    """
    Responsible for fetching a full block from the node and verifying that
    the transaction list is complete (i.e. stable across two consecutive reads).

    Nodes sometimes return a block body before all transactions have been
    propagated internally, so we poll until the tx count stabilises.
    """

    def __init__(
        self,
        w3: AsyncWeb3,
        logger: logging.Logger,
        *,
        # Allow per-instance tuning so fast chains (e.g. BSC 3s) can use
        # tighter intervals while slow chains can afford longer waits.
        retries: int = _BLOCK_COMPLETENESS_RETRIES,
        interval: float = _BLOCK_COMPLETENESS_INTERVAL,
    ) -> None:
        self._w3 = w3
        self.logger = logger
        self._retries = retries
        self._interval = interval

    async def fetch_complete(self, block_hash: Any) -> AttributeDict | None:
        """
        Fetch a block by hash and wait until its transaction count is stable
        across two consecutive reads.

        Nodes (especially under load) can return a block body before all
        transactions have been propagated internally.  We keep re-fetching
        until the tx count matches the previous read, which is the cheapest
        deterministic completeness signal available without a receipt check.

        Returns the full block AttributeDict, or None if it could not be
        retrieved after all retries.
        """
        # Normalise HexBytes → hex string so the RPC call is unambiguous
        if isinstance(block_hash, (bytes, bytearray)):
            block_hash = "0x" + block_hash.hex()

        prev_tx_count: int | None = None
        block: AttributeDict | None = None

        for attempt in range(self._retries):
            try:
                block = await self._w3.eth.get_block(block_hash, full_transactions=True)
            except Exception as exc:
                if (
                    "not found" in str(exc).lower()
                    and attempt < self._retries - 1
                ):
                    # Node hasn't propagated the block body yet — common on
                    # fast chains where the header arrives before the body.
                    self.logger.debug(
                        "Block %s not yet available (attempt %d/%d), retrying…",
                        block_hash,
                        attempt + 1,
                        self._retries,
                    )
                    await asyncio.sleep(self._interval)
                    continue
                self.logger.warning(
                    "Could not fetch block %s after %d attempts: %s",
                    block_hash,
                    attempt + 1,
                    exc,
                )
                return None

            tx_count = len(block.get("transactions", []))

            if prev_tx_count is not None and tx_count == prev_tx_count:
                # Two consecutive reads agree — block body is stable.
                self.logger.debug(
                    "Block %s complete: %d txs (stable after %d checks)",
                    block.get("number"),
                    tx_count,
                    attempt + 1,
                )
                return block

            # First read or count changed — wait and re-fetch.
            prev_tx_count = tx_count
            if attempt < self._retries - 1:
                await asyncio.sleep(self._interval)

        self.logger.warning(
            "Block %s tx count never stabilised after %d retries; "
            "emitting with %d txs (may be incomplete)",
            block.get("number") if block else block_hash,
            self._retries,
            len(block.get("transactions", [])) if block else 0,
        )
        return block

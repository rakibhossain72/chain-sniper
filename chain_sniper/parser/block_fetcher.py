import asyncio
import logging
from typing import Any

from web3 import AsyncWeb3
from web3.datastructures import AttributeDict

_BLOCK_COMPLETENESS_RETRIES = 5
_BLOCK_COMPLETENESS_INTERVAL = 0.4


class BlockFetcher:
    """
    Responsible for fetching a full block from the node and verifying that
    the transaction list is complete (i.e. stable across two consecutive reads).

    Nodes sometimes return a block body before all transactions have been
    propagated internally, so we poll until the tx count stabilises.
    """

    def __init__(self, w3: AsyncWeb3, logger: logging.Logger) -> None:
        self._w3 = w3
        self.logger = logger

    async def fetch_complete(self, block_hash: Any) -> AttributeDict | None:
        """
        Fetch a block by hash and wait until its transaction count is stable.

        Returns the full block AttributeDict, or None if it could not be
        retrieved after all retries.
        """
        prev_tx_count: int | None = None
        block: AttributeDict | None = None

        for attempt in range(_BLOCK_COMPLETENESS_RETRIES):
            try:
                block = await self._w3.eth.get_block(block_hash, full_transactions=True)
            except Exception as exc:
                if (
                    "not found" in str(exc).lower()
                    and attempt < _BLOCK_COMPLETENESS_RETRIES - 1
                ):
                    self.logger.debug(
                        "Block %s not yet available (attempt %d), retrying…",
                        block_hash if isinstance(block_hash, str) else block_hash.hex(),
                        attempt + 1,
                    )
                    await asyncio.sleep(_BLOCK_COMPLETENESS_INTERVAL)
                    continue
                self.logger.warning(
                    "Could not fetch block %s after %d attempts: %s",
                    block_hash,
                    attempt + 1,
                    exc,
                )
                return None

            tx_count = len(block.get("transactions", []))

            if tx_count == prev_tx_count:
                self.logger.debug(
                    "Block %s complete: %d txs (stable after %d checks)",
                    block.get("number"),
                    tx_count,
                    attempt + 1,
                )
                return block

            prev_tx_count = tx_count
            if attempt < _BLOCK_COMPLETENESS_RETRIES - 1:
                await asyncio.sleep(_BLOCK_COMPLETENESS_INTERVAL)

        self.logger.warning(
            "Block %s tx count never stabilised; emitting with %d txs",
            block.get("number") if block else block_hash,
            len(block.get("transactions", [])) if block else 0,
        )
        return block

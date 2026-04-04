"""
Processing pipeline that pairs a TransactionFilter + LogFilter with a Strategy.
"""

from typing import Optional
from chain_sniper.parser.block_parser import parse_block
from chain_sniper.parser.log_decoder import parse_log
from chain_sniper.filters import TransactionFilter, LogFilter
from chain_sniper.abstracts.base_strategy import BaseStrategy


class Pipeline:

    def __init__(
        self,
        *,
        tx_filter: Optional[TransactionFilter] = None,
        log_filter: Optional[LogFilter] = None,
        strategy: Optional[BaseStrategy] = None,
    ) -> None:
        self.tx_filter = tx_filter
        self.log_filter = log_filter
        self.strategy = strategy

    async def process_block(self, block) -> None:
        txs = parse_block(block)

        for tx in txs:
            if self.tx_filter and self.tx_filter.match(tx):
                await self.strategy.execute(tx)

    async def process_log(self, log) -> None:
        log = parse_log(log)
        log_args = log.get("args", {})
        print(f"Decoded log args: {log_args}")

        # LogFilter post-filter rules (optional — if none, all pass)
        if self.log_filter and not self.log_filter.match(log_args):
            return

        await self.strategy.execute_log(log_args)

from chain_sniper.parser.block_parser import parse_block
from chain_sniper.parser.log_decoder import parse_log
from chain_sniper.abstracts.base_filter import BaseFilter
from chain_sniper.abstracts.base_strategy import BaseStrategy


class Pipeline:

    def __init__(self, filter: BaseFilter | None = None, strategy: BaseStrategy | None = None):

        self.filter = filter
        self.strategy = strategy

    async def process_block(self, block):
        txs = parse_block(block)

        for tx in txs:

            if self.filter.match(tx):

                await self.strategy.execute(tx)

    async def process_log(self, log):
        log = parse_log(log)
        if self.filter and self.filter.match_log(log):
            await self.strategy.execute_log(log)

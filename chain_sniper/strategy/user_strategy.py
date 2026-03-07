from chain_sniper.abstracts.base_strategy import BaseStrategy


class UserStrategy(BaseStrategy):

    async def execute(self, tx):

        print("MATCH FOUND")

        print(tx)

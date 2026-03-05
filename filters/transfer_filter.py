from abstracts.base_filter import BaseFilter


class TransferFilter(BaseFilter):

    def __init__(self, target_wallet):
        self.target_wallet = target_wallet

    def match(self, tx):
        if tx.get("to") == self.target_wallet:
            return True
        return False

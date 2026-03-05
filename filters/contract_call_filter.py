from abstracts.base_filter import BaseFilter

class ContractCallFilter(BaseFilter):
    def __init__(self, target_contract):
        self.target_contract = target_contract

    def match(self, tx):
        return tx.get("to") == self.target_contract

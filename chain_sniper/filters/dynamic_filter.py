import logging
from typing import Any, Dict, List
from chain_sniper.filters.base import BaseFilter
from chain_sniper.parser.rule_parser import RuleMatcher


class DynamicFilter(BaseFilter):
    """
    A state-aware filter that evaluates transactions and logs against dynamic rules
    held in memory, which can be dynamically updated at runtime.

    Uses MongoDB-style rule matching with operators like $gt, $gte, $in, $regex, etc.
    Supports dot notation for nested access (e.g., "args.value" for decoded logs).
    """

    def __init__(self, logger: logging.Logger = logging.getLogger(__name__)):
        self.tx_rules: List[Dict[str, Any]] = []
        self.log_rules: List[Dict[str, Any]] = []
        self.rule_matcher = RuleMatcher(logger=logger)

        self.logger = logger

    def add_tx_rule(self, rule: Dict[str, Any]):
        """
        Add a transaction rule using MongoDB-style operators.

        Examples:
            filter.add_tx_rule({"to": "0x123...", "value": {"_op": "$gte", "_value": 1000}})
            filter.add_tx_rule({"from": {"_op": "$in", "_value": ["0x456...", "0x789..."]}})
        """
        self.logger.info(f"Adding TX rule: {rule}")
        self.tx_rules.append(rule)

    def add_log_rule(self, rule: Dict[str, Any]):
        """
        Add a log rule using MongoDB-style operators.

        Works with both raw logs and decoded logs. Use dot notation for decoded fields.

        Examples:
            # Raw log fields
            filter.add_log_rule({"address": "0x55d3..."})
            filter.add_log_rule({"topics": {"_op": "$in", "_value": ["0xddf25..."]}})

            # Decoded log fields
            filter.add_log_rule({"event": "Transfer"})
            filter.add_log_rule({"args.from": "0x123..."})
            filter.add_log_rule({"args.value": {"_op": "$gte", "_value": 1000}})
            filter.add_log_rule({"args.to": {"_op": "$regex", "_value": "^0x"}})
        """
        self.logger.info(f"Adding log rule: {rule}")
        self.log_rules.append(rule)

    def match(self, tx: Dict[str, Any]) -> bool:
        """
        Check if transaction matches any of the dynamic transaction rules.
        """
        if not self.tx_rules:
            return False

        for rule in self.tx_rules:
            try:
                if self.rule_matcher.match_rule(tx, rule):
                    return True
            except (ValueError, KeyError) as e:
                self.logger.error(f"TX rule error {rule}: {e}")
        return False

    def match_log(self, log: Dict[str, Any]) -> bool:
        """
        Check if log matches any of the dynamic log rules.

        Works with both raw and decoded logs.
        """
        if not self.log_rules:
            return False

        for rule in self.log_rules:
            try:
                if self.rule_matcher.match_rule(log, rule):
                    return True
            except (ValueError, KeyError) as e:
                self.logger.error(f"Log rule error {rule}: {e}")
        return False

"""
Versatile filter that combines dynamic rules and static target matching.
"""

import logging
from typing import Any, Dict, List, Optional
from chain_sniper.filters.base import BaseFilter
from chain_sniper.parser.rule_parser import RuleMatcher


class Filter(BaseFilter):
    """
    A versatile filter that combines dynamic rule matching
    with static target matching.

    This filter supports multiple filtering strategies:
    - Dynamic MongoDB-style rules for transactions and logs
    - Static target wallet matching (for tracking incoming transfers)
    - Static target contract matching (for tracking contract interactions)
    - Combination of all filtering strategies

    Usage modes:
    1. Dynamic mode: Use add_tx_rule() and add_log_rule()
       for MongoDB-style rules
    2. Static mode: Set target_wallet and/or target_contract
       in constructor
    3. Hybrid mode: Combine both dynamic rules and static targets
    4. Custom mode: Extend this class and override match()
       or match_log() methods

    Examples:
        # Simple wallet tracking
        filter = Filter(target_wallet="0x123...")

        # Contract interaction tracking
        filter = Filter(target_contract="0x456...")

        # Dynamic rules
        filter = Filter()
        filter.add_tx_rule({"value": {"_op": "$gte", "_value": 10**18}})

        # Hybrid: static + dynamic
        filter = Filter(target_wallet="0x123...")
        filter.add_tx_rule({"value": {"_op": "$gte", "_value": 10**17}})
    """

    def __init__(
        self,
        target_wallet: Optional[str] = None,
        target_contract: Optional[str] = None,
        logger: logging.Logger = logging.getLogger(__name__)
    ):
        """
        Initialize the filter.

        Args:
            target_wallet: Optional wallet address to match
                transactions to (for tracking incoming transfers)
            target_contract: Optional contract address to match
                transactions to (for tracking contract interactions)
            logger: Logger instance for error reporting
        """
        # Dynamic filter properties
        self.tx_rules: List[Dict[str, Any]] = []
        self.log_rules: List[Dict[str, Any]] = []
        self.rule_matcher = RuleMatcher(logger=logger)

        # Static filter properties
        self.target_wallet = target_wallet
        self.target_contract = target_contract

        self.logger = logger

    def add_tx_rule(self, rule: Dict[str, Any]):
        """
        Add a transaction rule using MongoDB-style operators.

        Examples:
            filter.add_tx_rule({
                "to": "0x123...",
                "value": {"_op": "$gte", "_value": 1000}
            })
            filter.add_tx_rule({
                "from": {"_op": "$in", "_value": ["0x456...", "0x789..."]}
            })
        """
        self.logger.info(f"Adding TX rule: {rule}")
        self.tx_rules.append(rule)

    def add_log_rule(self, rule: Dict[str, Any]):
        """
        Add a log rule using MongoDB-style operators.

        Works with both raw logs and decoded logs.
        Use dot notation for decoded fields.

        Examples:
            # Raw log fields
            filter.add_log_rule({"address": "0x55d3..."})
            filter.add_log_rule({
                "topics": {"_op": "$in", "_value": ["0xddf25..."]}
            })

            # Decoded log fields
            filter.add_log_rule({"event": "Transfer"})
            filter.add_log_rule({"args.from": "0x123..."})
            filter.add_log_rule({
                "args.value": {"_op": "$gte", "_value": 1000}
            })
            filter.add_log_rule({
                "args.to": {"_op": "$regex", "_value": "^0x"}
            })
        """
        self.logger.info(f"Adding log rule: {rule}")
        self.log_rules.append(rule)

    def match(self, tx: Dict[str, Any]) -> bool:
        """
        Check if transaction matches any of the filters.

        Matches if:
        - Transaction matches any dynamic TX rule, OR
        - Transaction's 'to' field matches target_wallet, OR
        - Transaction's 'to' field matches target_contract

        Args:
            tx: Transaction dictionary

        Returns:
            True if transaction matches any filter
        """
        # Check dynamic rules
        if self.tx_rules:
            for rule in self.tx_rules:
                try:
                    if self.rule_matcher.match_rule(tx, rule):
                        return True
                except (ValueError, KeyError) as e:
                    self.logger.error(f"TX rule error {rule}: {e}")

        # Check static target_wallet (for tracking incoming transfers)
        if self.target_wallet and tx.get("to") == self.target_wallet:
            return True

        # Check static target_contract (for tracking contract interactions)
        if self.target_contract and tx.get("to") == self.target_contract:
            return True

        return False

    def match_log(self, log: Dict[str, Any]) -> bool:
        """
        Check if log matches any of the dynamic log rules.

        Works with both raw and decoded logs.

        Args:
            log: Log dictionary (may be raw or decoded)

        Returns:
            True if log matches any dynamic log rule
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

    def clear_rules(self):
        """
        Clear all dynamic rules (both TX and log rules).
        """
        self.tx_rules.clear()
        self.log_rules.clear()
        self.logger.info("Cleared all dynamic rules")

    def clear_tx_rules(self):
        """
        Clear only transaction rules.
        """
        self.tx_rules.clear()
        self.logger.info("Cleared TX rules")

    def clear_log_rules(self):
        """
        Clear only log rules.
        """
        self.log_rules.clear()
        self.logger.info("Cleared log rules")

    def set_target_wallet(self, target_wallet: Optional[str]):
        """
        Set or update the target wallet address.

        Args:
            target_wallet: Wallet address to match, or None to disable
        """
        self.target_wallet = target_wallet
        self.logger.info(f"Set target wallet: {target_wallet}")

    def set_target_contract(self, target_contract: Optional[str]):
        """
        Set or update the target contract address.

        Args:
            target_contract: Contract address to match, or None to disable
        """
        self.target_contract = target_contract
        self.logger.info(f"Set target contract: {target_contract}")

    def get_config(self) -> Dict[str, Any]:
        """
        Get the current filter configuration.

        Returns:
            Dictionary containing current filter settings
        """
        return {
            "tx_rules_count": len(self.tx_rules),
            "log_rules_count": len(self.log_rules),
            "target_wallet": self.target_wallet,
            "target_contract": self.target_contract,
            "has_dynamic_rules": bool(self.tx_rules or self.log_rules),
            "has_static_targets": bool(
                self.target_wallet or self.target_contract
            )
        }

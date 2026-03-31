"""
Versatile filter that combines dynamic rules and static target matching.
"""

import logging
import json
from typing import Any, Dict, List
from chain_sniper.filters.base import BaseFilter
from chain_sniper.parser.rule_parser import RuleMatcher
from chain_sniper.parser.log_decoder import LogDecoder


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
        filter = Filter()..add_tx_rule({"to": "0x123..."})

        # Contract interaction tracking
        filter = Filter().add_tx_rule({"to": "0x456..."})

        # Dynamic rules
        filter = Filter()
        filter.add_tx_rule({"value": {"_op": "$gte", "_value": 10**18}})

        # Hybrid: static + dynamic
        filter = Filter()
        filter.add_tx_rule({"to": "0x123..."})
        filter.add_tx_rule({"value": {"_op": "$gte", "_value": 10**17}})
    """

    def __init__(
        self,
        logger: logging.Logger = logging.getLogger(__name__)
    ):
        """
        Initialize the filter.

        Args:
            logger: Logger instance for error reporting
        """
        # Dynamic filter properties
        self.tx_rules: List[Dict[str, Any]] = []
        self.log_rules: List[Dict[str, Any]] = []
        self.rule_matcher = RuleMatcher(logger=logger)

        # Log decoding properties
        self._log_decoder = LogDecoder()
        self._abi_map: Dict[str, List[Dict[str, Any]]] = {}

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

    def add_abi(
        self, abi: List[Dict[str, Any]] | str, address: str | None = None
    ):
        """
        Register an ABI for log decoding.

        Args:
            abi: Contract ABI as list or JSON string
            address: Contract address (optional, for address-specific decoding)
        """
        if isinstance(abi, str):
            abi = json.loads(abi)

        key = address.lower() if address else "*"
        self._abi_map[key] = abi
        self.logger.info(f"Registered ABI for address: {address or 'all'}")

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

        return False

    def match_log(self, log: Dict[str, Any]) -> bool:
        """
        Check if log matches any of the dynamic log rules.

        Works with both raw and decoded logs.
        If ABI is registered, logs will be decoded before matching.

        Args:
            log: Log dictionary (may be raw or decoded)

        Returns:
            True if log matches any dynamic log rule
        """
        if not self.log_rules:
            return False

        # Decode log if ABI is available
        decoded_log = self._decode_log(log)

        for rule in self.log_rules:
            try:
                if self.rule_matcher.match_rule(decoded_log, rule):
                    return True
            except (ValueError, KeyError) as e:
                self.logger.error(f"Log rule error {rule}: {e}")

        return False

    def _decode_log(self, log: Dict[str, Any]) -> Dict[str, Any]:
        """
        Decode a log using registered ABIs.

        Args:
            log: Raw log dictionary

        Returns:
            Decoded log if ABI found, otherwise original log
        """
        address = log.get("address")
        address_lower = address.lower() if address else None
        topics = log.get("topics", [])

        if topics:
            topic = topics[0]
            # Convert HexBytes to string if needed
            if hasattr(topic, 'hex'):
                topic = topic.hex()
            elif isinstance(topic, bytes):
                topic = topic.hex()
            # Try exact address match
            abi = self._abi_map.get(address_lower)
            if abi:
                return self._log_decoder.decode_log(log, abi)
            # Try wildcard address
            abi = self._abi_map.get("*")
            if abi:
                return self._log_decoder.decode_log(log, abi)

        return log

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

    def get_config(self) -> Dict[str, Any]:
        """
        Get the current filter configuration.

        Returns:
            Dictionary containing current filter settings
        """
        return {
            "tx_rules_count": len(self.tx_rules),
            "log_rules_count": len(self.log_rules),
            "has_dynamic_rules": bool(self.tx_rules or self.log_rules),
            "registered_abis": len(self._abi_map),
        }

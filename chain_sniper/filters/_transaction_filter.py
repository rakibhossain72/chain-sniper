"""
Transaction and block filter with dynamic MongoDB-style rule matching.

Unlike logs (which are pre-filtered at the node level), transactions are
received in bulk — every transaction in every block — and must be filtered
locally.  This module handles that local filtering.
"""

import logging
import threading
from uuid import uuid4
from typing import Any, Dict, List

from chain_sniper.parser.rule_parser import RuleMatcher


class TransactionFilter:
    """
    Filter for transactions and blocks using dynamic MongoDB-style rules.

    Rules are stored as {"id": str, "rule": dict} entries.
    Each ``add_rule`` call returns the assigned ``rule_id`` so callers can
    remove the rule later.

    Thread-safe: a ``threading.Lock`` guards all mutations and is released
    before calling ``RuleMatcher`` (which may be slow).
    """

    def __init__(
        self,
        logger: logging.Logger = logging.getLogger(__name__),
    ) -> None:
        self._rules: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._rule_matcher = RuleMatcher(logger=logger)
        self.logger = logger

    #  Rule management 

    def add_rule(self, rule: Dict[str, Any]) -> str:
        """
        Add a transaction / block filter rule (MongoDB-style operators).

        Returns:
            rule_id – unique string ID assigned to this rule.
        """
        rule_id = str(uuid4())
        entry = {"id": rule_id, "rule": rule}
        with self._lock:
            self._rules.append(entry)
        self.logger.info("Added TX rule id=%s: %s", rule_id, rule)
        return rule_id

    def remove_rule(self, rule_id: str) -> bool:
        """
        Remove a rule by its ID.

        Returns:
            True if the rule was found and removed, False otherwise.
        """
        with self._lock:
            for i, entry in enumerate(self._rules):
                if entry["id"] == rule_id:
                    del self._rules[i]
                    self.logger.info("Removed TX rule id=%s", rule_id)
                    return True
        self.logger.warning("remove_rule: unknown rule_id=%s", rule_id)
        return False

    def clear_rules(self) -> None:
        """Remove all rules."""
        with self._lock:
            self._rules.clear()
        self.logger.info("Cleared all TX rules")

    #  Matching 

    def match(self, tx: Dict[str, Any]) -> bool:
        """
        Check whether *tx* matches **any** registered rule.

        Takes a snapshot of the rule list under the lock, then releases
        the lock before calling ``RuleMatcher``.
        """
        with self._lock:
            snapshot = list(self._rules)

        for entry in snapshot:
            try:
                if self._rule_matcher.match_rule(tx, entry["rule"]):
                    return True
            except (ValueError, KeyError) as exc:
                self.logger.error(
                    "TX rule error id=%s: %s", entry["id"], exc,
                )

        return False

    #  Introspection 

    @property
    def rules(self) -> List[Dict[str, Any]]:
        """Return a snapshot of current rules."""
        with self._lock:
            return list(self._rules)

    @property
    def has_rules(self) -> bool:
        with self._lock:
            return bool(self._rules)

    def get_config(self) -> Dict[str, Any]:
        """Return the current filter configuration."""
        with self._lock:
            count = len(self._rules)
            ids = [e["id"] for e in self._rules]
        return {
            "rules_count": count,
            "has_rules": bool(count),
            "rule_ids": ids,
        }

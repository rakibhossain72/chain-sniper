from typing import Any, Callable
import re
import logging

class RuleMatcher:
    """
    Parses and evaluates rule conditions against a transaction.

    Simple equality:
        {"amount": 100, "currency": "USD"}

    Operator-based:
        {"amount": {"_op": "$gt", "_value": 50}}

    Supported operators:
        Comparison : $eq, $ne, $gt, $gte, $lt, $lte
        String     : $contains, $startswith, $endswith, $regex
        List       : $in, $nin
        Type check : $exists
    """

    _OPERATORS: dict[str, Callable] = {
        # Comparison
        "$eq":         lambda a, b: a == b,
        "$ne":         lambda a, b: a != b,
        "$gt":         lambda a, b: a > b,
        "$gte":        lambda a, b: a >= b,
        "$lt":         lambda a, b: a < b,
        "$lte":        lambda a, b: a <= b,

        # String
        "$contains":   lambda a, b: isinstance(a, str) and str(b).lower() in a.lower(),
        "$startswith": lambda a, b: isinstance(a, str) and a.lower().startswith(str(b).lower()),
        "$endswith":   lambda a, b: isinstance(a, str) and a.lower().endswith(str(b).lower()),
        "$regex":      lambda a, b: bool(re.search(b, str(a))),

        # List
        "$in":         lambda a, b: isinstance(b, list) and a in b,
        "$nin":        lambda a, b: isinstance(b, list) and a not in b,

        # Existence
        "$exists":     lambda a, b: (a is not None) == bool(b),
    }

    def __init__(self, case_sensitive: bool = False, strict_mode: bool = False, logger: logging.Logger = logging.getLogger(__name__)):
        """
        Args:
            case_sensitive : If False, string equality checks are case-insensitive (default: False).
            strict_mode    : If True, raises on missing keys instead of returning False (default: False).
            logger           : Logger instance for logging messages (default:.getLogger(__name__)).
        """
        self.case_sensitive = case_sensitive
        self.strict_mode = strict_mode
        self.logger = logger

    def _normalize(self, value: Any) -> Any:
        """Lowercase strings when case-insensitive mode is active."""
        if not self.case_sensitive and isinstance(value, str):
            return value.lower()
        return value

    def _evaluate(self, tx_value: Any, condition: Any) -> bool:
        """
        Evaluate a single condition against a transaction field value.
        Handles simple equality and operator-based conditions.
        """
        # Simple scalar equality
        if isinstance(condition, (str, int, float, bool)):
            return self._normalize(tx_value) == self._normalize(condition)

        # Operator-based condition
        if isinstance(condition, dict):
            op  = condition.get("_op")
            val = condition.get("_value")

            if not op:
                raise ValueError(f"Condition dict missing '_op': {condition}")
            if op not in self._OPERATORS:
                raise ValueError(f"Unsupported operator '{op}'. Supported: {list(self._OPERATORS)}")

            # Normalize only for string-comparison operators
            if op in ("$eq", "$ne", "$contains", "$startswith", "$endswith"):
                tx_value = self._normalize(tx_value)
                val      = self._normalize(val)

            return self._OPERATORS[op](tx_value, val)

        raise ValueError(f"Invalid condition format — expected scalar or dict, got: {type(condition)}")

    def match_rule(self, tx: dict, rule: dict) -> bool:
        """
        Check if a transaction satisfies ALL conditions in a single rule (AND logic).
        Returns False on missing keys unless strict_mode is enabled.
        """
        for key, condition in rule.items():
            # Handle nested key access e.g. "meta.source"
            tx_value = self._get_nested(tx, key)

            if tx_value is None:
                # $exists can still validly operate on missing keys
                if isinstance(condition, dict) and condition.get("_op") == "$exists":
                    if not self._evaluate(None, condition):
                        return False
                    continue

                if self.strict_mode:
                    raise KeyError(f"Key '{key}' not found in transaction")
                return False

            if not self._evaluate(tx_value, condition):
                return False

        return True

    def match_any(self, tx: dict, rules: list[dict]) -> dict | None:
        """
        Check if transaction matches ANY rule (OR logic).
        Returns the first matched rule or None.
        """
        for rule in rules:
            try:
                if self.match_rule(tx, rule):
                    return rule
            except (ValueError, KeyError) as e:
                self.logger.error(f"Rule error {rule}: {e}")
        return None

    @staticmethod
    def _get_nested(data: dict, key: str) -> Any:
        """
        Access nested dict values using dot notation.
        e.g. 'meta.source' -> data['meta']['source']
        """
        keys = key.split(".")
        for k in keys:
            if not isinstance(data, dict):
                return None
            data = data.get(k)
        return data

    def add_operator(self, name: str, fn: Callable) -> None:
        """Register a custom operator at runtime."""
        if not name.startswith("$"):
            raise ValueError(f"Operator name must start with '$', got: '{name}'")
        self._OPERATORS[name] = fn
        self.logger.info(f"Custom operator '{name}' registered.")
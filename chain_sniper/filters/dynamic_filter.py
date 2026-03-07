import logging
from typing import Any, Dict, List
from chain_sniper.abstracts.base_filter import BaseFilter
from chain_sniper.parser.rule_parser import RuleMatcher

class DynamicFilter(BaseFilter):
    """
    A state-aware filter that evaluates transactions and logs against dynamic rules
    held in memory, which can be dynamically updated at runtime.
    """
    def __init__(self, logger: logging.Logger = logging.getLogger(__name__)):
        self.tx_rules: List[Dict[str, Any]] = []
        self.log_rules: List[Dict[str, Any]] = []
        self.rule_matcher = RuleMatcher(logger=logger)

        self.logger = logger

    def add_tx_rule(self, rule: Dict[str, Any]):
        self.logger.info(f"Adding new TX rule: {rule}")
        self.tx_rules.append(rule)
        
    def add_log_rule(self, rule: Dict[str, Any]):
        self.logger.info(f"Adding new LOG rule: {rule}")
        self.log_rules.append(rule)

    def match(self, tx: Any) -> bool:
        """
        Check if the given transaction matches any of the dynamic transaction rules.
        """
        if not self.tx_rules:
            return False

        for rule in self.tx_rules:
            try:
                if self.rule_matcher.match_rule(tx, rule):
                    return True
            except (ValueError, KeyError) as e:
                self.logger.error(f"Rule error {rule}: {e}")
        return False
    
    def match_log(self, log: Any) -> bool:
        """
        Check if the given log matches any of the dynamic log rules.
        """
        if not self.log_rules:
            return False
            
        for rule in self.log_rules:
            try:
                min_amount = rule.get("min_amount")
                target_topic = rule.get("target_topic")
                
                # Assume standard hex format for data
                data = log.get("data", "0x")
                amount = 0
                if len(data) >= 66:
                    try:
                        amount = int(data[-64:], 16) / (10 ** 18)
                    except ValueError:
                        pass
                
                if min_amount and amount >= min_amount:
                    if target_topic and target_topic not in log.get("topics", []):
                        continue
                    return True
            except Exception as e:
                self.logger.error(f"Error evaluating log rule {rule}: {e}")
                
        return False

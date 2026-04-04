"""
Async Redis pub/sub listener for dynamic rule management.

Subscribes to a Redis channel and pushes received rules into
TransactionFilter / LogFilter instances in real-time.
"""

import asyncio
import json
import logging
from typing import Optional

import redis.asyncio as redis
from chain_sniper.filters import TransactionFilter, LogFilter

logger = logging.getLogger(__name__)


class RedisRuleListener:
    """
    Listens to a Redis pub/sub channel and applies incoming rules to
    the provided ``TransactionFilter`` and ``LogFilter`` instances.

    Supported message actions:
      - ``add``    with type ``tx`` / ``log`` / ``log_subscription``
      - ``remove`` with type ``tx`` / ``log`` / ``log_subscription``
      - ``clear``  with rule_type ``tx`` / ``log`` / ``log_subscription``
      - ``unsubscribe``  with ``sub_id``
    """

    def __init__(
        self,
        *,
        tx_filter: Optional[TransactionFilter] = None,
        log_filter: Optional[LogFilter] = None,
        redis_url: str = "redis://localhost",
        channel: str = "sniper_rules",
    ):
        self._tx_filter = tx_filter
        self._log_filter = log_filter
        self.redis_url = redis_url
        self.channel = channel
        self.redis_client: Optional[redis.Redis] = None
        self.pubsub: Optional[redis.client.PubSub] = None
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        try:
            self.redis_client = redis.from_url(self.redis_url)
            self.pubsub = self.redis_client.pubsub()
            await self.pubsub.subscribe(self.channel)
            logger.info(
                "Connected to Redis. Listening for rules on channel '%s'...",
                self.channel,
            )
            self._task = asyncio.create_task(self._listen())
        except Exception as e:
            logger.error("Failed to connect to Redis for rule listener: %s", e)

    async def _listen(self):
        try:
            if not self.pubsub:
                return
            async for message in self.pubsub.listen():
                if message["type"] == "message":
                    self._process_message(message["data"])
        except asyncio.CancelledError:
            logger.info("Redis listener task cancelled.")
        except Exception as e:
            logger.error("Error in Redis listener loop: %s", e)

    def _process_message(self, data: bytes):
        try:
            rule_data = json.loads(data)
            action = rule_data.get("action", "add")

            if action == "add":
                rule_type = rule_data.get("type")
                if rule_type == "tx":
                    self._handle_add_tx(rule_data)
                elif rule_type == "log":
                    self._handle_add_log(rule_data)
                elif rule_type == "log_subscription":
                    self._handle_add_log_subscription(rule_data)
                else:
                    logger.warning("Unknown rule type: %s", rule_type)

            elif action == "remove":
                rule_id = rule_data.get("rule_id")
                if not rule_id:
                    logger.warning("Remove message missing 'rule_id'")
                    return
                self._handle_remove(rule_id, rule_data.get("type"))

            elif action == "clear":
                self._handle_clear(rule_data.get("rule_type"))

            elif action == "unsubscribe":
                sub_id = rule_data.get("sub_id")
                if sub_id and self._log_filter:
                    self._log_filter.unsubscribe(sub_id)
                    logger.info("Unsubscribed log sub_id=%s via Redis", sub_id)

            else:
                logger.warning("Unknown action: %r", action)

        except json.JSONDecodeError:
            logger.error("Failed to decode Redis message: %s", data)
        except Exception as e:
            logger.error("Error processing Redis message: %s", e)

    #  Add handlers 

    def _handle_add_tx(self, rule_data: dict):
        if self._tx_filter is None:
            logger.warning("No TransactionFilter — ignoring TX rule")
            return
        rule_data.pop("type", None)
        rule_data.pop("action", None)
        rule_id = self._tx_filter.add_rule(rule_data)
        logger.info("Added TX rule from Redis: id=%s rule=%s", rule_id, rule_data)

    def _handle_add_log(self, rule_data: dict):
        """Add a log post-filter rule."""
        if self._log_filter is None:
            logger.warning("No LogFilter — ignoring log rule")
            return
        rule_data.pop("type", None)
        rule_data.pop("action", None)
        rule_id = self._log_filter.add_rule(rule_data)
        logger.info("Added log rule from Redis: id=%s rule=%s", rule_id, rule_data)

    def _handle_add_log_subscription(self, rule_data: dict):
        """Add a log subscription on the node."""
        if self._log_filter is None:
            logger.warning("No LogFilter — ignoring log subscription")
            return
        rule_data.pop("type", None)
        rule_data.pop("action", None)
        sub_id = self._log_filter.subscribe(
            address=rule_data.get("address"),
            topics=rule_data.get("topics"),
            abi=rule_data.get("abi"),
            event_name=rule_data.get("event_name"),
        )
        logger.info("Added log subscription from Redis: sub_id=%s", sub_id)

    #  Remove / clear handlers 

    def _handle_remove(self, rule_id: str, rule_type: str | None = None):
        removed = False
        if rule_type == "tx" and self._tx_filter:
            removed = self._tx_filter.remove_rule(rule_id)
        elif rule_type == "log" and self._log_filter:
            removed = self._log_filter.remove_rule(rule_id)
        elif rule_type == "log_subscription" and self._log_filter:
            removed = self._log_filter.unsubscribe(rule_id)
        else:
            if self._tx_filter and self._tx_filter.remove_rule(rule_id):
                removed = True
            elif self._log_filter and self._log_filter.remove_rule(rule_id):
                removed = True
        if not removed:
            logger.warning("Remove: rule_id=%s not found", rule_id)

    def _handle_clear(self, rule_type: str | None):
        if rule_type == "tx" and self._tx_filter:
            self._tx_filter.clear_rules()
            logger.info("Cleared all TX rules via Redis")
        elif rule_type == "log" and self._log_filter:
            self._log_filter.clear_rules()
            logger.info("Cleared all log rules via Redis")
        elif rule_type == "log_subscription" and self._log_filter:
            self._log_filter.clear_subscriptions()
            logger.info("Cleared all log subscriptions via Redis")
        elif rule_type is None:
            if self._tx_filter:
                self._tx_filter.clear_rules()
            if self._log_filter:
                self._log_filter.clear_rules()
                self._log_filter.clear_subscriptions()
            logger.info("Cleared all rules and subscriptions via Redis")
        else:
            logger.warning("Unknown rule_type for clear: %s", rule_type)

    #  Shutdown 

    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        if self.pubsub:
            await self.pubsub.unsubscribe(self.channel)
            await self.pubsub.close()

        if self.redis_client:
            await self.redis_client.aclose()

        logger.info("Redis rule listener stopped.")

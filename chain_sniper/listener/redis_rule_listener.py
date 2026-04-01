import asyncio
import json
import logging
from typing import Optional
import redis.asyncio as redis
from chain_sniper.filters import Filter

logger = logging.getLogger(__name__)


class RedisRuleListener:
    """
    An asynchronous background listener that subscribes to a Redis channel
    and pushes received rules into the provided Filter instance.
    """
    def __init__(
        self,
        dynamic_filter: Filter,
        redis_url: str = "redis://localhost",
        channel: str = "sniper_rules"
    ):
        self.dynamic_filter = dynamic_filter
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
                f"Connected to Redis. Listening for new rules"
                f" on channel '{self.channel}'..."
            )
            
            self._task = asyncio.create_task(self._listen())
        except Exception as e:
            logger.error(f"Failed to connect to Redis for rule listener: {e}")

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
            logger.error(f"Error in Redis listener loop: {e}")

    def _process_message(self, data: bytes):
        try:
            rule_data = json.loads(data)
            action = rule_data.get("action", "add")

            if action == "add":
                rule_type = rule_data.get("type")
                if rule_type == "log":
                    rule_data.pop("type", None)
                    rule_data.pop("action", None)
                    rule_id = self.dynamic_filter.add_log_rule(rule_data)
                    logger.info(
                        f"Added dynamic log rule from Redis:"
                        f" rule_id={rule_id} rule={rule_data}"
                    )
                elif rule_type == "tx":
                    rule_data.pop("type", None)
                    rule_data.pop("action", None)
                    rule_id = self.dynamic_filter.add_tx_rule(rule_data)
                    logger.info(
                        f"Added dynamic tx rule from Redis:"
                        f" rule_id={rule_id} rule={rule_data}"
                    )
                else:
                    logger.warning(f"Unknown rule type received: {rule_type}")

            elif action == "remove":
                rule_id = rule_data.get("rule_id")
                if not rule_id:
                    logger.warning(
                        "Redis remove message missing 'rule_id' field"
                    )
                    return
                removed = self.dynamic_filter.remove_rule(rule_id)
                if not removed:
                    logger.warning(
                        f"Redis remove: rule_id={rule_id} not found in filter"
                    )

            elif action == "clear":
                rule_type = rule_data.get("rule_type")
                if rule_type == "tx":
                    self.dynamic_filter.clear_tx_rules()
                    logger.info("Cleared all TX rules via Redis message")
                elif rule_type == "log":
                    self.dynamic_filter.clear_log_rules()
                    logger.info("Cleared all log rules via Redis message")
                else:
                    logger.warning(
                        f"Redis clear message has unknown rule_type: {rule_type}"
                    )

            else:
                logger.warning(
                    f"Redis rule message has unknown action: {action!r}"
                )

        except json.JSONDecodeError:
            logger.error(f"Failed to decode rule message from Redis: {data}")
        except Exception as e:
            logger.error(f"Error processing Redis rule message: {e}")

    async def stop(self):
        """Cleanly shutdown the redis rule listener task and connection."""
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

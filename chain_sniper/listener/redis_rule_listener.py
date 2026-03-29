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
            rule_type = rule_data.get("type")
            
            if rule_type == "log":
                # remove the "type" key before adding to filter
                rule_data.pop("type", None)
                self.dynamic_filter.add_log_rule(rule_data)
                logger.info(
                    f"Successfully added dynamically log rule"
                    f" from Redis: {rule_data}"
                )
            elif rule_type == "tx":
                # remove the "type" key before adding to filter
                rule_data.pop("type", None)
                self.dynamic_filter.add_tx_rule(rule_data)
                logger.info(
                    f"Successfully added dynamically tx rule"
                    f" from Redis: {rule_data}"
                )
            else:
                logger.warning(f"Unknown rule type received: {rule_type}")
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

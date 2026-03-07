# Chain Sniper

A high-performance Ethereum/EVM blockchain listener and transaction monitor.

## Overview

Chain Sniper provides a robust set of tools for monitoring blockchain activities in real-time. It features a scalable, memory-safe, and clean architecture based on a pipeline pattern (Listener → Parser → Filters → Strategy → Output). It supports both **WebSocket subscriptions** for low-latency updates, **HTTP polling** for fallback logic, and **Redis-based Dynamic Filtering**.

### Key Features

-  **Multi-Chain Support**: Compatible with any EVM-compatible chain (Ethereum, BSC, Polygon, Base, etc.).
-  **Flexible Listeners**: 
  - `WebSocketListener`: Real-time block and log subscriptions.
  - `PollListener`: Reliable HTTP polling with automatic fallback for nodes that don't support stateful filters.
  - `RedisRuleListener`: Inject real-time filter rules while the system is running.
-  **Pipeline Architecture**: Clean separation of concerns using `Filters` and `Strategies`.
-  **Auto-Recovery**: Built-in reconnection logic with exponential backoff.
-  **Dynamic Filtering**: Modify your targeting criteria on the fly without restarting the service.

## Project Structure

The project has been organized into a cohesive python package:

```text
chain-sniper/
├── chain_sniper/               # The main library package
│   ├── abstracts/              # Base classes (Strategy, Filter)
│   ├── chains/                 # Chain-specific configuration/logic
│   ├── cli/                    # CLI handling points
│   ├── core/                   # Utilities, configuration, exceptions
│   ├── engine/                 # Processing pipeline logic
│   ├── execution/              # Request and webhook executions
│   ├── filters/                # User and dynamic filters
│   ├── listener/               # WebSocket, poll, and Redis listeners
│   ├── parser/                 # Block, tx, and rule parsing
│   ├── storage/                # State and redis logic
│   ├── strategy/               # Trading/execution strategies
│   └── workers/                # Async task workers
├── examples/                   # Standalone scripts to demonstrate usage
├── tests/                      # Testing directory
└── main.py                     # Entry point for your application
```

## Installation

This project utilizes [uv](https://github.com/astral-sh/uv) and modern Python native specifications via `pyproject.toml`.

```bash
# Clone the repository
git clone https://github.com/rakibhossain72/chain-sniper.git
cd chain-sniper

# Install dependencies and sync environment using uv
uv sync
```

Alternatively, use `pip`:
```bash
pip install -r pyproject.toml
```

## Quick Start

### Watch New Blocks and Apply a Pipeline

Set up your `.env` file containing your `RPC_URL`:

```bash
echo "RPC_URL=wss://your-rpc-url" > .env
```

Create a pipeline in `main.py`:

```python
import asyncio
import os
import dotenv
from chain_sniper.listener.websocket_listener import WebSocketListener, BlockDetail
from chain_sniper.engine.pipeline import Pipeline
from chain_sniper.filters.dynamic_filter import DynamicFilter
from chain_sniper.abstracts.base_strategy import BaseStrategy

dotenv.load_dotenv()
RPC_URL = os.getenv("RPC_URL")

class MyStrategy(BaseStrategy):
    async def execute(self, tx):
        print(f"Executing strategy for transaction: {tx}")

async def main():
    # 1. Initialize filters
    dyn_filter = DynamicFilter()
    
    # 2. Setup the pipeline
    pipeline = Pipeline(filter=dyn_filter, strategy=MyStrategy())

    # 3. Setup Listener
    listener = WebSocketListener(RPC_URL, block_detail=BlockDetail.FULL_BLOCK)
    listener.on("block", pipeline.process_block)

    # 4. Start listening
    await listener.start()

if __name__ == "__main__":
    asyncio.run(main())
```

Run your code:
```bash
uv run main.py
```

## Advanced Examples

Check out the `examples/` directory for more advanced usage:

- Basic Monitoring: `watch_blocks.py`, `watch_blocks_poll.py`
- Advanced Filtering: `watch_erc20.py`, `watch_native_wss.py`
- Dynamic Rules: `push_redis_rule.py`

## Updating Dynamic Rules

You can inject rules dynamically without restarting the main python process via Redis.

1. Start your background rule listener inside your main process using `RedisRuleListener`.
2. Push new rules via a redis pubsub channel:

```python
# See examples/push_redis_rule.py
import redis
import json

r = redis.Redis(host='localhost', port=6379, decode_responses=True)
rule = {"type": "log", "min_amount": 1000}
r.publish('sniper_rules', json.dumps(rule))
```

## License

MIT

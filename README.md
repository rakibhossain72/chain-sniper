# Chain Sniper

A high-performance Ethereum/EVM blockchain listener and transaction monitor.

## Overview

Chain Sniper provides a robust set of tools for monitoring blockchain activities in real-time. It features a scalable, memory-safe, and clean architecture based on a pipeline pattern (Listener → Parser → Filters → Strategy → Output). It supports both **WebSocket subscriptions** for low-latency updates, **HTTP polling** for fallback logic, and **Redis-based Dynamic Filtering**.

### Key Features

-  **Multi-Chain Support**: Compatible with any EVM-compatible chain (Ethereum, BSC, Polygon, Base, etc.).
-  **Flexible Listeners**:
   - `WebSocketListener`: Real-time block and log subscriptions via WebSocket.
   - `HttpListener` (`PollListener`): Reliable HTTP polling with automatic fallback for nodes that don't support stateful filters.
   - `RedisRuleListener`: Inject real-time filter rules while the system is running.
-  **Pipeline Architecture**: Clean separation of concerns using `Filters` and `Strategies`.
-  **Auto-Recovery**: Built-in reconnection logic with exponential backoff.
-  **Dynamic Filtering**: Modify your targeting criteria on the fly without restarting the service.
-  **ABI-Based Event Filtering**: Add log filters using contract ABI and event names instead of cryptic topic hashes. Logs are automatically decoded into readable parameters.

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

## Choosing Between WebSocket and HTTP

- **WebSocketListener**: Best for real-time monitoring with low latency. Use when your RPC provider supports WebSocket subscriptions.
- **HttpListener**: Use for RPC providers that only support HTTP, or when you need polling-based monitoring. Automatically falls back to `eth_getLogs` scanning if stateful filters aren't supported.

## Modular Architecture

Chain Sniper now includes reusable modules for common tasks:

- **`chain_sniper.utils.config`**: Configuration management (env vars, RPC URLs)
- **`chain_sniper.utils.logging`**: Consistent logging setup
- **`chain_sniper.utils.abis`**: ABI loading and manipulation utilities
- **`chain_sniper.contracts`**: Pre-registered contracts with ABIs and addresses
- **`chain_sniper.utils.handlers`**: Reusable event handler factories
- **`chain_sniper.utils.runner`**: Listener creation and execution utilities

### Quick Examples

#### Simple ERC20 Transfer Monitor (WebSocket)

```python
import asyncio
from chain_sniper.utils import (
    get_rpc_url, setup_logging, create_websocket_listener,
    create_block_handler, create_log_handler, create_error_handler, run_listener
)
from chain_sniper.contracts import get_contract_abi, get_contract_address

async def main():
    # Setup
    rpc_url = get_rpc_url()
    logger = setup_logging()

    # Create listener
    listener = create_websocket_listener(rpc_url, logger=logger)

    # Get contract details
    usdt_address = get_contract_address("USDT_BSC")
    erc20_abi = get_contract_abi("ERC20")

    # Add ABI-based filter (auto-decodes logs!)
    listener.add_abi_log_filter(abi=erc20_abi, address=usdt_address, event_name="Transfer")

    # Register handlers
    listener.on("block", create_block_handler())
    listener.on("log", create_log_handler())
    listener.on("error", create_error_handler())

    # Run with proper error handling
    await run_listener(listener)

asyncio.run(main())
```

#### HTTP Polling Version

```python
# Same code, just change the listener type
listener = create_http_listener(rpc_url, logger=logger, poll_interval=2.0)
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
from chain_sniper.listener.websocket_listener import WebSocketListener
from chain_sniper.listener.common import BlockDetail
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

- **Modular Examples**: `simple_transfer_monitor.py` - Clean example using reusable modules
- Basic Monitoring: `watch_blocks.py`, `watch_blocks_poll.py`
- Advanced Filtering: `watch_erc20.py`, `watch_erc20_http.py`
- Dynamic Rules: `push_redis_rule.py`

## ABI-Based Event Filtering

Chain Sniper supports easy event filtering using contract ABIs instead of topic hashes. This makes it user-friendly and automatically decodes logs into readable parameters.

### Using ABI and Event Name (Recommended)

```python
from chain_sniper.listener.websocket_listener import WebSocketListener
from chain_sniper.listener.common import BlockDetail

listener = WebSocketListener("wss://your-rpc-url", block_detail=BlockDetail.FULL_BLOCK)
```

Or using the modular utilities:

```python
from chain_sniper.utils import create_websocket_listener

listener = create_websocket_listener("wss://your-rpc-url", block_detail="full_block")
```

### Using Topic Hashes (Raw Logs)

For cases where you prefer raw logs or don't have the ABI:

```python
listener.add_abi_log_filter(
    address="0x...",
    topics=["0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"]
)

# Logs remain raw (not decoded)
@listener.on("log")
async def on_raw_log(log):
    data = log.get("data", "0x")
    amount = int(data[-64:], 16) / (10 ** 18)
    print(f"Raw transfer amount: {amount}")
```

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

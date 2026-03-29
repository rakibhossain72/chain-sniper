# Chain Sniper

⚡ **Simple blockchain event monitoring with automatic decoding**

Monitor ERC20 transfers, NFT mints, and any smart contract events with just a few lines of code. Chain Sniper automatically decodes events using contract ABIs and provides a clean, decorator-based API.

## Quick Start

### Watch ERC20 Transfers (5 lines!)

```python
from chain_sniper import ChainSniper

# Custom ERC20 ABI for Transfer event
ERC20_ABI = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "from", "type": "address"},
            {"indexed": True, "name": "to", "type": "address"},
            {"indexed": False, "name": "value", "type": "uint256"},
        ],
        "name": "Transfer",
        "type": "event",
    }
]

# USDT contract address on BSC
USDT = "0x55d398326f99059fF775485246999027B3197955"

# Monitor USDT transfers on BSC
sniper = ChainSniper("wss://bsc-ws-node.nariox.org:443")

@sniper.event(contract=USDT, abi=ERC20_ABI, name="Transfer")
async def handle_transfer(event):
    print(f"Transfer: {event['args']['value']/10**18} USDT")

await sniper.start()
```

### Advanced Filtering

```python
from chain_sniper import ChainSniper, Filter

# Only show transfers > 1000 USDT
filter = Filter()
filter.add_log_rule({"args.value": {"_op": "$gte", "_value": 1000000000000000000000}})  # 1000 * 10^18

sniper = ChainSniper("wss://bsc-ws-node.nariox.org:443")
sniper.filter(filter)

@sniper.event(contract=USDT, abi=ERC20_ABI, name="Transfer")
async def handle_transfer(event):
    print(f"Big transfer: {event['args']['value']/10**18} USDT")

await sniper.start()
```

### HTTP Polling (for nodes without WebSocket)

```python
sniper = ChainSniper("https://bsc-dataseed.binance.org/")  # HTTP URL = auto HTTP polling

@sniper.event(contract=USDT, abi=ERC20_ABI, name="Transfer")
async def handle_transfer(event):
    print(f"Transfer: {event['args']['value']/10**18} USDT")

await sniper.start()
```

## Project Structure

Clean, modular architecture focused on simplicity:

```text
chain-sniper/
├── chain_sniper/
│   ├── __init__.py             # Main exports: ChainSniper, Filter, etc.
│   ├── sniper.py               # ChainSniper builder class (main API)
│   ├── types.py                # Type aliases and protocols
│   ├── listener/               # Event listeners
│   │   ├── common.py           # Shared types (BlockDetail, _IdGen)
│   │   ├── websocket_listener.py # Real-time WebSocket monitoring
│   │   ├── poll_listener.py    # HTTP polling fallback
│   │   └── redis_rule_listener.py # Dynamic rule injection
│   ├── parser/                 # Data parsing and decoding
│   │   ├── log_decoder.py      # ABI-based event decoding
│   │   ├── block_parser.py     # Transaction extraction
│   │   └── rule_parser.py      # MongoDB-style rule matching
│   ├── filters/                # Event/transaction filtering
│   │   ├── base.py             # BaseFilter interface
│   │   └── _filter.py          # Versatile rule-based filtering
│   └── utils/                  # Shared utilities
│       ├── abi_filter.py       # Shared ABI filtering logic
│       ├── config.py           # Environment configuration
│       ├── logging.py          # Logging setup
│       ├── abis.py             # ABI loading utilities
│       ├── handlers.py         # Event handler factories
│       └── runner.py           # Listener execution utilities
├── examples/                   # Usage examples
└── main.py                     # Legacy pipeline example
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

## API Reference

### ChainSniper

Decorator-based API for blockchain monitoring.

```python
from chain_sniper import ChainSniper, Filter

# Custom ERC20 ABI
ERC20_ABI = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "from", "type": "address"},
            {"indexed": True, "name": "to", "type": "address"},
            {"indexed": False, "name": "value", "type": "uint256"},
        ],
        "name": "Transfer",
        "type": "event",
    }
]

# Basic usage
sniper = ChainSniper("wss://your-rpc")

@sniper.event(contract="0x...", abi=ERC20_ABI, name="Transfer")
async def handle_transfer(event):
    print(event["args"])

await sniper.start()

# With filtering
filter = Filter()
filter.add_log_rule({"args.value": {"_op": "$gte", "_value": 1000000}})

sniper = ChainSniper("https://your-rpc")  # Auto-detects HTTP polling
sniper.filter(filter)

@sniper.event(contract="0x...", abi=ERC20_ABI, name="Transfer")
async def handle_transfer(event):
    print(event["args"])

await sniper.start()
```

#### Constructor
- `ChainSniper(rpc_url: str)` - WebSocket or HTTP RPC URL

#### Methods
- `.event(contract, abi, name, topics)` - Decorator for registering event handlers
- `.filter(filter_obj, **rules)` - Add filtering logic
- `.on_event(callback)` - Handle decoded log events
- `.on_block(callback)` - Handle new blocks
- `.on_error(callback)` - Handle errors
- `.block_detail("header"|"full_block")` - Set block detail level
- `.poll_interval(seconds)` - HTTP polling interval
- `.start()` - Begin monitoring
- `.stop()` - Stop monitoring

### Filter

MongoDB-style rule matching with operators like `$gt`, `$gte`, `$in`, `$regex`, etc.

```python
filter = Filter()
filter.add_log_rule({"args.value": {"_op": "$gte", "_value": 1000000}})
filter.add_tx_rule({"to": "0x123...", "value": {"_op": "$gt", "_value": 0}})
```

## Choosing Between WebSocket and HTTP

- **WebSocketListener**: Best for real-time monitoring with low latency. Use when your RPC provider supports WebSocket subscriptions.
- **HttpListener**: Use for RPC providers that only support HTTP, or when you need polling-based monitoring. Automatically falls back to `eth_getLogs` scanning if stateful filters aren't supported.

## Modular Architecture

Chain Sniper now includes reusable modules for common tasks:

- **`chain_sniper.utils.config`**: Configuration management (env vars, RPC URLs)
- **`chain_sniper.utils.logging`**: Consistent logging setup
- **`chain_sniper.utils.abis`**: ABI loading and manipulation utilities
- **`chain_sniper.utils.handlers`**: Reusable event handler factories
- **`chain_sniper.utils.runner`**: Listener creation and execution utilities

### Quick Examples

#### Simple ERC20 Transfer Monitor (WebSocket)

```python
import asyncio
from chain_sniper.utils import get_rpc_url, setup_logging
from chain_sniper import ChainSniper

# Custom ERC20 ABI for Transfer event
ERC20_ABI = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "from", "type": "address"},
            {"indexed": True, "name": "to", "type": "address"},
            {"indexed": False, "name": "value", "type": "uint256"},
        ],
        "name": "Transfer",
        "type": "event",
    }
]

# USDT contract address on BSC
USDT = "0x55d398326f99059fF775485246999027B3197955"

async def main():
    # Setup
    rpc_url = get_rpc_url()
    logger = setup_logging()

    # Create sniper
    sniper = ChainSniper(rpc_url)

    @sniper.event(contract=USDT, abi=ERC20_ABI, name="Transfer")
    async def transfer_handler(event):
        args = event["args"]
        amount = args["value"] / 10**18
        print(f"USDT Transfer: {args['from']} → {args['to']}: {amount:.2f} USDT")

    # Register error handler
    @sniper.on_error
    async def error_handler(error):
        logger.error(f"Error: {error}")

    # Run with proper error handling
    await sniper.start()

asyncio.run(main())
```

#### HTTP Polling Version

```python
# Same code, just change the RPC URL to HTTP
sniper = ChainSniper("https://your-rpc-url")  # Auto-detects HTTP polling
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
from chain_sniper.filters import Filter
from chain_sniper.abstracts.base_strategy import BaseStrategy

dotenv.load_dotenv()
RPC_URL = os.getenv("RPC_URL")

class MyStrategy(BaseStrategy):
    async def execute(self, tx):
        print(f"Executing strategy for transaction: {tx}")

async def main():
    # 1. Initialize filters
    dyn_filter = Filter()
    
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
from chain_sniper import ChainSniper

# Custom ERC20 ABI
ERC20_ABI = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "from", "type": "address"},
            {"indexed": True, "name": "to", "type": "address"},
            {"indexed": False, "name": "value", "type": "uint256"},
        ],
        "name": "Transfer",
        "type": "event",
    }
]

sniper = ChainSniper("wss://your-rpc-url")

@sniper.event(contract="0x...", abi=ERC20_ABI, name="Transfer")
async def handle_transfer(event):
    print(event["args"])

await sniper.start()
```

### Using Topic Hashes (Raw Logs)

For cases where you prefer raw logs or don't have the ABI:

```python
sniper = ChainSniper("wss://your-rpc-url")

@sniper.event(
    contract="0x...",
    topics=["0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"]
)
async def on_raw_log(log):
    data = log.get("data", "0x")
    amount = int(data[-64:], 16) / (10 ** 18)
    print(f"Raw transfer amount: {amount}")

await sniper.start()
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

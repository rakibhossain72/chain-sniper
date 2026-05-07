# Chain Sniper

<p align="center">
  <a href="https://pypi.org/project/chain-sniper/">
    <img src="https://img.shields.io/pypi/v/chain-sniper" alt="PyPI">
  </a>
  <a href="https://pypi.org/project/chain-sniper/">
    <img src="https://img.shields.io/pypi/pyversions/chain-sniper" alt="Python">
  </a>
  <a href="https://github.com/rakibhossain72/chain-sniper/blob/main/LICENSE">
    <img src="https://img.shields.io/pypi/l/chain-sniper" alt="License">
  </a>
</p>

A high-performance Ethereum/EVM blockchain listener and transaction monitor. 

## Features

- **Decorator-based API** — Register event handlers with clean Python decorators
- **Automatic ABI decoding** — Decode events into readable parameters using contract ABIs
- **Multiple transport modes** — WebSocket for real-time monitoring or HTTP polling as fallback
- **Fault-tolerant RPC pools** — Multiple endpoints with automatic failover and latency-based selection
- **MongoDB-style filtering** — Rich rule-based filtering with operators like `$gte`, `$in`, `$regex`
- **Dynamic rule injection** — Update filtering rules in real-time via Redis without restarting
- **Transaction monitoring** — Watch blocks, transactions, and decode input data
- **Reorg detection** — Handle chain reorganizations gracefully
- **Multi-chain support** — Works with any EVM-compatible chain (Ethereum, BSC, Polygon, etc.)

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

### Fault-Tolerant RPC Pool

```python
import asyncio
from chain_sniper import ChainSniper
from chain_sniper.rpc_pool import RPCPool

async def main():
    # Create RPC pool with multiple endpoints for fault tolerance
    pool = await RPCPool.create(
        rpcs=[
            "https://bsc-dataseed1.binance.org",
            "https://public-bsc-mainnet.fastnode.io",
            "wss://bsc-ws-node.nariox.org:443",
        ],
        expected_chain_id=56,  # BSC chain ID
    )
    sniper = ChainSniper(pool)

    @sniper.event(contract=USDT, abi=ERC20_ABI, name="Transfer")
    async def handle_transfer(event):
        print(f"Transfer: {event['args']['value']/10**18} USDT")

    await sniper.start()

asyncio.run(main())
```

### HTTP Polling (for nodes without WebSocket)

```python
sniper = ChainSniper("https://bsc-dataseed.binance.org/")  # HTTP URL = auto HTTP polling

@sniper.event(contract=USDT, abi=ERC20_ABI, name="Transfer")
async def handle_transfer(event):
    print(f"Transfer: {event['args']['value']/10**18} USDT")

await sniper.start()
```

### Transaction Monitoring

```python
from chain_sniper import ChainSniper

sniper = ChainSniper("wss://your-rpc")
sniper.block_detail("full_block")  # Include transaction data

@sniper.on_transaction
async def handle_tx(tx):
    print(f"Transaction: {tx['hash']} | {tx['from']} -> {tx['to']}")

await sniper.start()
```

## Project Structure

```
chain-sniper/
├── chain_sniper/
│   ├── __init__.py             # Main exports: ChainSniper, Filter, BlockDetail
│   ├── sniper.py               # ChainSniper builder class (main API)
│   ├── types.py              # Type aliases and enums
│   ├── listener/            # Event listeners
│   │   ├── websocket_listener.py   # WebSocket real-time monitoring
│   │   ├── poll_listener.py     # HTTP polling fallback
│   │   ├── redis_rule_listener.py # Dynamic rule injection via Redis
│   │   └── common.py           # Shared types (BlockDetail, etc.)
│   ├── parser/              # Data parsing and decoding
│   │   ├── log_decoder.py    # ABI-based event decoding
│   │   ├── tx_parser.py     # Transaction parsing and input data decoding
│   │   ├── block_parser.py  # Block extraction
│   │   └── rule_parser.py  # MongoDB-style rule matching
│   ├── filters/            # Event/transaction filtering
│   │   ├── base.py        # BaseFilter interface
│   │   └── _filter.py     # Versatile rule-based filtering
│   ├── rpc_pool/          # Fault-tolerant RPC management
│   │   ├── rpc_pool.py    # Multi-endpoint pool with health monitoring
│   │   └── rpc_node.py   # Individual RPC node representation
│   ├── execution/         # Action execution (webhooks, etc.)
│   ├── storage/          # State management (Redis, etc.)
│   ├── chains/           # Chain-specific configurations
│   └── utils/            # Shared utilities
│       ├── config.py      # Configuration management
│       ├── logging.py    # Logging setup
│       ├── abis.py       # ABI loading utilities
│       ├── handlers.py    # Event handler factories
│       └── runner.py     # Listener execution utilities
├── examples/             # Usage examples
└── tests/              # Test suite
```

## Installation

This project uses [uv](https://github.com/astral-sh/uv) for dependency management.

```bash
# Clone the repository
git clone https://github.com/rakibhossain72/chain-sniper.git
cd chain-sniper

# Install dependencies using uv
uv sync
```

Alternatively, use `pip`:

```bash
pip install -r pyproject.toml
```

## Configuration

Create a `.env` file with your RPC URL:

```bash
echo "RPC_URL=wss://your-rpc-url" > .env
```

## API Reference

### ChainSniper

Decorator-based API for blockchain monitoring. Accepts either a plain RPC URL or an `RPCPool` for fault-tolerant multi-endpoint setups.

```python
from chain_sniper import ChainSniper, Filter, BlockDetail
from chain_sniper.rpc_pool import RPCPool
from chain_sniper.utils.abis import load_abi_from_file

# Basic usage with single endpoint
sniper = ChainSniper("wss://your-rpc")

# Fault-tolerant with RPC pool
pool = await RPCPool.create(
    rpcs=["https://rpc1.com", "wss://rpc2.com"],
    expected_chain_id=56,
)
sniper = ChainSniper(pool, chain_id=56)
```

#### Constructor

- `ChainSniper(rpc: str | RPCPool, chain_id: int | None)` — WebSocket/HTTP RPC URL or RPCPool instance

#### Event Registration

```python
# Using ABI and event name (recommended)
@sniper.event(contract="0x...", abi=ERC20_ABI, name="Transfer")
async def handle_transfer(event):
    print(event["args"])

# Using raw topic hashes
@sniper.event(
    contract="0x...",
    topics=["0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"]
)
async def on_raw_log(log):
    print(log)
```

#### Transaction Monitoring

```python
# Watch all transactions in blocks
sniper.block_detail("full_block")

@sniper.on_transaction
async def handle_tx(tx):
    print(f"TX: {tx['hash']} | {tx['from']} -> {tx['to']}")

# Or use on_block to process transactions from blocks
@sniper.on_block
async def handle_block(block):
    for tx in block.get("transactions", []):
        print(f"TX: {tx['hash']}")
```

#### Filtering

```python
# MongoDB-style filtering
filter = Filter()
filter.add_log_rule({"args.value": {"_op": "$gte", "_value": 1000000000000000000000}})
filter.add_tx_rule({"to": "0x123...", "value": {"_op": "$gt", "_value": 0}})

sniper = ChainSniper("wss://your-rpc")
sniper.filter(filter)
```

#### Reorg Handling

```python
@sniper.on_reorg
async def handle_reorg(reorg_event):
    print(f"Reorg detected: {reorg_event}")
```

#### Configuration Methods

- `.event(contract, abi, name)` — Decorator for registering event handlers
- `.watch(abi, address, event)` — Fluent API for event registration
- `.filter(filter_obj, **rules)` — Add filtering logic
- `.on_event(callback)` — Handle decoded log events
- `.on_block(callback)` — Handle new blocks
- `.on_transaction(callback)` — Handle individual transactions
- `.on_reorg(callback)` — Handle chain reorganizations
- `.on_error(callback)` — Handle errors
- `.block_detail("header" | "full_block")` — Set block detail level
- `.poll_interval(seconds)` — HTTP polling interval
- `.start()` — Begin monitoring
- `.stop()` — Stop monitoring

### Filter

MongoDB-style rule matching with rich operators:

- **Comparison**: `$eq`, `$ne`, `$gt`, `$gte`, `$lt`, `$lte`
- **Array**: `$in`, `$nin`
- **Pattern**: `$regex`, `$exists`
- **Logical**: Nested rules with `$and`, `$or`

```python
from chain_sniper import Filter

filter = Filter()

# Transaction rules
filter.add_tx_rule({"to": "0x55d398326f99059fF775485246999027B3197955"})
filter.add_tx_rule({"value": {"_op": "$gte", "_value": 10**18}})
filter.add_tx_rule({
    "from": {
        "_op": "$in",
        "_value": ["0x123...", "0x456..."]
    }
})

# Log/event rules
filter.add_log_rule({
    "args.value": {"_op": "$gte", "_value": 1000000000000000000000}
})

# Remove rules dynamically
rule_id = filter.add_tx_rule({"to": "0x..."})
filter.remove_rule(rule_id)
```

#### Filter Methods

- `.add_tx_rule(rule)` — Add transaction filter rule
- `.add_log_rule(rule)` — Add log/event filter rule
- `.remove_rule(rule_id)` — Remove rule by ID
- `.clear_tx_rules()` — Clear all transaction rules
- `.clear_log_rules()` — Clear all log rules
- `.clear_rules()` — Clear all rules
- `.get_config()` — Get current filter configuration

### RPCPool

Fault-tolerant multi-endpoint RPC manager with automatic health monitoring and latency-based selection.

```python
from chain_sniper.rpc_pool import RPCPool

pool = await RPCPool.create(
    rpcs=[
        "https://bsc-dataseed1.binance.org",
        "https://public-bsc-mainnet.fastnode.io",
        "wss://bsc-ws-node.nariox.org:443",
    ],
    expected_chain_id=56,
)

# Pool automatically selects fastest healthy endpoint
sniper = ChainSniper(pool)
```

#### RPCPool Methods

- `.get_rpc()` — Get fastest healthy endpoint URL
- `.mark_failed(url)` — Mark endpoint as failed
- `.record_success(url, elapsed_ms)` — Update latency metrics
- `.stop()` — Cancel health monitor pattern

### BlockDetail

Controls how much block data is fetched.

```python
from chain_sniper import BlockDetail

sniper = ChainSniper("wss://your-rpc")
sniper.block_detail(BlockDetail.HEADER)  # Just block headers
sniper.block_detail(BlockDetail.FULL_BLOCK)  # Full block with transactions
```

## Examples

Check out the `examples/` directory for complete usage examples:

| Example | Description |
|---------|-------------|
| `simple_transfer_monitor.py` | Clean example using RPC pools |
| `watch_erc20.py` | Monitor ERC20 transfers with filtering |
| `watch_erc20_http.py` | HTTP polling version |
| `watch_transactions.py` | Monitor all transactions in blocks |
| `watch_transactions_dynamic_filter.py` | Transaction filtering with Filter |
| `watch_with_dynamic_filter.py` | Dynamic rule injection via Redis |
| `decode_input_data_example.py` | Decode transaction input data |
| `push_redis_rule.py` | Push rules to Redis dynamically |

## Dynamic Rule Injection via Redis

Inject filtering rules without restarting your monitor:

1. Start your listener with Redis rule listener:

```python
from chain_sniper.listener import RedisRuleListener

redis_listener = RedisRuleListener(
    dynamic_filter=filter,
    redis_url="redis://localhost",
    channel="sniper_rules",
)
await redis_listener.start()
```

2. Push rules via Redis CLI or Python:

```python
import redis
import json

r = redis.Redis(host='localhost', port=6379, decode_responses=True)

# Push a rule
rule = {"type": "tx", "to": "0x55d398326f99059fF775485246999027B3197955"}
r.publish('sniper_rules', json.dumps({"action": "add_tx", "rule": rule}))

# Remove a rule
r.publish('sniper_rules', json.dumps({"action": "remove", "rule_id": "uuid-here"}))
```

## Choosing Between WebSocket and HTTP

- **WebSocket** — Best for real-time monitoring with low latency. Use when your RPC provider supports WebSocket subscriptions.
- **HTTP** — Use for RPC providers that only support HTTP, or when you need polling-based monitoring. Automatically falls back to `eth_getLogs` scanning if stateful filters aren't supported.

## Dependencies

- `aiofiles>=25.1.0`
- `dotenv>=0.9.9`
- `redis>=7.2.1`
- `web3>=7.14.1`
- `websockets>=15.0.1`

## License

MIT
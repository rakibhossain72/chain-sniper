# Chain Sniper

A high-performance EVM blockchain listener and transaction monitor.

## Install

```bash
git clone https://github.com/rakibhossain72/chain-sniper.git
cd chain-sniper
uv sync
```

Or with pip:

```bash
pip install chain-sniper
```

## Quick Start

```python
from chain_sniper import ChainSniper

ERC20_ABI = [...]  # Transfer event ABI
USDT = "0x55d398326f99059fF775485246999027B3197955"

sniper = ChainSniper("wss://bsc-ws-node.nariox.org:443")

@sniper.event(contract=USDT, abi=ERC20_ABI, name="Transfer")
async def handle_transfer(event):
    print(f"Transfer: {event['args']['value'] / 10**18} USDT")

await sniper.start()
```

Pass an HTTP URL instead of WebSocket to use polling mode automatically.

## RPC Pool (fault-tolerant)

```python
from chain_sniper.rpc_pool import RPCPool

pool = await RPCPool.create(
    rpcs=[
        "https://bsc-dataseed1.binance.org",
        "wss://bsc-ws-node.nariox.org:443",
    ],
    expected_chain_id=56,
)
sniper = ChainSniper(pool)
```

## Transaction Monitoring

```python
sniper.block_detail("full_block")

@sniper.on_transaction
async def handle_tx(tx):
    print(f"{tx['hash']} | {tx['from']} -> {tx['to']}")
```

## Filtering

MongoDB-style rules with operators: `$eq`, `$ne`, `$gt`, `$gte`, `$lt`, `$lte`, `$in`, `$nin`, `$regex`, `$exists`.

```python
from chain_sniper import Filter

f = Filter()
f.add_tx_rule({"value": {"_op": "$gte", "_value": 10**18}})
f.add_log_rule({"args.value": {"_op": "$gte", "_value": 1000 * 10**18}})

sniper.filter(f)
```

## Dynamic Rules via Redis

Inject or remove filter rules at runtime without restarting:

```python
from chain_sniper.listener import RedisRuleListener

redis_listener = RedisRuleListener(
    dynamic_filter=f,
    redis_url="redis://localhost",
    channel="sniper_rules",
)
await redis_listener.start()
```

Push rules from anywhere:

```python
import redis, json

r = redis.Redis(host="localhost", port=6379, decode_responses=True)
r.publish("sniper_rules", json.dumps({"action": "add_tx", "rule": {"to": "0x..."}}))
```

## Key API

| Method | Description |
|--------|-------------|
| `@sniper.event(contract, abi, name)` | Register an event handler |
| `@sniper.on_transaction` | Handle individual transactions |
| `@sniper.on_block` | Handle new blocks |
| `@sniper.on_reorg` | Handle chain reorgs |
| `sniper.filter(f)` | Attach a Filter |
| `sniper.block_detail("header" \| "full_block")` | Set block detail level |
| `sniper.start() / .stop()` | Start or stop monitoring |

See `examples/` for complete usage patterns.

## License

MIT

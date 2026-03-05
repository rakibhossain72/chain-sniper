# Chain Sniper

A high-performance Ethereum/EVM blockchain listener and transaction monitor.

## Overview

Chain Sniper provides a robust set of tools for monitoring blockchain activities in real-time. It supports both **WebSocket subscriptions** for low-latency updates and **HTTP polling** for environments where WebSockets are unstable or unavailable.

### Key Features

- ⛓️ **Multi-Chain Support**: Compatible with any EVM-compatible chain (Ethereum, BSC, Polygon, Base, etc.).
- 📡 **Flexible Listeners**: 
  - `WebSocketListener`: Real-time block and log subscriptions.
  - `HttpListener`: Reliable HTTP polling with automatic fallback for nodes that don't support stateful filters.
- 🛠️ **Event-Driven**: Simple `.on("event", callback)` API for handling blocks, logs, and errors.
- 🔄 **Auto-Recovery**: Built-in reconnection logic with exponential backoff.
- 🔍 **Detailed Monitoring**: Support for header-only or full-block data (including transactions).

## Installation

```bash
# Clone the repository
git clone https://github.com/rakibhossain72/chain-sniper.git
cd chain-sniper

# Install dependencies
pip install aiohttp websockets web3
```

## Quick Start

### 1. Watch New Blocks (WebSocket)

```python
import asyncio
from listener.websocket_listener import WebSocketListener

async def handle_block(block):
    print(f"New block: {int(block['number'], 16)}")

async def main():
    listener = WebSocketListener("wss://bsc.drpc.org")
    listener.on("block", handle_block)
    await listener.start()

if __name__ == "__main__":
    asyncio.run(main())
```

### 2. Poll Blocks (HTTP)

```python
import asyncio
from listener.poll_listener import HttpListener

async def main():
    # Use HTTP RPC URL
    listener = HttpListener("https://bsc-dataseed.binance.org/")
    listener.on("block", lambda b: print(f"Polled block: {int(b['number'], 16)}"))
    await listener.start()

asyncio.run(main())
```

## Examples

Check out the `examples/` directory for more advanced usage:

- `watch_blocks.py`: Basic block monitoring via WebSockets.
- `watch_blocks_poll.py`: Block monitoring via HTTP polling.
- `watch_erc20.py`: Filtering for specific ERC20 `Transfer` events (e.g., USDT on BSC).
- `watch_native_wss.py`: Combining `WebSocketListener` with `web3.py` for deep transaction inspection.

## Usage Tips

1. **RPC Selection**: Many public RPCs have limitations on WebSocket log subscriptions. For production Log monitoring, consider using a provider like Alchemy, QuickNode, or Chainstack.
2. **Environment**: Use `PYTHONPATH=.` when running examples from the terminal to ensure internal modules are correctly discovered.

```bash
export PYTHONPATH=$PYTHONPATH:.
python3 examples/watch_erc20.py
```

## License

MIT

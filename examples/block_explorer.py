"""
Block Explorer Example - Parse all blockchain data like Etherscan.

Captures and simulates DB storage for:
- Blocks (header + metadata)
- Transactions (value transfers, contract calls, contract creations)
- Accounts (all addresses seen)
- Contracts (deployed contracts)
- Token transfers (ERC20 + ERC721)
- Event logs (all contract events)
- Chain reorgs

Uses Anvil local testnet: ws://127.0.0.1:8545

Run Anvil first:
    anvil

Then run this script:
    python examples/block_explorer.py
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, Optional, Set

from chain_sniper import ChainSniper, LogFilter
from chain_sniper.utils.logging import setup_logging

ANVIL_WS = "ws://127.0.0.1:8545"

# ERC20 Transfer(address indexed from, address indexed to, uint256 value)
ERC20_TRANSFER_ABI = [
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

# ERC721 Transfer(address indexed from, address indexed to, uint256 indexed tokenId)
ERC721_TRANSFER_ABI = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "from", "type": "address"},
            {"indexed": True, "name": "to", "type": "address"},
            {"indexed": True, "name": "tokenId", "type": "uint256"},
        ],
        "name": "Transfer",
        "type": "event",
    }
]

# ERC20 Approval(address indexed owner, address indexed spender, uint256 value)
ERC20_APPROVAL_ABI = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "owner", "type": "address"},
            {"indexed": True, "name": "spender", "type": "address"},
            {"indexed": False, "name": "value", "type": "uint256"},
        ],
        "name": "Approval",
        "type": "event",
    }
]


# ============================================================================
# Dummy async DB layer
# ============================================================================

async def db_upsert_block(data: Dict[str, Any]) -> None:
    await asyncio.sleep(0)  # simulate async I/O
    print(f"  [DB:block]    #{data['number']}  txs={data['tx_count']}  gas={data['gas_used']}/{data['gas_limit']}")


async def db_upsert_transaction(data: Dict[str, Any]) -> None:
    await asyncio.sleep(0)
    kind = "CREATE" if data["is_contract_creation"] else "CALL" if data["is_contract_call"] else "TRANSFER"
    print(f"  [DB:tx]       {kind}  {data['hash'][:18]}...  value={data['value_eth']:.6f} ETH")


async def db_upsert_account(address: str, block: int) -> None:
    await asyncio.sleep(0)
    print(f"  [DB:account]  {address}  first_seen=#{block}")


async def db_upsert_contract(data: Dict[str, Any]) -> None:
    await asyncio.sleep(0)
    addr = data.get("address") or "(pending receipt)"
    print(f"  [DB:contract] deployed={addr}  creator={data['creator']}  block=#{data['block_number']}")


async def db_insert_token_transfer(data: Dict[str, Any]) -> None:
    await asyncio.sleep(0)
    kind = "ERC721" if data.get("token_id") is not None else "ERC20"
    print(f"  [DB:token]    {kind}  from={data['from'][:10]}...  to={data['to'][:10]}...  amount={data.get('value', data.get('token_id'))}")


async def db_insert_log(data: Dict[str, Any]) -> None:
    await asyncio.sleep(0)
    name = data.get("event_name") or "unknown"
    print(f"  [DB:log]      event={name}  contract={data['address'][:10]}...  tx={data['tx_hash'][:18]}...")


async def db_handle_reorg(data: Dict[str, Any]) -> None:
    await asyncio.sleep(0)
    print(f"  [DB:reorg]    ROLLBACK from block #{data['detected_at_block']}")


# ============================================================================
# Helpers
# ============================================================================

def to_hex(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray)):
        return "0x" + value.hex()
    return str(value)


def get(obj: Any, key: str, default: Any = None) -> Any:
    """Works for both dict and AttributeDict."""
    try:
        return obj[key] if obj[key] is not None else default
    except (KeyError, TypeError):
        return default


# ============================================================================
# Transaction processor
# ============================================================================

async def process_tx(
    tx: Any,
    block_number: int,
    block_timestamp: int,
    seen_accounts: Set[str],
) -> None:
    tx_hash = to_hex(get(tx, "hash"))
    from_addr = get(tx, "from")
    to_addr = get(tx, "to")
    value = get(tx, "value", 0)
    input_data = to_hex(get(tx, "input")) or "0x"

    is_contract_creation = to_addr is None
    is_contract_call = (not is_contract_creation) and len(input_data) > 2

    # Store transaction
    await db_upsert_transaction({
        "hash": tx_hash,
        "block_number": block_number,
        "block_timestamp": block_timestamp,
        "from": from_addr,
        "to": to_addr,
        "value": value,
        "value_eth": value / 10**18,
        "gas": get(tx, "gas"),
        "gas_price": get(tx, "gasPrice"),
        "max_fee_per_gas": get(tx, "maxFeePerGas"),
        "max_priority_fee_per_gas": get(tx, "maxPriorityFeePerGas"),
        "nonce": get(tx, "nonce"),
        "input": input_data,
        "tx_index": get(tx, "transactionIndex"),
        "tx_type": get(tx, "type"),
        "is_contract_creation": is_contract_creation,
        "is_contract_call": is_contract_call,
    })

    # Track accounts
    for addr in (from_addr, to_addr):
        if addr and addr not in seen_accounts:
            seen_accounts.add(addr)
            await db_upsert_account(addr, block_number)

    # Contract creation — store deployment record
    # (contract address comes from receipt; we store what we have now)
    if is_contract_creation:
        await db_upsert_contract({
            "address": None,  # resolved from receipt in production
            "creator": from_addr,
            "tx_hash": tx_hash,
            "block_number": block_number,
            "init_bytecode": input_data,
            "value": value,
        })


# ============================================================================
# Main
# ============================================================================

async def main() -> None:
    logger = setup_logging(level="INFO", logger_name="block-explorer")

    # Subscribe to all Transfer and Approval events (no address filter = all contracts)
    log_filter = LogFilter()
    log_filter.subscribe(abi=ERC20_TRANSFER_ABI, event_name="Transfer")   # ERC20 transfers
    log_filter.subscribe(abi=ERC721_TRANSFER_ABI, event_name="Transfer")  # ERC721 transfers
    log_filter.subscribe(abi=ERC20_APPROVAL_ABI, event_name="Approval")   # ERC20 approvals

    sniper = ChainSniper(ANVIL_WS)
    sniper.block_detail("full_block")
    sniper.filter(log_filter=log_filter)

    seen_accounts: Set[str] = set()
    stats = {"blocks": 0, "txs": 0, "logs": 0, "token_transfers": 0, "contracts": 0}

    # -------------------------------------------------------------------------
    # Block handler — processes every block + all its transactions
    # -------------------------------------------------------------------------
    @sniper.on_block
    async def on_block(block: Any) -> None:
        number = get(block, "number")
        timestamp = get(block, "timestamp", 0)
        transactions = get(block, "transactions") or []
        miner = get(block, "miner")
        gas_used = get(block, "gasUsed", 0)
        gas_limit = get(block, "gasLimit", 1)
        base_fee = get(block, "baseFeePerGas")

        logger.info("")
        logger.info("━" * 70)
        logger.info(f"📦  Block #{number}  |  {datetime.fromtimestamp(timestamp).isoformat()}")
        logger.info(f"    miner={miner}  txs={len(transactions)}  gas={gas_used}/{gas_limit}  baseFee={base_fee}")
        logger.info("━" * 70)

        await db_upsert_block({
            "number": number,
            "hash": to_hex(get(block, "hash")),
            "parent_hash": to_hex(get(block, "parentHash")),
            "timestamp": timestamp,
            "miner": miner,
            "gas_used": gas_used,
            "gas_limit": gas_limit,
            "base_fee_per_gas": base_fee,
            "difficulty": get(block, "difficulty"),
            "extra_data": to_hex(get(block, "extraData")),
            "tx_count": len(transactions),
            "uncle_count": len(get(block, "uncles") or []),
        })
        stats["blocks"] += 1

        # Process each transaction in the block
        for tx in transactions:
            await process_tx(tx, number, timestamp, seen_accounts)
            stats["txs"] += 1
            if get(tx, "to") is None:
                stats["contracts"] += 1

        logger.info(f"\n📊  Running totals — blocks={stats['blocks']}  txs={stats['txs']}  "
                    f"accounts={len(seen_accounts)}  contracts={stats['contracts']}  "
                    f"token_transfers={stats['token_transfers']}  logs={stats['logs']}")

    # -------------------------------------------------------------------------
    # Event handler — processes decoded contract events (ERC20/ERC721/etc.)
    # -------------------------------------------------------------------------
    @sniper.on_event
    async def on_event(event: Any) -> None:
        address = get(event, "address")
        tx_hash = to_hex(get(event, "transactionHash"))
        block_number = get(event, "blockNumber")
        log_index = get(event, "logIndex")
        event_name = get(event, "event")
        args = get(event, "args") or {}
        topics = [to_hex(t) for t in (get(event, "topics") or [])]

        log_data = {
            "address": address,
            "tx_hash": tx_hash,
            "block_number": block_number,
            "log_index": log_index,
            "event_name": event_name,
            "topics": topics,
            "data": to_hex(get(event, "data")),
            "removed": get(event, "removed", False),
            "decoded_args": dict(args) if args else {},
        }
        await db_insert_log(log_data)
        stats["logs"] += 1

        # Detect token transfers (ERC20 and ERC721 share the Transfer event name)
        if event_name == "Transfer" and args:
            from_addr = args.get("from")
            to_addr = args.get("to")
            token_id = args.get("tokenId")   # ERC721
            value = args.get("value")        # ERC20

            transfer_data = {
                "token": address,
                "from": from_addr or "0x0",
                "to": to_addr or "0x0",
                "tx_hash": tx_hash,
                "block_number": block_number,
                "log_index": log_index,
            }

            if token_id is not None:
                # ERC721 NFT transfer
                transfer_data["token_id"] = token_id
                transfer_data["token_standard"] = "ERC721"
            elif value is not None:
                # ERC20 fungible token transfer
                transfer_data["value"] = value
                transfer_data["token_standard"] = "ERC20"

            await db_insert_token_transfer(transfer_data)
            stats["token_transfers"] += 1

            # Track token contract as an account
            if address and address not in seen_accounts:
                seen_accounts.add(address)
                await db_upsert_account(address, block_number)

        # Detect Approval events
        elif event_name == "Approval" and args:
            logger.info(f"  🔑 Approval  owner={args.get('owner', '')[:10]}...  "
                        f"spender={args.get('spender', '')[:10]}...  "
                        f"value={args.get('value', 0)}")

    # -------------------------------------------------------------------------
    # Reorg handler — rollback orphaned chain data
    # -------------------------------------------------------------------------
    @sniper.on_reorg
    async def on_reorg(event: Any) -> None:
        logger.warning(f"⚠️  Reorg at block #{event['detected_at_block']}  "
                       f"expected_parent={event['expected_parent']}  "
                       f"actual_parent={event['actual_parent']}")
        await db_handle_reorg(event)

    # -------------------------------------------------------------------------
    # Error handler
    # -------------------------------------------------------------------------
    @sniper.on_error
    async def on_error(exc: Exception) -> None:
        logger.error(f"❌  {exc}")

    logger.info(f"🚀  Block Explorer starting on {ANVIL_WS}")
    logger.info("    Tracking: blocks · transactions · accounts · contracts · ERC20/ERC721 transfers · events")
    logger.info("    Press Ctrl+C to stop\n")

    await sniper.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋  Block Explorer stopped.")

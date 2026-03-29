"""
Utility functions for formatting blockchain data in human-readable format.
"""

from typing import Any, Dict


def hex_to_int(hex_str: str) -> int:
    """
    Convert hex string to integer.
    
    Args:
        hex_str: Hex string (e.g., "0x1a2b3c")
        
    Returns:
        Integer value
    """
    if not hex_str or hex_str == "0x":
        return 0
    return int(hex_str, 16)


def format_wei(wei: int, decimals: int = 18) -> float:
    """
    Convert wei to ether/token units.
    
    Args:
        wei: Amount in wei
        decimals: Number of decimals (default 18 for ETH)
        
    Returns:
        Formatted amount as float
    """
    return wei / (10 ** decimals)


def format_transaction(tx: Dict[str, Any], 
                       token_decimals: int = 18) -> Dict[str, Any]:
    """
    Format transaction data in human-readable format.
    
    Args:
        tx: Raw transaction dictionary from blockchain
        token_decimals: Number of decimals for value (default 18 for ETH)
        
    Returns:
        Formatted transaction dictionary with human-readable values
    """
    formatted = {}
    
    # Basic transaction info
    formatted["hash"] = tx.get("hash", "")
    formatted["from"] = tx.get("from", "")
    formatted["to"] = tx.get("to", "Contract Creation")
    
    # Block info
    if "blockNumber" in tx:
        formatted["blockNumber"] = hex_to_int(tx["blockNumber"])
    if "blockHash" in tx:
        formatted["blockHash"] = tx["blockHash"]
    if "transactionIndex" in tx:
        formatted["transactionIndex"] = hex_to_int(tx["transactionIndex"])
    
    # Value
    if "value" in tx:
        value_wei = hex_to_int(tx["value"])
        formatted["valueWei"] = value_wei
        formatted["value"] = format_wei(value_wei, token_decimals)
    
    # Gas info
    if "gas" in tx:
        formatted["gas"] = hex_to_int(tx["gas"])
    if "gasPrice" in tx:
        gas_price_wei = hex_to_int(tx["gasPrice"])
        formatted["gasPriceWei"] = gas_price_wei
        formatted["gasPrice"] = format_wei(gas_price_wei, 9)  # Gwei
    
    # Transaction type
    if "type" in tx:
        tx_type = hex_to_int(tx["type"])
        type_names = {
            0: "Legacy",
            1: "EIP-2930",
            2: "EIP-1559"
        }
        formatted["type"] = type_names.get(tx_type, f"Type {tx_type}")
    
    # Nonce
    if "nonce" in tx:
        formatted["nonce"] = hex_to_int(tx["nonce"])
    
    # Input data
    if "input" in tx:
        input_data = tx["input"]
        formatted["input"] = input_data
        if input_data.startswith("0x"):
            formatted["inputLength"] = len(input_data) - 2
        else:
            formatted["inputLength"] = len(input_data)
    
    # Chain ID
    if "chainId" in tx:
        formatted["chainId"] = hex_to_int(tx["chainId"])
    
    # Keep original hex values for reference
    formatted["_raw"] = tx
    
    return formatted


def format_block(block: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format block data in human-readable format.
    
    Args:
        block: Raw block dictionary from blockchain
        
    Returns:
        Formatted block dictionary with human-readable values
    """
    formatted = {}
    
    # Block info
    if "number" in block:
        formatted["number"] = hex_to_int(block["number"])
    if "hash" in block:
        formatted["hash"] = block["hash"]
    if "parentHash" in block:
        formatted["parentHash"] = block["parentHash"]
    
    # Timestamp
    if "timestamp" in block:
        formatted["timestamp"] = hex_to_int(block["timestamp"])
    
    # Gas info
    if "gasUsed" in block:
        formatted["gasUsed"] = hex_to_int(block["gasUsed"])
    if "gasLimit" in block:
        formatted["gasLimit"] = hex_to_int(block["gasLimit"])
    
    # Transaction count
    if "transactions" in block:
        transactions = block["transactions"]
        formatted["transactionCount"] = len(transactions)
        # Format transactions if they are full objects
        if transactions and isinstance(transactions[0], dict):
            formatted["transactions"] = [
                format_transaction(tx) for tx in transactions
            ]
        else:
            # Just transaction hashes
            formatted["transactions"] = transactions
    
    # Keep original for reference
    formatted["_raw"] = block
    
    return formatted


def format_log(log: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format log data in human-readable format.
    
    Args:
        log: Raw log dictionary from blockchain
        
    Returns:
        Formatted log dictionary with human-readable values
    """
    formatted = {}
    
    # Log info
    if "address" in log:
        formatted["address"] = log["address"]
    if "topics" in log:
        formatted["topics"] = log["topics"]
    if "data" in log:
        formatted["data"] = log["data"]
    
    # Block info
    if "blockNumber" in log:
        formatted["blockNumber"] = hex_to_int(log["blockNumber"])
    if "blockHash" in log:
        formatted["blockHash"] = log["blockHash"]
    if "transactionHash" in log:
        formatted["transactionHash"] = log["transactionHash"]
    if "transactionIndex" in log:
        formatted["transactionIndex"] = hex_to_int(log["transactionIndex"])
    if "logIndex" in log:
        formatted["logIndex"] = hex_to_int(log["logIndex"])
    
    # Decoded event info (if available)
    if "event" in log:
        formatted["event"] = log["event"]
    if "args" in log:
        formatted["args"] = log["args"]
    
    # Keep original for reference
    formatted["_raw"] = log
    
    return formatted


def print_transaction(tx: Dict[str, Any], 
                      token_decimals: int = 18,
                      token_symbol: str = "ETH") -> None:
    """
    Print transaction in a readable format.
    
    Args:
        tx: Transaction dictionary (raw or formatted)
        token_decimals: Number of decimals for value
        token_symbol: Token symbol for display
    """
    # Format if raw
    if "_raw" not in tx:
        tx = format_transaction(tx, token_decimals)
    
    print(f"Transaction: {tx['hash'][:10]}...")
    print(f"  Block: {tx.get('blockNumber', 'N/A')}")
    print(f"  From: {tx['from'][:10]}...")
    if tx['to'] != "Contract Creation":
        print(f"  To: {tx['to'][:10]}...")
    else:
        print("  To: Contract Creation")
    print(f"  Value: {tx.get('value', 0):.6f} {token_symbol}")
    print(f"  Gas: {tx.get('gas', 0):,}")
    print(f"  Gas Price: {tx.get('gasPrice', 0):.2f} Gwei")
    print(f"  Type: {tx.get('type', 'N/A')}")
    print()


def print_block(block: Dict[str, Any]) -> None:
    """
    Print block in a readable format.
    
    Args:
        block: Block dictionary (raw or formatted)
    """
    # Format if raw
    if "_raw" not in block:
        block = format_block(block)
    
    print(f"Block #{block['number']}")
    print(f"  Hash: {block['hash'][:10]}...")
    print(f"  Transactions: {block.get('transactionCount', 0)}")
    print(f"  Gas Used: {block.get('gasUsed', 0):,}")
    print(f"  Gas Limit: {block.get('gasLimit', 0):,}")
    print()

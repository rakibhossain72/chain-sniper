"""
ABI utilities for loading and working with contract ABIs.
"""

import json
from typing import List, Dict, Any
from web3 import Web3


def load_abi_from_file(filepath: str) -> List[Dict[str, Any]]:
    """
    Load ABI from a JSON file.

    Args:
        filepath: Path to the ABI JSON file

    Returns:
        ABI as a list of dictionaries
    """
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def load_abi_from_string(abi_json: str) -> List[Dict[str, Any]]:
    """
    Load ABI from a JSON string.

    Args:
        abi_json: ABI as JSON string

    Returns:
        ABI as a list of dictionaries
    """
    return json.loads(abi_json)


def get_event_signature(abi: List[Dict[str, Any]], event_name: str) -> str:
    """
    Get the event signature for a given event name from ABI.

    Args:
        abi: Contract ABI
        event_name: Name of the event

    Returns:
        Event signature string
    """
    for item in abi:
        if item.get("type") == "event" and item.get("name") == event_name:
            inputs = item.get("inputs", [])
            input_types = [inp["type"] for inp in inputs]
            return f"{event_name}({','.join(input_types)})"

    raise ValueError(f"Event '{event_name}' not found in ABI")


def get_event_topic(event_signature: str) -> str:
    """
    Compute the keccak256 topic hash for an event signature.

    Args:
        event_signature: Event signature string (e.g. "Transfer(address,address,uint256)")

    Returns:
        Topic hash as hex string with 0x prefix
    """
    return Web3.keccak(text=event_signature).hex()


def get_function_signature(abi: List[Dict[str, Any]], function_name: str) -> str:
    """
    Get the function signature for a given function name from ABI.

    Args:
        abi: Contract ABI
        function_name: Name of the function

    Returns:
        Function signature string
    """
    for item in abi:
        if item.get("type") == "function" and item.get("name") == function_name:
            inputs = item.get("inputs", [])
            input_types = [inp["type"] for inp in inputs]
            return f"{function_name}({','.join(input_types)})"

    raise ValueError(f"Function '{function_name}' not found in ABI")


if __name__ == "__main__":
    # Example usage
    abi = load_abi_from_file("examples/abis/erc20.json")
    event_sig = get_event_signature(abi, "Transfer")
    func_sig = get_function_signature(abi, "transfer")
    print(f"Event signature: {event_sig}")
    print(f"Function signature: {func_sig}")

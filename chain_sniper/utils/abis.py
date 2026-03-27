"""
ABI utilities for loading and working with contract ABIs.
"""

import json
import os
from typing import List, Dict, Any, Union


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

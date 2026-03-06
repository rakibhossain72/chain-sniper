from typing import Any


def parse_block(block: dict | None) -> list[dict]:
    """
    Parse transactions from a block, converting all field values to their proper types.

    Args:
        block: A dictionary representing a block, or None.

    Returns:
        A list of parsed and type-converted transaction dictionaries.
    """
    if not block:
        return []

    txs = []
    for tx in block.get("transactions", []):
        if isinstance(tx, dict):
            txs.append(_convert_tx_types(tx))
        else:
            txs.append(tx)
    return txs


def _convert_tx_types(tx: dict) -> dict:
    """
    Convert transaction fields to their appropriate Python types.
    Handles hex strings, booleans, integers, and nested structures.
    """
    converted = {}
    for key, value in tx.items():
        converted[key] = _convert_value(key, value)
    return converted


def _convert_value(key: str, value: Any) -> Any:
    """Recursively convert a value based on its key name and content."""
    if value is None:
        return None

    # Recursively handle nested dicts
    if isinstance(value, dict):
        return {k: _convert_value(k, v) for k, v in value.items()}

    # Recursively handle lists
    if isinstance(value, list):
        return [_convert_value(key, item) for item in value]

    # Hex string fields → int
    HEX_INT_FIELDS = {
        "blockNumber", "transactionIndex", "nonce", "gas",
        "gasPrice", "gasUsed", "value", "maxFeePerGas",
        "maxPriorityFeePerGas", "chainId", "type", "v",
    }
    if key in HEX_INT_FIELDS and isinstance(value, str) and value.startswith("0x"):
        return int(value, 16)

    # Boolean strings
    if isinstance(value, str):
        if value.lower() == "true":
            return True
        if value.lower() == "false":
            return False

    # Numeric strings
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            pass
        try:
            return float(value)
        except ValueError:
            pass

    return value
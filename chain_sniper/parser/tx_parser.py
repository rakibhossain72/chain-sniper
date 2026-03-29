"""
Transaction parser for decoding transaction input data.
"""

from web3 import Web3
from web3.exceptions import ABIFunctionNotFound
import json
from typing import Optional, Tuple, Dict, Any, Union
from functools import lru_cache


class TransactionParser:
    """Parser for decoding Ethereum transaction input data."""

    def __init__(self):
        self._w3 = Web3()

    @lru_cache(maxsize=256)
    def _get_contract(self, abi_key: str, contract_address: Optional[str]):
        """Returns a cached contract object."""
        abi = json.loads(abi_key)
        address = (
            self._w3.to_checksum_address(contract_address)
            if contract_address
            else None
        )
        return self._w3.eth.contract(address=address, abi=abi)

    @lru_cache(maxsize=512)
    def _normalize_abi(self, raw: str) -> str:
        """Normalize ABI to canonical JSON string."""
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValueError("Invalid ABI JSON string") from exc

        if isinstance(parsed, dict):
            parsed = [parsed] if "type" in parsed else list(parsed.values())

        if not isinstance(parsed, list):
            raise ValueError(
                "ABI must be a list of function/event definitions"
            )

        return json.dumps(parsed, separators=(",", ":"), sort_keys=True)

    def _selector(self, tx_input: str) -> str:
        """Returns the 4-byte selector string."""
        return tx_input[:10]

    def decode_input(
        self,
        tx_input: Union[str, bytes],
        abi: Union[list, str, dict],
        contract_address: Optional[str] = None,
    ) -> Tuple[Optional[str], Optional[Dict[str, Any]], Optional[str]]:
        """
        Decode transaction input data using the provided ABI.

        Args:
            tx_input: Hex string (0x-prefixed) or raw bytes
            abi: Contract ABI (list, JSON string, or dict)
            contract_address: Optional checksum address

        Returns:
            Tuple of (function_name, decoded_args, error_message)
        """
        # Normalize tx_input
        if isinstance(tx_input, (bytes, bytearray, memoryview)):
            tx_input = tx_input.hex()
        if not tx_input.startswith("0x"):
            tx_input = "0x" + tx_input

        # Normalize ABI
        if isinstance(abi, list):
            raw_abi = json.dumps(abi, separators=(",", ":"), sort_keys=True)
        elif isinstance(abi, dict):
            raw_abi = json.dumps(abi, separators=(",", ":"), sort_keys=True)
        else:
            raw_abi = abi

        try:
            abi_key = self._normalize_abi(raw_abi)
        except ValueError as exc:
            return None, None, str(exc)

        # Get cached contract
        try:
            contract = self._get_contract(abi_key, contract_address)
        except Exception as exc:
            return None, None, f"Contract instantiation error: {exc}"

        # Decode
        try:
            func_obj, decoded_args = contract.decode_function_input(tx_input)
            return func_obj.fn_name, dict(decoded_args), None

        except ABIFunctionNotFound:
            sel = self._selector(tx_input)
            return None, None, (
                f"Function with selector {sel} not found in ABI"
            )
        except ValueError as exc:
            msg = str(exc)
            if "Could not find any function with matching selector" in msg:
                return None, None, (
                    f"selector {self._selector(tx_input)} not in ABI"
                )
            return None, None, f"ValueError: {msg}"
        except Exception as exc:
            return None, None, f"Unexpected error: {exc}"

    def cache_info(self) -> Dict[str, Any]:
        """Returns cache statistics."""
        return {
            "abi_normalization": self._normalize_abi.cache_info()._asdict(),
            "contract_objects": self._get_contract.cache_info()._asdict(),
        }

    def clear_caches(self) -> None:
        """Clear all cached entries."""
        self._normalize_abi.cache_clear()
        self._get_contract.cache_clear()

    def parse_tx(self, tx: dict) -> dict:
        """Parse transaction and extract useful fields."""
        return {
            "hash": tx.get("hash"),
            "from": tx.get("from"),
            "to": tx.get("to"),
            "value": tx.get("value"),
            "input": tx.get("input"),
            "gas": tx.get("gas"),
            "gasPrice": tx.get("gasPrice"),
            "nonce": tx.get("nonce"),
            "blockNumber": tx.get("blockNumber"),
            "blockHash": tx.get("blockHash"),
            "transactionIndex": tx.get("transactionIndex"),
        }

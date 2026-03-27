"""
Predefined contract definitions with ABIs and addresses.
"""

import os
from typing import Dict, List, Any
from chain_sniper.utils.abis import load_abi_from_file


class ContractRegistry:
    """Registry for commonly used contracts."""

    def __init__(self):
        self._contracts: Dict[str, Dict[str, Any]] = {}

    def register_contract(
        self, name: str, abi: List[Dict[str, Any]], addresses: Dict[str, str]
    ) -> None:
        """
        Register a contract with its ABI and network addresses.

        Args:
            name: Contract name (e.g., "ERC20", "USDT")
            abi: Contract ABI
            addresses: Dict mapping network names to addresses
        """
        self._contracts[name] = {"abi": abi, "addresses": addresses}

    def get_abi(self, name: str) -> List[Dict[str, Any]]:
        """Get ABI for a registered contract."""
        if name not in self._contracts:
            raise ValueError(f"Contract '{name}' not found")
        return self._contracts[name]["abi"]

    def get_address(self, name: str, network: str = "mainnet") -> str:
        """Get address for a registered contract on a specific network."""
        if name not in self._contracts:
            raise ValueError(f"Contract '{name}' not found")
        addresses = self._contracts[name]["addresses"]
        if network not in addresses:
            raise ValueError(f"Network '{network}' not found for contract '{name}'")
        return addresses[network]


# Global registry instance
registry = ContractRegistry()

# Register common contracts
try:
    # ERC20 standard ABI
    erc20_abi_path = os.path.join(os.path.dirname(__file__), "abis", "erc20.json")
    erc20_abi = load_abi_from_file(erc20_abi_path)

    # Register ERC20 standard
    registry.register_contract("ERC20", erc20_abi, {})

    # Register specific tokens
    registry.register_contract(
        "USDT_BSC", erc20_abi, {"mainnet": "0x55d398326f99059fF775485246999027B3197955"}
    )

    registry.register_contract(
        "USDC_ETH", erc20_abi, {"mainnet": "0xA0b86a33E6441e88C5c5Ae8f1c8bC0F9F1b8C6F8"}
    )

except FileNotFoundError:
    # ABI file not found, skip registration
    pass


def get_contract_abi(name: str) -> List[Dict[str, Any]]:
    """Convenience function to get contract ABI."""
    return registry.get_abi(name)


def get_contract_address(name: str, network: str = "mainnet") -> str:
    """Convenience function to get contract address."""
    return registry.get_address(name, network)

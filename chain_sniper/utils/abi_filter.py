"""
Shared ABI filtering and decoding logic for listeners.
"""
import json
from typing import List, Dict, Any, Optional, Tuple
from web3 import Web3
from chain_sniper.parser.log_decoder import LogDecoder


class ABIFilterRegistry:
    """
    Registry for managing ABI-based filtering and decoding.

    Handles the mapping of (address, topic) -> ABI for automatic log decoding.
    """

    def __init__(self):
        self._abi_map: Dict[
            Tuple[Optional[str], Optional[str]], List[Dict[str, Any]]
        ] = {}
        self._log_decoder = LogDecoder()

    def register_abi_filter(
        self,
        abi: List[Dict[str, Any]] | str,
        address: str | List[str] | None = None,
        event_name: str | None = None,
        topics: List[str | List[str] | None] | None = None,
    ) -> List[str] | None:
        """
        Register an ABI filter for decoding logs.

        Args:
            abi: Contract ABI as list or JSON string
            address: Contract address (optional)
            event_name: Event name to filter (optional)
            topics: Raw topics to filter (optional)

        Returns:
            Generated topics if event_name provided, None otherwise
        """
        # Parse ABI if it's a JSON string
        if isinstance(abi, str):
            abi = json.loads(abi)

        generated_topics = None

        if event_name and not topics:
            # Generate topics from ABI + event_name

            w3 = Web3()
            contract = w3.eth.contract(abi=abi)
            event = getattr(contract.events, event_name)()
            generated_topics = [event.topic]

        # Handle address normalization - support both single address and list
        if address and isinstance(address, str):
            addresses = [address]
        elif address and isinstance(address, list):
            addresses = address
        else:
            addresses = [None]  # No address filter

        # Store ABI mapping for decoding
        for addr in addresses:
            addr_lower = addr.lower() if addr else None

            if generated_topics:
                for topic in generated_topics:
                    # Convert HexBytes to string if needed
                    if hasattr(topic, 'hex'):
                        topic = topic.hex()
                    elif isinstance(topic, bytes):
                        topic = topic.hex()
                    if isinstance(topic, str):
                        self._abi_map[(addr_lower, topic)] = abi
            elif topics:
                # Handle raw topics
                for topic in topics:
                    # Convert HexBytes to string if needed
                    if hasattr(topic, 'hex'):
                        topic = topic.hex()
                    elif isinstance(topic, bytes):
                        topic = topic.hex()
                    if isinstance(topic, str):
                        self._abi_map[(addr_lower, topic)] = abi
                    elif isinstance(topic, list):
                        # Handle nested OR lists
                        for sub_topic in topic:
                            # Convert HexBytes to string if needed
                            if hasattr(sub_topic, 'hex'):
                                sub_topic = sub_topic.hex()
                            elif isinstance(sub_topic, bytes):
                                sub_topic = sub_topic.hex()
                            if isinstance(sub_topic, str):
                                self._abi_map[(addr_lower, sub_topic)] = abi
            else:
                # No specific topics - store for address-only matching
                self._abi_map[(addr_lower, None)] = abi

        return generated_topics

    def decode_log(self, log: Dict[str, Any]) -> Dict[str, Any]:
        """
        Decode a log using registered ABIs.

        Args:
            log: Raw log dictionary

        Returns:
            Decoded log if ABI found, otherwise original log
        """
        address = log.get("address")
        address_lower = address.lower() if address else None
        topics = log.get("topics", [])

        if topics:
            topic = topics[0]
            # Convert HexBytes to string if needed
            if hasattr(topic, 'hex'):
                topic = topic.hex()
            elif isinstance(topic, bytes):
                topic = topic.hex()
            if not str(topic).startswith("0x"):
                topic = "0x" + str(topic)
            # Try exact match
            abi = self._abi_map.get((address_lower, topic))
            if abi:
                return self._log_decoder.decode_log(log, abi)
            # Try address only
            abi = self._abi_map.get((address_lower, None))
            if abi:
                return self._log_decoder.decode_log(log, abi)

        return log

    def decode_transaction(self, tx: Dict[str, Any]) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """
        Decode a transaction using registered ABIs.

        Args:
            tx: Raw transaction dictionary

        Returns:
            Tuple of (function_name, arguments_dict) if matched, otherwise (None, None)
        """
        if not tx.get("input") or tx["input"] == "0x":
            return None, None
            
        address = tx.get("to")
        address_lower = address.lower() if address else None
        
        # Try address specific mapping first
        abi = self._abi_map.get((address_lower, None))
        
        # Try fallback matching
        abis_to_try = []
        if abi:
            abis_to_try.append(abi)
        else:
            # Try all unique ABIs registered
            for stored_abi in self._abi_map.values():
                if stored_abi not in abis_to_try:
                    abis_to_try.append(stored_abi)
                    
        w3 = Web3()
        for test_abi in abis_to_try:
            try:
                contract = w3.eth.contract(abi=test_abi)
                func_obj, args = contract.decode_function_input(tx["input"])
                return func_obj.fn_name, args
            except Exception:
                continue
                
        return None, None

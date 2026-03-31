import logging
import json
from web3 import Web3

logger = logging.getLogger(__name__)


class LogDecoder:
    """
    Decodes Ethereum smart contract logs.
    If an ABI is provided, it will attempt to match the log
    to the contract events and decode the data/topics into readable parameters.
    """
    def __init__(self, w3: Web3 = None) -> None:
        # We can use a disconnected Web3 instance just for decoding logic
        self.w3 = w3 or Web3()
        self._contract_cache = {}

    def decode_log(self, log: dict, abi=None) -> dict:
        """
        Attempts to decode an Ethereum log using the provided ABI.
        Returns the original log if no ABI is provided or decoding fails.
        """
        if not abi:
            return log

        try:
            # We convert ABI to JSON string to use as a hashable cache key
            if isinstance(abi, list):
                abi_key = json.dumps(abi, sort_keys=True)
            else:
                abi_key = str(abi)

            if abi_key not in self._contract_cache:
                if isinstance(abi, str):
                    abi = json.loads(abi)
                self._contract_cache[abi_key] = self.w3.eth.contract(abi=abi)

            contract = self._contract_cache[abi_key]

            event_names = [
                item.get('name') for item in contract.abi
                if item.get('type') == 'event' and item.get('name')
            ]

            for event_name in event_names:
                try:
                    event = getattr(contract.events, event_name)()
                    # process_log attempts to match topic[0]
                    decoded = event.process_log(log)

                    return dict(decoded)
                except Exception:
                    continue

        except Exception as e:
            logger.debug(f"Failed to decode log with the provided ABI: {e}")

        # Fallback to returning untouched raw log
        return log


# Provide a module-level singleton instance for convenience
_default_decoder = LogDecoder()


def parse_log(log: dict, abi=None) -> dict:
    """
    Parses a log dictionary.
    If ABI is provided, will return a decoded log dictionary.
    """
    return _default_decoder.decode_log(log, abi)

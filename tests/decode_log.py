from web3 import Web3
from web3._utils.events import get_event_data

event_abi = {
    "anonymous": False,
    "inputs": [
        {"indexed": True, "name": "from", "type": "address"},
        {"indexed": True, "name": "to", "type": "address"},
        {"indexed": False, "name": "value", "type": "uint256"},
    ],
    "name": "Transfer",
    "type": "event",
}

log = {
    "address": "0x55d398326f99059ff775485246999027b3197955",
    "topics": [
        "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
        "0x00000000000000000000000028e2ea090877bf75740558f6bfb36a5ffee9e9df",
        "0x000000000000000000000000b300000b72deaeb607a12d5f54773d1c19c7028d",
    ],
    "data":
        "0x00000000000000000000000000000000000000000000002338176da92ba8c8ad",
    "blockNumber": "0x54e70b2",
    "transactionHash":
        "0xef619cb54c86df981f8df425ef3f521fc7bd1881beaea5d8bdc369c6c5d5db98",
    "transactionIndex": "0x1",
    "blockHash":
        "0xef26c2bfb39a25883e41e83b2944fb0e0942c6492319362a23f9e30b028edee6",
    "blockTimestamp": "0x69c669db",
    "logIndex": "0xa",
    "removed": False,
}

w3 = Web3()

decoded = get_event_data(w3.codec, event_abi, log)

print(decoded["args"])

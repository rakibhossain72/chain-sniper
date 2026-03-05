def parse_block(block):

    txs = []

    for tx in block.get("transactions", []):
        txs.append(tx)

    return txs

import json
import redis

def push_rule(rule_type: str, rule_data: dict):
    """
    Pushes a new dynamic rule to the running 'chain-sniper' bot via Redis Pub/Sub.
    """
    try:
        # Update redis URL as needed
        r = redis.Redis(host='localhost', port=6379, db=0)
        
        # Build the payload
        payload = rule_data.copy()
        payload["type"] = rule_type
        
        # Publish to the default channel 'sniper_rules'
        data_str = json.dumps(payload)
        r.publish('sniper_rules', data_str)
        
        print(f"Successfully pushed rule: {data_str}")
    except Exception as e:
        print(f"Failed to push rule: {e}")

if __name__ == "__main__":
    import sys
    
    # Simple CLI handling just as an example
    action = sys.argv[1] if len(sys.argv) > 1 else 'log'
    
    if action == 'log':
        print("Pushing a log rule looking for > 1500 amount...")
        push_rule('log', {
            "address": "0x55d398326f99059fF775485246999027B3197955",
            "target_topic": "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
        })
    elif action == 'tx':
        print("Pushing a tx rule looking for interactions with a specific address...")
        push_rule('tx', {
            # "to": "0x0000000000000000000000000000000000001000",
            "value": {"_op": "$lt", "_value": 1000}
        })
    else:
        print("Usage: python push_redis_rule.py [log|tx]")

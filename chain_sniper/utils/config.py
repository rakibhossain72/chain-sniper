"""
Configuration utilities for Chain Sniper.
"""

import os
import dotenv


def load_config() -> dict:
    """
    Load configuration from environment variables.

    Returns:
        dict: Configuration dictionary with common settings.
    """
    dotenv.load_dotenv()

    return {
        "rpc_url": os.getenv("RPC_URL"),
        "redis_url": os.getenv("REDIS_URL", "redis://localhost:6379"),
        "log_level": os.getenv("LOG_LEVEL", "INFO"),
    }


def get_rpc_url() -> str:
    """Get RPC URL from environment or config."""
    config = load_config()
    rpc_url = config["rpc_url"]
    if not rpc_url:
        raise ValueError("RPC_URL environment variable is required")
    return rpc_url

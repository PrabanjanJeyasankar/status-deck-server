# ---
# File: app/utils/redis_utils.py
# Purpose: Redis utilities for publishing messages to channels asynchronously
# ---

from redis import asyncio as aioredis
import json
import os

# Redis connection URL and client initialization for async publishing
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost")
redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)

# ---
# Publish a dictionary payload as a JSON string to a specified Redis channel.
# Handles exceptions gracefully and logs failures for visibility during development.
# ---
async def publish_to_redis(channel: str, payload: dict):
    message = json.dumps(payload)
    try:
        subscribers = await redis_client.publish(channel, message)
        # print(f"[REDIS] Published to {channel} | Subscribers: {subscribers}")
    except Exception as e:
        print(f"[REDIS] Failed to publish to {channel}: {e}")

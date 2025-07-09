# ---
# File: app/websocket/redis_listener.py
# Purpose: Redis subscriber to broadcast monitor updates to connected WS clients per org
#          for distributed WS-enabled FastAPI servers (Status Deck 2.0).
# ---

from redis import asyncio as aioredis
import os
import json
import logging
from app.websocket.monitor_updates import manager

# Configure module-level logger
logger = logging.getLogger(__name__)

# ---
# Determine Redis connection URL with proper priority:
# 1) REDIS_URL (internal Railway connection)
# 2) REDIS_PUBLIC_URL (if internal is not set)
# 3) "redis://localhost:6379" for local development fallback
# ---
REDIS_URL = os.getenv("REDIS_URL") or os.getenv("REDIS_PUBLIC_URL") or "redis://localhost:6379"

async def redis_listener():
    """
    Subscribes to 'monitor_updates_channel' in Redis and
    forwards messages to connected WebSocket clients per organization.
    """
    redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("monitor_updates_channel")
    logger.info("[Redis Listener] Subscribed to 'monitor_updates_channel'")

    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    organization_id = data.get("organization_id")
                    if organization_id:
                        logger.info(f"[Redis Listener] Received update for {organization_id}")
                        await manager.broadcast(organization_id, data)
                    else:
                        logger.warning(f"[Redis Listener] Missing organization_id: {data}")
                except Exception as e:
                    logger.error(f"[Redis Listener] Failed to process message: {e}")
    except Exception as e:
        logger.error(f"[Redis Listener] Listener error: {e}")
    finally:
        await pubsub.unsubscribe("monitor_updates_channel")
        await pubsub.close()
        await redis_client.close()
        logger.info("[Redis Listener] Cleanly shut down")

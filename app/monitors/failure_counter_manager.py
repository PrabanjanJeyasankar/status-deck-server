# app/monitors/failure_counter_manager.py

from redis import asyncio as aioredis
from datetime import datetime, timezone
import json

redis_client = aioredis.from_url("redis://localhost", decode_responses=True)

KEY_PREFIX = "monitor_failure_count:"
FAILED_PINGS_KEY_PREFIX = "monitor_failed_pings:"
FIRST_DOWN_KEY_PREFIX = "monitor_first_down_timestamp:"
CRITICAL_THRESHOLD = 12

async def increment_failure_counter(monitor_id: str):
    key = f"{KEY_PREFIX}{monitor_id}"
    count = await redis_client.get(key)
    if count is None:
        await set_first_down_timestamp(monitor_id)
        count = 0
    else:
        count = int(count)

    # Stop at threshold, don't increment further
    if count >= CRITICAL_THRESHOLD:
        print(f"[DETECT] Monitor {monitor_id} is already at CRITICAL. Not incrementing further until resolved.")
        return CRITICAL_THRESHOLD

    new_count = await redis_client.incr(key)
    print(f"[DETECT] Monitor {monitor_id} consecutive count: {new_count}")
    return int(new_count)

async def reset_failure_counter(monitor_id: str):
    await redis_client.delete(f"{KEY_PREFIX}{monitor_id}")
    await clear_failed_pings(monitor_id)
    await clear_first_down_timestamp(monitor_id)
    print(f"[RESET] Failure counter and failed pings reset for {monitor_id}.")

async def get_failure_counter(monitor_id: str) -> int:
    count = await redis_client.get(f"{KEY_PREFIX}{monitor_id}")
    return int(count) if count else 0

async def set_first_down_timestamp(monitor_id: str):
    # Use timezone-aware UTC now
    await redis_client.set(
        f"{FIRST_DOWN_KEY_PREFIX}{monitor_id}",
        datetime.now(timezone.utc).isoformat()
    )

async def get_first_down_timestamp(monitor_id: str) -> str:
    return await redis_client.get(f"{FIRST_DOWN_KEY_PREFIX}{monitor_id}")

async def clear_first_down_timestamp(monitor_id: str):
    await redis_client.delete(f"{FIRST_DOWN_KEY_PREFIX}{monitor_id}")

async def add_failed_ping(monitor_id: str, ping_data: dict):
    await redis_client.rpush(f"{FAILED_PINGS_KEY_PREFIX}{monitor_id}", json.dumps(ping_data))

async def get_failed_pings(monitor_id: str) -> list[dict]:
    data = await redis_client.lrange(f"{FAILED_PINGS_KEY_PREFIX}{monitor_id}", 0, -1)
    return [json.loads(item) for item in data]

async def clear_failed_pings(monitor_id: str):
    await redis_client.delete(f"{FAILED_PINGS_KEY_PREFIX}{monitor_id}")

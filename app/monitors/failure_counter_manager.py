# ---
# File: app/monitors/failure_counter_manager.py
# Purpose: Manage monitor failure counters and failed ping logs using Redis.
# Used for incident detection, tracking consecutive failures, and clearing state upon resolution.
# ---

from redis import asyncio as aioredis
from datetime import datetime, timezone
import json
import os

# ---
# Initialize Redis client using REDIS_URL for Railway compatibility,
# fallback to localhost for local development.
# ---
redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
redis_client = aioredis.from_url(redis_url, decode_responses=True)

# Key prefixes for Redis storage organization
KEY_PREFIX = "monitor_failure_count:"
FAILED_PINGS_KEY_PREFIX = "monitor_failed_pings:"
FIRST_DOWN_KEY_PREFIX = "monitor_first_down_timestamp:"

# Threshold after which a monitor is considered critically down
CRITICAL_THRESHOLD = 12

# ---
# Increment the failure counter for a monitor in Redis.
# Initializes first down timestamp if this is the first failure.
# Stops incrementing once the critical threshold is reached.
# Returns the current failure count after increment.
# ---
async def increment_failure_counter(monitor_id: str):
    key = f"{KEY_PREFIX}{monitor_id}"
    count = await redis_client.get(key)
    if count is None:
        await set_first_down_timestamp(monitor_id)
        count = 0
    else:
        count = int(count)

    if count >= CRITICAL_THRESHOLD:
        print(f"[DETECT] Monitor {monitor_id} is already at CRITICAL. Not incrementing further until resolved.")
        return CRITICAL_THRESHOLD

    new_count = await redis_client.incr(key)
    print(f"[DETECT] Monitor {monitor_id} consecutive count: {new_count}")
    return int(new_count)

# ---
# Reset the failure counter, failed pings, and first down timestamp
# for a monitor upon resolution.
# ---
async def reset_failure_counter(monitor_id: str):
    await redis_client.delete(f"{KEY_PREFIX}{monitor_id}")
    await clear_failed_pings(monitor_id)
    await clear_first_down_timestamp(monitor_id)
    print(f"[RESET] Failure counter and failed pings reset for {monitor_id}.")

# ---
# Retrieve the current failure counter for a monitor.
# Returns 0 if no failures recorded yet.
# ---
async def get_failure_counter(monitor_id: str) -> int:
    count = await redis_client.get(f"{KEY_PREFIX}{monitor_id}")
    return int(count) if count else 0

# ---
# Set the first timestamp when a monitor went down in UTC ISO format.
# ---
async def set_first_down_timestamp(monitor_id: str):
    await redis_client.set(
        f"{FIRST_DOWN_KEY_PREFIX}{monitor_id}",
        datetime.now(timezone.utc).isoformat()
    )

# ---
# Retrieve the first down timestamp for a monitor if it exists.
# ---
async def get_first_down_timestamp(monitor_id: str) -> str:
    return await redis_client.get(f"{FIRST_DOWN_KEY_PREFIX}{monitor_id}")

# ---
# Clear the first down timestamp for a monitor after resolution.
# ---
async def clear_first_down_timestamp(monitor_id: str):
    await redis_client.delete(f"{FIRST_DOWN_KEY_PREFIX}{monitor_id}")

# ---
# Append a failed ping record for a monitor to its Redis list.
# Used to collect failure details for incident root cause analysis.
# ---
async def add_failed_ping(monitor_id: str, ping_data: dict):
    await redis_client.rpush(f"{FAILED_PINGS_KEY_PREFIX}{monitor_id}", json.dumps(ping_data))

# ---
# Retrieve all failed pings for a monitor, parsed into dicts.
# ---
async def get_failed_pings(monitor_id: str) -> list[dict]:
    data = await redis_client.lrange(f"{FAILED_PINGS_KEY_PREFIX}{monitor_id}", 0, -1)
    return [json.loads(item) for item in data]

# ---
# Clear all stored failed pings for a monitor after incident resolution.
# ---
async def clear_failed_pings(monitor_id: str):
    await redis_client.delete(f"{FAILED_PINGS_KEY_PREFIX}{monitor_id}")

# app/monitors/auto_incident_monitor.py

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timezone, timedelta
import asyncio
import httpx
import json
import logging

from app.db import db as database
from app.incidents.incident_services import IncidentService
from app.utils.status_utils import determine_monitor_status
from app.utils.redis_utils import publish_to_redis
from app.monitors.failure_counter_manager import add_failed_ping, reset_failure_counter

logging.getLogger("httpx").setLevel(logging.WARNING)

scheduler = AsyncIOScheduler()
monitor_failure_counts = {}

async def safe_create_monitoring_result(data, retries=3, delay=2):
    monitor_id = data.get("monitorId")

    # ✅ Check if monitor exists before insertion
    if monitor_id:
        monitor_exists = await database.monitor.find_unique(where={"id": monitor_id})
        if not monitor_exists:
            print(f"[DB] Skipping MonitoringResult insertion: Monitor {monitor_id} does not exist.")
            return

    for attempt in range(retries):
        try:
            await database.monitoringresult.create(data)
            print(f"[DB] MonitoringResult created successfully for monitor {monitor_id}.")
            return
        except Exception as e:
            if "ForeignKeyViolationError" in str(e):
                print(f"[DB] FK violation on MonitoringResult for monitor {monitor_id}, retrying in {delay}s (Attempt {attempt + 1}/{retries})")
                await asyncio.sleep(delay)
                delay *= 2
            else:
                print(f"[DB] Unexpected error while creating MonitoringResult for monitor {monitor_id}: {e}")
                raise

    print(f"[DB] Failed to create MonitoringResult for monitor {monitor_id} after {retries} attempts.")

async def ping_monitor(monitor):
    try:
        headers = {}
        if monitor.headers:
            header_list = json.loads(monitor.headers) if isinstance(monitor.headers, str) else monitor.headers
            headers = {header["key"]: header["value"] for header in header_list}

        timeout_seconds = monitor.timeout / 1000 if monitor.timeout else 5

        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            start_time = datetime.now(timezone.utc)
            response = await client.request(method=monitor.method, url=monitor.url, headers=headers)
            end_time = datetime.now(timezone.utc)
            response_time_ms = int((end_time - start_time).total_seconds() * 1000)

            if response.is_error:
                status = "DOWN"
                error_message = f"HTTP error {response.status_code}"
            else:
                status = determine_monitor_status(
                    response.status_code,
                    response_time_ms,
                    monitor.degradedThreshold,
                )
                error_message = None

            print(f"[PING] {monitor.id} | {monitor.name} | {monitor.url} | {status} | {response_time_ms}ms")

            await safe_create_monitoring_result({
                "monitorId": monitor.id,
                "checkedAt": datetime.now(timezone.utc),
                "status": status,
                "responseTimeMs": response_time_ms,
                "httpStatusCode": response.status_code,
                "error": error_message,
            })

            if status == "DOWN":
                await add_failed_ping(monitor.id, {
                    "checkedAt": datetime.now(timezone.utc).isoformat(),
                    "responseTimeMs": response_time_ms,
                    "httpStatusCode": response.status_code,
                    "error": error_message,
                })

            await IncidentService.handle_monitor_status_change(monitor.id, status)
            await publish_monitor_update(monitor.id, status, response_time_ms, response.status_code, error_message)

    except Exception as e:
        print(f"[PING] {monitor.id} | {monitor.name} | {monitor.url} | DOWN | Exception: {e}")
        await safe_create_monitoring_result({
            "monitorId": monitor.id,
            "checkedAt": datetime.now(timezone.utc),
            "status": "DOWN",
            "responseTimeMs": None,
            "httpStatusCode": None,
            "error": str(e),
        })
        await add_failed_ping(monitor.id, {
            "checkedAt": datetime.now(timezone.utc).isoformat(),
            "responseTimeMs": None,
            "httpStatusCode": None,
            "error": str(e),
        })
        await IncidentService.handle_monitor_status_change(monitor.id, "DOWN")
        await publish_monitor_update(monitor.id, "DOWN", None, None, str(e))

async def publish_monitor_update(monitor_id, status, response_time, status_code, error):
    monitor = await database.monitor.find_unique(
        where={"id": monitor_id},
        include={"service": {"include": {"organization": True}}},
    )
    if not monitor:
        return

    organization_id = monitor.service.organizationId if monitor.service else None
    payload = {
        "id": monitor.id,
        "name": monitor.name,
        "url": monitor.url,
        "method": monitor.method,
        "interval": monitor.interval,
        "type": monitor.type,
        "headers": monitor.headers,
        "active": monitor.active,
        "degradedThreshold": monitor.degradedThreshold,
        "timeout": monitor.timeout,
        "serviceId": monitor.serviceId,
        "serviceName": monitor.service.name if monitor.service else None,
        "latestResult": {
            "status": status,
            "responseTimeMs": response_time,
            "httpStatusCode": status_code,
            "checkedAt": datetime.now(timezone.utc).isoformat(),
            "error": error,
        },
    }
    await publish_to_redis("monitor_updates_channel", {
        "organization_id": organization_id,
        "type": "monitor_update",
        "payload": payload,
    })

async def schedule_existing_monitors():
    monitors = await database.monitor.find_many(where={"active": True})
    for monitor in monitors:
        scheduler.add_job(
            ping_monitor,
            trigger=IntervalTrigger(seconds=monitor.interval),
            args=[monitor],
            name=f"Monitor-{monitor.id}",
            replace_existing=True,
        )

async def listen_for_monitor_events():
    from redis import asyncio as aioredis
    redis_client = aioredis.from_url("redis://localhost", decode_responses=True)
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("monitor_created", "monitor_updated", "monitor_deleted")

    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        event_type = message["channel"]
        monitor_id = message["data"]
        if event_type in ["monitor_created", "monitor_updated"]:
            monitor = await database.monitor.find_unique(where={"id": monitor_id})
            if monitor:
                scheduler.add_job(
                    ping_monitor,
                    trigger=IntervalTrigger(seconds=monitor.interval),
                    args=[monitor],
                    name=f"Monitor-{monitor.id}",
                    replace_existing=True,
                    next_run_time=datetime.now(timezone.utc) + timedelta(seconds=5)
                )
                if event_type == "monitor_updated":
                    await reset_failure_counter(monitor_id)
        elif event_type == "monitor_deleted":
            job_id = f"Monitor-{monitor_id}"
            if scheduler.get_job(job_id):
                scheduler.remove_job(job_id)

async def main():
    await database.connect()
    await schedule_existing_monitors()
    scheduler.start()
    await listen_for_monitor_events()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("[AUTO_MONITOR] Shutting down gracefully...")

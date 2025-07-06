# monitors/routes.py

from .models import MonitorCreateRequest, MonitorResponse
from fastapi.encoders import jsonable_encoder
from fastapi import APIRouter, HTTPException
from statistics import median, quantiles
from redis import asyncio as aioredis
from datetime import datetime
from fastapi import Query
from typing import List, Optional
from app.db import db
import json

from app.monitors.failure_counter_manager import (
    clear_failed_pings,
    clear_first_down_timestamp,
    redis_client,
    KEY_PREFIX,
)

router = APIRouter(prefix="/api/services/{serviceId}/monitors", tags=["Monitors"])


redis_client = aioredis.from_url("redis://localhost", decode_responses=True)

@router.post("", response_model=MonitorResponse)
async def create_monitor(serviceId: str, data: MonitorCreateRequest):
    monitor = await db.monitor.create({
        "name": data.name,
        "url": str(data.url),
        "method": data.method,
        "interval": data.interval,
        "type": data.type,
        "headers": json.dumps(jsonable_encoder(data.headers or [])),
        "active": data.active,
        "degradedThreshold": data.degradedThreshold,
        "timeout": data.timeout,
        "serviceId": serviceId,
    })


    confirmed_monitor = await db.monitor.find_unique(where={"id": monitor.id})
    if not confirmed_monitor:
        raise HTTPException(status_code=500, detail="Monitor creation failed, could not confirm persistence.")


    await redis_client.publish("monitor_created", monitor.id)

    return MonitorResponse(
        id=monitor.id,
        name=monitor.name,
        url=monitor.url,
        method=monitor.method,
        interval=monitor.interval,
        type=monitor.type,
        headers=monitor.headers,
        active=monitor.active,
        degradedThreshold=monitor.degradedThreshold,
        timeout=monitor.timeout,
        serviceId=monitor.serviceId,
        createdAt=monitor.createdAt.isoformat(),
        updatedAt=monitor.updatedAt.isoformat(),
    )

@router.get("", response_model=List[MonitorResponse])
async def get_monitors(serviceId: str):
    monitors = await db.monitor.find_many(
        where={"serviceId": serviceId},
        order={"createdAt": "asc"}
    )
    return [
        MonitorResponse(
            id=m.id,
            name=m.name,
            url=m.url,
            method=m.method,
            interval=m.interval,
            type=m.type,
            headers=m.headers,
            active=m.active,
            degradedThreshold=m.degradedThreshold,
            timeout=m.timeout,
            serviceId=m.serviceId,
            createdAt=m.createdAt.isoformat(),
            updatedAt=m.updatedAt.isoformat(),
        )
        for m in monitors
    ]

@router.get("/{monitorId}", response_model=MonitorResponse)
async def get_monitor(serviceId: str, monitorId: str):
    monitor = await db.monitor.find_unique(where={"id": monitorId, "serviceId": serviceId})
    if not monitor:
        raise HTTPException(status_code=404, detail="Monitor not found")
    return MonitorResponse(
        id=monitor.id,
        name=monitor.name,
        url=monitor.url,
        method=monitor.method,
        interval=monitor.interval,
        type=monitor.type,
        headers=monitor.headers,
        active=monitor.active,
        degradedThreshold=monitor.degradedThreshold,
        timeout=monitor.timeout,
        serviceId=monitor.serviceId,
        createdAt=monitor.createdAt.isoformat(),
        updatedAt=monitor.updatedAt.isoformat(),
    )


@router.delete("/{monitorId}")
async def delete_monitor(serviceId: str, monitorId: str):
    monitor = await db.monitor.find_unique(where={"id": monitorId, "serviceId": serviceId})
    if not monitor:
        raise HTTPException(status_code=404, detail="Monitor not found")
    await db.monitor.delete(where={"id": monitorId})

    # Clean up Redis keys
    await redis_client.delete(f"{KEY_PREFIX}{monitorId}")
    await clear_failed_pings(monitorId)
    await clear_first_down_timestamp(monitorId)
    print(f"[CLEANUP] Redis keys deleted for monitor {monitorId}")

    #  publish to Redis so the worker can remove this monitor from scheduler
    await redis_client.publish("monitor_deleted", monitorId)

    return {"success": True, "message": "Monitor deleted successfully"}

@router.get("/{monitorId}/results")
async def get_monitor_results(
    serviceId: str,
    monitorId: str,
    limit: int = Query(100, le=500),
    from_date: Optional[str] = None,
    to_date: Optional[str] = None
):
    monitor = await db.monitor.find_unique(where={"id": monitorId, "serviceId": serviceId})
    if not monitor:
        raise HTTPException(status_code=404, detail="Monitor not found.")

    filters = {"monitorId": monitorId}
    if from_date:
        filters["checkedAt"] = {"gte": datetime.fromisoformat(from_date)}
    if to_date:
        filters["checkedAt"] = {"lte": datetime.fromisoformat(to_date)}

    results = await db.monitoringresult.find_many(
        where=filters,
        order={"checkedAt": "desc"},
        take=limit
    )

    return [
        {
            "id": r.id,
            "checkedAt": r.checkedAt.astimezone().strftime("%Y-%m-%d %I:%M %p"),
            "status": r.status,
            "responseTimeMs": r.responseTimeMs,
            "httpStatusCode": r.httpStatusCode,
            "error": r.error,
        }
        for r in results
    ]



@router.get("/{monitorId}/stats")
async def get_monitor_stats(
    serviceId: str,
    monitorId: str,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None
):
    monitor = await db.monitor.find_unique(where={"id": monitorId, "serviceId": serviceId})
    if not monitor:
        raise HTTPException(status_code=404, detail="Monitor not found.")

    filters = {"monitorId": monitorId}
    if from_date:
        filters["checkedAt"] = {"gte": datetime.fromisoformat(from_date)}
    if to_date:
        filters.setdefault("checkedAt", {}).update({"lte": datetime.fromisoformat(to_date)})

    results = await db.monitoringresult.find_many(where=filters, order={"checkedAt": "asc"})

    total_pings = len(results)
    if total_pings == 0:
        return {
            "uptime": 0,
            "failures": 0,
            "lastPing": None,
            "totalPings": 0,
            "p50": None,
            "p75": None,
            "p90": None,
            "p95": None,
            "p99": None,
            "historyGraph": [],
        }

    fails = sum(1 for r in results if r.status == "DOWN")
    uptime_percentage = round(((total_pings - fails) / total_pings) * 100, 2)

    response_times = [r.responseTimeMs for r in results if r.responseTimeMs is not None]
    response_times_sorted = sorted(response_times)

    p50 = median(response_times_sorted) if response_times_sorted else None
    p75, p90, p95, p99 = [None]*4
    if response_times_sorted:
        qs = quantiles(response_times_sorted, n=100)
        p75 = qs[74]
        p90 = qs[89]
        p95 = qs[94]
        p99 = qs[98]

    last_ping = results[-1].checkedAt.astimezone().strftime("%Y-%m-%d %I:%M %p")

    history_graph = [
        {"timestamp": r.checkedAt.astimezone().isoformat(), "status": r.status}
        for r in results
    ]

    return {
        "uptime": uptime_percentage,
        "failures": fails,
        "lastPing": last_ping,
        "totalPings": total_pings,
        "p50": p50,
        "p75": p75,
        "p90": p90,
        "p95": p95,
        "p99": p99,
        "historyGraph": history_graph,
    }

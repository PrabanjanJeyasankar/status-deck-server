# ---
# File: app/health/routes.py
# Purpose: Health endpoints for service readiness and dependency checks
# ---

from fastapi import APIRouter
from redis import asyncio as aioredis
import os
import time

from app.db import db

START_TIME = time.time()

router = APIRouter(prefix="/api/v1/health", tags=["Health"])


async def check_database() -> dict:
    detail = {"status": "ok"}
    try:
        is_connected = getattr(db, "is_connected", lambda: False)()
        if not is_connected:
            await db.connect()

        if hasattr(db, "execute_raw"):
            await db.execute_raw("SELECT 1")
        elif hasattr(db, "query_raw"):
            await db.query_raw("SELECT 1")
    except Exception as exc:
        detail["status"] = "error"
        detail["error"] = str(exc)
    return detail


async def check_redis() -> dict:
    detail = {"status": "ok"}
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    try:
        client = aioredis.from_url(redis_url, decode_responses=True)
        pong = await client.ping()
        await client.close()
        if pong is not True:
            detail["status"] = "error"
            detail["error"] = f"Unexpected PING response: {pong}"
    except Exception as exc:
        detail["status"] = "error"
        detail["error"] = str(exc)
    return detail


@router.get("")
async def health():
    db_status = await check_database()
    redis_status = await check_redis()

    overall = "ok"
    if db_status["status"] != "ok" or redis_status["status"] != "ok":
        overall = "degraded"

    return {
        "service": "status-deck-api",
        "status": overall,
        "uptime_seconds": int(time.time() - START_TIME),
        "checks": {
            "database": db_status,
            "redis": redis_status,
        },
    }

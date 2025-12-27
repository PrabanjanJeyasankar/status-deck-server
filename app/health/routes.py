# ---
# File: app/health/routes.py
# Purpose: Health endpoints for service readiness, dependency checks, and keep-alive monitoring
# ---

from fastapi import APIRouter
from redis import asyncio as aioredis
import os
import time

from app.db import db

# Track when the server started (for uptime calculation)
START_TIME = time.time()

router = APIRouter(prefix="/api/v1/health", tags=["Health"])


async def check_database() -> dict:
    """
    Database Health Check
    
    Verifies the PostgreSQL database connection by executing a simple query.
    Returns status "ok" if connection is successful, "error" otherwise.
    """
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
    """
    Redis Health Check
    
    Verifies the Redis connection by sending a PING command.
    Returns status "ok" if PING returns True, "error" otherwise.
    """
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
    """
    Primary Health Endpoint
    
    Comprehensive health check that verifies all critical service dependencies.
    Used by hosting platforms for readiness probes and by keep-alive service.
    
    Returns:
        - service: Application name
        - status: "ok" if all checks pass, "degraded" if any fail
        - uptime_seconds: How long the server has been running
        - checks: Individual status for each dependency (database, redis)
    
    HTTP Status Codes:
        - 200: Service is healthy (all checks passed)
        - 200: Service is degraded (some checks failed, but server is running)
    """
    db_status = await check_database()
    redis_status = await check_redis()

    # Determine overall status
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


@router.get("/keepalive")
async def keepalive_status():
    """
    Keep-Alive Statistics Endpoint
    
    Returns detailed statistics about the keep-alive service that prevents cold starts.
    Useful for monitoring and debugging the self-ping mechanism.
    
    Returns:
        - enabled: Whether keep-alive service is active
        - target_url: URL being pinged (if enabled)
        - interval_seconds: Time between pings
        - timeout_seconds: HTTP request timeout
        - statistics: Ping success/failure counts and success rate
        - uptime_seconds: Server uptime (for context)
    
    Example Response (Enabled):
        {
            "enabled": true,
            "target_url": "https://status-deck.onrender.com/health",
            "interval_seconds": 300,
            "timeout_seconds": 10,
            "statistics": {
                "total_pings": 42,
                "successful_pings": 40,
                "failed_pings": 2,
                "success_rate_percent": 95.24
            },
            "uptime_seconds": 12600
        }
    
    Example Response (Disabled):
        {
            "enabled": false,
            "reason": "KEEPALIVE_URL environment variable not set"
        }
    """
    # Import from main module to access keep-alive state
    # Note: We import here to avoid circular dependencies
    import app.main as main_module
    
    # Check if keep-alive is configured
    keepalive_url = main_module.KEEPALIVE_URL
    
    if not keepalive_url:
        return {
            "enabled": False,
            "reason": "KEEPALIVE_URL environment variable not set",
            "uptime_seconds": int(time.time() - START_TIME),
        }
    
    # Keep-alive is enabled - return detailed statistics
    total_pings = main_module._keepalive_ping_count
    total_failures = main_module._keepalive_failure_count
    total_attempts = total_pings + total_failures
    
    # Calculate success rate (avoid division by zero)
    success_rate = 0.0
    if total_attempts > 0:
        success_rate = (total_pings / total_attempts) * 100
    
    return {
        "enabled": True,
        "target_url": keepalive_url,
        "interval_seconds": main_module.KEEPALIVE_INTERVAL_SECONDS,
        "timeout_seconds": main_module.KEEPALIVE_TIMEOUT_SECONDS,
        "statistics": {
            "total_pings": total_pings,
            "successful_pings": total_pings,
            "failed_pings": total_failures,
            "success_rate_percent": round(success_rate, 2),
        },
        "uptime_seconds": int(time.time() - START_TIME),
    }

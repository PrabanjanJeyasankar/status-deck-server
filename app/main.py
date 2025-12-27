# ---
# File: app/main.py
# Purpose: FastAPI app initialization, middleware, CORS, Redis listener,
#          and router inclusion for Status Deck 2.0
# ---

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
import asyncio
import os
import httpx

from app.db import db

# Import routers for API functionality
from app.services.routes import router as services_router
from app.auth.routes import router as auth_router
from app.monitors.routes import router as monitor_router
from app.monitors.latest_results import router as monitor_latest_router
from app.monitors import org_monitors
from app.incidents import routes as incident_routes
from app.websocket import monitor_updates, incidents_ws_router
from app.websocket import redis_listener
from app.health.routes import router as health_router

# ---
# Logging Configuration
# ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---
# Keep-Alive Configuration (Cold Start Prevention)
# ---
# Purpose: Prevents hosting platforms (like Render.com) from putting the server to sleep
#          due to inactivity by periodically pinging the server's own health endpoint.
#
# Configuration via Environment Variables:
#   - KEEPALIVE_URL: Full URL to ping (e.g., https://your-app.onrender.com/health)
#                    If empty/unset, keep-alive is disabled.
#   - KEEPALIVE_INTERVAL_SECONDS: Time between pings (default: 600 = 10 minutes)
#                                  Recommended: 300-600 seconds (5-10 min)
#   - KEEPALIVE_TIMEOUT_SECONDS: HTTP request timeout (default: 10 seconds)
#
# Why This Matters:
#   Many hosting platforms spin down free-tier apps after 15 minutes of inactivity.
#   This causes "cold starts" - slow first requests after idle periods. By pinging
#   ourselves regularly, we keep the server warm and responsive.
#
# Implementation Details:
#   - Runs as a background asyncio task, isolated from main application logic
#   - Non-blocking: failures don't affect app functionality
#   - Graceful shutdown: stops cleanly when app shuts down
#   - Detailed logging for monitoring and debugging
# ---
KEEPALIVE_URL = os.environ.get("KEEPALIVE_URL", "").strip()
KEEPALIVE_INTERVAL_SECONDS = int(os.environ.get("KEEPALIVE_INTERVAL_SECONDS", "600"))
KEEPALIVE_TIMEOUT_SECONDS = int(os.environ.get("KEEPALIVE_TIMEOUT_SECONDS", "10"))

# Internal state management for keep-alive background task
_keepalive_stop_event = asyncio.Event()
_keepalive_task: asyncio.Task | None = None
_keepalive_ping_count = 0
_keepalive_failure_count = 0


async def keepalive_loop(url: str, interval_seconds: int, timeout_seconds: int) -> None:
    """
    Keep-Alive Background Task
    
    Continuously pings the specified URL at regular intervals to prevent cold starts.
    This task runs indefinitely until the application shuts down.
    
    Args:
        url: Full HTTP/HTTPS URL to ping (typically the /health endpoint)
        interval_seconds: Time to wait between ping attempts
        timeout_seconds: HTTP request timeout limit
        
    Implementation Notes:
        - Uses httpx.AsyncClient for non-blocking HTTP requests
        - Tracks success/failure statistics for monitoring
        - Logs every ping attempt with status code or error details
        - Resilient: continues running even if individual pings fail
        - Respects shutdown signals via _keepalive_stop_event
    """
    global _keepalive_ping_count, _keepalive_failure_count
    
    logger.info(
        "[KEEPALIVE] Service started | Target: %s | Interval: %ds | Timeout: %ds",
        url,
        interval_seconds,
        timeout_seconds,
    )
    
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        while not _keepalive_stop_event.is_set():
            try:
                response = await client.get(url)
                _keepalive_ping_count += 1
                
                # Log successful pings with status code
                if response.status_code == 200:
                    logger.info(
                        "[KEEPALIVE] ✓ Ping successful | Status: %s | Total pings: %d | Failures: %d",
                        response.status_code,
                        _keepalive_ping_count,
                        _keepalive_failure_count,
                    )
                else:
                    # Unexpected status code (not 200) - still counts as success but worth noting
                    logger.warning(
                        "[KEEPALIVE] ⚠ Unexpected status | Status: %s | Total pings: %d",
                        response.status_code,
                        _keepalive_ping_count,
                    )
                    
            except Exception as exc:
                # Network errors, timeouts, or other failures
                _keepalive_failure_count += 1
                logger.warning(
                    "[KEEPALIVE] ✗ Ping failed | Error: %s | Total failures: %d/%d",
                    str(exc)[:100],  # Truncate long error messages
                    _keepalive_failure_count,
                    _keepalive_ping_count + _keepalive_failure_count,
                )

            # Wait for the specified interval before next ping
            # Uses wait_for with timeout to allow graceful shutdown
            try:
                await asyncio.wait_for(
                    _keepalive_stop_event.wait(),
                    timeout=interval_seconds
                )
                # If we reach here, stop event was set - exit loop
                break
            except asyncio.TimeoutError:
                # Normal path: timeout expired, time for next ping
                continue
    
    logger.info(
        "[KEEPALIVE] Service stopped | Total pings: %d | Failures: %d",
        _keepalive_ping_count,
        _keepalive_failure_count,
    )

# ---
# Initialize FastAPI app instance
# ---
app = FastAPI()

# ---
# CORS Middleware for local and deployed frontend access
# ---
cors_env = os.environ.get("CORS_ALLOW_ORIGINS", "")
allowed_origins = [origin.strip() for origin in cors_env.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---
# Middleware: Log all incoming HTTP requests for debugging
# ---
@app.middleware("http")
async def log_cors(request: Request, call_next):
    logger.info(f"[CORS] {request.method} {request.url}")
    response = await call_next(request)
    logger.info(f"[CORS] Response Access-Control-Allow-Origin: {response.headers.get('access-control-allow-origin')}")
    return response

# ---
# Application Lifecycle Events
# ---

@app.on_event("startup")
async def startup():
    """
    Application Startup Handler
    
    Initializes all critical services and background tasks when the server starts.
    Executed once during application bootstrap.
    
    Startup Sequence:
        1. Database connection establishment
        2. Redis listener for real-time monitor updates (WebSocket broadcasting)
        3. Keep-alive service (if configured) to prevent cold starts
        
    Error Handling:
        - Database connection failures will crash the app (by design - can't run without DB)
        - Background tasks (Redis, keep-alive) run independently and won't block startup
    """
    global _keepalive_task
    
    # Step 1: Database Connection
    logger.info("[STARTUP] Connecting to database...")
    await db.connect()
    logger.info("[STARTUP] ✓ Database connected successfully")

    # Step 2: Redis Listener for Real-Time Updates
    logger.info("[STARTUP] Starting Redis listener for monitor updates...")
    asyncio.create_task(redis_listener.redis_listener())
    logger.info("[STARTUP] ✓ Redis listener task created")

    # Step 3: Keep-Alive Service (Conditional)
    if KEEPALIVE_URL:
        logger.info("[STARTUP] Keep-alive is ENABLED")
        _keepalive_task = asyncio.create_task(
            keepalive_loop(
                KEEPALIVE_URL,
                KEEPALIVE_INTERVAL_SECONDS,
                KEEPALIVE_TIMEOUT_SECONDS
            )
        )
        logger.info("[STARTUP] ✓ Keep-alive task created")
    else:
        logger.info("[STARTUP] Keep-alive is DISABLED (KEEPALIVE_URL not set)")
    
    logger.info("[STARTUP] All services initialized successfully")

@app.on_event("shutdown")
async def shutdown():
    """
    Application Shutdown Handler
    
    Gracefully stops all services and background tasks when the server is shutting down.
    Ensures clean resource cleanup to prevent data corruption or connection leaks.
    
    Shutdown Sequence:
        1. Stop keep-alive service (if running)
        2. Disconnect from database
        
    Timeout Protection:
        - Keep-alive task has 5-second grace period before forced cancellation
        - Prevents hanging shutdowns while ensuring cleanup attempts complete
    """
    global _keepalive_task
    
    # Step 1: Graceful Keep-Alive Shutdown
    if _keepalive_task:
        logger.info("[SHUTDOWN] Stopping keep-alive service...")
        _keepalive_stop_event.set()  # Signal task to stop
        
        try:
            # Wait up to 5 seconds for graceful shutdown
            await asyncio.wait_for(_keepalive_task, timeout=5)
            logger.info("[SHUTDOWN] ✓ Keep-alive stopped gracefully")
        except asyncio.TimeoutError:
            # Force cancellation if graceful shutdown times out
            logger.warning("[SHUTDOWN] Keep-alive timeout - forcing cancellation")
            _keepalive_task.cancel()
            try:
                await _keepalive_task
            except asyncio.CancelledError:
                logger.info("[SHUTDOWN] ✓ Keep-alive cancelled")
    
    # Step 2: Database Disconnection
    logger.info("[SHUTDOWN] Disconnecting database...")
    await db.disconnect()
    logger.info("[SHUTDOWN] ✓ Database disconnected")
    
    logger.info("[SHUTDOWN] All services stopped successfully")

# ---
# Global exception handler for structured error logging
# ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"[UNHANDLED EXCEPTION] {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
    )

# ---
# Include all routers for API structure and real-time monitoring
# ---
app.include_router(services_router)
app.include_router(auth_router)
app.include_router(monitor_router)
app.include_router(monitor_latest_router)
app.include_router(org_monitors.router)
app.include_router(monitor_updates.router)
app.include_router(incident_routes.router)
app.include_router(incidents_ws_router.router)
app.include_router(health_router)

# ---
# Health check endpoint for Railway & Vercel readiness probe
# ---
@app.get("/health")
async def health_check():
    return {"status": "ok"}

# ---
# Entrypoint for local development with Uvicorn
# ---
if __name__ == "__main__":
    import uvicorn
    import os

    port = int(os.environ.get("PORT", 8000))
    logger.info(f"[RUN] Starting Uvicorn on 0.0.0.0:{port}")
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=False
    )

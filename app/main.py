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

# ---
# Logging Configuration
# ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---
# Initialize FastAPI app instance
# ---
app = FastAPI()

# ---
# CORS Middleware for local and deployed frontend access
# ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://status-deck-client.vercel.app",
        "http://localhost:5173",
        "http://127.0.0.1:5173"
    ],
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
# Startup event:
# - Connect to the database
# - Start Redis listener for monitor updates to broadcast via WS
# ---
@app.on_event("startup")
async def startup():
    logger.info("[STARTUP] Connecting to database...")
    await db.connect()
    logger.info("[STARTUP] Database connected.")

    logger.info("[STARTUP] Starting Redis listener for monitor updates...")
    asyncio.create_task(redis_listener.redis_listener())

# ---
# Shutdown event:
# - Cleanly disconnect from the database
# ---
@app.on_event("shutdown")
async def shutdown():
    logger.info("[SHUTDOWN] Disconnecting database...")
    await db.disconnect()
    logger.info("[SHUTDOWN] Database disconnected.")

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

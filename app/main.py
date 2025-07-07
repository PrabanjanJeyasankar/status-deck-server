# ---
# File: app/main.py
# Purpose: FastAPI app initialization, middleware setup, and router inclusion
# ---

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.monitors.latest_results import router as monitor_latest_router
from app.services.routes import router as services_router
from app.monitors.routes import router as monitor_router
from app.incidents import routes as incident_routes
from app.auth.routes import router as auth_router
from app.websocket import incidents_ws_router
from app.websocket import monitor_updates
from app.monitors import org_monitors
from app.db import db

# Initialize FastAPI app instance
app = FastAPI()

@app.middleware("http")
async def log_cors(request, call_next):
    print(f"[CORS LOG] {request.method} {request.url}")
    logger.info(f"[CORS] {request.method} {request.url}")
    response = await call_next(request)
    print(f"[CORS LOG] response headers: {response.headers.get('Access-Control-Allow-Origin')}")
    logger.info(f"[CORS] Response Access-Control-Allow-Origin: {response.headers.get('access-control-allow-origin')}")
    return response

# CORS configuration for local development and future frontend deployments
origins = [
    "http://localhost:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://status-deck-client.vercel.app",
        "http://localhost:5173",
        "http://127.0.0.1:5173"
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ---
# On startup:
# - Connect to the database
# - Note: WS broadcasting handled externally by ws_broadcaster.py
# ---
@app.on_event("startup")
async def startup():
    logger.info("[STARTUP] Connecting to database...")
    await db.connect()
    logger.info("[STARTUP] Database connected successfully.")

# ---
# On shutdown:
# - Disconnect from the database cleanly
# ---
async def shutdown():
    logger.info("[SHUTDOWN] Disconnecting from database...")
    await db.disconnect()
    logger.info("[SHUTDOWN] Database disconnected successfully.")

# ---
# Include all routers for modular API endpoints:
# - Services, Auth, Monitors, Monitor Latest Results
# - Organization Monitors, Monitor Updates WS, Incidents, Incidents WS
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
# Health check endpoint for Railway and Vercel readiness probes
# ---
@app.get("/health")
async def health_check():
    return {"status": "ok"}

# ---
# Entrypoint for Railway and local runs
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


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

# CORS configuration for local development and future frontend deployments
origins = [
    "http://localhost:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
    # Add deployed frontend URLs here
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # You may restrict this later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---
# On startup:
# - Connect to the database
# - Note: WS broadcasting handled externally by ws_broadcaster.py
# ---
@app.on_event("startup")
async def startup():
    await db.connect()
    # print("[INFO] Database connected successfully.")
    # print("[INFO] WS broadcasting is handled by ws_broadcaster.py, not here.")

# ---
# On shutdown:
# - Disconnect from the database cleanly
# ---
@app.on_event("shutdown")
async def shutdown():
    await db.disconnect()
    # print("[INFO] Database disconnected successfully.")

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

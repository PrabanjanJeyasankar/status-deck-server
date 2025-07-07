# ---
# File: monitors/org_monitors.py
# Purpose: FastAPI route to fetch all monitors for an organization,
# including their associated service names for frontend listing.
# ---

from fastapi import APIRouter, HTTPException, Query
from app.db import db
from .models import MonitorWithServiceResponse
from typing import List

# ---
# Initialize the router under /api/monitors for all monitor-related endpoints.
# ---
router = APIRouter(prefix="/api/monitors", tags=["Monitors"])

# ---
# GET endpoint to retrieve all monitors under a given organization,
# flattening monitors from services and attaching the service name to each monitor.
# Used for dashboards and admin pages to list and manage all monitors easily.
# ---
@router.get("", response_model=List[MonitorWithServiceResponse])
async def get_all_monitors(organizationId: str = Query(...)):
    # Fetch all services for the organization with their associated monitors
    services = await db.service.find_many(
        where={"organizationId": organizationId},
        include={"monitors": True},
        order={"createdAt": "asc"}
    )

    all_monitors = []

    # Flatten monitors with attached service name
    for svc in services:
        for m in svc.monitors:
            all_monitors.append(
                MonitorWithServiceResponse(
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
                    serviceName=svc.name,
                    createdAt=m.createdAt.isoformat(),
                    updatedAt=m.updatedAt.isoformat()
                )
            )

    return all_monitors

# ---
# File: monitors/latest_result.py
# Purpose: FastAPI route to fetch the latest monitoring results for each monitor
# in all services of a given organization, including response details for dashboard display.
# ---

from fastapi import APIRouter, HTTPException, Query
from app.db import db
from typing import List, Optional
from pydantic import BaseModel

# ---
# Initialize the router with the /api/monitors prefix
# ---
router = APIRouter(prefix="/api/monitors", tags=["Monitors"])

# ---
# Pydantic response model defining the structure of monitor data returned,
# including the latest monitoring result for each monitor.
# ---
class MonitorLatestResultResponse(BaseModel):
    id: str
    name: str
    url: str
    method: str
    interval: int
    type: str
    headers: list
    active: bool
    degradedThreshold: int
    timeout: int
    serviceId: str
    serviceName: str
    latestResult: Optional[dict]  # Contains latest MonitoringResult details if available

# ---
# GET endpoint to retrieve the latest monitoring results for each monitor
# belonging to all services of the specified organization.
# Orders services by creation date, retrieves each monitor's latest result,
# and returns a flattened list of monitors with their latest statuses.
# ---
@router.get("/latest-results", response_model=List[MonitorLatestResultResponse])
async def get_latest_monitor_results(organizationId: str = Query(...)):
    try:
        # Fetch all services under the organization with associated monitors
        # and their latest monitoring result (most recent by checkedAt).
        services = await db.service.find_many(
            where={"organizationId": organizationId},
            include={
                "monitors": {
                    "include": {
                        "monitoringResults": {
                            "orderBy": {"checkedAt": "desc"},
                            "take": 1
                        }
                    }
                }
            },
            order={"createdAt": "asc"}
        )

        results = []

        # Flatten monitors from services and attach their latest monitoring result
        for service in services:
            for monitor in service.monitors:
                latest = (
                    monitor.monitoringResults[0]
                    if monitor.monitoringResults else None
                )
                results.append(
                    MonitorLatestResultResponse(
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
                        serviceName=service.name,
                        latestResult={
                            "status": latest.status if latest else None,
                            "responseTimeMs": latest.responseTimeMs if latest else None,
                            "httpStatusCode": latest.httpStatusCode if latest else None,
                            "checkedAt": latest.checkedAt.isoformat() if latest else None,
                            "error": latest.error if latest else None
                        } if latest else None
                    )
                )

        return results

    except Exception as e:
        # Return 400 with error details on failure for clearer frontend debugging
        raise HTTPException(status_code=400, detail=str(e))

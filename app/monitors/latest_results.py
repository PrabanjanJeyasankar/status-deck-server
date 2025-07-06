# monitors/latest_result.py
from fastapi import APIRouter, HTTPException, Query
from app.db import db
from typing import List, Optional
from pydantic import BaseModel

router = APIRouter(prefix="/api/monitors", tags=["Monitors"])

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
    latestResult: Optional[dict]  # will hold latest MonitoringResult details

@router.get("/latest-results", response_model=List[MonitorLatestResultResponse])
async def get_latest_monitor_results(organizationId: str = Query(...)):
    try:
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
        raise HTTPException(status_code=400, detail=str(e))

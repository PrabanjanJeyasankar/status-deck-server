#monitors/org_monitors.py

from fastapi import APIRouter, HTTPException, Query
from app.db import db
from .models import MonitorWithServiceResponse
from typing import List

router = APIRouter(prefix="/api/monitors", tags=["Monitors"])

@router.get("", response_model=List[MonitorWithServiceResponse])
async def get_all_monitors(organizationId: str = Query(...)):
    services = await db.service.find_many(
        where={"organizationId": organizationId},
        include={"monitors": True},
        order={"createdAt": "asc"}
    )
    all_monitors = []
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

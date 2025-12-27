# ---
# File: services/routes.py
# Purpose: FastAPI routes for managing services and retrieving monitors with latest results
# ---

from fastapi import APIRouter, HTTPException, Query, Path
from app.db import db
from .models import ServiceCreateRequest, ServiceUpdateRequest, ServiceResponse
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter(prefix="/services", tags=["Services"])

# ---
# Create a new service under an organization.
# Accepts service details (name, status, description, organizationId),
# creates the service record in the database,
# and returns the created service along with organization name.
# ---
@router.post("", response_model=ServiceResponse)
async def create_service(data: ServiceCreateRequest):
    try:
        service = await db.service.create({
            "name": data.name,
            "status": data.status or "OPERATIONAL",
            "organizationId": data.organizationId,
            "description": data.description,
        })

        organization = await db.organization.find_unique(where={"id": data.organizationId})

        return ServiceResponse(
            id=service.id,
            name=service.name,
            status=service.status,
            description=service.description,
            organizationId=service.organizationId,
            organizationName=organization.name if organization else None,
            createdAt=service.createdAt.isoformat()
        )

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ---
# Retrieve all services under a specific organization.
# Requires organizationId as a query parameter,
# returns a list of services with organization names,
# ordered by creation time ascending.
# ---
@router.get("", response_model=List[ServiceResponse])
async def get_services(organizationId: str = Query(...)):
    try:
        services = await db.service.find_many(
            where={"organizationId": organizationId},
            include={"organization": True},
            order={"createdAt": "asc"}
        )
        return [
            ServiceResponse(
                id=s.id,
                name=s.name,
                status=s.status,
                description=s.description,
                organizationId=s.organizationId,
                organizationName=s.organization.name if s.organization else None,
                createdAt=s.createdAt.isoformat(),
                updatedAt=s.updatedAt.isoformat(),
            )
            for s in services
        ]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ---
# Retrieve a single service by its serviceId.
# Returns the service details including organization name,
# or raises a 404 if the service does not exist.
# ---
@router.get("/{serviceId}", response_model=ServiceResponse)
async def get_service(serviceId: str):
    service = await db.service.find_unique(
        where={"id": serviceId},
        include={"organization": True}
    )
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    return ServiceResponse(
        id=service.id,
        name=service.name,
        status=service.status,
        organizationId=service.organizationId,
        organizationName=service.organization.name if service.organization else None,
        createdAt=service.createdAt.isoformat(),
        updatedAt=service.updatedAt.isoformat(),
    )

# ---
# Update a service by its serviceId.
# Accepts partial update data (name, status, description),
# applies the updates, and returns the updated service with organization name.
# Raises 404 if the service does not exist.
# ---
@router.patch("/{serviceId}", response_model=ServiceResponse)
async def update_service(serviceId: str, data: ServiceUpdateRequest):
    service = await db.service.find_unique(
        where={"id": serviceId},
        include={"organization": True}
    )
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    updated_data = {}
    if data.name is not None:
        updated_data["name"] = data.name
    if data.status is not None:
        updated_data["status"] = data.status
    if data.description is not None:
        updated_data["description"] = data.description
    updated_service = await db.service.update(
        where={"id": serviceId},
        data=updated_data,
        include={"organization": True}
    )
    return ServiceResponse(
        id=updated_service.id,
        name=updated_service.name,
        status=updated_service.status,
        description=updated_service.description,
        organizationId=updated_service.organizationId,
        organizationName=updated_service.organization.name if updated_service.organization else None,
        createdAt=updated_service.createdAt.isoformat(),
        updatedAt=updated_service.updatedAt.isoformat(),
    )

# ---
# Delete a service by its serviceId.
# Cleans up by:
# - Deleting monitoring results for monitors under the service
# - Deleting monitors under the service
# - Finally deleting the service itself
# Returns a success response upon completion.
# ---
@router.delete("/{serviceId}")
async def delete_service(serviceId: str):
    service = await db.service.find_unique(where={"id": serviceId})
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    # Get all monitor IDs under this service
    monitors = await db.monitor.find_many(
        where={"serviceId": serviceId}
    )
    monitor_ids = [monitor.id for monitor in monitors]

    # Delete related MonitoringResults first
    if monitor_ids:
        await db.monitoringresult.delete_many(
            where={"monitorId": {"in": monitor_ids}}
        )

    # Delete related monitors
    await db.monitor.delete_many(where={"serviceId": serviceId})

    # Finally, delete the service
    await db.service.delete(where={"id": serviceId})

    return {"success": True}

# Data model representing the latest monitoring result for a monitor
class MonitorLatestResult(BaseModel):
    status: Optional[str]
    responseTimeMs: Optional[int]
    httpStatusCode: Optional[int]
    checkedAt: Optional[str]
    error: Optional[str]

# Data model representing a monitor along with its latest monitoring result
class MonitorWithLatestResponse(BaseModel):
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
    createdAt: str
    updatedAt: str
    latestResult: Optional[MonitorLatestResult]

# ---
# Retrieve all monitors under a specific service,
# each with its latest monitoring result attached if available.
# Returns a list of monitors with their current status, response time, and other metadata.
# ---
@router.get("/{serviceId}/monitors-with-latest", response_model=List[MonitorWithLatestResponse])
async def get_monitors_with_latest(serviceId: str = Path(...)):
    try:
        monitors = await db.monitor.find_many(
            where={"serviceId": serviceId},
            include={
                "monitoringResults": {
                    "orderBy": {"checkedAt": "desc"},
                    "take": 1,
                }
            },
            order={"createdAt": "asc"}
        )

        return [
            MonitorWithLatestResponse(
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
                createdAt=m.createdAt.isoformat(),
                updatedAt=m.updatedAt.isoformat(),
                latestResult=MonitorLatestResult(
                    status=latest.status,
                    responseTimeMs=latest.responseTimeMs,
                    httpStatusCode=latest.httpStatusCode,
                    checkedAt=latest.checkedAt.isoformat() if latest.checkedAt else None,
                    error=latest.error,
                ) if (latest := (m.monitoringResults[0] if m.monitoringResults else None)) else None
            )
            for m in monitors
        ]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ---
# File: incidents/routes.py
# Purpose: FastAPI routes for creating, retrieving, updating, and adding updates to incidents
# ---

from fastapi import APIRouter, HTTPException, Query
from typing import List

from app.incidents import models as incident_schemas
from app.db import db as prisma
from app.incidents.models import IncidentUpdate
from app.monitors.failure_counter_manager import reset_failure_counter

# Set up router for incident-related API endpoints under /api/incidents
router = APIRouter(prefix="/api/incidents", tags=["Incidents"])

# ---
# Create a new incident in the database.
# Takes an IncidentCreate payload with incident details,
# inserts it into the incidents table,
# and returns the created incident including its updates.
# ---
@router.post("/", response_model=incident_schemas.IncidentRead)
async def create_incident(payload: incident_schemas.IncidentCreate):
    incident = await prisma.incident.create(
        data={
            "organizationId": payload.organizationId,
            "title": payload.title,
            "description": payload.description,
            "severity": payload.severity,
            "affectedServiceIds": payload.affectedServiceIds,
            "monitorId": payload.monitorId,
            "autoCreated": payload.autoCreated,
            "createdByUserId": payload.createdByUserId,
        },
        include={"updates": True},
    )
    return incident

# ---
# Get all incidents for a given organization.
# Requires the organizationId as a query parameter.
# Returns a list of incidents including their updates.
# ---
@router.get("/", response_model=List[incident_schemas.IncidentRead])
async def get_incidents(organizationId: str = Query(...)):
    incidents = await prisma.incident.find_many(
        where={"organizationId": organizationId},
        include={"updates": True},
    )
    return incidents

# ---
# Retrieve a single incident by its ID.
# Returns the incident and its updates if found,
# otherwise raises a 404 if the incident does not exist.
# ---
@router.get("/{incident_id}", response_model=incident_schemas.IncidentRead)
async def get_incident(incident_id: str):
    incident = await prisma.incident.find_unique(
        where={"id": incident_id},
        include={"updates": True},
    )
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident

# ---
# Update fields of an existing incident by its ID.
# Accepts a partial update payload (IncidentUpdate),
# updates only provided fields,
# and if the incident is resolved and linked to a monitor,
# resets the failure counter for that monitor.
# ---
@router.patch("/{incident_id}")
async def update_incident(incident_id: str, payload: IncidentUpdate):
    existing_incident = await prisma.incident.find_unique(where={"id": incident_id})
    if not existing_incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    updated_incident = await prisma.incident.update(
        where={"id": incident_id},
        data=payload.dict(exclude_unset=True),
    )

    if updated_incident.status == "RESOLVED" and updated_incident.monitorId:
        await reset_failure_counter(updated_incident.monitorId)

    return updated_incident

# ---
# Add an update entry to an existing incident.
# Verifies that the incident exists before adding the update.
# Accepts an IncidentUpdateCreate payload with the message and createdBy user,
# and returns the created update entry.
# ---
@router.post("/{incident_id}/updates", response_model=incident_schemas.IncidentUpdateRead)
async def add_incident_update(incident_id: str, payload: incident_schemas.IncidentUpdateCreate):
    incident = await prisma.incident.find_unique(where={"id": incident_id})
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    update = await prisma.incidentupdate.create(
        data={
            "incidentId": incident_id,
            "message": payload.message,
            "createdBy": payload.createdBy,
        }
    )
    return update

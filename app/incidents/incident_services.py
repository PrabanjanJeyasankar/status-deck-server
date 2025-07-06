# ---
# File: app/services/incident_services.py
# Purpose: Handles automated incident creation, escalation, and resolution based on monitor status changes
# ---

from app.utils.redis_utils import publish_to_redis
from datetime import datetime, timezone
from app.monitors.failure_counter_manager import (
    increment_failure_counter,
    reset_failure_counter,
    clear_failed_pings,
)
from app.db import db as database
from datetime import datetime

INCIDENT_THRESHOLDS = {
    "LOW": 3,
    "MEDIUM": 5,
    "HIGH": 7,
    "CRITICAL": 10,
}
SEVERITY_ORDER = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]

# ---
# Service class for incident management tied to monitor health.
# Provides methods to handle monitor status changes,
# auto-resolve incidents when monitors recover,
# and create or escalate incidents when monitors degrade or go down.
# ---
class IncidentService:

    # ---
    # Handles a status change event for a monitor.
    # If the monitor is UP, attempts to auto-resolve any existing open incident.
    # If the monitor is DOWN or DEGRADED, increments failure counters,
    # checks thresholds, and creates or escalates incidents as needed.
    # ---
    @staticmethod
    async def handle_monitor_status_change(monitor_id: str, status: str):
        if status == "UP":
            await IncidentService._resolve_incident_if_exists(monitor_id)
            return

        # Only handle incident creation/escalation for non-UP statuses
        if status in ("DOWN", "DEGRADED"):
            consecutive_failures = await increment_failure_counter(monitor_id)
            severity_to_raise = next(
                (severity for severity, threshold in INCIDENT_THRESHOLDS.items()
                 if consecutive_failures == threshold),
                None
            )
            if severity_to_raise:
                await IncidentService._create_or_update_incident(monitor_id, status, severity_to_raise)

    # ---
    # Resolves an existing auto-created, open incident for a monitor if found.
    # Marks it as RESOLVED with the current UTC timestamp,
    # publishes the update to Redis for subscribers,
    # resets the monitor's failure counter and clears failed pings.
    # ---
    @staticmethod
    async def _resolve_incident_if_exists(monitor_id: str):
        incident = await database.incident.find_first(
            where={
                "monitorId": monitor_id,
                "status": "OPEN",
                "autoCreated": True,
            }
        )
        if incident:
            resolved_incident = await database.incident.update(
                where={"id": incident.id},
                data={
                    "status": "RESOLVED",
                    "resolvedAt": datetime.now(timezone.utc),
                }
            )
            print(
                f"\n✅ [INCIDENT AUTO-RESOLVE] 🚀 Incident {resolved_incident.id} for monitor {monitor_id} auto-resolved at {resolved_incident.resolvedAt.isoformat()}.\n",
                flush=True
            )
            await publish_to_redis("incident_updates_channel", {
                "organization_id": resolved_incident.organizationId,
                "type": "incident_resolved",
                "payload": {
                    "id": resolved_incident.id,
                    "status": "RESOLVED",
                    "resolvedAt": resolved_incident.resolvedAt.isoformat(),
                    "monitorId": resolved_incident.monitorId,
                    "autoResolved": True,
                }
            })
            await reset_failure_counter(monitor_id)
            await clear_failed_pings(monitor_id)

    # ---
    # Creates a new incident or escalates an existing one for a monitor.
    # If an open incident exists, escalates severity if needed.
    # If no incident exists, creates a new incident record,
    # publishes the incident creation to Redis,
    # and clears failed pings for the monitor after creation.
    # ---
    @staticmethod
    async def _create_or_update_incident(monitor_id: str, status: str, severity: str):
        monitor = await database.monitor.find_unique(
            where={"id": monitor_id},
            include={"service": {"include": {"organization": True}}},
        )

        if not monitor:
            print(f"[INCIDENT] Monitor {monitor_id} not found.")
            return

        service = getattr(monitor, 'service', None)
        org_id = getattr(service, 'organizationId', None) if service else None
        service_id = getattr(monitor, 'serviceId', None)
        monitor_name = getattr(monitor, 'name', None)

        if not service or not org_id or not monitor_name:
            print(f"[INCIDENT][ERROR] Service, org, or monitor name missing for monitor {monitor_id}. Monitor: {monitor}, Service: {service}")
            return

        existing_incident = await database.incident.find_first(
            where={
                "monitorId": monitor_id,
                "status": "OPEN",
                "autoCreated": True,
            }
        )

        if existing_incident:
            current_idx = SEVERITY_ORDER.index(existing_incident.severity)
            new_idx = SEVERITY_ORDER.index(severity)
            update_data = {}
            if new_idx > current_idx:
                update_data["severity"] = severity
                print(f"[INCIDENT] Escalated incident {existing_incident.id} to {severity}")
            if update_data:
                await database.incident.update(
                    where={"id": existing_incident.id},
                    data=update_data
                )
        else:
            incident_payload = {
                "title": f"{monitor.name} {status}",
                "description": f"Monitor {monitor.name} is reporting status {status}.",
                "severity": severity,
                "status": "OPEN",
                "autoCreated": True,
                "monitorId": monitor_id,
                "serviceId": service_id,
                "organizationId": org_id,
                "affectedServiceIds": [service_id] if service_id else [],
            }

            try:
                incident = await database.incident.create(data=incident_payload)
            except Exception as e:
                print(f"[INCIDENT][ERROR] Failed to create incident: {e}")
                return

            await publish_to_redis("incident_updates_channel", {
                "organization_id": org_id,
                "type": "incident_created",
                "payload": {
                    "id": incident.id,
                    "title": incident.title,
                    "severity": incident.severity,
                    "status": incident.status,
                    "monitorId": incident.monitorId,
                    "createdAt": incident.createdAt.isoformat(),
                    "url": monitor.url,
                    "method": monitor.method,
                    "serviceName": service.name if service else None,
                    "organizationId": org_id,
                }
            })
            print(f"[INCIDENT] Created incident {incident.id} for monitor {monitor_id}")
            await clear_failed_pings(monitor_id)

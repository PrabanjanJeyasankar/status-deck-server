# ---
# File: app/websocket/incidents_ws_router.py
# Purpose: WebSocket router for real-time incident updates via Redis pub/sub per organization
# ---

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from redis import asyncio as aioredis
import asyncio
import json
import logging

# print("[WS Router] incidents_ws_router imported and registered.")

router = APIRouter()

REDIS_URL = "redis://localhost"
logger = logging.getLogger(__name__)

# ---
# Manages active WebSocket connections per organization for incident updates.
# Handles connection management, disconnections, and broadcasting messages to all
# clients under the same organization.
# ---
class IncidentWSManager:
    def __init__(self):
        self.active_connections = {}

    async def connect(self, websocket: WebSocket, organization_id: str):
        await websocket.accept()
        self.active_connections.setdefault(organization_id, []).append(websocket)
        logger.info(f"[WS] Incident connected: {organization_id}")

    def disconnect(self, websocket: WebSocket, organization_id: str):
        connections = self.active_connections.get(organization_id, [])
        if websocket in connections:
            connections.remove(websocket)
            logger.info(f"[WS] Incident disconnected: {organization_id}")
        if not connections:
            self.active_connections.pop(organization_id, None)

    async def broadcast(self, organization_id: str, message: dict):
        connections = self.active_connections.get(organization_id, [])
        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"[WS] Send error: {e}")
                self.disconnect(connection, organization_id)

manager = IncidentWSManager()

# ---
# WebSocket endpoint for subscribing to incident updates for a specific organization.
# - Accepts a WebSocket connection.
# - Subscribes to the Redis 'incident_updates_channel'.
# - Filters and broadcasts messages to the client if the organization matches.
# - Handles client disconnects and cleanup gracefully.
# ---
@router.websocket("/ws/incidents/{organization_id}")
async def incident_websocket(websocket: WebSocket, organization_id: str):
    # print(f"[IncidentSocket] New connection for org: {organization_id}")
    await manager.connect(websocket, organization_id)

    redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("incident_updates_channel")
    # print(f"[IncidentSocket] Subscribed to Redis channel for {organization_id}")

    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
            if message:
                try:
                    data = json.loads(message["data"])
                    # print(f"[IncidentSocket] Raw Redis message: {data}")

                    if data.get("organization_id") == organization_id:
                        # print(f"[IncidentSocket] Broadcasting to org {organization_id}")
                        await manager.broadcast(organization_id, data)
                    else:
                        # print(f"[IncidentSocket] Ignored message for org {data.get('organization_id')}")
                        pass
                except json.JSONDecodeError as e:
                    # print(f"[IncidentSocket] JSON decode error: {e}, raw: {message['data']}")
                    pass
                except Exception as e:
                    # print(f"[IncidentSocket] Failed processing message: {e}")
                    pass

            # Handle optional ping/control messages to keep connection alive
            try:
                await websocket.receive_text()
            except WebSocketDisconnect:
                break

            await asyncio.sleep(0.1)

    except WebSocketDisconnect:
        # print(f"[IncidentSocket] Disconnected: {organization_id}")
        pass
    finally:
        manager.disconnect(websocket, organization_id)
        await pubsub.unsubscribe("incident_updates_channel")
        await pubsub.close()
        await redis_client.close()
        # print(f"[IncidentSocket] Cleaned up for {organization_id}")

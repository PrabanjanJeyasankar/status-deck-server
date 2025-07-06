# ---
# File: app/websocket/monitor_updates.py
# Purpose: WebSocket router for streaming real-time monitor updates per organization
# ---

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, logger
from typing import List, Dict

router = APIRouter()

# ---
# Manages active WebSocket connections per organization for monitor updates.
# Handles accepting connections, disconnections, and broadcasting updates to
# all clients under a specific organization.
# ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, organization_id: str):
        await websocket.accept()
        if organization_id not in self.active_connections:
            self.active_connections[organization_id] = []
        self.active_connections[organization_id].append(websocket)
        # print(f"✅ WebSocket connected for {organization_id} | Total connections: {len(self.active_connections[organization_id])}")

    def disconnect(self, websocket: WebSocket, organization_id: str):
        if organization_id in self.active_connections:
            if websocket in self.active_connections[organization_id]:
                self.active_connections[organization_id].remove(websocket)
                # print(f"⛔ WebSocket disconnected for {organization_id} | Remaining: {len(self.active_connections[organization_id])}")

    async def broadcast(self, organization_id: str, message: dict):
        connections = self.active_connections.get(organization_id, [])
        for connection in connections.copy():
            try:
                await connection.send_json(message)
                logger.info(f"✅ Sent to WS client for org {organization_id}: {message}")
            except Exception as e:
                logger.error(f"❌ Failed to send WS message: {e}")
                self.disconnect(connection, organization_id)

manager = ConnectionManager()

# ---
# WebSocket endpoint for subscribing to real-time monitor updates for an organization.
# Keeps the connection alive by receiving text frames indefinitely until the client disconnects.
# ---
@router.websocket("/ws/monitors/{organization_id}")
async def monitor_updates_websocket(websocket: WebSocket, organization_id: str):
    await manager.connect(websocket, organization_id)
    try:
        while True:
            await websocket.receive_text()  # Keep connection alive for updates
    except WebSocketDisconnect:
        manager.disconnect(websocket, organization_id)

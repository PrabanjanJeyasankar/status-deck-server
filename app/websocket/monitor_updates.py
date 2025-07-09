# ---
# File: app/websocket/monitor_updates.py
# Purpose: WebSocket router for real-time monitor updates per organization with Redis pub/sub for distributed scaling
# ---

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import List, Dict
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

class ConnectionManager:
    def __init__(self):
        # Maps organization_id -> list of active WebSockets
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, organization_id: str):
        await websocket.accept()
        if organization_id not in self.active_connections:
            self.active_connections[organization_id] = []
        self.active_connections[organization_id].append(websocket)
        logger.info(f"[WS] Connected for {organization_id} | Total: {len(self.active_connections[organization_id])}")

    def disconnect(self, websocket: WebSocket, organization_id: str):
        if organization_id in self.active_connections and websocket in self.active_connections[organization_id]:
            self.active_connections[organization_id].remove(websocket)
            logger.info(f"[WS] Disconnected for {organization_id} | Remaining: {len(self.active_connections[organization_id])}")

    async def broadcast(self, organization_id: str, message: dict):
        connections = self.active_connections.get(organization_id, [])
        if not connections:
            logger.info(f"[WS] No clients to broadcast for {organization_id}")
            return

        logger.info(f"[WS] Broadcasting to {len(connections)} clients for {organization_id}")

        for connection in connections.copy():
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"[WS] Failed to send message: {e}")
                self.disconnect(connection, organization_id)

# Singleton manager instance for use in listener and WS route
manager = ConnectionManager()

@router.websocket("/ws/monitors/{organization_id}")
async def monitor_updates_websocket(websocket: WebSocket, organization_id: str):
    await manager.connect(websocket, organization_id)
    try:
        while True:
            await websocket.receive_text()  # Keeps connection alive
    except WebSocketDisconnect:
        manager.disconnect(websocket, organization_id)

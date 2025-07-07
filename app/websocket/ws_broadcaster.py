# ---
# File: app/websocket/ws_broadcaster.py
# Purpose: WebSocket broadcaster for real-time monitor updates via Redis pub/sub per organization
# ---

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from redis import asyncio as aioredis
from typing import List, Dict
import asyncio
import logging
import json
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost")

app = FastAPI()

# ---
# Manages active WebSocket connections per organization.
# Handles accepting connections, disconnecting clients,
# and broadcasting updates to all clients under a specific organization.
# ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, organization_id: str):
        await websocket.accept()
        if organization_id not in self.active_connections:
            self.active_connections[organization_id] = []
        self.active_connections[organization_id].append(websocket)
        # logger.info(f" WebSocket connected for {organization_id} | Total connections: {len(self.active_connections[organization_id])}")

    def disconnect(self, websocket: WebSocket, organization_id: str):
        if organization_id in self.active_connections and websocket in self.active_connections[organization_id]:
            self.active_connections[organization_id].remove(websocket)
            # logger.info(f"⛔ WebSocket disconnected for {organization_id} | Remaining: {len(self.active_connections[organization_id])}")

    async def broadcast(self, message: dict):
        organization_id = message.get("organization_id")
        if not organization_id:
            logger.warning(f"⚠️ No organization_id in message: {message}")
            return

        connections = self.active_connections.get(organization_id, [])
        # logger.info(f"📡 Broadcasting to {len(connections)} clients for {organization_id}")

        for connection in connections.copy():
            try:
                await connection.send_json(message)
                # logger.info(f" Sent to WS client for org {organization_id}: {message}")
            except Exception as e:
                logger.error(f" Failed to send WS message: {e}")
                self.disconnect(connection, organization_id)

manager = ConnectionManager()

# ---
# WebSocket endpoint for clients to subscribe to monitor updates for a specific organization.
# Keeps the connection alive indefinitely until the client disconnects.
# ---
@app.websocket("/ws/monitors/{organization_id}")
async def websocket_endpoint(websocket: WebSocket, organization_id: str):
    await manager.connect(websocket, organization_id)
    try:
        while True:
            await websocket.receive_text()  # keep connection alive
    except WebSocketDisconnect:
        manager.disconnect(websocket, organization_id)

# ---
# Listens to the Redis 'monitor_updates_channel' for real-time monitor updates.
# On receiving a message, parses it and broadcasts it to connected WebSocket clients
# under the appropriate organization.
# ---
async def redis_listener():
    redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("monitor_updates_channel")
    # logger.info("🔄 Listening for monitor updates on Redis")

    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    # logger.info(f" Received data: {data}")
                    await manager.broadcast(data)
                except Exception as e:
                    logger.error(f" Failed to process message: {e}")
    except asyncio.CancelledError:
        logger.info(" Redis listener cancelled, shutting down cleanly.")
    finally:
        await pubsub.unsubscribe("monitor_updates_channel")
        await pubsub.close()
        await redis_client.close()

# ---
# On FastAPI app startup, launch the Redis listener as a background task.
# ---
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(redis_listener())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.websocket.ws_broadcaster:app", host="0.0.0.0", port=8001, reload=True)

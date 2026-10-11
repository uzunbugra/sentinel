# =============================================================================
# SentinelFlow API - WebSocket Alert Stream
# =============================================================================
"""``/ws/alerts``: live alert stream (alerts are pushed via ``state.broadcast_alert``)."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

from sentinelflow.api.state import state

router = APIRouter()


@router.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    """
    WebSocket endpoint for real-time fraud alert streaming.

    Connect to receive alerts as they are detected.
    """
    await websocket.accept()
    state.ws_clients.append(websocket)
    logger.info(f"WebSocket client connected (total: {len(state.ws_clients)})")

    try:
        await websocket.send_json(
            {
                "type": "connection",
                "message": "Connected to SentinelFlow alert stream",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

        while True:
            data = await websocket.receive_text()

            if data == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        if websocket in state.ws_clients:
            state.ws_clients.remove(websocket)

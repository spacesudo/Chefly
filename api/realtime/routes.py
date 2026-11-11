from typing import Optional

from fastapi import APIRouter, HTTPException, WebSocket, status

from api.auth.dependencies import authenticate_access_token, get_current_user_id
from api.realtime.connection import RealtimeConnection

router = APIRouter(tags=["realtime"])


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: Optional[str] = None):
    """Authenticate with `?token=<access token>` (browsers can't set WebSocket headers) or `Authorization: Bearer`."""
    header = websocket.headers.get("authorization", "")
    raw_token = token or (header[7:] if header.lower().startswith("bearer ") else None)
    try:
        token_data = await authenticate_access_token(raw_token)
        user_id = get_current_user_id(token_data)
    except HTTPException:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await websocket.accept()
    await RealtimeConnection(websocket, user_id, token_data["exp"]).run()

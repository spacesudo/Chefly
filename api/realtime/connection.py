"""One WebSocket per client: server pushes every event for the user; client sends chat actions.

Client -> server:  {"type": "ping"}
                   {"type": "typing", "conversation_id": "..."}
                   {"type": "read", "conversation_id": "..."}
                   {"type": "send_message", "conversation_id": "...", "content": "...", "shared_post_id": "...", "client_id": "..."}
Server -> client:  ready, pong, ack, error, notification, notification.removed, chat.message, chat.message_updated,
                   chat.message_deleted, chat.read, chat.typing, chat.request_accepted, chat.conversation_removed
"""

import asyncio
import json
import logging
from datetime import datetime
from uuid import UUID

from fastapi import HTTPException, WebSocket, WebSocketDisconnect, status
from pydantic import ValidationError

from api.chat.schemas import MessageCreate
from api.chat.service import ChatService
from api.db.redis import redis_client
from api.notifications.service import NotificationService
from api.realtime.events import envelope, publish, user_channel

logger = logging.getLogger(__name__)

chat_service = ChatService()
notification_service = NotificationService()


class RealtimeConnection:

    def __init__(self, websocket: WebSocket, user_id: UUID, token_expires_at: float):
        self.websocket = websocket
        self.user_id = user_id
        self.token_expires_at = token_expires_at
        # conversation_id -> other participant, so typing events don't hit the DB every keystroke
        self.peers: dict[UUID, UUID] = {}
        self.handlers = {
            "ping": self._ping,
            "typing": self._typing,
            "read": self._read,
            "send_message": self._send_message,
        }

    async def send(self, type: str, data: dict) -> None:
        await self.websocket.send_text(envelope(type, data))

    async def run(self) -> None:
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(user_channel(self.user_id))
        tasks = [asyncio.create_task(self._forward(pubsub)), asyncio.create_task(self._receive())]
        try:
            await self.send("ready", await self._ready_payload())
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                exc = task.exception()
                if exc and not isinstance(exc, WebSocketDisconnect):
                    logger.warning("WebSocket closed with error", exc_info=exc)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await pubsub.unsubscribe(user_channel(self.user_id))
            await pubsub.aclose()

    async def _ready_payload(self) -> dict:
        async with chat_service.session_factory() as session:
            return {
                "user_id": str(self.user_id),
                "unread_notifications": await notification_service.unread_count(self.user_id, session),
                "chat": (await chat_service.unread_summary(self.user_id, session)).model_dump(),
            }

    async def _forward(self, pubsub) -> None:
        async for message in pubsub.listen():
            if message["type"] == "message":
                await self.websocket.send_text(message["data"])

    async def _receive(self) -> None:
        while True:
            raw = await self.websocket.receive_text()
            if datetime.now().timestamp() >= self.token_expires_at:
                await self.send("error", {"status": 401, "detail": "Token expired, reconnect with a new token"})
                await self.websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return
            msg: dict = {}
            try:
                msg = json.loads(raw)
                handler = self.handlers.get(msg.get("type"))
                if not handler:
                    raise HTTPException(status_code=400, detail=f"Unknown message type: {msg.get('type')}")
                await handler(msg)
            except HTTPException as e:
                await self._error(msg, e.status_code, e.detail)
            except ValidationError as e:
                await self._error(msg, 422, e.errors(include_url=False, include_context=False))
            except (ValueError, KeyError, TypeError, AttributeError):
                await self._error(msg, 400, "Invalid message")

    async def _error(self, msg: dict, code: int, detail) -> None:
        payload = msg if isinstance(msg, dict) else {}
        await self.send("error", {"type": payload.get("type"), "client_id": payload.get("client_id"), "status": code, "detail": detail})

    # Handlers

    async def _ping(self, msg: dict) -> None:
        await self.send("pong", {})

    async def _typing(self, msg: dict) -> None:
        conversation_id = UUID(msg["conversation_id"])
        if conversation_id not in self.peers:
            async with chat_service.session_factory() as session:
                self.peers[conversation_id] = await chat_service.get_peer_id(conversation_id, self.user_id, session)
        await publish(self.peers[conversation_id], "chat.typing", {"conversation_id": str(conversation_id), "user_id": str(self.user_id)})

    async def _read(self, msg: dict) -> None:
        async with chat_service.session_factory() as session:
            await chat_service.mark_read(UUID(msg["conversation_id"]), self.user_id, session)

    async def _send_message(self, msg: dict) -> None:
        data = MessageCreate(content=msg.get("content"), shared_post_id=msg.get("shared_post_id"))
        async with chat_service.session_factory() as session:
            message = await chat_service.send_message(UUID(msg["conversation_id"]), self.user_id, data, session)
        await self.send("ack", {"client_id": msg.get("client_id"), "message": message.model_dump(mode="json")})

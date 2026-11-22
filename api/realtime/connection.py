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

from fastapi import WebSocket, WebSocketDisconnect, status
from pydantic import ValidationError

from api.chat.schemas import MessageCreate
from api.chat.service import ChatService
from api.config import Config
from api.db.redis import is_jwt_blacklisted, redis_client
from api.errors import ChefLyException, InternalServerError, InvalidSocketMessage, InvalidToken, RevokedToken, UnknownSocketMessage
from api.notifications.service import NotificationService
from api.realtime.events import envelope, publish, revocation_channel, user_channel

logger = logging.getLogger(__name__)

chat_service = ChatService()
notification_service = NotificationService()

# Fallback for missed revocation pub/sub messages: how often an idle socket rechecks the blacklist
SESSION_CHECK_INTERVAL = 30


class RealtimeConnection:

    def __init__(self, websocket: WebSocket, user_id: UUID, token_expires_at: float, token_jti: str):
        self.websocket = websocket
        self.user_id = user_id
        self.token_expires_at = token_expires_at
        self.token_jti = token_jti
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
        await pubsub.subscribe(user_channel(self.user_id), revocation_channel(self.token_jti))
        tasks = [
            asyncio.create_task(self._forward(pubsub)),
            asyncio.create_task(self._receive()),
            asyncio.create_task(self._watch_session()),
        ]
        try:
            if await self._session_error():
                return
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
            await pubsub.unsubscribe(user_channel(self.user_id), revocation_channel(self.token_jti))
            await pubsub.aclose()

    async def _ready_payload(self) -> dict:
        async with chat_service.session_factory() as session:
            return {
                "user_id": str(self.user_id),
                "unread_notifications": await notification_service.unread_count(self.user_id, session),
                "chat": (await chat_service.unread_summary(self.user_id, session)).model_dump(),
            }

    async def _session_error(self) -> ChefLyException | None:
        """Close the socket and return the reason if its token has expired or been revoked."""
        if datetime.now().timestamp() >= self.token_expires_at:
            error = InvalidToken("Your token has expired", "Reconnect with a fresh access token")
        elif await is_jwt_blacklisted(self.token_jti):
            error = RevokedToken()
        else:
            return None
        await self._close(error)
        return error

    async def _close(self, error: ChefLyException) -> None:
        try:
            await self._error({}, error)
            await self.websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=error.error_code)
        except Exception:
            pass

    async def _watch_session(self) -> None:
        """Close the socket as soon as the token expires, and periodically recheck revocation."""
        while True:
            remaining = self.token_expires_at - datetime.now().timestamp()
            await asyncio.sleep(max(0, min(SESSION_CHECK_INTERVAL, remaining)))
            if await self._session_error():
                return

    async def _forward(self, pubsub) -> None:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            if message["channel"] == revocation_channel(self.token_jti):
                await self._close(RevokedToken())
                return
            if await self._session_error():
                return
            await self.websocket.send_text(message["data"])

    async def _receive(self) -> None:
        while True:
            raw = await self.websocket.receive_text()
            if await self._session_error():
                return
            msg: dict = {}
            try:
                msg = json.loads(raw)
                handler = self.handlers.get(msg.get("type"))
                if not handler:
                    raise UnknownSocketMessage(f"Unknown message type: {msg.get('type')}")
                await handler(msg)
            except ChefLyException as e:
                await self._error(msg, e)
            except ValidationError as e:
                details = [{"field": ".".join(map(str, err["loc"])), "message": err["msg"]} for err in e.errors()]
                error = InvalidSocketMessage(f"Invalid {details[0]['field']}: {details[0]['message']}", "Fix the listed fields and try again")
                await self._error(msg, error, status=422, details=details)
            except (ValueError, KeyError, TypeError, AttributeError):
                await self._error(msg, InvalidSocketMessage())
            except Exception as e:
                logger.exception("Unhandled error in WebSocket handler")
                await self._error(msg, InternalServerError(), debug=f"{type(e).__name__}: {e}" if Config.DEBUG else None)

    async def _error(self, msg: dict, error: ChefLyException, status: int | None = None, details: list | None = None, debug: str | None = None) -> None:
        """Same body as REST errors, plus the originating message `type` and `client_id` so clients can match it up."""
        payload = msg if isinstance(msg, dict) else {}
        body = {"type": payload.get("type"), "client_id": payload.get("client_id"), "status": status or error.status_code, **error.to_dict()}
        if details:
            body["details"] = details
        if debug:
            body["debug"] = debug
        await self.send("error", body)

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

"""Per-user event bus. Anything published here is delivered to every open WebSocket of that user.

Envelope sent to clients: {"type": "<event type>", "data": {...}}
"""

import json
import logging
from typing import Iterable
from uuid import UUID

from api.db.redis import redis_client

logger = logging.getLogger(__name__)


def user_channel(user_id: UUID) -> str:
    return f"events:{user_id}"


def envelope(type: str, data: dict) -> str:
    return json.dumps({"type": type, "data": data}, default=str)


async def publish(user_ids: UUID | Iterable[UUID], type: str, data: dict) -> None:
    """Best-effort fan-out; never raises."""
    for user_id in [user_ids] if isinstance(user_ids, UUID) else set(user_ids):
        try:
            await redis_client.publish(user_channel(user_id), envelope(type, data))
        except Exception:
            logger.warning("Failed to publish %s event", type, exc_info=True)

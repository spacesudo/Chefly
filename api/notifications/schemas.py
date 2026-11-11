from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel

from api.db.models import NotificationType


class NotificationActor(BaseModel):
    id: UUID
    username: str


class NotificationPost(BaseModel):
    id: UUID
    title: str


class NotificationCommunity(BaseModel):
    id: UUID
    name: str


class NotificationResponse(BaseModel):
    id: UUID
    type: NotificationType
    message: str
    is_read: bool
    actor: Optional[NotificationActor] = None
    actor_count: int
    post: Optional[NotificationPost] = None
    comment_id: Optional[UUID] = None
    community: Optional[NotificationCommunity] = None
    created_at: datetime
    updated_at: datetime

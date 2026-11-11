from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

MAX_MESSAGE_LENGTH = 4000


class ConversationStart(BaseModel):
    user_id: UUID


class MessageCreate(BaseModel):
    content: Optional[str] = Field(default=None, max_length=MAX_MESSAGE_LENGTH)
    shared_post_id: Optional[UUID] = None


class MessageEdit(BaseModel):
    content: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)


class ChatUser(BaseModel):
    id: UUID
    username: str


class SharedPostPreview(BaseModel):
    id: UUID
    title: str
    author_username: str
    tags: List[str] = []


class MessageResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    sender_id: UUID
    content: Optional[str] = None
    shared_post: Optional[SharedPostPreview] = None
    # True when a post was shared but the viewer can't see it (e.g. private community)
    shared_post_unavailable: bool = False
    is_deleted: bool = False
    created_at: datetime
    edited_at: Optional[datetime] = None


class ConversationResponse(BaseModel):
    id: UUID
    other_user: ChatUser
    # False = this conversation is in your message-requests inbox
    is_accepted: bool
    # False = the other person hasn't accepted your messages yet
    other_accepted: bool
    last_message: Optional[MessageResponse] = None
    unread_count: int = 0
    my_last_read_at: Optional[datetime] = None
    # Read receipt: your messages sent at or before this time have been seen
    other_last_read_at: Optional[datetime] = None
    last_message_at: Optional[datetime] = None
    created_at: datetime


class ChatUnreadSummary(BaseModel):
    unread_conversations: int
    requests: int

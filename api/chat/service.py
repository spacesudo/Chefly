"""1-to-1 DMs with message requests, read receipts, edits/deletes and shared posts.

Every change is pushed to both participants' WebSockets via api.realtime.events.publish.
"""

from datetime import datetime, timezone
from typing import List
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import and_, func
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from api.communities.access import ensure_can_view_post, visible_posts_filter
from api.db.main import async_session_maker
from api.db.models import Conversation, ConversationParticipant, Follows, Message, Posts, User
from api.realtime.events import publish
from api.tags.service import TagService

from .schemas import (
    ChatUnreadSummary,
    ChatUser,
    ConversationResponse,
    MessageCreate,
    MessageResponse,
    SharedPostPreview,
)

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
MAX_PAGE_SIZE = 100


def _now() -> datetime:
    return datetime.now(timezone.utc)


def dm_key(a: UUID, b: UUID) -> str:
    return ":".join(sorted((str(a), str(b))))


class ChatService:

    # Used by the WebSocket handler, which has no request-scoped session
    session_factory = async_session_maker
    tag_service = TagService()

    # Lookups

    async def _participants(self, conversation_id: UUID, user_id: UUID, session: AsyncSession) -> tuple[ConversationParticipant, ConversationParticipant]:
        """Returns (me, other); 404 if the user isn't in the conversation."""
        result = await session.execute(
            select(ConversationParticipant).where(ConversationParticipant.conversation_id == conversation_id)
        )
        participants = {p.user_id: p for p in result.scalars().all()}
        me = participants.pop(user_id, None)
        if not me or not participants:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        return me, next(iter(participants.values()))

    async def get_peer_id(self, conversation_id: UUID, user_id: UUID, session: AsyncSession) -> UUID:
        _, other = await self._participants(conversation_id, user_id, session)
        return other.user_id

    async def _get_own_message(self, conversation_id: UUID, message_id: UUID, user_id: UUID, session: AsyncSession) -> tuple[Message, UUID]:
        _, other = await self._participants(conversation_id, user_id, session)
        message = await session.get(Message, message_id)
        if not message or message.conversation_id != conversation_id or message.is_deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
        if message.sender_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only change your own messages")
        return message, other.user_id

    # Serialization

    async def message_responses(self, messages: List[Message], viewer_id: UUID, session: AsyncSession) -> List[MessageResponse]:
        post_ids = {m.shared_post_id for m in messages if m.shared_post_id and not m.is_deleted}
        previews: dict[UUID, SharedPostPreview] = {}
        if post_ids:
            result = await session.execute(
                select(Posts.id, Posts.title, User.username)
                .join(User, User.id == Posts.author_id)
                .where(Posts.id.in_(post_ids), visible_posts_filter(viewer_id))
            )
            rows = result.all()
            tags = await self.tag_service.get_tags_for_posts((r[0] for r in rows), session)
            previews = {
                pid: SharedPostPreview(id=pid, title=title, author_username=author, tags=tags.get(pid, []))
                for pid, title, author in rows
            }
        return [
            MessageResponse(
                id=m.id,
                conversation_id=m.conversation_id,
                sender_id=m.sender_id,
                content=None if m.is_deleted else m.content,
                shared_post=previews.get(m.shared_post_id),
                shared_post_unavailable=bool(m.shared_post_id) and m.shared_post_id not in previews,
                is_deleted=m.is_deleted,
                created_at=m.created_at,
                edited_at=m.edited_at,
            )
            for m in messages
        ]

    async def conversation_responses(self, conversations: List[Conversation], viewer_id: UUID, session: AsyncSession) -> List[ConversationResponse]:
        if not conversations:
            return []
        ids = [c.id for c in conversations]

        result = await session.execute(select(ConversationParticipant).where(ConversationParticipant.conversation_id.in_(ids)))
        participants: dict[UUID, dict[UUID, ConversationParticipant]] = {}
        for p in result.scalars().all():
            participants.setdefault(p.conversation_id, {})[p.user_id] = p

        def other_of(conversation_id: UUID) -> ConversationParticipant:
            return next(p for uid, p in participants[conversation_id].items() if uid != viewer_id)

        other_ids = {other_of(cid).user_id for cid in ids}
        usernames = dict((await session.execute(select(User.id, User.username).where(User.id.in_(other_ids)))).all())

        result = await session.execute(
            select(Message)
            .where(Message.conversation_id.in_(ids))
            .distinct(Message.conversation_id)
            .order_by(Message.conversation_id, Message.created_at.desc())
        )
        last_messages = {m.conversation_id: m for m in result.scalars().all()}
        last_responses = {r.conversation_id: r for r in await self.message_responses(list(last_messages.values()), viewer_id, session)}

        cp = ConversationParticipant
        result = await session.execute(
            select(Message.conversation_id, func.count())
            .join(cp, and_(cp.conversation_id == Message.conversation_id, cp.user_id == viewer_id))
            .where(
                Message.conversation_id.in_(ids),
                Message.sender_id != viewer_id,
                Message.is_deleted == False,
                Message.created_at > func.coalesce(cp.last_read_at, EPOCH),
            )
            .group_by(Message.conversation_id)
        )
        unread = dict(result.all())

        responses = []
        for c in conversations:
            mine, other = participants[c.id][viewer_id], other_of(c.id)
            responses.append(ConversationResponse(
                id=c.id,
                other_user=ChatUser(id=other.user_id, username=usernames.get(other.user_id, "unknown")),
                is_accepted=mine.is_accepted,
                other_accepted=other.is_accepted,
                last_message=last_responses.get(c.id),
                unread_count=unread.get(c.id, 0),
                my_last_read_at=mine.last_read_at,
                other_last_read_at=other.last_read_at,
                last_message_at=c.last_message_at,
                created_at=c.created_at,
            ))
        return responses

    # Conversations

    async def start_conversation(self, user_id: UUID, other_id: UUID, session: AsyncSession) -> ConversationResponse:
        """Get or create the DM with `other_id`. It lands in their requests inbox unless they follow you."""
        if other_id == user_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot message yourself")
        if not await session.get(User, other_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        key = dm_key(user_id, other_id)
        conversation = (await session.execute(select(Conversation).where(Conversation.dm_key == key))).scalar_one_or_none()
        if not conversation:
            other_follows_me = (await session.execute(
                select(Follows.id).where(Follows.follower_id == other_id, Follows.following_id == user_id)
            )).first()
            conversation = Conversation(dm_key=key, created_at=_now())
            session.add(conversation)
            try:
                await session.flush()
                session.add_all([
                    ConversationParticipant(conversation_id=conversation.id, user_id=user_id, is_accepted=True),
                    ConversationParticipant(conversation_id=conversation.id, user_id=other_id, is_accepted=other_follows_me is not None),
                ])
                await session.commit()
            except IntegrityError:
                # Both users opened the DM at the same time
                await session.rollback()
                conversation = (await session.execute(select(Conversation).where(Conversation.dm_key == key))).scalar_one()
        return (await self.conversation_responses([conversation], user_id, session))[0]

    async def list_conversations(self, user_id: UUID, session: AsyncSession, requests: bool = False, limit: int = 20, offset: int = 0) -> List[ConversationResponse]:
        """Inbox (accepted) or message requests, most recent first. Empty conversations are hidden."""
        result = await session.execute(
            select(Conversation)
            .join(ConversationParticipant, and_(
                ConversationParticipant.conversation_id == Conversation.id,
                ConversationParticipant.user_id == user_id,
            ))
            .where(ConversationParticipant.is_accepted == (not requests), Conversation.last_message_at.is_not(None))
            .order_by(Conversation.last_message_at.desc())
            .offset(offset)
            .limit(min(limit, MAX_PAGE_SIZE))
        )
        return await self.conversation_responses(list(result.scalars().all()), user_id, session)

    async def get_conversation(self, conversation_id: UUID, user_id: UUID, session: AsyncSession) -> ConversationResponse:
        await self._participants(conversation_id, user_id, session)
        conversation = await session.get(Conversation, conversation_id)
        return (await self.conversation_responses([conversation], user_id, session))[0]

    async def accept_request(self, conversation_id: UUID, user_id: UUID, session: AsyncSession) -> None:
        me, other = await self._participants(conversation_id, user_id, session)
        if me.is_accepted:
            return
        me.is_accepted = True
        await session.commit()
        await publish([user_id, other.user_id], "chat.request_accepted", {"conversation_id": str(conversation_id), "user_id": str(user_id)})

    async def decline_request(self, conversation_id: UUID, user_id: UUID, session: AsyncSession) -> None:
        """Deletes the conversation. The sender isn't told, so a decline looks like an unread request to them."""
        me, _ = await self._participants(conversation_id, user_id, session)
        if me.is_accepted:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only pending message requests can be declined")
        await session.delete(await session.get(Conversation, conversation_id))
        await session.commit()
        await publish(user_id, "chat.conversation_removed", {"conversation_id": str(conversation_id)})

    async def unread_summary(self, user_id: UUID, session: AsyncSession) -> ChatUnreadSummary:
        cp = ConversationParticipant
        unread = await session.execute(
            select(func.count(func.distinct(Message.conversation_id)))
            .join(cp, and_(cp.conversation_id == Message.conversation_id, cp.user_id == user_id))
            .where(
                cp.is_accepted == True,
                Message.sender_id != user_id,
                Message.is_deleted == False,
                Message.created_at > func.coalesce(cp.last_read_at, EPOCH),
            )
        )
        requests = await session.execute(
            select(func.count())
            .select_from(Conversation)
            .join(cp, and_(cp.conversation_id == Conversation.id, cp.user_id == user_id))
            .where(cp.is_accepted == False, Conversation.last_message_at.is_not(None))
        )
        return ChatUnreadSummary(unread_conversations=unread.scalar_one(), requests=requests.scalar_one())

    # Messages

    async def get_messages(self, conversation_id: UUID, user_id: UUID, session: AsyncSession, before: datetime | None = None, limit: int = 50) -> List[MessageResponse]:
        """Newest first. Page back with `before` = created_at of the oldest message you have."""
        await self._participants(conversation_id, user_id, session)
        query = select(Message).where(Message.conversation_id == conversation_id)
        if before:
            query = query.where(Message.created_at < before)
        result = await session.execute(query.order_by(Message.created_at.desc()).limit(min(limit, MAX_PAGE_SIZE)))
        return await self.message_responses(list(result.scalars().all()), user_id, session)

    async def send_message(self, conversation_id: UUID, user_id: UUID, data: MessageCreate, session: AsyncSession) -> MessageResponse:
        content = (data.content or "").strip() or None
        if not content and not data.shared_post_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A message needs content or a shared post")
        me, other = await self._participants(conversation_id, user_id, session)
        if data.shared_post_id:
            post = await session.get(Posts, data.shared_post_id)
            if not post:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
            await ensure_can_view_post(post, user_id, session)

        sent_at = _now()
        message = Message(
            conversation_id=conversation_id,
            sender_id=user_id,
            content=content,
            shared_post_id=data.shared_post_id,
            created_at=sent_at,
        )
        session.add(message)
        (await session.get(Conversation, conversation_id)).last_message_at = sent_at
        # Replying to a request accepts it; your own message counts as read
        me.is_accepted = True
        me.last_read_at = sent_at
        await session.commit()

        for viewer_id, is_request in ((other.user_id, not other.is_accepted), (user_id, False)):
            response = (await self.message_responses([message], viewer_id, session))[0]
            await publish(viewer_id, "chat.message", {"message": response.model_dump(mode="json"), "is_request": is_request})
        return (await self.message_responses([message], user_id, session))[0]

    async def edit_message(self, conversation_id: UUID, message_id: UUID, user_id: UUID, content: str, session: AsyncSession) -> MessageResponse:
        message, other_id = await self._get_own_message(conversation_id, message_id, user_id, session)
        message.content = content.strip()
        message.edited_at = _now()
        await session.commit()
        for viewer_id in (other_id, user_id):
            response = (await self.message_responses([message], viewer_id, session))[0]
            await publish(viewer_id, "chat.message_updated", response.model_dump(mode="json"))
        return (await self.message_responses([message], user_id, session))[0]

    async def delete_message(self, conversation_id: UUID, message_id: UUID, user_id: UUID, session: AsyncSession) -> None:
        """Soft delete: the message stays in the timeline as "deleted" with its content removed."""
        message, other_id = await self._get_own_message(conversation_id, message_id, user_id, session)
        message.is_deleted = True
        message.content = None
        message.shared_post_id = None
        await session.commit()
        await publish([other_id, user_id], "chat.message_deleted", {"id": str(message_id), "conversation_id": str(conversation_id)})

    async def mark_read(self, conversation_id: UUID, user_id: UUID, session: AsyncSession) -> datetime | None:
        """Mark everything up to the latest message as read and send a read receipt to the other person."""
        me, other = await self._participants(conversation_id, user_id, session)
        latest = (await session.execute(
            select(func.max(Message.created_at)).where(Message.conversation_id == conversation_id)
        )).scalar_one()
        if latest and (me.last_read_at is None or latest > me.last_read_at):
            me.last_read_at = latest
            await session.commit()
            await publish([other.user_id, user_id], "chat.read", {
                "conversation_id": str(conversation_id),
                "user_id": str(user_id),
                "last_read_at": latest.isoformat(),
            })
        return me.last_read_at

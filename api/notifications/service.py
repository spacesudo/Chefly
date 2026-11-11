"""Notifications stored in Postgres and pushed live to the user's WebSocket(s)."""

import logging
from datetime import datetime
from typing import Iterable, List
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import delete, func, update
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from api.db.main import async_session_maker
from api.db.models import Community, Notification, NotificationActor, NotificationType, Posts, User
from api.realtime.events import publish

from .schemas import NotificationActor as ActorSummary, NotificationCommunity, NotificationPost, NotificationResponse

logger = logging.getLogger(__name__)

# Types collapsed into a single unread notification per post ("dave and 3 others upvoted ...")
GROUPED_TYPES = {NotificationType.UPVOTE}


def _message(n: Notification, actor: str, post_title: str | None, community_name: str | None) -> str:
    who = actor if n.actor_count <= 1 else f"{actor} and {n.actor_count - 1} other{'s' if n.actor_count > 2 else ''}"
    post = f' "{post_title}"' if post_title else ""
    return {
        NotificationType.FOLLOW: f"{who} started following you",
        NotificationType.UPVOTE: f"{who} upvoted your post{post}",
        NotificationType.COMMENT: f"{who} commented on your post{post}",
        NotificationType.REPLY: f"{who} replied to your comment on{post or ' a post'}",
        NotificationType.JOIN_REQUEST: f"{who} requested to join {community_name}",
        NotificationType.JOIN_APPROVED: f"Your request to join {community_name} was approved",
        NotificationType.ADDED_TO_COMMUNITY: f"{who} added you to {community_name}",
        NotificationType.PROMOTED_TO_ADMIN: f"{who} made you an admin of {community_name}",
    }[n.type]


class NotificationService:

    # Notifications are written in their own session so a failure never rolls back the caller's work
    session_factory = async_session_maker

    async def notify(
        self,
        recipient_ids: UUID | Iterable[UUID],
        type: NotificationType,
        actor_id: UUID | None = None,
        *,
        post_id: UUID | None = None,
        comment_id: UUID | None = None,
        community_id: UUID | None = None,
    ) -> None:
        """Best-effort: create (or group) notifications and push them to live streams. Never raises."""
        recipients = {recipient_ids} if isinstance(recipient_ids, UUID) else set(recipient_ids)
        recipients.discard(actor_id)
        if not recipients:
            return
        try:
            async with self.session_factory() as session:
                notifications = [
                    n for r in recipients
                    if (n := await self._upsert(session, r, type, actor_id, post_id, comment_id, community_id))
                ]
                await session.commit()
                responses = await self.to_responses(notifications, session)
            for notification, response in zip(notifications, responses):
                await publish(notification.recipient_id, "notification", response.model_dump(mode="json"))
        except Exception:
            logger.warning("Failed to send notification", exc_info=True)

    async def retract(self, recipient_id: UUID, type: NotificationType, actor_id: UUID, *, post_id: UUID) -> None:
        """Best-effort: remove an actor from grouped notifications (e.g. an upvote was undone). Never raises.

        The count drops and the latest remaining actor is shown; a group left with no actors is deleted.
        """
        if type not in GROUPED_TYPES or recipient_id == actor_id:
            return
        try:
            async with self.session_factory() as session:
                groups = await self._groups_with_actor(session, recipient_id, type, post_id, actor_id)
                updated, removed = [], []
                for n in groups:
                    await session.execute(
                        delete(NotificationActor).where(
                            NotificationActor.notification_id == n.id, NotificationActor.user_id == actor_id
                        )
                    )
                    remaining = await self._actor_ids(session, n.id)
                    if remaining:
                        n.actor_count, n.actor_id = len(remaining), remaining[0]
                        updated.append(n)
                    else:
                        removed.append(n.id)
                        await session.delete(n)
                await session.commit()
                responses = await self.to_responses(updated, session)
            for response in responses:
                await publish(recipient_id, "notification", response.model_dump(mode="json"))
            for notification_id in removed:
                await publish(recipient_id, "notification.removed", {"id": str(notification_id)})
        except Exception:
            logger.warning("Failed to retract notification", exc_info=True)

    async def _groups_with_actor(self, session, recipient_id, type, post_id, actor_id) -> List[Notification]:
        result = await session.execute(
            select(Notification)
            .join(NotificationActor, NotificationActor.notification_id == Notification.id)
            .where(
                Notification.recipient_id == recipient_id,
                Notification.type == type,
                Notification.post_id == post_id,
                NotificationActor.user_id == actor_id,
            )
        )
        return list(result.scalars().all())

    async def _actor_ids(self, session, notification_id: UUID) -> List[UUID]:
        """Actors in a group, most recent first."""
        result = await session.execute(
            select(NotificationActor.user_id)
            .where(NotificationActor.notification_id == notification_id)
            .order_by(NotificationActor.created_at.desc())
        )
        return list(result.scalars().all())

    async def _upsert(self, session, recipient_id, type, actor_id, post_id, comment_id, community_id) -> Notification | None:
        """Returns the created/updated notification, or None if nothing changed."""
        if type in GROUPED_TYPES:
            if await self._groups_with_actor(session, recipient_id, type, post_id, actor_id):
                return None  # already counted (e.g. repeated upvote)
            result = await session.execute(
                select(Notification).where(
                    Notification.recipient_id == recipient_id,
                    Notification.type == type,
                    Notification.post_id == post_id,
                    Notification.is_read == False,
                )
            )
            existing = result.scalars().first()
            if existing:
                session.add(NotificationActor(notification_id=existing.id, user_id=actor_id))
                await session.flush()
                existing.actor_id = actor_id
                existing.actor_count = len(await self._actor_ids(session, existing.id))
                existing.updated_at = datetime.now()
                return existing
        notification = Notification(
            recipient_id=recipient_id,
            type=type,
            actor_id=actor_id,
            post_id=post_id,
            comment_id=comment_id,
            community_id=community_id,
        )
        session.add(notification)
        if type in GROUPED_TYPES:
            await session.flush()
            session.add(NotificationActor(notification_id=notification.id, user_id=actor_id))
        return notification

    async def to_responses(self, notifications: List[Notification], session: AsyncSession) -> List[NotificationResponse]:
        actor_ids = {n.actor_id for n in notifications if n.actor_id}
        post_ids = {n.post_id for n in notifications if n.post_id}
        community_ids = {n.community_id for n in notifications if n.community_id}

        users = dict((await session.execute(select(User.id, User.username).where(User.id.in_(actor_ids)))).all()) if actor_ids else {}
        posts = dict((await session.execute(select(Posts.id, Posts.title).where(Posts.id.in_(post_ids)))).all()) if post_ids else {}
        communities = dict((await session.execute(select(Community.id, Community.name).where(Community.id.in_(community_ids)))).all()) if community_ids else {}

        responses = []
        for n in notifications:
            actor_name = users.get(n.actor_id, "Someone")
            post_title, community_name = posts.get(n.post_id), communities.get(n.community_id)
            responses.append(NotificationResponse(
                id=n.id,
                type=n.type,
                message=_message(n, actor_name, post_title, community_name),
                is_read=n.is_read,
                actor=ActorSummary(id=n.actor_id, username=actor_name) if n.actor_id in users else None,
                actor_count=n.actor_count,
                post=NotificationPost(id=n.post_id, title=post_title) if post_title else None,
                comment_id=n.comment_id,
                community=NotificationCommunity(id=n.community_id, name=community_name) if community_name else None,
                created_at=n.created_at,
                updated_at=n.updated_at,
            ))
        return responses

    async def get_notifications(self, user_id: UUID, session: AsyncSession, unread_only: bool = False, limit: int = 20, offset: int = 0) -> List[NotificationResponse]:
        try:
            query = select(Notification).where(Notification.recipient_id == user_id)
            if unread_only:
                query = query.where(Notification.is_read == False)
            result = await session.execute(query.order_by(Notification.updated_at.desc()).offset(offset).limit(limit))
            return await self.to_responses(list(result.scalars().all()), session)
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error getting notifications: {e}")

    async def unread_count(self, user_id: UUID, session: AsyncSession) -> int:
        result = await session.execute(
            select(func.count()).select_from(Notification).where(Notification.recipient_id == user_id, Notification.is_read == False)
        )
        return result.scalar_one()

    async def _get_own(self, notification_id: UUID, user_id: UUID, session: AsyncSession) -> Notification:
        notification = await session.get(Notification, notification_id)
        if not notification or notification.recipient_id != user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
        return notification

    async def mark_read(self, notification_id: UUID, user_id: UUID, session: AsyncSession) -> None:
        notification = await self._get_own(notification_id, user_id, session)
        notification.is_read = True
        await session.commit()

    async def mark_all_read(self, user_id: UUID, session: AsyncSession) -> int:
        result = await session.execute(
            update(Notification).where(Notification.recipient_id == user_id, Notification.is_read == False).values(is_read=True)
        )
        await session.commit()
        return result.rowcount

    async def delete_notification(self, notification_id: UUID, user_id: UUID, session: AsyncSession) -> None:
        await self._get_own(notification_id, user_id, session)
        await session.execute(delete(Notification).where(Notification.id == notification_id))
        await session.commit()

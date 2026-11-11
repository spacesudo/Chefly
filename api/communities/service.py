from contextlib import asynccontextmanager
from datetime import datetime
from typing import List
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import delete, func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from api.communities.access import (
    ensure_can_view_community,
    get_community_or_404,
    get_membership,
)
from api.db.models import (
    Community,
    CommunityJoinRequest,
    CommunityMember,
    CommunityRole,
    JoinRequestStatus,
    NotificationType,
    Posts,
    User,
)
from api.notifications.service import NotificationService
from api.posts.schemas import PostCreate
from api.posts.service import PostService

from .schemas import (
    CommunityCreate,
    CommunityEdit,
    JoinRequestResponse,
    MemberResponse,
)

MANAGERS = {CommunityRole.OWNER, CommunityRole.ADMIN}


@asynccontextmanager
async def _handle_errors(session: AsyncSession, action: str):
    try:
        yield
    except HTTPException:
        await session.rollback()
        raise
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error {action}: {e}")


class CommunityService:

    post_service = PostService()
    notification_service = NotificationService()

    async def _require_role(self, community_id: UUID, user_id: UUID, session: AsyncSession, roles: set[CommunityRole]) -> CommunityMember:
        member = await get_membership(community_id, user_id, session)
        if not member or member.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to do this")
        return member

    async def _ensure_name_available(self, name: str, session: AsyncSession) -> None:
        result = await session.execute(select(Community.id).where(func.lower(Community.name) == name.lower()))
        if result.first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Community name already taken")

    async def _add_member(self, community: Community, user_id: UUID, session: AsyncSession, role: CommunityRole = CommunityRole.MEMBER) -> CommunityMember:
        member = CommunityMember(community_id=community.id, user_id=user_id, role=role)
        session.add(member)
        community.members_count += 1
        return member

    async def _manager_ids(self, community_id: UUID, session: AsyncSession) -> list[UUID]:
        result = await session.execute(
            select(CommunityMember.user_id).where(
                CommunityMember.community_id == community_id, CommunityMember.role.in_(MANAGERS)
            )
        )
        return list(result.scalars().all())

    # Communities

    async def create_community(self, user_id: UUID, data: CommunityCreate, session: AsyncSession) -> Community:
        async with _handle_errors(session, "creating community"):
            await self._ensure_name_available(data.name, session)
            community = Community(**data.model_dump(), owner_id=user_id)
            session.add(community)
            await session.flush()
            await self._add_member(community, user_id, session, CommunityRole.OWNER)
            await session.commit()
            await session.refresh(community)
            return community

    async def list_communities(self, session: AsyncSession, q: str | None = None, limit: int = 20, offset: int = 0) -> List[Community]:
        async with _handle_errors(session, "listing communities"):
            query = select(Community)
            if q:
                query = query.where(Community.name.ilike(f"%{q}%"))
            result = await session.execute(
                query.order_by(Community.members_count.desc(), Community.created_at.desc()).offset(offset).limit(limit)
            )
            return list(result.scalars().all())

    async def get_user_communities(self, user_id: UUID, session: AsyncSession) -> List[tuple[Community, CommunityRole]]:
        async with _handle_errors(session, "getting user communities"):
            result = await session.execute(
                select(Community, CommunityMember.role)
                .join(CommunityMember, CommunityMember.community_id == Community.id)
                .where(CommunityMember.user_id == user_id)
                .order_by(CommunityMember.created_at.desc())
            )
            return [(community, role) for community, role in result.all()]

    async def get_community(self, community_id: UUID, user_id: UUID, session: AsyncSession) -> tuple[Community, CommunityRole | None]:
        async with _handle_errors(session, "getting community"):
            community = await get_community_or_404(community_id, session)
            member = await get_membership(community_id, user_id, session)
            return community, member.role if member else None

    async def edit_community(self, community_id: UUID, user_id: UUID, data: CommunityEdit, session: AsyncSession) -> Community:
        async with _handle_errors(session, "editing community"):
            community = await get_community_or_404(community_id, session)
            await self._require_role(community_id, user_id, session, MANAGERS)
            updates = data.model_dump(exclude_none=True)
            if "name" in updates and updates["name"].lower() != community.name.lower():
                await self._ensure_name_available(updates["name"], session)
            for key, value in updates.items():
                setattr(community, key, value)
            community.updated_at = datetime.now()
            await session.commit()
            await session.refresh(community)
            return community

    async def delete_community(self, community_id: UUID, user_id: UUID, session: AsyncSession) -> None:
        async with _handle_errors(session, "deleting community"):
            community = await get_community_or_404(community_id, session)
            await self._require_role(community_id, user_id, session, {CommunityRole.OWNER})
            await self.post_service.delete_posts_with_dependents(select(Posts.id).where(Posts.community_id == community_id), session)
            await session.execute(delete(CommunityJoinRequest).where(CommunityJoinRequest.community_id == community_id))
            await session.execute(delete(CommunityMember).where(CommunityMember.community_id == community_id))
            await session.delete(community)
            await session.commit()

    # Membership

    async def join_community(self, community_id: UUID, user_id: UUID, session: AsyncSession) -> dict:
        async with _handle_errors(session, "joining community"):
            community = await get_community_or_404(community_id, session)
            if await get_membership(community_id, user_id, session):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You are already a member of this community")

            if not community.is_private:
                await self._add_member(community, user_id, session)
                await session.commit()
                return {"status": "joined", "message": "Joined community successfully"}

            result = await session.execute(
                select(CommunityJoinRequest).where(
                    CommunityJoinRequest.community_id == community_id,
                    CommunityJoinRequest.user_id == user_id,
                )
            )
            request = result.scalar_one_or_none()
            if request and request.status == JoinRequestStatus.PENDING:
                return {"status": "requested", "message": "Join request already pending"}
            if request:
                request.status = JoinRequestStatus.PENDING
                request.created_at = datetime.now()
            else:
                session.add(CommunityJoinRequest(community_id=community_id, user_id=user_id))
            await session.commit()
            await self.notification_service.notify(
                await self._manager_ids(community_id, session), NotificationType.JOIN_REQUEST, user_id, community_id=community_id
            )
            return {"status": "requested", "message": "Join request sent"}

    async def leave_community(self, community_id: UUID, user_id: UUID, session: AsyncSession) -> None:
        async with _handle_errors(session, "leaving community"):
            community = await get_community_or_404(community_id, session)
            member = await get_membership(community_id, user_id, session)
            if not member:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You are not a member of this community")
            if member.role == CommunityRole.OWNER:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The owner cannot leave; delete the community instead")
            await session.delete(member)
            community.members_count -= 1
            await session.commit()

    async def get_members(self, community_id: UUID, user_id: UUID, session: AsyncSession, limit: int = 50, offset: int = 0) -> List[MemberResponse]:
        async with _handle_errors(session, "getting members"):
            community = await get_community_or_404(community_id, session)
            await ensure_can_view_community(community, user_id, session)
            result = await session.execute(
                select(CommunityMember, User.username)
                .join(User, User.id == CommunityMember.user_id)
                .where(CommunityMember.community_id == community_id)
                .order_by(CommunityMember.created_at)
                .offset(offset)
                .limit(limit)
            )
            return [
                MemberResponse(user_id=m.user_id, username=username, role=m.role, joined_at=m.created_at)
                for m, username in result.all()
            ]

    async def add_member(self, community_id: UUID, actor_id: UUID, target_id: UUID, session: AsyncSession) -> CommunityMember:
        async with _handle_errors(session, "adding member"):
            community = await get_community_or_404(community_id, session)
            await self._require_role(community_id, actor_id, session, MANAGERS)
            if not await session.get(User, target_id):
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
            if await get_membership(community_id, target_id, session):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User is already a member")

            member = await self._add_member(community, target_id, session)
            result = await session.execute(
                select(CommunityJoinRequest).where(
                    CommunityJoinRequest.community_id == community_id,
                    CommunityJoinRequest.user_id == target_id,
                    CommunityJoinRequest.status == JoinRequestStatus.PENDING,
                )
            )
            pending = result.scalar_one_or_none()
            if pending:
                pending.status = JoinRequestStatus.APPROVED
            await session.commit()
            await session.refresh(member)
            await self.notification_service.notify(target_id, NotificationType.ADDED_TO_COMMUNITY, actor_id, community_id=community_id)
            return member

    async def remove_member(self, community_id: UUID, actor_id: UUID, target_id: UUID, session: AsyncSession) -> None:
        async with _handle_errors(session, "removing member"):
            community = await get_community_or_404(community_id, session)
            actor = await self._require_role(community_id, actor_id, session, MANAGERS)
            target = await get_membership(community_id, target_id, session)
            if not target:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
            if target.role == CommunityRole.OWNER:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The owner cannot be removed")
            if target.role == CommunityRole.ADMIN and actor.role != CommunityRole.OWNER:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the owner can remove admins")
            await session.delete(target)
            community.members_count -= 1
            await session.commit()

    async def update_role(self, community_id: UUID, actor_id: UUID, target_id: UUID, role: CommunityRole, session: AsyncSession) -> CommunityMember:
        async with _handle_errors(session, "updating role"):
            await get_community_or_404(community_id, session)
            await self._require_role(community_id, actor_id, session, {CommunityRole.OWNER})
            if role == CommunityRole.OWNER:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role must be admin or member")
            target = await get_membership(community_id, target_id, session)
            if not target:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
            if target.role == CommunityRole.OWNER:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The owner's role cannot be changed")
            promoted = role == CommunityRole.ADMIN and target.role != CommunityRole.ADMIN
            target.role = role
            await session.commit()
            await session.refresh(target)
            if promoted:
                await self.notification_service.notify(target_id, NotificationType.PROMOTED_TO_ADMIN, actor_id, community_id=community_id)
            return target

    # Join requests

    async def get_join_requests(self, community_id: UUID, actor_id: UUID, session: AsyncSession) -> List[JoinRequestResponse]:
        async with _handle_errors(session, "getting join requests"):
            await get_community_or_404(community_id, session)
            await self._require_role(community_id, actor_id, session, MANAGERS)
            result = await session.execute(
                select(CommunityJoinRequest, User.username)
                .join(User, User.id == CommunityJoinRequest.user_id)
                .where(
                    CommunityJoinRequest.community_id == community_id,
                    CommunityJoinRequest.status == JoinRequestStatus.PENDING,
                )
                .order_by(CommunityJoinRequest.created_at)
            )
            return [JoinRequestResponse(**req.model_dump(), username=username) for req, username in result.all()]

    async def review_join_request(self, community_id: UUID, request_id: UUID, actor_id: UUID, approve: bool, session: AsyncSession) -> CommunityJoinRequest:
        async with _handle_errors(session, "reviewing join request"):
            community = await get_community_or_404(community_id, session)
            await self._require_role(community_id, actor_id, session, MANAGERS)
            request = await session.get(CommunityJoinRequest, request_id)
            if not request or request.community_id != community_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Join request not found")
            if request.status != JoinRequestStatus.PENDING:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Join request already reviewed")

            if approve:
                request.status = JoinRequestStatus.APPROVED
                if not await get_membership(community_id, request.user_id, session):
                    await self._add_member(community, request.user_id, session)
            else:
                request.status = JoinRequestStatus.REJECTED
            await session.commit()
            await session.refresh(request)
            if approve:
                await self.notification_service.notify(request.user_id, NotificationType.JOIN_APPROVED, actor_id, community_id=community_id)
            return request

    # Posts

    async def create_post(self, community_id: UUID, user_id: UUID, data: PostCreate, session: AsyncSession) -> Posts:
        async with _handle_errors(session, "creating community post"):
            await get_community_or_404(community_id, session)
            if not await get_membership(community_id, user_id, session):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You must be a member of this community")
            data.author_id = str(user_id)
            return await self.post_service.create_post(data, session, community_id=community_id)

    async def get_posts(self, community_id: UUID, user_id: UUID, session: AsyncSession, limit: int = 20, offset: int = 0) -> List[Posts]:
        async with _handle_errors(session, "getting community posts"):
            community = await get_community_or_404(community_id, session)
            await ensure_can_view_community(community, user_id, session)
            result = await session.execute(
                select(Posts)
                .where(Posts.community_id == community_id)
                .order_by(Posts.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            return list(result.scalars().all())

    async def delete_post(self, community_id: UUID, post_id: UUID, user_id: UUID, session: AsyncSession) -> None:
        async with _handle_errors(session, "deleting community post"):
            post = await session.get(Posts, post_id)
            if not post or post.community_id != community_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found in this community")
            if post.author_id != user_id:
                await self._require_role(community_id, user_id, session, MANAGERS)
            await self.post_service.delete_posts_with_dependents([post_id], session)
            await session.commit()

"""Community membership and visibility rules shared across posts, comments, votes and bookmarks."""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from api.db.models import Community, CommunityMember, Posts


def _private_community_ids():
    return select(Community.id).where(Community.is_private == True)


def public_posts_filter():
    """Posts outside any community, or in a public community."""
    return or_(Posts.community_id.is_(None), Posts.community_id.notin_(_private_community_ids()))


def visible_posts_filter(user_id: UUID):
    """Public posts plus posts from private communities the user belongs to."""
    return or_(
        public_posts_filter(),
        Posts.community_id.in_(select(CommunityMember.community_id).where(CommunityMember.user_id == user_id)),
    )


async def get_community_or_404(community_id: UUID, session: AsyncSession) -> Community:
    result = await session.execute(select(Community).where(Community.id == community_id))
    community = result.scalar_one_or_none()
    if not community:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Community not found")
    return community


async def get_membership(community_id: UUID, user_id: UUID, session: AsyncSession) -> CommunityMember | None:
    result = await session.execute(
        select(CommunityMember).where(
            CommunityMember.community_id == community_id,
            CommunityMember.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def ensure_can_view_community(community: Community, user_id: UUID, session: AsyncSession) -> None:
    if community.is_private and not await get_membership(community.id, user_id, session):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This community is private")


async def ensure_can_view_post(post: Posts, user_id: UUID, session: AsyncSession) -> None:
    if post.community_id is None:
        return
    community = await get_community_or_404(post.community_id, session)
    await ensure_can_view_community(community, user_id, session)


async def ensure_can_participate(post: Posts, user_id: UUID, session: AsyncSession) -> None:
    """Replying to a community post requires membership in that community."""
    if post.community_id is None:
        return
    if not await get_membership(post.community_id, user_id, session):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You must be a member of this community")

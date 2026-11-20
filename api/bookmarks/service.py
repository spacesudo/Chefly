from typing import List
from uuid import UUID

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from api.communities.access import ensure_can_view_post, visible_posts_filter
from api.db.models import Bookmark, Posts
from api.errors import BookmarkNotFound
from api.posts.algorithm import safe_record_interaction
from api.posts.service import PostService


class BookmarkService:

    post_service = PostService()

    async def _get_bookmark(self, user_id: UUID, post_id: UUID, session: AsyncSession) -> Bookmark | None:
        result = await session.execute(
            select(Bookmark).where(Bookmark.user_id == user_id, Bookmark.post_id == post_id)
        )
        return result.scalar_one_or_none()

    async def add_bookmark(self, user_id: UUID, post_id: UUID, session: AsyncSession) -> Bookmark:
        post = await self.post_service.get_post_by_id(str(post_id), session)
        await ensure_can_view_post(post, user_id, session)

        existing = await self._get_bookmark(user_id, post_id, session)
        if existing:
            return existing

        bookmark = Bookmark(user_id=user_id, post_id=post_id)
        session.add(bookmark)
        await session.commit()
        await session.refresh(bookmark)
        await safe_record_interaction(
            user_id=user_id,
            post_id=post.id,
            interaction_type="bookmarks",
            author_id=post.author_id,
            tags=await self.post_service.tag_service.get_tag_names(post.id, session),
        )
        return bookmark

    async def remove_bookmark(self, user_id: UUID, post_id: UUID, session: AsyncSession) -> None:
        bookmark = await self._get_bookmark(user_id, post_id, session)
        if not bookmark:
            raise BookmarkNotFound()

        post = await self.post_service.get_post_by_id(str(post_id), session)
        await session.delete(bookmark)
        await session.commit()
        await safe_record_interaction(
            user_id=user_id,
            post_id=post.id,
            interaction_type="unbookmarks",
            author_id=post.author_id,
            mark_viewed=False,
            tags=await self.post_service.tag_service.get_tag_names(post.id, session),
        )

    async def get_bookmarked_posts(self, user_id: UUID, session: AsyncSession, limit: int = 20, offset: int = 0) -> List[Posts]:
        result = await session.execute(
            select(Posts)
            .join(Bookmark, Bookmark.post_id == Posts.id)
            .where(Bookmark.user_id == user_id, visible_posts_filter(user_id))
            .order_by(Bookmark.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def is_bookmarked(self, user_id: UUID, post_id: UUID, session: AsyncSession) -> bool:
        return await self._get_bookmark(user_id, post_id, session) is not None

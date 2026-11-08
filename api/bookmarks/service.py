from typing import List
from uuid import UUID

from fastapi import HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from api.db.models import Bookmark, Posts
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
        try:
            post = await self.post_service.get_post_by_id(str(post_id), session)

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
            )
            return bookmark
        except HTTPException:
            await session.rollback()
            raise
        except Exception as e:
            await session.rollback()
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error adding bookmark: {e}")

    async def remove_bookmark(self, user_id: UUID, post_id: UUID, session: AsyncSession) -> None:
        try:
            bookmark = await self._get_bookmark(user_id, post_id, session)
            if not bookmark:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bookmark not found")

            post = await self.post_service.get_post_by_id(str(post_id), session)
            await session.delete(bookmark)
            await session.commit()
            await safe_record_interaction(
                user_id=user_id,
                post_id=post.id,
                interaction_type="unbookmarks",
                author_id=post.author_id,
                mark_viewed=False,
            )
        except HTTPException:
            await session.rollback()
            raise
        except Exception as e:
            await session.rollback()
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error removing bookmark: {e}")

    async def get_bookmarked_posts(self, user_id: UUID, session: AsyncSession, limit: int = 20, offset: int = 0) -> List[Posts]:
        try:
            result = await session.execute(
                select(Posts)
                .join(Bookmark, Bookmark.post_id == Posts.id)
                .where(Bookmark.user_id == user_id)
                .order_by(Bookmark.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            return list(result.scalars().all())
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error getting bookmarks: {e}")

    async def is_bookmarked(self, user_id: UUID, post_id: UUID, session: AsyncSession) -> bool:
        try:
            return await self._get_bookmark(user_id, post_id, session) is not None
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error getting bookmark status: {e}")

from datetime import datetime
from typing import List
from uuid import UUID

from sqlalchemy import delete
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from api.communities.access import public_posts_filter, visible_posts_filter
from api.db.models import Bookmark, Comments, Posts, Votes
from api.errors import InvalidId, PostNotFound
from api.follows.service import FollowService
from api.posts.schemas import PostCreate, PostEdit
from api.tags.service import TagService

class PostService:
    
    follow_service = FollowService()
    tag_service = TagService()
    
    async def create_post(self, post_data: PostCreate, session: AsyncSession, community_id: UUID | None = None) -> Posts:
        new_post = Posts(**post_data.model_dump(exclude={"tags"}), community_id=community_id)
        session.add(new_post)
        await session.flush()
        await self.tag_service.set_post_tags(new_post.id, post_data.tags, session)
        await session.commit()
        await session.refresh(new_post)
        return new_post
        
    async def get_post_by_id(self, post_id: str, session: AsyncSession) -> Posts | None:
        try:
            post_uuid = UUID(str(post_id))
        except ValueError:
            raise InvalidId("Invalid post ID")
        post = (await session.execute(select(Posts).where(Posts.id == post_uuid))).scalar_one_or_none()
        if not post:
            raise PostNotFound()
        return post
        
    async def delete_posts_with_dependents(self, post_ids, session: AsyncSession) -> None:
        """Delete posts along with their votes, comments, bookmarks and tags. Caller commits."""
        await self.tag_service.remove_tags_for_posts(post_ids, session)
        await session.execute(delete(Votes).where(Votes.post_id.in_(post_ids)))
        await session.execute(delete(Comments).where(Comments.post_id.in_(post_ids)))
        await session.execute(delete(Bookmark).where(Bookmark.post_id.in_(post_ids)))
        await session.execute(delete(Posts).where(Posts.id.in_(post_ids)))

    async def delete_post(self, post_id: str, session: AsyncSession) -> None:
        post = await self.get_post_by_id(post_id, session)
        await self.delete_posts_with_dependents([post.id], session)
        await session.commit()
        
    async def get_all_posts(self, user_id: UUID, session: AsyncSession) -> List[Posts]:
        result = await session.execute(select(Posts).where(visible_posts_filter(user_id)))
        return list(result.scalars().all())
        
    async def edit_post(self, post_id: str, post_data: PostEdit, session: AsyncSession) -> Posts:
        post = await self.get_post_by_id(post_id, session)
        for key, value in post_data.model_dump(exclude={"tags"}, exclude_none=True).items():
            setattr(post, key, value)
        if post_data.tags is not None:
            await self.tag_service.set_post_tags(post.id, post_data.tags, session)
        post.updated_at = datetime.now()
        await session.commit()
        await session.refresh(post)
        return post
        
    async def following_feed(self, user_id: UUID, session: AsyncSession, limit: int = 20, offset: int = 0) -> List[Posts]:
        followers = await self.follow_service.get_following(user_id, session)
        following_ids = [following.id for following in followers]
        
        result = await session.execute(
            select(Posts)
            .where(Posts.author_id.in_(following_ids), visible_posts_filter(user_id))
            .order_by(Posts.created_at.desc())
            .limit(limit)
            .offset(offset) 
        )
        posts = result.scalars().all()
        
        return list(posts) if posts else await self.feed(session, limit, offset)
        
    async def feed(self, session: AsyncSession, limit: int = 20, offset: int = 0) -> List[Posts]:
        result = await session.execute(
            select(Posts)
            .where(public_posts_filter())
            .order_by(Posts.created_at.desc())
            .order_by(Posts.upvote_count.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

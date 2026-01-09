from typing import List
from uuid import UUID

from fastapi import HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from api.db.models import Posts
from api.posts.schemas import PostCreate, PostEdit

class PostService:
    async def create_post(self, post_data: PostCreate, session: AsyncSession) -> Posts:
        try:
            new_post = Posts(**post_data.model_dump())
            session.add(new_post)
            await session.commit()
            await session.refresh(new_post)
            return new_post
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error creating post: {e}")
        
    async def get_post_by_id(self, post_id: str, session: AsyncSession) -> Posts | None:
        try:
            result = await session.execute(select(Posts).where(Posts.id == UUID(post_id)))
            post = result.scalar_one_or_none()
            if not post:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
            return post
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid post ID format")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error getting post by id: {e}")
        
    async def delete_post(self, post_id: str, session: AsyncSession) -> None:
        try:
            post = await self.get_post_by_id(post_id, session)
            if post:
                await session.delete(post)
                await session.commit()
        except HTTPException:
            raise
        except Exception as e:
            await session.rollback()
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error deleting post: {e}")
        
    async def get_all_posts(self, session: AsyncSession) -> List[Posts]:
        try:
            result = await session.execute(select(Posts))
            posts = result.scalars().all()
            return list(posts)
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error getting all posts: {e}")
        
    async def edit_post(self, post_id: str, post_data: PostEdit, session: AsyncSession) -> Posts:
        try:
            post = await self.get_post_by_id(post_id, session)
            if post:
                for key, value in post_data.model_dump().items():
                    if value is not None:
                        setattr(post, key, value)
                await session.commit()
                await session.refresh(post)
                return post
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
        
        except Exception as e:
            await session.rollback()
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error editing post: {e}")

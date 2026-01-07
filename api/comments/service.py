from typing import List
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm.attributes import set_committed_value
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from api.db.models import Comments, Posts
from api.posts.service import PostService

from .schemas import CommentCreate, CommentEdit, CommentResponse

class CommentService:
    
    post_service = PostService()
    
    async def create_comment(self, comment_data: CommentCreate, session: AsyncSession) -> Comments:
        try:
            if comment_data.parent_id:
                parent_comment = await self.get_comment_by_id(comment_data.parent_id, session)
                if not parent_comment:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent comment not found")
                if parent_comment.post_id != comment_data.post_id:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Parent comment does not belong to the same post")
            post = await self.post_service.get_post_by_id(comment_data.post_id, session)
            if post:
                post.comment_count += 1
                await session.commit()
                await session.refresh(post)
                
            new_comment = Comments(**comment_data.model_dump())
            session.add(new_comment)
            await session.commit()
            await session.refresh(new_comment)
            return new_comment
        
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error creating comment: {e}")
        
    async def load_replies_recursively(self, comment: Comments, session: AsyncSession, depth: int = 0, max_depth: int = 3):
        if depth >= max_depth:
            comment.replies = []
            return

        result = await session.execute(
            select(Comments)
            .where(Comments.parent_id == comment.id)
            .where(Comments.is_deleted == False)
            .order_by(Comments.created_at)
        )
        replies = list(result.scalars().all())
        comment.replies = replies

        for reply in replies:
            await self.load_replies_recursively(
                reply,
                session,
                depth + 1,
                max_depth
            )
            
    async def get_comments_by_post(
    self, 
    post_id: UUID, 
    session: AsyncSession, 
    include_replies: bool = True
) -> List[Comments]:
        # Get ALL comments for the post in one query
        result = await session.execute(
            select(Comments)
            .where(Comments.post_id == post_id)
            .where(Comments.is_deleted == False)
            .order_by(Comments.created_at)
        )
        all_comments = list(result.scalars().all())
        
        if not include_replies:
            return [c for c in all_comments if c.parent_id is None]
        
        # Build comment tree
        comment_dict = {comment.id: comment for comment in all_comments}
        
        # Initialize empty replies list for each comment
        for comment in all_comments:
            set_committed_value(comment, 'replies', [])
        
        # Build the tree structure
        top_level_comments = []
        for comment in all_comments:
            if comment.parent_id is None:
                top_level_comments.append(comment)
            else:
                parent = comment_dict.get(comment.parent_id)
                if parent:
                    # Get current replies and append
                    current_replies = getattr(parent, 'replies', [])
                    current_replies.append(comment)
                    set_committed_value(parent, 'replies', current_replies)
        
        return top_level_comments
        
    async def get_replies_to_comment(self, comment_id: UUID, session: AsyncSession) -> List[Comments]:
        result = await session.execute(
            select(Comments).where(Comments.parent_id == comment_id)
            .where(Comments.is_deleted == False)
            .order_by(Comments.created_at)
        )
        replies = result.scalars().all()
        return list(replies)
    
    async def get_comment_by_id(self, comment_id: UUID, session: AsyncSession) -> Comments:
        try:
            result = await session.execute(select(Comments).where(Comments.id == comment_id))
            comment = result.scalar_one_or_none()
            if not comment:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
            return comment
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error getting comment: {e}")

    async def edit_comment(
        self, 
        comment_id: UUID, 
        comment_data: CommentEdit, 
        user_id: UUID,  
        session: AsyncSession
    ) -> Comments:
        try:
            comment = await self.get_comment_by_id(comment_id, session)
            
            if comment.user_id != user_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN, 
                    detail="You are not the author of this comment"
                )
            
            if comment_data.content is not None:
                comment.content = comment_data.content
            
            await session.commit()
            await session.refresh(comment)
            return comment
        
        except HTTPException:
            raise
        except Exception as e:
            await session.rollback()
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error editing comment: {e}")

    async def delete_comment(
        self, 
        comment_id: UUID, 
        user_id: UUID,
        session: AsyncSession
    ) -> None:
        try:
            comment = await self.get_comment_by_id(comment_id, session)
            
            if comment.user_id != user_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You are not the author of this comment"
                )
            
            comment.is_deleted = True
            await session.commit()
        except HTTPException:
            await session.rollback()
            raise
        except Exception as e:
            await session.rollback()
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error deleting comment: {e}")
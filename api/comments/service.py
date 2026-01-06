from .schemas import CommentCreate, CommentEdit, CommentResponse
from api.db.models import Comments
from sqlmodel.ext.asyncio.session import AsyncSession
from fastapi import HTTPException, status
from uuid import UUID
from sqlmodel import select
from typing import List

class CommentService:
    async def create_comment(self, comment_data: CommentCreate, session: AsyncSession) -> Comments:
        try:
            if comment_data.parent_id:
                parent_comment = await self.get_comment_by_id(comment_data.parent_id, session)
                if not parent_comment:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent comment not found")
                if parent_comment.post_id != comment_data.post_id:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Parent comment does not belong to the same post")
            new_comment = Comments(**comment_data.model_dump())
            session.add(new_comment)
            await session.commit()
            await session.refresh(new_comment)
            return new_comment
        
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error creating comment: {e}")
        
    async def get_comments_by_post(self, post_id: UUID, session: AsyncSession, include_replies: bool = True) -> List[Comments]:
        result = await session.execute(
            select(Comments).where(Comments.post_id == post_id)
            .where(Comments.parent_id.is_(None))
            .where(Comments.is_deleted == False)
            .order_by(Comments.created_at)
        )
        top_comments = result.scalars().all()
        
        if include_replies:
            for comment in top_comments:
                await session.refresh(comment, ["replies"])
                
        return list(top_comments)
    
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
from typing import List
from uuid import UUID

from sqlalchemy.orm.attributes import set_committed_value
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from api.communities.access import ensure_can_participate, ensure_can_view_post
from api.db.models import Comments, NotificationType, Posts
from api.errors import CommentNotFound, NotCommentAuthor, ParentCommentMismatch, ParentCommentNotFound
from api.notifications.service import NotificationService
from api.posts.algorithm import safe_record_interaction
from api.posts.service import PostService

from .schemas import CommentCreate, CommentEdit, CommentResponse

class CommentService:
    
    post_service = PostService()
    notification_service = NotificationService()
    
    async def create_comment(self, comment_data: CommentCreate, session: AsyncSession) -> Comments:
        parent_comment = None
        if comment_data.parent_id:
            try:
                parent_comment = await self.get_comment_by_id(comment_data.parent_id, session)
            except CommentNotFound:
                raise ParentCommentNotFound()
            if parent_comment.post_id != comment_data.post_id:
                raise ParentCommentMismatch()
        post = await self.post_service.get_post_by_id(str(comment_data.post_id), session)
        await ensure_can_participate(post, comment_data.user_id, session)

        new_comment = Comments(**comment_data.model_dump())
        session.add(new_comment)
        post.comment_count += 1
        await session.commit()
        await session.refresh(new_comment)
        await session.refresh(post)

        await safe_record_interaction(
            user_id=new_comment.user_id,
            post_id=post.id,
            interaction_type="comments",
            author_id=post.author_id,
            tags=await self.post_service.tag_service.get_tag_names(post.id, session),
        )
        await self._notify_comment(new_comment, post, parent_comment)
        return new_comment
        
    async def _notify_comment(self, comment: Comments, post: Posts, parent: Comments | None) -> None:
        """Reply -> parent comment's author; post author gets a comment notification unless they're the one replied to."""
        refs = dict(post_id=post.id, comment_id=comment.id)
        if parent:
            await self.notification_service.notify(parent.user_id, NotificationType.REPLY, comment.user_id, **refs)
        if not parent or parent.user_id != post.author_id:
            await self.notification_service.notify(post.author_id, NotificationType.COMMENT, comment.user_id, **refs)

    async def ensure_can_view(self, post_id: UUID, user_id: UUID, session: AsyncSession) -> None:
        post = await self.post_service.get_post_by_id(str(post_id), session)
        await ensure_can_view_post(post, user_id, session)

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
        comment = (await session.execute(select(Comments).where(Comments.id == comment_id))).scalar_one_or_none()
        if not comment:
            raise CommentNotFound()
        return comment

    async def edit_comment(
        self, 
        comment_id: UUID, 
        comment_data: CommentEdit, 
        user_id: UUID,  
        session: AsyncSession
    ) -> Comments:
        comment = await self.get_comment_by_id(comment_id, session)
        if comment.user_id != user_id:
            raise NotCommentAuthor()
        if comment_data.content is not None:
            comment.content = comment_data.content
        await session.commit()
        await session.refresh(comment)
        return comment

    async def delete_comment(
        self, 
        comment_id: UUID, 
        user_id: UUID,
        session: AsyncSession
    ) -> None:
        comment = await self.get_comment_by_id(comment_id, session)
        if comment.user_id != user_id:
            raise NotCommentAuthor()
        comment.is_deleted = True
        await session.commit()
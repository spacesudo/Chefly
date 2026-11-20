from typing import List
from uuid import UUID

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from api.communities.access import ensure_can_view_post
from api.db.models import NotificationType, Posts, Votes, VoteType
from api.errors import NotVoteOwner, VoteNotFound
from api.notifications.service import NotificationService
from api.posts.algorithm import safe_record_interaction
from api.posts.service import PostService

from .schemas import VoteCreate, VoteResponse


class VoteService:
    
    post_service = PostService()
    notification_service = NotificationService()

    async def _record_vote_interaction(
        self, user_id: UUID, post: Posts, vote_type: VoteType, session: AsyncSession
    ) -> None:
        interaction_type = "upvotes" if vote_type == VoteType.UPVOTE else "downvotes"
        await safe_record_interaction(
            user_id=user_id,
            post_id=post.id,
            interaction_type=interaction_type,
            author_id=post.author_id,
            tags=await self.post_service.tag_service.get_tag_names(post.id, session),
        )
        if vote_type == VoteType.UPVOTE:
            await self.notification_service.notify(post.author_id, NotificationType.UPVOTE, user_id, post_id=post.id)

    async def _retract_upvote_notification(self, user_id: UUID, post: Posts) -> None:
        await self.notification_service.retract(post.author_id, NotificationType.UPVOTE, user_id, post_id=post.id)
    
    async def create_vote(self, vote_data: VoteCreate, session: AsyncSession) -> Votes:
        result = await session.execute(
            select(Votes).where(
                Votes.post_id == vote_data.post_id,
                Votes.user_id == vote_data.user_id
            )
        )
        existing_vote = result.scalar_one_or_none()
        
        post = await self.post_service.get_post_by_id(str(vote_data.post_id), session)
        await ensure_can_view_post(post, vote_data.user_id, session)
        
        if existing_vote:
            if existing_vote.vote_type == vote_data.vote_type:
                return existing_vote
            
            old_vote_type = existing_vote.vote_type
            existing_vote.vote_type = vote_data.vote_type
            
            if old_vote_type == VoteType.UPVOTE:
                post.upvote_count -= 1
            else:
                post.downvote_count -= 1
            
            if vote_data.vote_type == VoteType.UPVOTE:
                post.upvote_count += 1
            else:
                post.downvote_count += 1
            
            await session.commit()
            await session.refresh(existing_vote)
            await session.refresh(post)
            if old_vote_type == VoteType.UPVOTE:
                await self._retract_upvote_notification(vote_data.user_id, post)
            await self._record_vote_interaction(
                vote_data.user_id, post, vote_data.vote_type, session
            )
            return existing_vote

        # Create new vote
        new_vote = Votes(**vote_data.model_dump())
        session.add(new_vote)
        
        # Update post vote count
        if vote_data.vote_type == VoteType.UPVOTE:
            post.upvote_count += 1
        else:
            post.downvote_count += 1
        
        await session.commit()
        await session.refresh(new_vote)
        await session.refresh(post)
        await self._record_vote_interaction(
            vote_data.user_id, post, vote_data.vote_type, session
        )
        return new_vote
               
    async def get_vote_by_id(self, vote_id: UUID, session: AsyncSession) -> Votes:
        vote = (await session.execute(select(Votes).where(Votes.id == vote_id))).scalar_one_or_none()
        if not vote:
            raise VoteNotFound()
        return vote
        
    async def delete_vote(self, vote_id: UUID, user_id: UUID, session: AsyncSession) -> None:
        """Remove your own vote. The post's counts and the vote row change in one commit."""
        vote = await self.get_vote_by_id(vote_id, session)
        if vote.user_id != user_id:
            raise NotVoteOwner()
        post = await self.post_service.get_post_by_id(str(vote.post_id), session)
        was_upvote = vote.vote_type == VoteType.UPVOTE
        if was_upvote:
            post.upvote_count -= 1
        else:
            post.downvote_count -= 1
        await session.delete(vote)
        await session.commit()
        await session.refresh(post)

        await safe_record_interaction(
            user_id=user_id,
            post_id=post.id,
            interaction_type="downvotes" if was_upvote else "upvotes",
            author_id=post.author_id,
            tags=await self.post_service.tag_service.get_tag_names(post.id, session),
        )
        if was_upvote:
            await self._retract_upvote_notification(user_id, post)
        
    async def get_votes_by_post(self, post_id: UUID, user_id: UUID, session: AsyncSession) -> List[Votes]:
        post = await self.post_service.get_post_by_id(str(post_id), session)
        await ensure_can_view_post(post, user_id, session)
        result = await session.execute(select(Votes).where(Votes.post_id == post_id))
        return list(result.scalars().all())
        
    async def get_votes_by_user(self, user_id: UUID, session: AsyncSession) -> List[Votes]:
        result = await session.execute(select(Votes).where(Votes.user_id == user_id))
        return list(result.scalars().all())
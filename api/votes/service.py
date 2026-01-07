from typing import List
from uuid import UUID

from fastapi import HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from api.db.models import Posts, Votes, VoteType
from api.posts.service import PostService

from .schemas import VoteCreate, VoteResponse

class VoteService:
    
    post_service = PostService()
    
    async def create_vote(self, vote_data: VoteCreate, session: AsyncSession) -> Votes:
        try:
            # Check if vote already exists
            result = await session.execute(
                select(Votes).where(
                    Votes.post_id == vote_data.post_id,
                    Votes.user_id == vote_data.user_id
                )
            )
            existing_vote = result.scalar_one_or_none()
            
            post = await self.post_service.get_post_by_id(str(vote_data.post_id), session)
            if not post:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
            
            if existing_vote:
                # Vote already exists - update it if vote type is different
                if existing_vote.vote_type == vote_data.vote_type:
                    # Same vote type - return existing vote (or raise error)
                    return existing_vote
                
                # Different vote type - update the vote
                old_vote_type = existing_vote.vote_type
                existing_vote.vote_type = vote_data.vote_type
                
                # Update post counts: remove old vote, add new vote
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
                return existing_vote
            else:
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
                return new_vote
                
        except HTTPException:
            await session.rollback()
            raise
        except Exception as e:
            await session.rollback()
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error creating vote: {e}") 
               
    async def get_vote_by_id(self, vote_id: UUID, session: AsyncSession) -> Votes:
        try:
            result = await session.execute(select(Votes).where(Votes.id == vote_id))
            vote = result.scalar_one_or_none()
            if not vote:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vote not found")
            return vote
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error getting vote by id: {e}")
        
    async def delete_vote(self, vote_id: UUID, session: AsyncSession) -> None:
        try:
            vote = await self.get_vote_by_id(vote_id, session)
            if vote:
                post = await self.post_service.get_post_by_id(str(vote.post_id), session)
                if post:
                    #post.upvote_count -= 1 if vote.vote_type == VoteType.UPVOTE else post.downvote_count -= 1
                    if vote.vote_type == VoteType.UPVOTE:
                        post.upvote_count -= 1
                    else:
                        post.downvote_count -= 1
                    await session.commit()
                    await session.refresh(post)
                await session.delete(vote)
                await session.commit()
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error deleting vote: {e}")
        
    async def get_votes_by_post(self, post_id: UUID, session: AsyncSession) -> List[Votes]:
        try:
            result = await session.execute(select(Votes).where(Votes.post_id == post_id))
            votes = result.scalars().all()
            return votes
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error getting votes by post: {e}")
        
    async def get_votes_by_user(self, user_id: UUID, session: AsyncSession) -> List[Votes]:
        try:
            result = await session.execute(select(Votes).where(Votes.user_id == user_id))
            votes = result.scalars().all()
            return votes
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error getting votes by user: {e}")
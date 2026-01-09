from typing import List
from uuid import UUID

from fastapi import HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from api.auth.service import UserService
from api.db.models import Follows, User

class FollowService:
    
    user_service = UserService()
    
    async def follow_user(self, follower_id: UUID, following_id: UUID, session: AsyncSession) -> Follows:
        try:
            if follower_id == following_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot follow yourself")
            
            result = await session.execute(
                select(Follows).where(
                    Follows.follower_id == follower_id,
                    Follows.following_id == following_id
                )
            )
            
            existing_follow = result.scalar_one_or_none()
            
            if existing_follow:
                return existing_follow
            
            new_follow = Follows(
                follower_id=follower_id,
                following_id=following_id
            )
            
            follower_user = await session.get(User, follower_id)
            following_user = await session.get(User, following_id)
            
            if not follower_user or not following_user:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
            
            if follower_user:
                follower_user.following_count += 1
            if following_user:
                following_user.followers_count += 1
                
            session.add(new_follow)
            await session.commit()
            await session.refresh(new_follow)
            return new_follow
        
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error following user: {e}")
        
    async def unfollow_user(self, follower_id: UUID, following_id: UUID, session: AsyncSession) -> None:
        try:
            result = await session.execute(
                select(Follows).where(
                    Follows.follower_id == follower_id,
                    Follows.following_id == following_id
                )
            )
            existing_follow = result.scalar_one_or_none()
            if not existing_follow:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="You're not following this user")
            
            follower_user = await session.get(User, follower_id)
            following_user = await session.get(User, following_id)
            
            if not follower_user or not following_user:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
            
            if follower_user:
                follower_user.following_count -= 1
            if following_user:
                following_user.followers_count -= 1
                
            session.delete(existing_follow)
            await session.commit()
            
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error unfollowing user: {e}")
        
    async def get_followers(self, user_id: UUID, session: AsyncSession) -> List[User]:
        try:
            result = await session.execute(
                select(User)
                .join(Follows, User.id == Follows.follower_id)
                .where(Follows.following_id == user_id)
            )
            followers = list(result.scalars().all())
            return followers
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error getting followers: {e}")
        

    async def get_following(self, user_id: UUID, session: AsyncSession) -> List[User]:
        try:
            result = await session.execute(
                select(User)
                .join(Follows, User.id == Follows.following_id)
                .where(Follows.follower_id == user_id)
            )
            following = list(result.scalars().all())
            return following
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error getting following: {e}")
        
    async def get_follow_status(self, follower_id: UUID, following_id: UUID, session: AsyncSession) -> bool:
        try:
            result = await session.execute(
                select(Follows).where(
                    Follows.follower_id == follower_id,
                    Follows.following_id == following_id
                )
            )
            return result.scalar_one_or_none() is not None
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error getting follow status: {e}")

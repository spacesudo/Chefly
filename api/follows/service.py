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
            follower_user = await self.user_service.get_user_by_id(follower_id, session)
            following_user = await self.user_service.get_user_by_id(following_id, session)
            
            if not follower_user or not following_user:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
            
            
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
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You are already following this user")
            
            new_follow = Follows(
                follower_id=follower_id,
                following_id=following_id
            )
            
            
            if follower_user:
                follower_user.following_count += 1
            if following_user:
                following_user.followers_count += 1
                
            session.add(new_follow)
            await session.commit()
            await session.refresh(new_follow)
            await session.refresh(follower_user)
            await session.refresh(following_user)
            return new_follow
        
        except HTTPException:
            await session.rollback()
            raise
        except Exception as e:
            await session.rollback()
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
                follower_user.following_count -= 1 if follower_user.following_count > 0 else 0
            if following_user:
                following_user.followers_count -= 1 if following_user.followers_count > 0 else 0
                
            await session.delete(existing_follow)
            await session.commit()
            
        except HTTPException:
            await session.rollback()
            raise
        except Exception as e:
            await session.rollback()
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
    
    async def get_follower_usernames(self, user_id: UUID, session: AsyncSession) -> List[str]:
        try:
            followers = await self.get_followers(user_id, session)
            return [follower.username for follower in followers]
        
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                detail=f"Error getting follower usernames: {e}"
            )
    
    async def get_following_usernames(self, user_id: UUID, session: AsyncSession) -> List[str] :
        try:
            followings = await self.get_following(user_id, session) 
            return [following.username for following in followings]
        
        except Exception as e:
            raise HTTPException(
                status_code= status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail = "Error getting following usernames: {e}"
            )      
    
    async def get_followers_count(self, user_id: UUID, session: AsyncSession) -> int:
        try:
            result = await session.execute(
                select(User).where(User.id == user_id)
            )
            user = result.scalar_one_or_none()
            return user.followers_count if user else 0
        
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error getting followers count: {e}")
        
    async def get_following_count(self, user_id: UUID, session: AsyncSession) -> int:
        try:
            result = await session.execute(
                select(User).where(User.id == user_id)
            )
            user = result.scalar_one_or_none()
            return user.following_count if user else 0
        
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error getting following count: {e}")
        
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
        

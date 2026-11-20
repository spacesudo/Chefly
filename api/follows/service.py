from typing import List
from uuid import UUID

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from api.auth.service import UserService
from api.db.models import Follows, NotificationType, User
from api.errors import AlreadyFollowing, CannotFollowSelf, NotFollowing, UserNotFound
from api.notifications.service import NotificationService
from api.posts.algorithm import safe_record_interaction

class FollowService:
    
    user_service = UserService()
    notification_service = NotificationService()
    
    async def follow_user(self, follower_id: UUID, following_id: UUID, session: AsyncSession) -> Follows:
        if follower_id == following_id:
            raise CannotFollowSelf()
        follower_user = await self.user_service.get_user_by_id(follower_id, session)
        following_user = await self.user_service.get_user_by_id(following_id, session)
        
        result = await session.execute(
            select(Follows).where(
                Follows.follower_id == follower_id,
                Follows.following_id == following_id
            )
        )
        if result.scalar_one_or_none():
            raise AlreadyFollowing()
        
        new_follow = Follows(
            follower_id=follower_id,
            following_id=following_id
        )
        follower_user.following_count += 1
        following_user.followers_count += 1
            
        session.add(new_follow)
        await session.commit()
        await session.refresh(new_follow)
        await session.refresh(follower_user)
        await session.refresh(following_user)

        await safe_record_interaction(
            user_id=follower_id,
            interaction_type="follows",
            author_id=following_id,
        )
        await self.notification_service.notify(following_id, NotificationType.FOLLOW, follower_id)

        return new_follow
        
    async def unfollow_user(self, follower_id: UUID, following_id: UUID, session: AsyncSession) -> None:
        result = await session.execute(
            select(Follows).where(
                Follows.follower_id == follower_id,
                Follows.following_id == following_id
            )
        )
        existing_follow = result.scalar_one_or_none()
        if not existing_follow:
            raise NotFollowing()
        
        follower_user = await session.get(User, follower_id)
        following_user = await session.get(User, following_id)
        if not follower_user or not following_user:
            raise UserNotFound()
        
        follower_user.following_count -= 1 if follower_user.following_count > 0 else 0
        following_user.followers_count -= 1 if following_user.followers_count > 0 else 0
            
        await session.delete(existing_follow)
        await session.commit()

        await safe_record_interaction(
            user_id=follower_id,
            interaction_type="unfollows",
            author_id=following_id,
        )
        
    async def get_followers(self, user_id: UUID, session: AsyncSession) -> List[User]:
        result = await session.execute(
            select(User)
            .join(Follows, User.id == Follows.follower_id)
            .where(Follows.following_id == user_id)
        )
        return list(result.scalars().all())

    async def get_following(self, user_id: UUID, session: AsyncSession) -> List[User]:
        result = await session.execute(
            select(User)
            .join(Follows, User.id == Follows.following_id)
            .where(Follows.follower_id == user_id)
        )
        return list(result.scalars().all())
    
    async def get_follower_usernames(self, user_id: UUID, session: AsyncSession) -> List[str]:
        return [follower.username for follower in await self.get_followers(user_id, session)]
    
    async def get_following_usernames(self, user_id: UUID, session: AsyncSession) -> List[str]:
        return [following.username for following in await self.get_following(user_id, session)]
    
    async def get_followers_count(self, user_id: UUID, session: AsyncSession) -> int:
        user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        return user.followers_count if user else 0
        
    async def get_following_count(self, user_id: UUID, session: AsyncSession) -> int:
        user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        return user.following_count if user else 0
        
    async def get_follow_status(self, follower_id: UUID, following_id: UUID, session: AsyncSession) -> bool:
        result = await session.execute(
            select(Follows).where(
                Follows.follower_id == follower_id,
                Follows.following_id == following_id
            )
        )
        return result.scalar_one_or_none() is not None

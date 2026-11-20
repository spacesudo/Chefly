from uuid import UUID

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from api.db.models import User
from api.errors import UserNotFound

from .schemas import UserCreate, UserLogin
from .utils import hash_password, verify_password

class UserService:
    
    async def get_user_by_email(self, email: str, session: AsyncSession) -> User | None:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if not user:
            raise UserNotFound()
        return user
        
    async def get_user_by_id(self, user_id: UUID, session: AsyncSession) -> User | None:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise UserNotFound()
        return user
        
    async def user_exists(self, email: str, session: AsyncSession) -> bool:
        result = await session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none() is not None
    
    async def create_user(self, user_data: UserCreate, session: AsyncSession) -> User:
        # Get password before dumping (since it's excluded)
        password = user_data.password
        # Dump user data excluding password
        new_user_dict = user_data.model_dump(exclude={"password"})
        new_user = User(**new_user_dict)
        new_user.hashed_password = hash_password(password)
        session.add(new_user)
        await session.commit()
        await session.refresh(new_user)
        return new_user
        
   

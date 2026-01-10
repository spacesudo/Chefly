from uuid import UUID

from fastapi import HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from api.db.main import get_session
from api.db.models import User

from .schemas import UserCreate, UserLogin
from .utils import hash_password, verify_password

class UserService:
    
    async def get_user_by_email(self, email: str, session: AsyncSession) -> User | None:
        try:
            result = await session.execute(select(User).where(User.email == email))
            user = result.scalar_one_or_none()
            if not user:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
            return user
        
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error getting user by email: {e}")
        
    async def get_user_by_id(self, user_id: UUID, session: AsyncSession) -> User | None:
        try:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if not user:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
            return user
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error getting user by id: {e}")
        
    async def user_exists(self, email: str, session: AsyncSession) -> bool:
        try:
            result = await session.execute(select(User).where(User.email == email))
            user = result.scalar_one_or_none()
            return user is not None
        except Exception:
            return False
    
    async def create_user(self, user_data: UserCreate, session: AsyncSession) -> User:
        try:
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
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error creating user: {e}")
        
   
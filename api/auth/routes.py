from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from .schemas import UserCreate, UserLogin
from api.auth.service import UserService
from api.db.main import get_session
from sqlmodel.ext.asyncio.session import AsyncSession
from .utils import decode_token, create_access_token, verify_password
from api.config import Config
from datetime import timedelta, datetime
from .dependencies import RefreshTokenBearer, AccessTokenBearer
from api.db.redis import add_jwt_to_blacklist


router = APIRouter(prefix="/auth", tags=["auth"])
user_service = UserService()

@router.post("/signup")
async def create_user(user_data: UserCreate, session: AsyncSession = Depends(get_session)):
    email =  user_data.email
    if await user_service.user_exists(email, session):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User already exists")
    user = await user_service.create_user(user_data, session)
    return user

@router.post("/login")
async def login(user_data: UserLogin, session: AsyncSession = Depends(get_session)):
    email = user_data.email
    password = user_data.password
    user = await user_service.get_user_by_email(email, session)
    if user is not None:
        password_valid = verify_password(password, user.hashed_password)
        if password_valid:
            access_token = create_access_token(
                user_data = {
                    'email' : user.email,
                    'username' : user.username,
                    'user_id' : str(user.id)
                }
            )
            refresh_token = create_access_token(
                user_data = {
                    'email' : user.email,
                    'username' : user.username,
                    'user_id' : str(user.id)
                },
                refresh = True,
                expiry = timedelta(seconds=Config.JWT_REFRESH_EXPIRY)
            )
            
            return JSONResponse(
                content = {
                    "message" : "Login successful",
                    "access_token" : access_token,
                    "refresh_token" : refresh_token,
                    "user" : {
                        "email" : user.email,
                        "username" : user.username,
                        "user_id" : str(user.id)
                    }
                },
                status_code = status.HTTP_200_OK
            )
        else:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    else:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
@router.post("/refresh")
async def refresh_token(token_details: dict = Depends(RefreshTokenBearer())):
    # Extract user data from the token (it's nested under 'user')
    user_data = token_details.get("user")
    if not user_data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token structure")
    
    # Create a new access token with the user data
    access_token = create_access_token(
        user_data={
            'email': user_data.get("email"),
            'username': user_data.get("username"),
            'user_id': user_data.get("user_id")
        }
    )
    return JSONResponse(
        content={
            "message": "Token refreshed",
            "access_token": access_token,
        },
        status_code=status.HTTP_200_OK
    )
    
@router.post("/logout")
async def logout(token_details: dict = Depends(AccessTokenBearer())):
    jti = token_details.get("jti")
    if not jti:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token structure")
    await add_jwt_to_blacklist(jti)
    return JSONResponse(
        content={
        "message": "Logged out successfully"},
        status_code=status.HTTP_200_OK
    )
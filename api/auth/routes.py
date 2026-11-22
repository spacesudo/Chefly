from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from .schemas import UserCreate, UserLogin
from api.auth.service import UserService
from api.db.main import get_session
from sqlmodel.ext.asyncio.session import AsyncSession
from .utils import decode_token, create_access_token, verify_password
from api.config import Config
from datetime import timedelta, datetime
from .dependencies import RefreshTokenBearer, AccessTokenBearer, refresh_session_id
from api.db.redis import add_jwt_to_blacklist, claim_jwt_once, revoke_session
from api.errors import InvalidCredentials, InvalidToken, RevokedToken, UserAlreadyExists, UserNotFound
import uuid


router = APIRouter(prefix="/auth", tags=["auth"])
user_service = UserService()


def issue_token_pair(user_data: dict, session_id: str) -> tuple[str, str]:
    access_token = create_access_token(user_data=user_data, session_id=session_id)
    refresh_token = create_access_token(
        user_data=user_data,
        refresh=True,
        expiry=timedelta(seconds=Config.JWT_REFRESH_EXPIRY),
        session_id=session_id
    )
    return access_token, refresh_token


@router.post("/signup")
async def create_user(user_data: UserCreate, session: AsyncSession = Depends(get_session)):
    email =  user_data.email
    if await user_service.user_exists(email, session):
        raise UserAlreadyExists()
    user = await user_service.create_user(user_data, session)
    return user

@router.post("/login")
async def login(user_data: UserLogin, session: AsyncSession = Depends(get_session)):
    email = user_data.email
    password = user_data.password
    try:
        user = await user_service.get_user_by_email(email, session)
    except UserNotFound:
        # Same error as a wrong password, so login can't be used to check which emails have accounts
        raise InvalidCredentials()
    if user is not None:
        password_valid = verify_password(password, user.hashed_password)
        if password_valid:
            access_token, refresh_token = issue_token_pair(
                user_data = {
                    'email' : user.email,
                    'username' : user.username,
                    'user_id' : str(user.id)
                },
                session_id = str(uuid.uuid4())
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
            raise InvalidCredentials()
    else:
        raise InvalidCredentials()
    
@router.post("/refresh")
async def refresh_token(token_details: dict = Depends(RefreshTokenBearer())):
    # Extract user data from the token (it's nested under 'user')
    user_data = token_details.get("user")
    jti = token_details.get("jti")
    if not user_data or not jti:
        raise InvalidToken()
    session_id = refresh_session_id(token_details)
    
    # Rotate: each refresh token can be used once. Reuse means it leaked, so end the whole session.
    if not await claim_jwt_once(jti, token_details.get("exp")):
        await revoke_session(session_id)
        raise RevokedToken()
    
    access_token, refresh_token = issue_token_pair(
        user_data={
            'email': user_data.get("email"),
            'username': user_data.get("username"),
            'user_id': user_data.get("user_id")
        },
        session_id=session_id
    )
    return JSONResponse(
        content={
            "message": "Token refreshed",
            "access_token": access_token,
            "refresh_token": refresh_token,
        },
        status_code=status.HTTP_200_OK
    )
    
@router.post("/logout")
async def logout(token_details: dict = Depends(AccessTokenBearer())):
    jti = token_details.get("jti")
    if not jti:
        raise InvalidToken()
    await add_jwt_to_blacklist(jti, token_details.get("exp"))
    session_id = token_details.get("sid")
    if session_id:
        # Revokes the refresh token and every other token issued in this login session
        await revoke_session(session_id)
    return JSONResponse(
        content={
        "message": "Logged out successfully"},
        status_code=status.HTTP_200_OK
    )
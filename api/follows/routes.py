from logging import Logger
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from api.auth.dependencies import AccessTokenBearer
from api.db.main import get_session
from api.follows.service import FollowService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/follows", tags=["follows"])
follow_service = FollowService()

@router.post("/users/{user_id}/follow")
async def follow_user(
    user_id: str,
    session: AsyncSession = Depends(get_session),
    token_details: dict = Depends(AccessTokenBearer())
):
    follower_id = UUID(token_details["user"]["user_id"])
    following_id = UUID(user_id)
    
    follow = await follow_service.follow_user(follower_id, following_id, session)
    return {"message": "Successfully followed user", "follow": follow}

@router.delete("/users/{user_id}/follow")
async def unfollow_user(
    user_id: str,
    session: AsyncSession = Depends(get_session),
    token_details: dict = Depends(AccessTokenBearer())
):
    follower_id = UUID(token_details["user"]["user_id"])
    following_id = UUID(user_id)
    
    await follow_service.unfollow_user(follower_id, following_id, session)
    return JSONResponse(
        content={
            "message": "Successfully unfollowed user"
        },
        status_code=status.HTTP_200_OK
    )

@router.get("/users/{user_id}/followers")
async def get_followers(
    user_id: str,
    session: AsyncSession = Depends(get_session)
):
    user_uuid = UUID(user_id)
    followers = await follow_service.get_followers(user_uuid, session)
    return followers

@router.get("/users/{user_id}/following")
async def get_following(
    user_id: str,
    session: AsyncSession = Depends(get_session)
):
    user_uuid = UUID(user_id)
    following = await follow_service.get_following(user_uuid, session)
    return following

@router.get("/users/{user_id}/follow-status")
async def get_follow_status(
    user_id: str,
    session: AsyncSession = Depends(get_session),
    token_details: dict = Depends(AccessTokenBearer())
):
    follower_id = UUID(token_details["user"]["user_id"])
    following_id = UUID(user_id)
    follow_status = await follow_service.get_follow_status(follower_id, following_id, session)
    return {"follow_status": follow_status}


"""Deliberately not using token bearer for this route as it is public information
    
    It is not sensitive information and does not require authentication to access.
    
    would add some optional token bearer for this route in the future if needed. where userid is passed as a query parameter.
"""


@router.get("/users/{user_id}/followers-count")
async def get_followers_count(
    user_id: str,
    session: AsyncSession = Depends(get_session)
):
    user_uuid = UUID(user_id)
    followers_count = await follow_service.get_followers_count(user_uuid, session)
    return {"followers_count": followers_count}

@router.get("/users/{user_id}/following-count")
async def get_following_count(
    user_id: str,
    session: AsyncSession = Depends(get_session)
):
    user_uuid = UUID(user_id)
    following_count = await follow_service.get_following_count(user_uuid, session)
    return {"following_count": following_count}

@router.get("/users/{user_id}/followers-usernames")
async def get_followers_usernames(
    user_id: str,
    session: AsyncSession = Depends(get_session)
):
    user_uuid = UUID(user_id)
    followers_usernames = await follow_service.get_follower_usernames(user_uuid, session)
    return {"followers_usernames": followers_usernames}

@router.get("/users/{user_id}/following-usernames")
async def get_following_usernames(
    user_id: str,
    session: AsyncSession = Depends(get_session)
):
    user_uuid = UUID(user_id)
    following_usernames = await follow_service.get_following_usernames(user_uuid, session)
    return {"following_usernames": following_usernames}

    
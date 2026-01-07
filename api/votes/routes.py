from logging import Logger
import logging
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from api.votes.schemas import VoteCreate, VoteResponse
from api.auth.dependencies import AccessTokenBearer
from api.votes.service import VoteService
from api.db.main import get_session
from api.db.models import Votes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/votes", tags=["votes"])
vote_service = VoteService()

@router.post("/create")
async def create_vote(vote_data: VoteCreate, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    user_id_str = token_details["user"]["user_id"]
    if not user_id_str:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    
    try:
        user_id = UUID(user_id_str)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid user ID format")
    
    if not vote_data.user_id:
        vote_data.user_id = user_id
        
    vote = await vote_service.create_vote(vote_data, session)
    return vote


@router.get("/{vote_id}")
async def get_vote_by_id(vote_id: str, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    try:
        vote_uuid = UUID(vote_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid vote ID format")
    
    vote = await vote_service.get_vote_by_id(vote_uuid, session)
    return vote

@router.delete("/{vote_id}")
async def delete_vote(vote_id: str, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    try:
        vote_uuid = UUID(vote_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid vote ID format")
    
    await vote_service.delete_vote(vote_uuid, session)
    return JSONResponse(
        content={"message": "Vote deleted successfully"},
        status_code=status.HTTP_200_OK
    )
    
@router.get("/post/{post_id}", response_model=List[VoteResponse])
async def get_votes_by_post(post_id: str, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    try:
        post_uuid = UUID(post_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid post ID format")
    
    votes = await vote_service.get_votes_by_post(post_uuid, session)
    return [VoteResponse(**vote.model_dump()) for vote in votes]

@router.get("/user/{user_id}", response_model=List[VoteResponse])
async def get_votes_by_user(user_id: str, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    try:
        user_uuid = UUID(user_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid user ID format")
    
    votes = await vote_service.get_votes_by_user(user_uuid, session)
    return [VoteResponse(**vote.model_dump()) for vote in votes]
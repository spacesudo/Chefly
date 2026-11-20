import logging
from typing import List

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from api.votes.schemas import VoteCreate, VoteResponse
from api.auth.dependencies import AccessTokenBearer, get_current_user_id, parse_uuid
from api.votes.service import VoteService
from api.db.main import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/votes", tags=["votes"])
vote_service = VoteService()

@router.post("/create")
async def create_vote(vote_data: VoteCreate, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    vote_data.user_id = get_current_user_id(token_details)
    vote = await vote_service.create_vote(vote_data, session)
    return vote


@router.get("/{vote_id}")
async def get_vote_by_id(vote_id: str, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    vote = await vote_service.get_vote_by_id(parse_uuid(vote_id, "vote"), session)
    return vote

@router.delete("/{vote_id}")
async def delete_vote(vote_id: str, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    await vote_service.delete_vote(parse_uuid(vote_id, "vote"), get_current_user_id(token_details), session)
    return JSONResponse(
        content={"message": "Vote deleted successfully"},
        status_code=status.HTTP_200_OK
    )
    
@router.get("/post/{post_id}", response_model=List[VoteResponse])
async def get_votes_by_post(post_id: str, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    votes = await vote_service.get_votes_by_post(parse_uuid(post_id, "post"), get_current_user_id(token_details), session)
    return [VoteResponse(**vote.model_dump()) for vote in votes]

@router.get("/user/{user_id}", response_model=List[VoteResponse])
async def get_votes_by_user(user_id: str, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    votes = await vote_service.get_votes_by_user(parse_uuid(user_id, "user"), session)
    return [VoteResponse(**vote.model_dump()) for vote in votes]

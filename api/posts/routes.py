from typing import List
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from api.posts.schemas import PostCreate, PostEdit, PostResponse
from api.posts.service import PostService
from api.posts.algorithm import get_fyp_recommendations
from api.db.main import get_session
from api.db.redis import redis_client
from sqlmodel.ext.asyncio.session import AsyncSession
from api.auth.dependencies import AccessTokenBearer, get_current_user_id
from api.communities.access import ensure_can_view_post
from api.errors import NotPostAuthor
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/posts", tags=["posts"])
post_service = PostService()
tag_service = post_service.tag_service

@router.post("/create")
async def create_post(post_data: PostCreate, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    post_data.author_id = str(get_current_user_id(token_details))
    post = await post_service.create_post(post_data, session)
    return await tag_service.to_response(post, session)

@router.get("/all", response_model=List[PostResponse])
async def get_all_posts(session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    posts = await post_service.get_all_posts(get_current_user_id(token_details), session)
    return await tag_service.to_responses(posts, session)

@router.get("/following-feed", response_model=List[PostResponse])
async def get_following_feed(limit: int = 20, offset: int = 0, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    posts = await post_service.following_feed(get_current_user_id(token_details), session, limit, offset)
    return await tag_service.to_responses(posts, session)

@router.get("/feed", response_model=List[PostResponse])
async def get_feed(limit: int = 20, offset: int = 0, session: AsyncSession = Depends(get_session)):
    posts = await post_service.feed(session, limit, offset)
    return await tag_service.to_responses(posts, session)

@router.get("/fyp", response_model=List[PostResponse])
async def get_fyp_feed(
    limit: int = 20,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
    token_details: dict = Depends(AccessTokenBearer()),
):
    posts = await get_fyp_recommendations(
        redis=redis_client,
        session=session,
        user_id=get_current_user_id(token_details),
        limit=limit,
        offset=offset,
    )
    return await tag_service.to_responses(posts, session)

@router.get("/{post_id}", response_model=PostResponse)
async def get_post(post_id: str, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    post = await post_service.get_post_by_id(post_id, session)
    await ensure_can_view_post(post, get_current_user_id(token_details), session)
    return await tag_service.to_response(post, session)

@router.delete("/{post_id}")
async def delete_post(post_id: str, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    post = await post_service.get_post_by_id(post_id, session)
    if post.author_id != get_current_user_id(token_details):
        raise NotPostAuthor()
    await post_service.delete_post(post_id, session)
    return JSONResponse(
        content={"message": "Post deleted successfully"},
        status_code=status.HTTP_200_OK
    )
    
@router.put("/{post_id}")
async def edit_post(post_id: str, post_data: PostEdit, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    post = await post_service.get_post_by_id(post_id, session)
    if post.author_id != get_current_user_id(token_details):
        raise NotPostAuthor()
    post = await post_service.edit_post(post_id, post_data, session)
    return await tag_service.to_response(post, session)

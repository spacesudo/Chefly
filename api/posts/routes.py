from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from api.posts.schemas import PostCreate, PostEdit
from api.posts.service import PostService
from api.db.main import get_session
from sqlmodel.ext.asyncio.session import AsyncSession
from api.auth.dependencies import AccessTokenBearer
from logging import Logger
from uuid import UUID
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/posts", tags=["posts"])
post_service = PostService()

@router.post("/create")
async def create_post(post_data: PostCreate, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    logger.info(f"Token details: {token_details}")
    user_id = token_details["user"]["user_id"]
    if not user_id:
        logger.error("User not found")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    
    if not post_data.author_id:
        post_data.author_id = user_id
        
    post = await post_service.create_post(post_data, session)
    return post

@router.get("/all")
async def get_all_posts(session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    posts = await post_service.get_all_posts(session)
    return posts

@router.get("/{post_id}")
async def get_post(post_id: str, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    post = await post_service.get_post_by_id(post_id, session)
    return post

@router.delete("/{post_id}")
async def delete_post(post_id: str, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    user_id_str = token_details["user"]["user_id"]
    if not user_id_str:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    
    # Convert user_id string to UUID for comparison
    try:
        user_id = UUID(user_id_str)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid user ID format")
    
    post = await post_service.get_post_by_id(post_id, session)
    if post.author_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You are not the author of this post")
    await post_service.delete_post(post_id, session)
    return JSONResponse(
        content={"message": "Post deleted successfully"},
        status_code=status.HTTP_200_OK
    )
    
@router.put("/{post_id}")
async def edit_post(post_id: str, post_data: PostEdit, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    user_id_str = token_details["user"]["user_id"]
    if not user_id_str:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    
    # Convert user_id string to UUID for comparison
    try:
        user_id = UUID(user_id_str)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid user ID format")
    
    post = await post_service.get_post_by_id(post_id, session)
    if post.author_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You are not the author of this post")
    post = await post_service.edit_post(post_id, post_data, session)
    return post
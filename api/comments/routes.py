from logging import Logger
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from api.auth.dependencies import AccessTokenBearer
from api.comments.schemas import CommentCreate, CommentEdit, CommentResponse
from api.comments.service import CommentService
from api.db.main import get_session
from api.db.models import Comments

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/comments", tags=["comments"])
comment_service = CommentService()

def convert_comment_with_replies(comment: Comments) -> CommentResponse:
    """Recursively convert Comments model to CommentResponse with nested replies."""
    # Convert replies recursively
    reply_responses = [
        convert_comment_with_replies(reply) 
        for reply in comment.replies
    ] if comment.replies else []
    
    # Create response with nested replies
    return CommentResponse(
        id=comment.id,
        content=comment.content,
        parent_id=comment.parent_id,
        user_id=comment.user_id,
        post_id=comment.post_id,
        replies=reply_responses,
        created_at=comment.created_at,
        updated_at=comment.updated_at
    )

@router.post("/create")
async def create_comment(comment_data: CommentCreate, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    user_id_str = token_details["user"]["user_id"]
    if not user_id_str:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    
    try:
        user_id = UUID(user_id_str)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid user ID format")
    
    if not comment_data.user_id:
        comment_data.user_id = user_id
        
    comment = await comment_service.create_comment(comment_data, session)
    return comment

@router.get("/post/{post_id}")
async def get_comments_by_post(
    post_id: str, 
    session: AsyncSession = Depends(get_session), 
    token_details: dict = Depends(AccessTokenBearer())
):
    try:
        post_uuid = UUID(post_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid post ID format")
    
    comments = await comment_service.get_comments_by_post(post_uuid, session, include_replies=True)
    return [convert_comment_with_replies(comment) for comment in comments]

@router.get("/{comment_id}/replies")
async def get_replies_to_comment(
    comment_id: str, 
    session: AsyncSession = Depends(get_session), 
    token_details: dict = Depends(AccessTokenBearer())
):
    try:
        comment_uuid = UUID(comment_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid comment ID format")
    
    replies = await comment_service.get_replies_to_comment(comment_uuid, session)
    return [convert_comment_with_replies(reply) for reply in replies]

@router.get("/{comment_id}")
async def get_comment_by_id(comment_id: str, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    comment = await comment_service.get_comment_by_id(comment_id, session)
    return comment

@router.put("/{comment_id}")
async def edit_comment(comment_id: str, comment_data: CommentEdit, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    user_id_str = token_details["user"]["user_id"]
    if not user_id_str:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    
    # Convert user_id string to UUID for comparison
    try:
        user_id = UUID(user_id_str)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid user ID format")
    
    await comment_service.edit_comment(comment_id, comment_data, user_id, session)
    return JSONResponse(
        content={"message": "Comment edited successfully"},
        status_code=status.HTTP_200_OK
    )

@router.delete("/{comment_id}")
async def delete_comment(comment_id: str, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    user_id_str = token_details["user"]["user_id"]
    if not user_id_str:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    
    try:
        user_id = UUID(user_id_str)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid user ID format")
    
    await comment_service.delete_comment(comment_id, user_id, session)
    return JSONResponse(
        content={"message": "Comment deleted successfully"},
        status_code=status.HTTP_200_OK
    )
    
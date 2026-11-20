import logging

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from api.auth.dependencies import AccessTokenBearer, get_current_user_id, parse_uuid
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
    comment_data.user_id = get_current_user_id(token_details)
    comment = await comment_service.create_comment(comment_data, session)
    return comment

@router.get("/post/{post_id}")
async def get_comments_by_post(
    post_id: str, 
    session: AsyncSession = Depends(get_session), 
    token_details: dict = Depends(AccessTokenBearer())
):
    post_uuid = parse_uuid(post_id, "post")
    await comment_service.ensure_can_view(post_uuid, get_current_user_id(token_details), session)
    comments = await comment_service.get_comments_by_post(post_uuid, session, include_replies=True)
    return [convert_comment_with_replies(comment) for comment in comments]

@router.get("/{comment_id}/replies")
async def get_replies_to_comment(
    comment_id: str, 
    session: AsyncSession = Depends(get_session), 
    token_details: dict = Depends(AccessTokenBearer())
):
    comment_uuid = parse_uuid(comment_id, "comment")
    comment = await comment_service.get_comment_by_id(comment_uuid, session)
    await comment_service.ensure_can_view(comment.post_id, get_current_user_id(token_details), session)
    replies = await comment_service.get_replies_to_comment(comment_uuid, session)
    return [convert_comment_with_replies(reply) for reply in replies]

@router.get("/{comment_id}")
async def get_comment_by_id(comment_id: str, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    comment = await comment_service.get_comment_by_id(parse_uuid(comment_id, "comment"), session)
    await comment_service.ensure_can_view(comment.post_id, get_current_user_id(token_details), session)
    return comment

@router.put("/{comment_id}")
async def edit_comment(comment_id: str, comment_data: CommentEdit, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    await comment_service.edit_comment(parse_uuid(comment_id, "comment"), comment_data, get_current_user_id(token_details), session)
    return JSONResponse(
        content={"message": "Comment edited successfully"},
        status_code=status.HTTP_200_OK
    )

@router.delete("/{comment_id}")
async def delete_comment(comment_id: str, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    await comment_service.delete_comment(parse_uuid(comment_id, "comment"), get_current_user_id(token_details), session)
    return JSONResponse(
        content={"message": "Comment deleted successfully"},
        status_code=status.HTTP_200_OK
    )
    

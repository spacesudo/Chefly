import logging

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from api.auth.dependencies import AccessTokenBearer, get_current_user_id, parse_uuid
from api.bookmarks.schemas import BookmarkResponse
from api.bookmarks.service import BookmarkService
from api.db.main import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bookmarks", tags=["bookmarks"])
bookmark_service = BookmarkService()


@router.get("/")
async def get_my_bookmarks(limit: int = 20, offset: int = 0, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    user_id = get_current_user_id(token_details)
    return await bookmark_service.get_bookmarked_posts(user_id, session, limit, offset)


@router.post("/posts/{post_id}", response_model=BookmarkResponse)
async def add_bookmark(post_id: str, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    user_id = get_current_user_id(token_details)
    bookmark = await bookmark_service.add_bookmark(user_id, parse_uuid(post_id, "post"), session)
    return BookmarkResponse(**bookmark.model_dump())


@router.delete("/posts/{post_id}")
async def remove_bookmark(post_id: str, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    user_id = get_current_user_id(token_details)
    await bookmark_service.remove_bookmark(user_id, parse_uuid(post_id, "post"), session)
    return JSONResponse(
        content={"message": "Bookmark removed successfully"},
        status_code=status.HTTP_200_OK
    )


@router.get("/posts/{post_id}/status")
async def get_bookmark_status(post_id: str, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    user_id = get_current_user_id(token_details)
    bookmarked = await bookmark_service.is_bookmarked(user_id, parse_uuid(post_id, "post"), session)
    return {"bookmarked": bookmarked}

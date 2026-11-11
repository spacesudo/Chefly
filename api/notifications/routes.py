from typing import List

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from api.auth.dependencies import AccessTokenBearer, get_current_user_id, parse_uuid
from api.db.main import get_session
from api.notifications.schemas import NotificationResponse
from api.notifications.service import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])
notification_service = NotificationService()


@router.get("/", response_model=List[NotificationResponse])
async def get_notifications(unread_only: bool = False, limit: int = 20, offset: int = 0, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    user_id = get_current_user_id(token_details)
    return await notification_service.get_notifications(user_id, session, unread_only, limit, offset)


@router.get("/unread-count")
async def get_unread_count(session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    user_id = get_current_user_id(token_details)
    return {"unread_count": await notification_service.unread_count(user_id, session)}


@router.post("/read-all")
async def mark_all_read(session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    user_id = get_current_user_id(token_details)
    updated = await notification_service.mark_all_read(user_id, session)
    return {"message": "All notifications marked as read", "updated": updated}


@router.post("/{notification_id}/read")
async def mark_read(notification_id: str, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    user_id = get_current_user_id(token_details)
    await notification_service.mark_read(parse_uuid(notification_id, "notification"), user_id, session)
    return JSONResponse(content={"message": "Notification marked as read"}, status_code=status.HTTP_200_OK)


@router.delete("/{notification_id}")
async def delete_notification(notification_id: str, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    user_id = get_current_user_id(token_details)
    await notification_service.delete_notification(parse_uuid(notification_id, "notification"), user_id, session)
    return JSONResponse(content={"message": "Notification deleted"}, status_code=status.HTTP_200_OK)

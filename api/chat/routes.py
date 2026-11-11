from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from api.auth.dependencies import AccessTokenBearer, get_current_user_id, parse_uuid
from api.chat.schemas import (
    ChatUnreadSummary,
    ConversationResponse,
    ConversationStart,
    MessageCreate,
    MessageEdit,
    MessageResponse,
)
from api.chat.service import ChatService
from api.db.main import get_session

router = APIRouter(prefix="/chats", tags=["chats"])
chat_service = ChatService()


def _message(message: str) -> JSONResponse:
    return JSONResponse(content={"message": message}, status_code=status.HTTP_200_OK)


@router.post("/", response_model=ConversationResponse)
async def start_conversation(data: ConversationStart, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    return await chat_service.start_conversation(get_current_user_id(token_details), data.user_id, session)


@router.get("/", response_model=List[ConversationResponse])
async def list_conversations(requests: bool = False, limit: int = 20, offset: int = 0, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    return await chat_service.list_conversations(get_current_user_id(token_details), session, requests, limit, offset)


@router.get("/unread-count", response_model=ChatUnreadSummary)
async def get_unread_summary(session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    return await chat_service.unread_summary(get_current_user_id(token_details), session)


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(conversation_id: str, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    return await chat_service.get_conversation(parse_uuid(conversation_id, "conversation"), get_current_user_id(token_details), session)


@router.post("/{conversation_id}/accept")
async def accept_request(conversation_id: str, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    await chat_service.accept_request(parse_uuid(conversation_id, "conversation"), get_current_user_id(token_details), session)
    return _message("Message request accepted")


@router.delete("/{conversation_id}/request")
async def decline_request(conversation_id: str, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    await chat_service.decline_request(parse_uuid(conversation_id, "conversation"), get_current_user_id(token_details), session)
    return _message("Message request declined")


@router.post("/{conversation_id}/read")
async def mark_read(conversation_id: str, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    last_read_at = await chat_service.mark_read(parse_uuid(conversation_id, "conversation"), get_current_user_id(token_details), session)
    return {"last_read_at": last_read_at}


@router.get("/{conversation_id}/messages", response_model=List[MessageResponse])
async def get_messages(conversation_id: str, before: Optional[datetime] = None, limit: int = 50, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    return await chat_service.get_messages(parse_uuid(conversation_id, "conversation"), get_current_user_id(token_details), session, before, limit)


@router.post("/{conversation_id}/messages", response_model=MessageResponse)
async def send_message(conversation_id: str, data: MessageCreate, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    return await chat_service.send_message(parse_uuid(conversation_id, "conversation"), get_current_user_id(token_details), data, session)


@router.put("/{conversation_id}/messages/{message_id}", response_model=MessageResponse)
async def edit_message(conversation_id: str, message_id: str, data: MessageEdit, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    return await chat_service.edit_message(
        parse_uuid(conversation_id, "conversation"), parse_uuid(message_id, "message"), get_current_user_id(token_details), data.content, session
    )


@router.delete("/{conversation_id}/messages/{message_id}")
async def delete_message(conversation_id: str, message_id: str, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    await chat_service.delete_message(
        parse_uuid(conversation_id, "conversation"), parse_uuid(message_id, "message"), get_current_user_id(token_details), session
    )
    return _message("Message deleted")

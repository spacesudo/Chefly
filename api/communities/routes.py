import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from api.auth.dependencies import AccessTokenBearer, get_current_user_id, parse_uuid
from api.communities.schemas import (
    CommunityCreate,
    CommunityEdit,
    CommunityResponse,
    JoinRequestResponse,
    MemberAdd,
    MemberResponse,
    RoleUpdate,
)
from api.communities.service import CommunityService
from api.db.main import get_session
from api.db.models import Community, CommunityRole
from api.posts.schemas import PostCreate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/communities", tags=["communities"])
community_service = CommunityService()


def _to_response(community: Community, role: Optional[CommunityRole] = None) -> CommunityResponse:
    return CommunityResponse(**community.model_dump(), my_role=role)


def _message(message: str) -> JSONResponse:
    return JSONResponse(content={"message": message}, status_code=status.HTTP_200_OK)


@router.post("/", response_model=CommunityResponse)
async def create_community(data: CommunityCreate, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    user_id = get_current_user_id(token_details)
    community = await community_service.create_community(user_id, data, session)
    return _to_response(community, CommunityRole.OWNER)


@router.get("/", response_model=List[CommunityResponse])
async def list_communities(q: Optional[str] = None, limit: int = 20, offset: int = 0, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    communities = await community_service.list_communities(session, q, limit, offset)
    return [_to_response(c) for c in communities]


@router.get("/me", response_model=List[CommunityResponse])
async def get_my_communities(session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    user_id = get_current_user_id(token_details)
    communities = await community_service.get_user_communities(user_id, session)
    return [_to_response(c, role) for c, role in communities]


@router.get("/{community_id}", response_model=CommunityResponse)
async def get_community(community_id: str, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    user_id = get_current_user_id(token_details)
    community, role = await community_service.get_community(parse_uuid(community_id, "community"), user_id, session)
    return _to_response(community, role)


@router.put("/{community_id}", response_model=CommunityResponse)
async def edit_community(community_id: str, data: CommunityEdit, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    user_id = get_current_user_id(token_details)
    community = await community_service.edit_community(parse_uuid(community_id, "community"), user_id, data, session)
    return _to_response(community)


@router.delete("/{community_id}")
async def delete_community(community_id: str, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    user_id = get_current_user_id(token_details)
    await community_service.delete_community(parse_uuid(community_id, "community"), user_id, session)
    return _message("Community deleted successfully")


@router.post("/{community_id}/join")
async def join_community(community_id: str, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    user_id = get_current_user_id(token_details)
    return await community_service.join_community(parse_uuid(community_id, "community"), user_id, session)


@router.post("/{community_id}/leave")
async def leave_community(community_id: str, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    user_id = get_current_user_id(token_details)
    await community_service.leave_community(parse_uuid(community_id, "community"), user_id, session)
    return _message("Left community successfully")


@router.get("/{community_id}/members", response_model=List[MemberResponse])
async def get_members(community_id: str, limit: int = 50, offset: int = 0, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    user_id = get_current_user_id(token_details)
    return await community_service.get_members(parse_uuid(community_id, "community"), user_id, session, limit, offset)


@router.post("/{community_id}/members")
async def add_member(community_id: str, data: MemberAdd, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    user_id = get_current_user_id(token_details)
    member = await community_service.add_member(parse_uuid(community_id, "community"), user_id, data.user_id, session)
    return {"message": "Member added successfully", "member": member}


@router.delete("/{community_id}/members/{member_id}")
async def remove_member(community_id: str, member_id: str, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    user_id = get_current_user_id(token_details)
    await community_service.remove_member(parse_uuid(community_id, "community"), user_id, parse_uuid(member_id, "user"), session)
    return _message("Member removed successfully")


@router.put("/{community_id}/members/{member_id}/role")
async def update_member_role(community_id: str, member_id: str, data: RoleUpdate, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    user_id = get_current_user_id(token_details)
    member = await community_service.update_role(parse_uuid(community_id, "community"), user_id, parse_uuid(member_id, "user"), data.role, session)
    return {"message": "Role updated successfully", "member": member}


@router.get("/{community_id}/requests", response_model=List[JoinRequestResponse])
async def get_join_requests(community_id: str, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    user_id = get_current_user_id(token_details)
    return await community_service.get_join_requests(parse_uuid(community_id, "community"), user_id, session)


@router.post("/{community_id}/requests/{request_id}/approve")
async def approve_join_request(community_id: str, request_id: str, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    user_id = get_current_user_id(token_details)
    await community_service.review_join_request(parse_uuid(community_id, "community"), parse_uuid(request_id, "request"), user_id, True, session)
    return _message("Join request approved")


@router.post("/{community_id}/requests/{request_id}/reject")
async def reject_join_request(community_id: str, request_id: str, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    user_id = get_current_user_id(token_details)
    await community_service.review_join_request(parse_uuid(community_id, "community"), parse_uuid(request_id, "request"), user_id, False, session)
    return _message("Join request rejected")


@router.post("/{community_id}/posts")
async def create_community_post(community_id: str, data: PostCreate, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    user_id = get_current_user_id(token_details)
    return await community_service.create_post(parse_uuid(community_id, "community"), user_id, data, session)


@router.get("/{community_id}/posts")
async def get_community_posts(community_id: str, limit: int = 20, offset: int = 0, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    user_id = get_current_user_id(token_details)
    return await community_service.get_posts(parse_uuid(community_id, "community"), user_id, session, limit, offset)


@router.delete("/{community_id}/posts/{post_id}")
async def delete_community_post(community_id: str, post_id: str, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    user_id = get_current_user_id(token_details)
    await community_service.delete_post(parse_uuid(community_id, "community"), parse_uuid(post_id, "post"), user_id, session)
    return _message("Post deleted successfully")

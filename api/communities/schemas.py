from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from api.db.models import CommunityRole, JoinRequestStatus


class CommunityCreate(BaseModel):
    name: str = Field(min_length=3, max_length=100)
    description: Optional[str] = Field(default=None, max_length=2000)
    is_private: bool = False


class CommunityEdit(BaseModel):
    name: Optional[str] = Field(default=None, min_length=3, max_length=100)
    description: Optional[str] = Field(default=None, max_length=2000)
    is_private: Optional[bool] = Field(default=None)


class CommunityResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    is_private: bool
    owner_id: UUID
    members_count: int
    created_at: datetime
    updated_at: datetime
    my_role: Optional[CommunityRole] = None


class MemberAdd(BaseModel):
    user_id: UUID


class RoleUpdate(BaseModel):
    role: CommunityRole


class MemberResponse(BaseModel):
    user_id: UUID
    username: str
    role: CommunityRole
    joined_at: datetime


class JoinRequestResponse(BaseModel):
    id: UUID
    community_id: UUID
    user_id: UUID
    username: str
    status: JoinRequestStatus
    created_at: datetime

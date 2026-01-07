from pydantic import BaseModel, Field
from typing import Optional, List
from uuid import UUID
from datetime import datetime

class CommentCreate(BaseModel):
    post_id: UUID
    content: str = Field(min_length=10, max_length=10000)
    parent_id: Optional[UUID] = Field(default=None)
    user_id: Optional[UUID] = Field(default=None)
    
class CommentEdit(BaseModel):
    content: Optional[str] = Field(default=None)
    
    
class CommentResponse(BaseModel):
    id: UUID
    content: str
    parent_id: Optional[UUID] = Field(default=None)
    user_id: UUID
    post_id: UUID
    replies: List["CommentResponse"] = []
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True
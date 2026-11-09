from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from uuid import UUID
from api.tags.utils import normalize_tags

class PostCreate(BaseModel):
    title: str = Field(min_length=3, max_length=100)
    content: str = Field(min_length=10, max_length=10000)
    tags: List[str] = Field(default_factory=list)
    author_id: Optional[str] = Field(default=None)

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, tags: List[str]) -> List[str]:
        return normalize_tags(tags)
    

class PostEdit(BaseModel):
    title: Optional[str] = Field(default=None)
    content: Optional[str] = Field(default=None)
    tags: Optional[List[str]] = Field(default=None)

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, tags: Optional[List[str]]) -> Optional[List[str]]:
        return None if tags is None else normalize_tags(tags)


class PostResponse(BaseModel):
    id: UUID
    title: str
    content: str
    author_id: UUID
    community_id: Optional[UUID] = None
    upvote_count: int = 0
    downvote_count: int = 0
    comment_count: int = 0
    created_at: datetime
    updated_at: datetime
    tags: List[str] = []
    

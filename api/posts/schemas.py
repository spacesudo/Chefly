from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from api.db.models import PostType

class PostCreate(BaseModel):
    title: str = Field(min_length=3, max_length=100)
    content: str = Field(min_length=10, max_length=10000)
    content_type: PostType
    author_id: Optional[str] = Field(default=None)
    

class PostEdit(BaseModel):
    title: Optional[str] = Field(default=None)
    content: Optional[str] = Field(default=None)
    content_type: Optional[PostType] = Field(default=None)
    
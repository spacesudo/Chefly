from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class BookmarkResponse(BaseModel):
    id: UUID
    post_id: UUID
    user_id: UUID
    created_at: datetime

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from api.db.models import VoteType

class VoteCreate(BaseModel):
    post_id: UUID
    user_id: UUID = Field(default=None)
    vote_type: VoteType

    
class VoteResponse(BaseModel):
    id: UUID
    post_id: UUID
    user_id: UUID
    vote_type: VoteType
    created_at: datetime
    
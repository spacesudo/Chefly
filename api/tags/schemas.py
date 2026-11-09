from pydantic import BaseModel


class TagResponse(BaseModel):
    name: str
    post_count: int

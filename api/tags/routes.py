from typing import List

from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from api.auth.dependencies import AccessTokenBearer, get_current_user_id
from api.db.main import get_session
from api.posts.schemas import PostResponse
from api.tags.schemas import TagResponse
from api.tags.service import TagService

router = APIRouter(prefix="/tags", tags=["tags"])
tag_service = TagService()


@router.get("/suggested", response_model=List[TagResponse])
async def get_suggested_tags(limit: int = 20, session: AsyncSession = Depends(get_session)):
    return await tag_service.suggested_tags(session, limit)


@router.get("/trending", response_model=List[TagResponse])
async def get_trending_tags(limit: int = 10, days: int = 7, session: AsyncSession = Depends(get_session)):
    return await tag_service.trending_tags(session, limit, days)


@router.get("/trending/posts", response_model=List[PostResponse])
async def get_trending_posts(limit: int = 20, offset: int = 0, days: int = 7, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    user_id = get_current_user_id(token_details)
    posts = await tag_service.get_trending_posts(user_id, session, limit, offset, days)
    return await tag_service.to_responses(posts, session)


@router.get("/search", response_model=List[TagResponse])
async def search_tags(q: str, limit: int = 10, session: AsyncSession = Depends(get_session)):
    return await tag_service.search_tags(q, session, limit)


@router.get("/{name}/posts", response_model=List[PostResponse])
async def get_posts_by_tag(name: str, limit: int = 20, offset: int = 0, session: AsyncSession = Depends(get_session), token_details: dict = Depends(AccessTokenBearer())):
    user_id = get_current_user_id(token_details)
    posts = await tag_service.get_posts_by_tag(name, user_id, session, limit, offset)
    return await tag_service.to_responses(posts, session)

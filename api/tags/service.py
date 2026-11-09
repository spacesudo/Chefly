from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Iterable, List
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import delete, func, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from api.communities.access import public_posts_filter, visible_posts_filter
from api.db.models import Posts, PostTag, Tag
from api.posts.schemas import PostResponse
from api.tags.schemas import TagResponse
from api.tags.utils import STARTER_TAGS, normalize_tag


class TagService:

    async def _get_or_create(self, names: list[str], session: AsyncSession) -> dict[str, UUID]:
        if not names:
            return {}
        await session.execute(
            pg_insert(Tag).values([{"name": n} for n in names]).on_conflict_do_nothing(index_elements=["name"])
        )
        result = await session.execute(select(Tag.name, Tag.id).where(Tag.name.in_(names)))
        return {name: tag_id for name, tag_id in result.all()}

    async def _adjust_counts(self, tag_counts: dict[UUID, int], session: AsyncSession) -> None:
        for tag_id, delta in tag_counts.items():
            await session.execute(update(Tag).where(Tag.id == tag_id).values(post_count=Tag.post_count + delta))

    async def set_post_tags(self, post_id: UUID, names: list[str], session: AsyncSession) -> None:
        """Replace a post's tags with `names` (already normalized). Caller commits."""
        result = await session.execute(
            select(Tag.name, Tag.id).join(PostTag, PostTag.tag_id == Tag.id).where(PostTag.post_id == post_id)
        )
        current = {name: tag_id for name, tag_id in result.all()}

        removed_ids = [tag_id for name, tag_id in current.items() if name not in names]
        if removed_ids:
            await session.execute(delete(PostTag).where(PostTag.post_id == post_id, PostTag.tag_id.in_(removed_ids)))
            await self._adjust_counts({tag_id: -1 for tag_id in removed_ids}, session)

        added = await self._get_or_create([n for n in names if n not in current], session)
        if added:
            await session.execute(pg_insert(PostTag).values([{"post_id": post_id, "tag_id": tag_id} for tag_id in added.values()]))
            await self._adjust_counts({tag_id: 1 for tag_id in added.values()}, session)

    async def remove_tags_for_posts(self, post_ids, session: AsyncSession) -> None:
        """Detach tags from posts that are about to be deleted. Caller commits."""
        result = await session.execute(
            select(PostTag.tag_id, func.count()).where(PostTag.post_id.in_(post_ids)).group_by(PostTag.tag_id)
        )
        counts = {tag_id: -count for tag_id, count in result.all()}
        await session.execute(delete(PostTag).where(PostTag.post_id.in_(post_ids)))
        await self._adjust_counts(counts, session)

    async def get_tags_for_posts(self, post_ids: Iterable[UUID], session: AsyncSession) -> dict[UUID, list[str]]:
        post_ids = list(post_ids)
        if not post_ids:
            return {}
        result = await session.execute(
            select(PostTag.post_id, Tag.name)
            .join(Tag, Tag.id == PostTag.tag_id)
            .where(PostTag.post_id.in_(post_ids))
            .order_by(Tag.name)
        )
        tags: dict[UUID, list[str]] = defaultdict(list)
        for post_id, name in result.all():
            tags[post_id].append(name)
        return tags

    async def get_tag_names(self, post_id: UUID, session: AsyncSession) -> list[str]:
        return (await self.get_tags_for_posts([post_id], session)).get(post_id, [])

    async def to_responses(self, posts: List[Posts], session: AsyncSession) -> List[PostResponse]:
        tags = await self.get_tags_for_posts((p.id for p in posts), session)
        return [PostResponse(**p.model_dump(), tags=tags.get(p.id, [])) for p in posts]

    async def to_response(self, post: Posts, session: AsyncSession) -> PostResponse:
        return (await self.to_responses([post], session))[0]

    async def get_posts_by_tag(self, name: str, user_id: UUID, session: AsyncSession, limit: int = 20, offset: int = 0) -> List[Posts]:
        try:
            result = await session.execute(
                select(Posts)
                .join(PostTag, PostTag.post_id == Posts.id)
                .join(Tag, Tag.id == PostTag.tag_id)
                .where(Tag.name == normalize_tag(name), visible_posts_filter(user_id))
                .order_by(Posts.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            return list(result.scalars().all())
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error getting posts by tag: {e}")

    async def search_tags(self, q: str, session: AsyncSession, limit: int = 10) -> List[TagResponse]:
        prefix = normalize_tag(q)
        if not prefix:
            return []
        result = await session.execute(
            select(Tag).where(Tag.name.startswith(prefix), Tag.post_count > 0).order_by(Tag.post_count.desc()).limit(limit)
        )
        return [TagResponse(name=t.name, post_count=t.post_count) for t in result.scalars().all()]

    async def popular_tags(self, session: AsyncSession, limit: int = 10) -> List[TagResponse]:
        result = await session.execute(
            select(Tag).where(Tag.post_count > 0).order_by(Tag.post_count.desc()).limit(limit)
        )
        return [TagResponse(name=t.name, post_count=t.post_count) for t in result.scalars().all()]

    async def _recent_tag_usage(self, session: AsyncSession, since: datetime, limit: int) -> List[TagResponse]:
        uses = func.count(PostTag.post_id).label("uses")
        result = await session.execute(
            select(Tag.name, uses)
            .join(PostTag, PostTag.tag_id == Tag.id)
            .join(Posts, Posts.id == PostTag.post_id)
            .where(Posts.created_at >= since, public_posts_filter())
            .group_by(Tag.name)
            .order_by(uses.desc(), Tag.name)
            .limit(limit)
        )
        return [TagResponse(name=name, post_count=count) for name, count in result.all()]

    async def trending_tags(self, session: AsyncSession, limit: int = 10, days: int = 7) -> List[TagResponse]:
        """Tags used most on public posts in the last `days`; falls back to all-time popular."""
        since = datetime.now(timezone.utc) - timedelta(days=days)
        return await self._recent_tag_usage(session, since, limit) or await self.popular_tags(session, limit)

    async def get_trending_posts(
        self,
        user_id: UUID,
        session: AsyncSession,
        limit: int = 20,
        offset: int = 0,
        days: int = 7,
        tag_limit: int = 10,
        exclude_ids: set[UUID] | None = None,
    ) -> List[Posts]:
        """Posts carrying any trending tag, ranked by engagement.

        Uses posts from the last `days` when tags are trending in that window; if nothing is trending,
        falls back to all-time popular tags without the date restriction.
        """
        since = datetime.now(timezone.utc) - timedelta(days=days)
        trending = await self._recent_tag_usage(session, since, tag_limit)
        if not trending:
            trending, since = await self.popular_tags(session, tag_limit), None
        if not trending:
            return []

        tagged_post_ids = (
            select(PostTag.post_id)
            .join(Tag, Tag.id == PostTag.tag_id)
            .where(Tag.name.in_([t.name for t in trending]))
        )
        engagement = (
            func.coalesce(Posts.upvote_count, 0)
            - func.coalesce(Posts.downvote_count, 0)
            + 2 * func.coalesce(Posts.comment_count, 0)
        )
        query = select(Posts).where(Posts.id.in_(tagged_post_ids), visible_posts_filter(user_id))
        if since is not None:
            query = query.where(Posts.created_at >= since)
        if exclude_ids:
            query = query.where(Posts.id.notin_(exclude_ids))
        result = await session.execute(
            query.order_by(engagement.desc(), Posts.created_at.desc()).offset(offset).limit(limit)
        )
        return list(result.scalars().all())

    async def suggested_tags(self, session: AsyncSession, limit: int = 20) -> List[TagResponse]:
        """Starter tags first, then the most popular user-created tags."""
        result = await session.execute(select(Tag.name, Tag.post_count).where(Tag.name.in_(STARTER_TAGS)))
        starter_counts = dict(result.all())
        suggestions = [TagResponse(name=n, post_count=starter_counts.get(n, 0)) for n in STARTER_TAGS]
        popular = await self.popular_tags(session, limit)
        suggestions += [t for t in popular if t.name not in STARTER_TAGS]
        return suggestions[:limit]

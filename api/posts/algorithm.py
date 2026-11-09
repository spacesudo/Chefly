"""Ephemeral Redis-backed FYP recommendations using interaction score weights."""

import logging
from typing import List
from uuid import UUID

from fastapi import HTTPException, status
from redis.asyncio import Redis
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from api.communities.access import visible_posts_filter
from api.db.models import Posts, PostTag, Tag
from api.db.redis import redis_client

logger = logging.getLogger(__name__)

INTERACTIONS_TTL = 60 * 60 * 24 * 7
PREFERRED_TAGS_LIMIT = 10

SCORE_WEIGHT = {
    "upvotes": 1,
    "downvotes": -1,
    "comments": 5,
    "follows": 10,
    "unfollows" : -10,
    "profile_view" : 3,
    "bookmarks": 7,
    "unbookmarks": -7,
}


def _user_interactions_key(user_id: UUID) -> str:
    return f"user:{user_id}:interactions"


def _user_viewed_key(user_id: UUID) -> str:
    return f"user:{user_id}:viewed_posts"


def _user_preferred_authors_key(user_id: UUID) -> str:
    return f"user:{user_id}:preferred_authors"


def _user_preferred_tags_key(user_id: UUID) -> str:
    return f"user:{user_id}:preferred_tags"


async def get_redis_client() -> Redis:
    return redis_client


async def record_interaction(
    redis: Redis,
    user_id: UUID,
    interaction_type: str,
    author_id: UUID,
    post_id: UUID | None = None,
    *,
    mark_viewed: bool = True,
    tags: list[str] | None = None,
):
    weight = SCORE_WEIGHT.get(interaction_type, 0.5)
    interactions_key = _user_interactions_key(user_id)

    if post_id is not None:
        await redis.hincrbyfloat(interactions_key, str(post_id), weight)
        await redis.zincrby("fyp:ranked_posts", weight, str(post_id))
        if mark_viewed:
            await redis.sadd(_user_viewed_key(user_id), str(post_id))
    else:
        await redis.hincrbyfloat(interactions_key, f"author:{author_id}", weight)

    await redis.zincrby(
        _user_preferred_authors_key(user_id),
        weight,
        str(author_id),
    )

    if tags:
        tags_key = _user_preferred_tags_key(user_id)
        for tag in tags:
            await redis.zincrby(tags_key, weight, tag)
        await redis.expire(tags_key, INTERACTIONS_TTL)

    await redis.expire(interactions_key, INTERACTIONS_TTL)
    await redis.expire(_user_preferred_authors_key(user_id), INTERACTIONS_TTL)


async def safe_record_interaction(
    user_id: UUID,
    interaction_type: str,
    author_id: UUID,
    post_id: UUID | None = None,
    *,
    mark_viewed: bool = True,
    tags: list[str] | None = None,
) -> None:
    try:
        await record_interaction(
            redis_client,
            user_id=user_id,
            interaction_type=interaction_type,
            author_id=author_id,
            post_id=post_id,
            mark_viewed=mark_viewed,
            tags=tags,
        )
    except Exception:
        logger.warning("Failed to record FYP interaction", exc_info=True)


async def get_fyp_recommendations(
    redis: Redis,
    session: AsyncSession,
    user_id: UUID,
    limit: int = 20,
    offset: int = 0,
) -> List[Posts]:
    try:
        has_interactions = await redis.exists(_user_interactions_key(user_id))

        if not has_interactions:
            return await get_popular_posts(session, user_id, limit, offset)
        return await get_personalized_posts(redis, session, user_id, limit, offset)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting FYP recommendations: {e}",
        )


async def get_popular_posts(
    session: AsyncSession, user_id: UUID, limit: int, offset: int = 0
) -> list[Posts]:
    result = await session.execute(
        select(Posts)
        .where(visible_posts_filter(user_id))
        .order_by(Posts.upvote_count.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(result.scalars().all())


async def _fetch_posts_by_ids(
    session: AsyncSession,
    user_id: UUID,
    post_ids: list[UUID],
    exclude_ids: set[UUID],
    limit: int,
    offset: int,
    rank_order: list[UUID] | None = None,
) -> list[Posts]:
    if not post_ids:
        return []

    candidate_ids = [pid for pid in post_ids if pid not in exclude_ids]
    if not candidate_ids:
        return []

    result = await session.execute(
        select(Posts).where(Posts.id.in_(candidate_ids), visible_posts_filter(user_id))
    )
    posts_by_id = {post.id: post for post in result.scalars().all()}

    if rank_order:
        ordered = [posts_by_id[pid] for pid in rank_order if pid in posts_by_id]
    else:
        ordered = list(posts_by_id.values())

    return ordered[offset : offset + limit]


async def get_personalized_posts(
    redis: Redis,
    session: AsyncSession,
    user_id: UUID,
    limit: int,
    offset: int = 0,
) -> list[Posts]:
    seen = {UUID(pid) for pid in await redis.smembers(_user_viewed_key(user_id))}
    candidate_count = offset + limit
    posts: list[Posts] = []
    collected_ids: set[UUID] = set()

    preferred_author_ids = [
        UUID(aid)
        for aid in await redis.zrevrange(
            _user_preferred_authors_key(user_id), 0, candidate_count
        )
    ]

    if preferred_author_ids:
        query = (
            select(Posts)
            .where(Posts.author_id.in_(preferred_author_ids), visible_posts_filter(user_id))
            .order_by(Posts.upvote_count.desc())
            .limit(candidate_count)
        )
        if seen:
            query = query.where(Posts.id.notin_(seen))
        result = await session.execute(query)
        for post in result.scalars().all():
            if post.id not in collected_ids:
                posts.append(post)
                collected_ids.add(post.id)

    if len(posts) < candidate_count:
        preferred_tags = await redis.zrevrangebyscore(
            _user_preferred_tags_key(user_id), "+inf", "(0", start=0, num=PREFERRED_TAGS_LIMIT
        )
        if preferred_tags:
            query = (
                select(Posts)
                .join(PostTag, PostTag.post_id == Posts.id)
                .join(Tag, Tag.id == PostTag.tag_id)
                .where(Tag.name.in_(preferred_tags), visible_posts_filter(user_id))
                .distinct()
                .order_by(Posts.upvote_count.desc(), Posts.created_at.desc())
                .limit(candidate_count - len(posts))
            )
            exclude = seen | collected_ids
            if exclude:
                query = query.where(Posts.id.notin_(exclude))
            result = await session.execute(query)
            for post in result.scalars().all():
                posts.append(post)
                collected_ids.add(post.id)

    if len(posts) < candidate_count:
        ranked_post_ids = [
            UUID(pid)
            for pid in await redis.zrevrange("fyp:ranked_posts", 0, candidate_count * 2)
        ]
        exclude = seen | collected_ids
        backfill = await _fetch_posts_by_ids(
            session,
            user_id,
            ranked_post_ids,
            exclude,
            candidate_count - len(posts),
            0,
            rank_order=ranked_post_ids,
        )
        posts.extend(backfill)

    if not posts:
        return await get_popular_posts(session, user_id, limit, offset)

    return posts[offset : offset + limit]

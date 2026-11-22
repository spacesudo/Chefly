import time

from redis.asyncio import Redis
from api.config import Config


redis_client = Redis(
    host=Config.REDIS_HOST,
    port=Config.REDIS_PORT,
    db=Config.REDIS_DB,
    decode_responses=True,
)


def _ttl_until(expires_at: float) -> int:
    return max(int(expires_at - time.time()) + 1, 1)


async def add_jwt_to_blacklist(jti: str, expires_at: float) -> None:
    """Block `jti` until `expires_at` (Unix timestamp), i.e. for the token's remaining lifetime."""
    await redis_client.set(
        name = jti,
        value = "",
        ex = _ttl_until(expires_at)
    )


async def claim_jwt_once(jti: str, expires_at: float) -> bool:
    """Atomically blacklist `jti`; returns False if it was already blacklisted (token reuse)."""
    return bool(await redis_client.set(
        name = jti,
        value = "",
        ex = _ttl_until(expires_at),
        nx = True
    ))


async def revoke_session(session_id: str) -> None:
    """Block a login session (`sid` claim) for as long as any token issued in it could still be valid."""
    max_lifetime = max(Config.JWT_ACCESS_EXPIRY, Config.JWT_REFRESH_EXPIRY)
    await add_jwt_to_blacklist(session_id, time.time() + max_lifetime)


async def is_jwt_blacklisted(jti: str) -> bool:
    return await redis_client.get(jti) is not None


async def get_redis() -> Redis:
    return redis_client

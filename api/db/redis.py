from redis.asyncio import Redis
from api.config import Config


JTI_EXPIRY = 3600

redis_client = Redis(host=Config.REDIS_HOST, port=Config.REDIS_PORT, db=Config.REDIS_DB)


async def add_jwt_to_blacklist(jti: str) -> None:
    await redis_client.set(
        name = jti,
        value = "",
        ex = JTI_EXPIRY
    )
    
async def is_jwt_blacklisted(jti: str) -> bool:
    return await redis_client.get(jti) is not None

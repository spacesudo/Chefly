from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from typing import AsyncGenerator
from api.config import Config
from sqlmodel import SQLModel

async_engine  = create_async_engine(
    Config.DB_URL,
    echo=True,
)

async def init_db():
    async with async_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
        
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async_session = async_sessionmaker(bind= async_engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        yield session
        

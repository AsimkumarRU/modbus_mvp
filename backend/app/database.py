from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from contextlib import asynccontextmanager

from .config import settings

# Async engine and sessionmaker are shared across the app
engine = create_async_engine(settings.DATABASE_URL, echo=False, future=True)
async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

@asynccontextmanager
async def get_async_session() -> AsyncSession:
    """Provide a transactional scope around a series of operations."""
    async with async_session() as session:
        yield session

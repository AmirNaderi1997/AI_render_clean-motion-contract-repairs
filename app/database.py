"""Async SQLAlchemy connection, disabled when DATABASE_URL is empty."""

import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import text

from app.config import settings
from app.models import Base


if settings.DATABASE_URL:
    # Each web/worker process owns its own event loop and engine. A small,
    # bounded pool prevents Studio SSE polling and parallel browser tabs from
    # opening an unbounded number of PostgreSQL clients.
    engine = create_async_engine(
        settings.DATABASE_URL,
        pool_size=int(os.getenv("DB_POOL_SIZE", "4")),
        max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "2")),
        pool_timeout=float(os.getenv("DB_POOL_TIMEOUT", "20")),
        pool_recycle=int(os.getenv("DB_POOL_RECYCLE", "300")),
        pool_pre_ping=True,
    )
    AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    DB_AVAILABLE = True
else:
    engine = None
    AsyncSessionLocal = None
    DB_AVAILABLE = False


async def get_db() -> AsyncGenerator[AsyncSession | None, None]:
    if AsyncSessionLocal is None:
        # Development/test fallback has no durable store; production startup
        # rejects this configuration before requests are served.
        yield None
        return
    async with AsyncSessionLocal() as session:
        yield session


async def init_db(*, create_schema: bool = True) -> None:
    if engine is None:
        return
    async with engine.begin() as conn:
        if create_schema:
            await conn.run_sync(Base.metadata.create_all)
        else:
            await conn.execute(text("SELECT 1"))


async def close_db() -> None:
    if engine is not None:
        await engine.dispose()

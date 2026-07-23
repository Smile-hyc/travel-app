from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.models.user import Base

_settings = get_settings()

_engine = create_async_engine(
    _settings.user_database_url,
    echo=False,
    connect_args={"check_same_thread": False},
)

_async_session_factory = async_sessionmaker(
    _engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """Create all tables on startup."""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncSession:
    """FastAPI dependency: yield an async database session."""
    async with _async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()

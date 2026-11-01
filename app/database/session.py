"""
Database session and engine initialization.
Supports lightweight local SQLite (default) and PostgreSQL with asynchronous/synchronous support.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings


# Base declarative class
class Base(DeclarativeBase):
    pass


# Synchronous engine (for Alembic migrations and utility scripts)
sync_engine = create_engine(
    settings.SYNC_DATABASE_URL,
    echo=(settings.LOG_LEVEL.upper() == "DEBUG"),
    connect_args={"check_same_thread": False} if "sqlite" in settings.SYNC_DATABASE_URL else {},
)

SyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)

# Asynchronous engine (for FastAPI async request handlers)
async_engine = create_async_engine(
    settings.DATABASE_URL,
    echo=(settings.LOG_LEVEL.upper() == "DEBUG"),
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency provider for FastAPI async endpoints."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def init_db() -> None:
    """Creates database tables synchronously if not already present."""
    from app.database import models  # noqa: F401
    Base.metadata.create_all(bind=sync_engine)

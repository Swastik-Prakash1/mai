"""Shared dependencies: DB session, Redis client, configuration."""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic_settings import BaseSettings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
import redis.asyncio as aioredis


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    anthropic_api_key: str = ""
    redis_url: str = "redis://localhost:6379/0"
    database_url: str = "sqlite+aiosqlite:///data/neuromesh.db"
    chroma_persist_dir: str = "/data/chroma"
    log_level: str = "INFO"
    eval_auto_run: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()


def get_engine():
    """Create async SQLAlchemy engine."""
    settings = get_settings()
    return create_async_engine(settings.database_url, echo=False)


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Create async session factory."""
    engine = get_engine()
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db_session():
    """FastAPI dependency for DB sessions."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_redis():
    """Get async Redis client."""
    settings = get_settings()
    return aioredis.from_url(settings.redis_url, decode_responses=True)

import os

from dotenv import load_dotenv
from sqlalchemy.engine.url import URL, make_url
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL must be set to a PostgreSQL connection URL")


def _postgres_async_url(url: str) -> URL:
    normalized = url.strip()
    if not normalized:
        raise ValueError("DATABASE_URL must not be empty")

    lowered = normalized.lower()
    if lowered.startswith("postgres://"):
        normalized = "postgresql://" + normalized.split("://", 1)[1]
    elif lowered.startswith("postgresql+asyncpg://"):
        pass
    elif lowered.startswith("postgresql://"):
        pass
    else:
        parsed_url = make_url(normalized)
        if parsed_url.drivername not in ("postgresql", "postgresql+asyncpg"):
            raise ValueError("DATABASE_URL must use PostgreSQL with the asyncpg driver")
        return parsed_url.set(drivername="postgresql+asyncpg")

    parsed_url = make_url(normalized)
    if parsed_url.drivername not in ("postgresql", "postgresql+asyncpg"):
        raise ValueError("DATABASE_URL must use PostgreSQL with the asyncpg driver")
    return parsed_url.set(drivername="postgresql+asyncpg")


engine = create_async_engine(
    _postgres_async_url(DATABASE_URL),
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    # Import models so their tables are registered on Base.metadata
    from app.models import connections, server, user_model  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        

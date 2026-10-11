import os

from dotenv import load_dotenv
from sqlalchemy import event, inspect
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./app.db"
)


def _async_driver_url(url: str) -> str:
    """Map a plain sqlite/postgres URL onto its async driver.

    Keeps DATABASE_URL swappable: `sqlite:///./app.db` and
    `postgresql://user:pass@host/db` both work without having to
    remember the `+aiosqlite` / `+asyncpg` driver suffixes.
    """
    if url.startswith("sqlite://") and not url.startswith("sqlite+"):
        return "sqlite+aiosqlite://" + url[len("sqlite://"):]
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://") and not url.startswith("postgresql+"):
        return "postgresql+asyncpg://" + url[len("postgresql://"):]
    return url


engine = create_async_engine(
    _async_driver_url(DATABASE_URL),
    pool_pre_ping=True,
)


@event.listens_for(engine.sync_engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    """SQLite ignores FK constraints (and ON DELETE CASCADE) unless the
    pragma is set on every connection. No-op on other backends."""
    if _async_driver_url(DATABASE_URL).startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

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
        await conn.run_sync(_migrate_servers_table)


def _migrate_servers_table(connection) -> None:
    """Add columns introduced after the initial SQLite schema was created."""
    inspector = inspect(connection)
    if "servers" not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns("servers")}
    missing_columns = {
        "media": "JSON",
        "colour": "VARCHAR",
        "about": "TEXT",
        "categories": "JSON",
        "annotated": "BOOLEAN NOT NULL DEFAULT FALSE",
        "disabled": "BOOLEAN NOT NULL DEFAULT FALSE",
        "location": "VARCHAR",
    }
    preparer = connection.dialect.identifier_preparer
    for name, definition in missing_columns.items():
        if name not in existing:
            connection.exec_driver_sql(
                f"ALTER TABLE {preparer.quote('servers')} "
                f"ADD COLUMN {preparer.quote(name)} {definition}"
            )

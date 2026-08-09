"""Database connection and session management."""

import os
from typing import Any, cast
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from rca_copilot.cli import incident_to_dict
from rca_copilot.incidents import random_incident
from rca_copilot.models_db import Base, IncidentRow
from rca_copilot.retrieval import flatten_events

# The connection string: driver + credentials + host + database name
# Format: postgresql+asyncpg://USER:PASSWORD@HOST:PORT/DATABASE

# Managed platforms (Railway, Heroku, etc.) hand out a *sync* URL:
#   postgres://...  or  postgresql://...
# and sometimes append psycopg-only params like ?sslmode=require.
# SQLAlchemy's async engine needs the postgresql+asyncpg:// scheme, and
# asyncpg rejects sslmode/channel_binding query params. Normalize both.
_ASYNCPG_INCOMPATIBLE_PARAMS = {"sslmode", "channel_binding"}


def _normalize_async_url(url: str) -> str:
    parts = urlsplit(url)
    scheme = parts.scheme
    if scheme in ("postgres", "postgresql"):
        scheme = "postgresql+asyncpg"
    kept: list[tuple[str, str]] = [
        (key, value)
        for key, value in parse_qsl(parts.query)
        if key not in _ASYNCPG_INCOMPATIBLE_PARAMS
    ]
    return urlunsplit(
        (scheme, parts.netloc, parts.path, urlencode(kept), parts.fragment)
    )


DATABASE_URL = _normalize_async_url(
    os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://rca:rca_dev_password@localhost:5432/rca_copilot",
    )
)

engine = create_async_engine(DATABASE_URL, echo=False)

async_session = async_sessionmaker(engine, expire_on_commit=False)




# Full-text search infrastructure. Kept as explicit, idempotent DDL rather than
# ORM magic: the tsvector and GIN index are Postgres-specific, and these ALTERs
# also upgrade an already-existing table that create_all() won't touch.
#
# search_vector is a STORED generated column: Postgres derives it from
# search_text automatically and keeps it in sync on every write, so the app
# never computes a tsvector by hand — it only writes plain search_text.
_FTS_DDL = (
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS search_text text",
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS search_vector tsvector "
    "GENERATED ALWAYS AS (to_tsvector('english', coalesce(search_text, ''))) STORED",
    "CREATE INDEX IF NOT EXISTS ix_incidents_search_vector "
    "ON incidents USING GIN (search_vector)",
)


async def create_tables() -> None:
    """Ensure the full schema (tables + FTS index) exists. Safe to run repeatedly."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for statement in _FTS_DDL:
            await conn.execute(text(statement))
    await _backfill_search_text()


async def _backfill_search_text() -> None:
    """Populate search_text for any rows that predate it (idempotent).

    On a fresh database this matches nothing. On an existing corpus it flattens
    each stored incident's events once; the generated search_vector then updates
    itself. Suitable for a corpus of this size; batch it if it ever grows large.
    """
    async with async_session() as session:
        rows = (
            (await session.execute(select(IncidentRow).where(IncidentRow.search_text.is_(None))))
            .scalars()
            .all()
        )
        for row in rows:
            row.search_text = flatten_events(row.events)
        if rows:
            await session.commit()


async def save_incidents(count: int) -> int:
    """Generate and persist `count` incidents. Returns how many were saved."""
    async with async_session() as session:
        for _ in range(count):
            data = incident_to_dict(random_incident())
            events = cast(list[dict[str, Any]], data["events"])
            row = IncidentRow(
                root_cause=data["root_cause"],
                narrative=data["narrative"],
                events=events,
                search_text=flatten_events(events),
            )
            session.add(row)
        await session.commit()
    return count


async def count_incidents() -> int:
    """Return how many incidents are stored."""
    from sqlalchemy import func

    async with async_session() as session:
        result = await session.execute(select(func.count()).select_from(IncidentRow))
        return result.scalar_one()
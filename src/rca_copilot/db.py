"""Database connection and session management."""

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from rca_copilot.cli import incident_to_dict
from rca_copilot.incidents import random_incident
from rca_copilot.models_db import Base, IncidentRow

# The connection string: driver + credentials + host + database name
# Format: postgresql+asyncpg://USER:PASSWORD@HOST:PORT/DATABASE
DATABASE_URL = "postgresql+asyncpg://rca:rca_dev_password@localhost:5432/rca_copilot"

engine = create_async_engine(DATABASE_URL, echo=False)

async_session = async_sessionmaker(engine, expire_on_commit=False)




async def create_tables() -> None:
    """Create all tables defined on Base. Safe to run repeatedly."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def save_incidents(count: int) -> int:
    """Generate and persist `count` incidents. Returns how many were saved."""
    async with async_session() as session:
        for _ in range(count):
            data = incident_to_dict(random_incident())
            row = IncidentRow(
                root_cause=data["root_cause"],
                narrative=data["narrative"],
                events=data["events"],
            )
            session.add(row)
        await session.commit()
    return count


async def count_incidents() -> int:
    """Return how many incidents are stored."""
    from sqlalchemy import func, select

    async with async_session() as session:
        result = await session.execute(select(func.count()).select_from(IncidentRow))
        return result.scalar_one()
"""Database connection and session management."""

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# The connection string: driver + credentials + host + database name
# Format: postgresql+asyncpg://USER:PASSWORD@HOST:PORT/DATABASE
DATABASE_URL = "postgresql+asyncpg://rca:rca_dev_password@localhost:5432/rca_copilot"

engine = create_async_engine(DATABASE_URL, echo=True)

async_session = async_sessionmaker(engine, expire_on_commit=False)
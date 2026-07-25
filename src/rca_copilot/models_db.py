"""Database models (ORM). Maps incidents to a Postgres table."""

from typing import Any

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class all ORM models inherit from."""


class IncidentRow(Base):
    """One incident, stored as a single row. Events live in a JSONB column."""

    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(primary_key=True)
    root_cause: Mapped[str] = mapped_column(String(100), index=True)
    narrative: Mapped[str] = mapped_column(String)
    events: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
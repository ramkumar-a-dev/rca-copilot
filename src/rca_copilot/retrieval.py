"""Retrieval: find the past incidents most similar to a new set of events."""

import re
from typing import Any

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def flatten_events(events: list[dict[str, Any]]) -> str:
    """Turn an incident's events into searchable text for retrieval."""
    combined = " ".join(f"{e['source']} {e['message']}" for e in events)
    return re.sub(r"\d+", "", combined)


class RetrievedIncident(BaseModel):
    """A stored incident returned by retrieval, with its relevance score."""

    id: int
    root_cause: str
    narrative: str
    score: float  # ts_rank relevance; higher = more overlap. Not a probability.


# plainto_tsquery ANDs every term ('a & b & c') — far too strict for retrieval,
# since an incoming incident would then have to share *every* word with a stored
# one. We reuse plainto's tokenizing/stemming/escaping, then swap the AND
# operators for OR so any shared vocabulary matches; ts_rank sorts by overlap.
_OR_QUERY = "replace(plainto_tsquery('english', :q)::text, '&', '|')::tsquery"

_RETRIEVE_SQL = text(
    f"""
    SELECT id, root_cause, narrative,
           ts_rank(search_vector, {_OR_QUERY}) AS score
    FROM incidents
    WHERE search_vector @@ {_OR_QUERY}
    ORDER BY score DESC, id
    LIMIT :k
    """
)


async def retrieve_similar(
    session: AsyncSession, query_text: str, k: int = 5
) -> list[RetrievedIncident]:
    """Return the top-k stored incidents whose text overlaps query_text, ranked.

    Retrieval only finds and ranks. Deciding whether the top match is strong
    enough to act on — or to abstain — is the reasoning layer's job (Stage 4).
    """
    result = await session.execute(_RETRIEVE_SQL.bindparams(q=query_text, k=k))
    return [
        RetrievedIncident(
            id=row.id,
            root_cause=row.root_cause,
            narrative=row.narrative,
            score=float(row.score),
        )
        for row in result
    ]
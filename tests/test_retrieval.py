"""Tests for full-text retrieval over the incident corpus.

Requires a reachable Postgres (DATABASE_URL); CI provides one. Each test
truncates and seeds a known corpus so ranking assertions are deterministic
regardless of what other tests wrote.
"""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from rca_copilot.api import app
from rca_copilot.db import async_session, create_tables, engine
from rca_copilot.models_db import IncidentRow
from rca_copilot.retrieval import flatten_events

POOL = (
    "connection_pool_exhaustion",
    [
        {
            "source": "weblogic-ms1",
            "message": "Connections pool exhausted, no connections available",
        },
        {
            "source": "xstore-pos",
            "message": "Socket timeout exception could not acquire DB connection",
        },
    ],
)
FILE = (
    "empty_upstream_file",
    [
        {
            "source": "datalake-etl",
            "message": "Job completed successfully but zero records, order missing",
        },
    ],
)


@pytest.fixture(autouse=True)
async def _fresh_engine_pool() -> AsyncIterator[None]:
    # pytest-asyncio uses a fresh loop per test; dispose so the engine doesn't
    # reuse a connection bound to a previous loop.
    yield
    await engine.dispose()


async def _seed(rows: list[tuple[str, list[dict[str, str]]]]) -> None:
    async with async_session() as session:
        await session.execute(text("TRUNCATE incidents RESTART IDENTITY"))
        for root_cause, events in rows:
            session.add(
                IncidentRow(
                    root_cause=root_cause,
                    narrative=f"{root_cause} narrative",
                    events=events,
                    search_text=flatten_events(events),
                )
            )
        await session.commit()


async def _post_similar(
    events: list[dict[str, str]], k: int = 5
) -> list[dict[str, object]]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/incidents/similar", json={"events": events, "k": k}
        )
    assert resp.status_code == 200
    matches: list[dict[str, object]] = resp.json()["matches"]
    return matches


async def test_retrieval_ranks_matching_pattern_first() -> None:
    await create_tables()
    await _seed([POOL, FILE])
    matches = await _post_similar(
        [
            {
                "source": "weblogic-ms9",
                "message": "pool exhausted, cannot acquire connection, socket timeout",
            }
        ]
    )
    assert matches, "expected at least one match"
    assert matches[0]["root_cause"] == "connection_pool_exhaustion"
    assert matches[0]["score"] > 0


async def test_retrieval_or_semantics_matches_on_partial_overlap() -> None:
    # A sparse query sharing only *some* vocabulary must still match — the whole
    # reason we use OR semantics rather than plainto_tsquery's AND.
    await create_tables()
    await _seed([POOL])
    matches = await _post_similar(
        [{"source": "weblogic-ms2", "message": "pool exhausted"}]
    )
    assert any(m["root_cause"] == "connection_pool_exhaustion" for m in matches)


async def test_retrieval_returns_empty_on_no_overlap() -> None:
    await create_tables()
    await _seed([POOL])
    matches = await _post_similar(
        [{"source": "unknown", "message": "totally unrelated gibberish xyzzy"}]
    )
    assert matches == []
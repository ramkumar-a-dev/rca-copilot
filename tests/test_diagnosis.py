"""Tests for the Stage 4 baseline diagnosis (majority-vote-or-abstain).

The gate logic is a pure function over RetrievedIncident lists, so most of
these need no database. One end-to-end test drives the /diagnose endpoint
against real Postgres to prove the retrieve -> reason -> respond wiring.
"""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from rca_copilot.api import app
from rca_copilot.db import async_session, create_tables, engine
from rca_copilot.diagnosis import INSUFFICIENT, diagnose
from rca_copilot.models_db import IncidentRow
from rca_copilot.retrieval import RetrievedIncident, flatten_events

POOL = "connection_pool_exhaustion"
FILE = "empty_upstream_file"
HALF = "half_open_channel"


def _m(root_cause: str) -> RetrievedIncident:
    return RetrievedIncident(id=1, root_cause=root_cause, narrative="n", score=0.1)


# --- pure gate logic (no database) ------------------------------------------


def test_majority_names_the_cause() -> None:
    d = diagnose([_m(POOL), _m(POOL), _m(POOL), _m(FILE), _m(HALF)], k=5)
    assert d.root_cause == POOL
    assert len(d.evidence) == 5


def test_no_majority_abstains() -> None:
    d = diagnose([_m(POOL), _m(POOL), _m(FILE), _m(FILE), _m(HALF)], k=5)
    assert d.root_cause == INSUFFICIENT


def test_thin_evidence_abstains_even_when_unanimous() -> None:
    # Two agreeing matches is not a majority of the 5 requested — abstain.
    d = diagnose([_m(POOL), _m(POOL)], k=5)
    assert d.root_cause == INSUFFICIENT


def test_no_matches_abstains_with_empty_evidence() -> None:
    d = diagnose([], k=5)
    assert d.root_cause == INSUFFICIENT
    assert d.evidence == []


def test_unanimous_majority_is_high_confidence() -> None:
    d = diagnose([_m(POOL)] * 5, k=5)
    assert d.root_cause == POOL
    assert d.confidence == "high"


def test_evidence_is_shown_even_when_abstaining() -> None:
    d = diagnose([_m(POOL), _m(FILE)], k=5)
    assert d.root_cause == INSUFFICIENT
    assert len(d.evidence) == 2  # it shows what it looked at


# --- end-to-end through the endpoint (needs Postgres) -----------------------


@pytest.fixture(autouse=True)
async def _fresh_engine_pool() -> AsyncIterator[None]:
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


async def test_diagnose_endpoint_names_pool_exhaustion() -> None:
    await create_tables()
    pool_events = [
        {"source": "weblogic-ms1", "message": "connection pool exhausted, no connections"},
        {"source": "xstore-pos", "message": "socket timeout could not acquire DB connection"},
    ]
    await _seed([(POOL, pool_events)] * 5 + [(FILE, [
        {"source": "datalake-etl", "message": "job completed zero records order missing"},
    ])])
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/diagnose",
            json={
                "events": [
                    {
                        "source": "weblogic-ms9",
                        "message": "pool exhausted, cannot acquire connection, socket timeout",
                    }
                ],
                "k": 5,
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["root_cause"] == POOL
    assert body["evidence"], "diagnosis should cite the incidents it used"
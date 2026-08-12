"""Tests for the Stage 4b LLM reasoner, using a fake client (no API key).

The real Anthropic call is never exercised here — a fake LLMClient returns
canned structured responses, so these run deterministically in CI with no key
and no cost. They cover the reasoner's guardrails and the /diagnose fallback.
"""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from rca_copilot import api
from rca_copilot.api import app
from rca_copilot.db import async_session, create_tables, engine
from rca_copilot.diagnosis import INSUFFICIENT, diagnose_with_llm
from rca_copilot.models_db import IncidentRow
from rca_copilot.retrieval import RetrievedIncident, flatten_events

POOL = "connection_pool_exhaustion"
HALF = "half_open_channel"


class FakeClient:
    def __init__(self, response: dict[str, Any]) -> None:
        self._response = response
        self.calls = 0

    async def diagnose(self, *, system: str, user: str) -> dict[str, Any]:
        self.calls += 1
        return self._response


def _m(root_cause: str) -> RetrievedIncident:
    return RetrievedIncident(id=1, root_cause=root_cause, narrative="n", score=0.1)


# --- reasoner guardrails (no database) --------------------------------------


async def test_llm_commits_on_a_justified_cause() -> None:
    client = FakeClient(
        {"root_cause": POOL, "confidence": "high", "reasoning": "pool ceiling"}
    )
    d = await diagnose_with_llm(client, [{"source": "s", "message": "m"}], [_m(POOL), _m(HALF)])
    assert d.root_cause == POOL
    assert d.confidence == "high"
    assert len(d.evidence) == 2


async def test_llm_can_abstain() -> None:
    client = FakeClient({"root_cause": INSUFFICIENT, "confidence": "low", "reasoning": "unclear"})
    d = await diagnose_with_llm(client, [{"source": "s", "message": "m"}], [_m(POOL)])
    assert d.root_cause == INSUFFICIENT


async def test_offscript_cause_is_coerced_to_abstain() -> None:
    # The model must pick a cause present in the evidence; anything else is not trusted.
    client = FakeClient({"root_cause": "made_up_cause", "confidence": "high", "reasoning": "x"})
    d = await diagnose_with_llm(client, [{"source": "s", "message": "m"}], [_m(POOL)])
    assert d.root_cause == INSUFFICIENT


async def test_no_matches_abstains_without_calling_the_model() -> None:
    client = FakeClient({"root_cause": POOL, "confidence": "high", "reasoning": "x"})
    d = await diagnose_with_llm(client, [{"source": "s", "message": "m"}], [])
    assert d.root_cause == INSUFFICIENT
    assert client.calls == 0  # no evidence -> no API call wasted


# --- /diagnose fallback + wiring (needs Postgres) ---------------------------


@pytest.fixture(autouse=True)
async def _fresh_engine_pool() -> AsyncIterator[None]:
    yield
    await engine.dispose()


async def _seed_pool_heavy() -> None:
    async with async_session() as session:
        await session.execute(text("TRUNCATE incidents RESTART IDENTITY"))
        events = [
            {"source": "weblogic-ms1", "message": "connection pool exhausted no connections"},
            {"source": "xstore-pos", "message": "socket timeout could not acquire DB connection"},
        ]
        for _ in range(5):
            session.add(IncidentRow(root_cause=POOL, narrative="pool", events=events,
                                    search_text=flatten_events(events)))
        await session.commit()


async def test_diagnose_falls_back_to_baseline_without_a_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # No configured client -> endpoint must use the deterministic baseline.
    monkeypatch.setattr(api, "get_llm_client", lambda: None)
    await create_tables()
    await _seed_pool_heavy()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/diagnose", json={
            "events": [{"source": "weblogic-ms9", "message": "pool exhausted socket timeout"}],
            "k": 5,
        })
    assert resp.status_code == 200
    assert resp.json()["root_cause"] == POOL


async def test_diagnose_uses_llm_when_client_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeClient(
        {"root_cause": POOL, "confidence": "medium", "reasoning": "cited pool ceiling"}
    )
    monkeypatch.setattr(api, "get_llm_client", lambda: fake)
    await create_tables()
    await _seed_pool_heavy()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/diagnose", json={
            "events": [{"source": "s", "message": "pool exhausted"}], "k": 5,
        })
    assert resp.status_code == 200
    body = resp.json()
    assert body["root_cause"] == POOL
    assert body["reasoning"] == "cited pool ceiling"
    assert fake.calls == 1
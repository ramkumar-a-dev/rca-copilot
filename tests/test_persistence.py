"""End-to-end tests for the Postgres-backed endpoints.

These require a reachable Postgres (DATABASE_URL). CI provides one as a
service; locally, run `docker compose up -d db` first. They run in a single
asyncio event loop (asyncio_mode = "auto"), so the async engine's connections
are created and reused within one loop — avoiding the cross-loop errors you
get when driving async SQLAlchemy through the sync TestClient.
"""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from rca_copilot.api import app
from rca_copilot.db import create_tables, engine


@pytest.fixture(autouse=True)
async def _fresh_engine_pool() -> AsyncIterator[None]:
    """Dispose the shared async engine's pool after each test.

    pytest-asyncio runs each async test in its own event loop. The module-level
    engine pools asyncpg connections bound to the loop that created them, so a
    connection pooled in one test raises "attached to a different loop" in the
    next. Disposing after each test forces fresh connections in each loop.
    Production keeps normal pooling — this fixture only affects the test suite.
    """
    yield
    await engine.dispose()


async def test_save_persists_and_count_reflects_it() -> None:
    await create_tables()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        before = (await client.get("/incidents/count")).json()["count"]

        response = await client.post("/incidents/save", json={"count": 4})
        assert response.status_code == 200
        assert response.json()["saved"] == 4

        after = (await client.get("/incidents/count")).json()["count"]
        assert after == before + 4


async def test_count_endpoint_returns_an_integer() -> None:
    await create_tables()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        body = (await client.get("/incidents/count")).json()
        assert isinstance(body["count"], int)
        assert body["count"] >= 0
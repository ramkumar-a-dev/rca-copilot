"""HTTP API for RCA Copilot."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel, Field

from rca_copilot.cli import incident_to_dict
from rca_copilot.db import count_incidents, create_tables, save_incidents
from rca_copilot.incidents import random_incident


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Run once on startup: ensure the incidents table exists.

    This couples boot to a reachable Postgres on purpose — a persistence
    service that can't reach its database should fail loudly, not pretend.
    """
    await create_tables()
    yield


app = FastAPI(title="RCA Copilot", version="0.1.0", lifespan=lifespan)


class GenerateRequest(BaseModel):
    """Request body for generating incidents."""

    count: int = Field(default=10, ge=1, le=1000)


class GenerateResponse(BaseModel):
    """Response containing generated incidents."""

    count: int
    incidents: list[dict[str, object]]

class DiagnoseRequest(BaseModel):
    """A bundle of log lines to diagnose."""

    events: list[str] = Field(min_length=1)


class DiagnoseResponse(BaseModel):
    """A proposed root cause with cited evidence."""

    root_cause: str
    confidence: str
    evidence: list[str]
    reasoning: str


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check. Deployment platforms ping this."""
    return {"status": "ok"}


@app.post("/incidents")
def create_incidents(request: GenerateRequest) -> GenerateResponse:
    """Generate a batch of synthetic incidents (in-memory, not persisted)."""
    incidents = [incident_to_dict(random_incident()) for _ in range(request.count)]
    return GenerateResponse(count=len(incidents), incidents=incidents)


@app.post("/incidents/save")
async def save_incidents_endpoint(request: GenerateRequest) -> dict[str, int]:
    """Generate incidents and persist them to Postgres. Returns how many were saved."""
    saved = await save_incidents(request.count)
    return {"saved": saved}


@app.get("/incidents/count")
async def incidents_count_endpoint() -> dict[str, int]:
    """Return how many incidents are currently stored in Postgres."""
    return {"count": await count_incidents()}


@app.post("/diagnose")
def diagnose(request: DiagnoseRequest) -> DiagnoseResponse:
    """Propose a root cause for a bundle of log events. Not yet implemented."""
    return DiagnoseResponse(
        root_cause="insufficient_evidence",
        confidence="low",
        evidence=[],
        reasoning="Diagnosis is not yet implemented. This endpoint returns a stub.",
    )
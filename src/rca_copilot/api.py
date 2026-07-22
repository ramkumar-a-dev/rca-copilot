"""HTTP API for RCA Copilot."""

from fastapi import FastAPI
from pydantic import BaseModel, Field

from rca_copilot.cli import incident_to_dict
from rca_copilot.incidents import random_incident

app = FastAPI(title="RCA Copilot", version="0.1.0")


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
    """Generate a batch of synthetic incidents."""
    incidents = [incident_to_dict(random_incident()) for _ in range(request.count)]
    return GenerateResponse(count=len(incidents), incidents=incidents)

@app.post("/diagnose")
def diagnose(request: DiagnoseRequest) -> DiagnoseResponse:
    """Propose a root cause for a bundle of log events. Not yet implemented."""
    return DiagnoseResponse(
        root_cause="insufficient_evidence",
        confidence="low",
        evidence=[],
        reasoning="Diagnosis is not yet implemented. This endpoint returns a stub.",
    )
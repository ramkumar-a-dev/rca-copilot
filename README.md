# RCA Copilot

[![CI](https://github.com/ramkumar-a-dev/rca-copilot/actions/workflows/ci.yml/badge.svg)](https://github.com/ramkumar-a-dev/rca-copilot/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.12-blue.svg)
![Lint](https://img.shields.io/badge/lint-ruff-000000.svg)
![Types](https://img.shields.io/badge/types-mypy--strict-2a6db2.svg)

Automated root-cause analysis for large-scale retail store systems — point-of-sale, order orchestration, payments, and the middleware between them.

The goal is agentic RCA: given a bundle of log events, retrieve similar past incidents and reason toward a root cause — or abstain when the evidence is too thin to be honest. Today the service is deployed with a real persistence layer and CI; the retrieval and reasoning layer is under active construction (see [Status](#status--roadmap)).

**▶ Try it live:** **[rca-copilot-production.up.railway.app/docs](https://rca-copilot-production.up.railway.app/docs)** — interactive API docs, no setup.

```bash
# health
curl https://rca-copilot-production.up.railway.app/health

# generate and persist 5 synthetic incidents, then read the stored count
curl -X POST https://rca-copilot-production.up.railway.app/incidents/save \
  -H 'Content-Type: application/json' -d '{"count": 5}'
curl https://rca-copilot-production.up.railway.app/incidents/count
```

---

## Why this exists

For eight years I did root-cause analysis by hand across a distributed retail store-systems estate — POS, order orchestration, payment integrations, and the middleware stitching them together — for brands including Adidas, Torrid, and Sally Beauty. When something broke across thousands of stores, the reasoning was mine: read the logs, correlate the events, recognize the failure class, find the cause.

This project is an attempt to automate that reasoning, and — just as importantly — to **measure honestly whether it actually works** rather than assume it does.

All incident and log data is **synthetic**. It reproduces *classes* of failure I've seen in production — connection-pool exhaustion, empty upstream files, half-open channels, infrastructure shutdowns, order-state divergence — with no proprietary or operational detail from any real system. The domain shapes the problem; none of the data is real.

---

## What it does today

A FastAPI service backed by Postgres. The surface, all browsable at `/docs`:

| Endpoint | Method | What it does |
| --- | --- | --- |
| `/health` | GET | Liveness check. |
| `/incidents` | POST | Generate a batch of synthetic incidents (in-memory). |
| `/incidents/save` | POST | Generate incidents **and persist them** to Postgres. |
| `/incidents/count` | GET | Read how many incidents are stored. |
| `/diagnose` | POST | Propose a root cause for a bundle of log events. **Currently a stub** — returns `insufficient_evidence`. This is the layer I'm building now. |

An incident is a labeled root cause, a human-readable narrative, and an ordered list of `LogEvent`s (timestamp, source, severity, message) — the same shape a real estate emits, generated across five distinct failure patterns.

---

## Architecture & the reasoning behind it

**Stack:** FastAPI · async SQLAlchemy 2.0 (asyncpg) · PostgreSQL (JSONB) · Docker (multi-stage) · Railway · `uv` · pytest · mypy · ruff.

The choices worth defending:

**One incident, one row, events in JSONB.** An incident is a variable-length list of heterogeneous log events. Rather than shred those into a rigid `events` table, each incident is a single row with its events in a JSONB column. This keeps writes atomic, preserves the full event payload losslessly, and lets the *retrieval* layer decide how to index events later — full-text search first, vector embeddings after — without migrating the event schema. The tradeoff is no relational querying of individual events; this workload retrieves whole incidents, not slices of events, so that cost is one I don't pay.

**Validation at the boundary.** Request and response bodies are Pydantic models. Malformed input is rejected at the HTTP edge with a clear `422` before it reaches business logic or the database. Types are enforced once, at the boundary, so internal code can trust its inputs.

**Async all the way down.** SQLAlchemy's async engine over asyncpg means the service isn't blocked on database round-trips — the I/O model matches FastAPI's, so concurrency comes from the framework rather than being bolted on.

**Deploy-portable config.** The same image runs unchanged locally, on Railway, or on any platform that injects a `$PORT` — the app binds the injected port (falling back to `8000`) and normalizes whatever `DATABASE_URL` the platform hands it, coercing sync `postgres://` / `postgresql://` schemes to the async asyncpg driver and stripping psycopg-only query params that asyncpg rejects. Configuration adapts to the environment instead of the environment adapting to configuration. (This one was earned the hard way during the first deploy.)

**Multi-stage Docker + locked dependencies.** Build tooling stays out of the runtime image, and the image installs from a frozen `uv.lock`, so what deploys is exactly what was tested — not a fresh, drifted resolution.

---

## Run it locally

Requires Docker.

```bash
# Full stack — API + Postgres — on http://localhost:8000
docker compose up --build

# ...or just the database, and run the app on the host
docker compose up -d db
uv run uvicorn rca_copilot.api:app --reload
```

Open <http://localhost:8000/docs>.

### Tests, types, lint

The suite runs against a **real Postgres, not a mock**. Locally, `docker compose up -d db` first; in CI, the workflow stands up its own `postgres:16` service and the async persistence tests actually read and write to it — so "passes CI" means the database path works, not just that the code compiles.

```bash
uv sync --dev
uv run ruff check .     # lint
uv run mypy src         # strict type checking
uv run pytest           # unit + async persistence tests
```

Every push is gated on all three.

---

## Status & roadmap

Honest state of the build. This is a deliberate, staged project, not a finished product — and the `/diagnose` stub is expected, not an oversight.

- ✅ **Domain model + synthetic data** — five failure classes, generators, CLI.
- ✅ **HTTP API + Postgres persistence** — validated endpoints, async ORM, tables created on boot.
- ✅ **Containerized & deployed** — multi-stage Docker, live on Railway, CI-gated (ruff + mypy strict + pytest against real Postgres).
- 🚧 **Retrieval** — full-text search over the incident corpus, so `/diagnose` can find the incidents most similar to an incoming set of events. *(Current work.)*
- ⬜ **Diagnosis** — LLM reasoning over the retrieved evidence, **with the ability to abstain when evidence is thin.** This is why `/diagnose` returns `insufficient_evidence` today: the honest default is to refuse until the reasoning exists.
- ⬜ **Evaluation** — measure diagnosis quality against known root causes, so improvement is something I can prove rather than claim.

---

I'm a systems person moving into backend and AI engineering. This repo is where I turn eight years of production root-cause work into software — built in the open, tested for real, and measured honestly.

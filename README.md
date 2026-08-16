# RCA Copilot

[![CI](https://github.com/ramkumar-a-dev/rca-copilot/actions/workflows/ci.yml/badge.svg)](https://github.com/ramkumar-a-dev/rca-copilot/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.12-blue.svg)
![Lint](https://img.shields.io/badge/lint-ruff-000000.svg)
![Types](https://img.shields.io/badge/types-mypy--strict-2a6db2.svg)

Automated root-cause analysis for large-scale retail store systems — point-of-sale, order orchestration, payments, and the middleware between them.

Given a bundle of log events, RCA Copilot retrieves the most similar past incidents, reasons over that evidence to name a root cause — separating the actual cause from downstream symptoms — and **abstains when the evidence is too thin to be honest.** It runs the full pipeline end to end and is live in production.

**▶ Try it live:** **[rca-copilot-production.up.railway.app/docs](https://rca-copilot-production.up.railway.app/docs)** — interactive API docs, no setup.

```bash
# seed a corpus, then diagnose a new incident
curl -X POST https://rca-copilot-production.up.railway.app/incidents/save \
  -H 'Content-Type: application/json' -d '{"count": 50}'

curl -s -X POST https://rca-copilot-production.up.railway.app/diagnose \
  -H 'Content-Type: application/json' \
  -d '{"events":[{"source":"weblogic-ms1","message":"connection pool exhausted, socket timeout acquiring DB connection"}],"k":5}'
```

A representative `/diagnose` response — note it names the cause and explicitly dismisses the misleading symptom:

```json
{
  "root_cause": "connection_pool_exhaustion",
  "confidence": "high",
  "reasoning": "The incident reports 'connection pool exhausted' on weblogic-ms1, which is the underlying cause. The 'socket timeout acquiring DB connection' is a downstream symptom of pool exhaustion, not the root cause. All five retrieved similar incidents confirm this pattern.",
  "evidence": [ { "id": 3, "root_cause": "connection_pool_exhaustion", "narrative": "...", "score": 0.076 }, "..." ]
}
```

---

## Why this exists

For eight years I did root-cause analysis by hand across a distributed retail store-systems estate — POS, order orchestration, payment integrations, and the middleware stitching them together — for brands including Adidas, Torrid, and Sally Beauty. When something broke across thousands of stores, the reasoning was mine: read the logs, correlate the events, recognize the failure class, find the cause.

This project automates that reasoning — and, just as importantly, **measures honestly whether it actually works** rather than assuming it does.

All incident and log data is **synthetic**. It reproduces *classes* of failure I've seen in production — connection-pool exhaustion, empty upstream files, half-open channels, infrastructure shutdowns, order-state divergence — with no proprietary or operational detail from any real system. The domain shapes the problem; none of the data is real.

---

## What it does

A FastAPI service backed by Postgres. The full surface, browsable at `/docs`:

| Endpoint | Method | What it does |
| --- | --- | --- |
| `/health` | GET | Liveness check. |
| `/incidents` | POST | Generate a batch of synthetic incidents (in-memory). |
| `/incidents/save` | POST | Generate incidents **and persist them** to Postgres. |
| `/incidents/count` | GET | Read how many incidents are stored. |
| `/incidents/similar` | POST | Full-text retrieval: return the stored incidents most similar to a bundle of events, ranked. |
| `/diagnose` | POST | Retrieve similar incidents, **reason over the evidence to name a root cause — or abstain** — and return the cited evidence and an explanation. |

An incident is a labeled root cause, a human-readable narrative, and an ordered list of `LogEvent`s (timestamp, source, severity, message) — the same shape a real estate emits, generated across five distinct failure patterns.

---

## How it works

**Stack:** FastAPI · async SQLAlchemy 2.0 (asyncpg) · PostgreSQL (JSONB + full-text search) · Anthropic API · Docker (multi-stage) · Railway · `uv` · pytest · mypy · ruff.

The pipeline: **generate → persist → retrieve → reason → diagnose-or-abstain.** The choices worth defending:

**One incident, one row, events in JSONB.** An incident is a variable-length list of heterogeneous log events. Rather than shred those into a rigid `events` table, each incident is a single row with its events in a JSONB column — atomic writes, lossless payloads, and the freedom to index events however retrieval needs without migrating the event schema. The tradeoff, no relational querying of individual events, costs nothing here: this workload retrieves whole incidents, not slices of events.

**Retrieval via Postgres full-text search.** Each incident's events are flattened to searchable text; a `tsvector` column (a Postgres *generated* column, kept in sync automatically) is indexed with GIN. The query uses OR-semantics — reusing `plainto_tsquery`'s tokenizing and stemming, then matching on *any* shared vocabulary and ranking by `ts_rank` — so an incoming incident matches on partial overlap instead of requiring every term. Crucially, the query and the corpus are flattened by the *same* function, so they always share one vocabulary. (Full-text search first; the JSONB design leaves the door open to vector embeddings later without a schema change.)

**Two-tier reasoning, with abstention as a first-class outcome.** A deterministic baseline takes a k-nearest-neighbour majority vote over the retrieved labels and *abstains* unless a cause holds a true majority — because over-calling a root cause sends responders down the wrong path. On top of that, an LLM reasoner (Anthropic, via **forced tool use** for guaranteed structured output) reads the new events and the retrieved narratives, and may commit on a harder, mixed case *when it can justify the call from the evidence* — recognizing, for example, that a timeout is downstream of a different underlying cause. Its answer is constrained to the causes actually present in the evidence; anything off-script is treated as an abstention rather than trusted. **If no API key is configured, `/diagnose` degrades gracefully to the deterministic vote** — the service never hard-depends on the model.

**Validation at the boundary.** Request and response bodies are Pydantic models; malformed input is rejected at the HTTP edge with a clear `422` before it reaches business logic or the database.

**Deploy-portable config.** The same image runs unchanged locally, on Railway, or on any platform that injects a `$PORT` — the app binds the injected port (falling back to `8000`) and normalizes whatever `DATABASE_URL` it's handed, coercing sync `postgres://`/`postgresql://` schemes to the async asyncpg driver and stripping psycopg-only query params asyncpg rejects.

**Multi-stage Docker + locked dependencies.** Build tooling stays out of the runtime image, and the image installs from a frozen `uv.lock`, so what deploys is exactly what was tested.

---

## How it's evaluated

The whole point is knowing whether it works, not assuming it. The eval harness (`python -m rca_copilot.evals`) generates a labeled corpus and a **disjoint held-out set** — held-out incidents are never saved to the corpus, so retrieval finds *similar-but-different* incidents and the score measures generalization, not memorization. The run is seeded and reproducible.

Because the system can abstain, a single "accuracy" number would lie. The harness reports **accuracy-when-it-commits** (the primary metric) alongside **coverage** (how often it commits at all) — an abstention is treated as an honest "I don't know," not a wrong answer.

**Baseline (majority vote), reproducible seeded run:** 49/50 held-out incidents correct with 1 abstention — **100% accuracy when it commits, 98% coverage**; across seeds, accuracy-when-decided averages ~98%. Because the failure classes are largely separable, the hard cases surface as honest abstentions rather than wrong answers.

The LLM reasoner is scored on the *same* harness for a direct, honest comparison:

```bash
uv run python -m rca_copilot.evals          # baseline (majority vote)
uv run python -m rca_copilot.evals --llm    # LLM reasoner (needs ANTHROPIC_API_KEY)
```

Its edge is recovering the hard/abstained cases and producing causal explanations a vote cannot — not a dramatic accuracy leap on an already-separable dataset. Stated plainly because that's the honest read.

---

## Run it locally

Requires Docker.

```bash
# full stack — API + Postgres — on http://localhost:8000
docker compose up --build

# ...or just the database, and run the app on the host
docker compose up -d db
uv run uvicorn rca_copilot.api:app --reload
```

`/diagnose` uses the LLM when `ANTHROPIC_API_KEY` is set (optionally `RCA_LLM_MODEL`); otherwise it falls back to the deterministic vote. Open <http://localhost:8000/docs>.

### Tests, types, lint

The suite runs against a **real Postgres, not a mock** — CI stands up its own `postgres:16` service and the async tests read and write to it, so "passes CI" means the database path works, not just that the code compiles. The LLM path is tested against a fake client, so tests need no API key and cost nothing.

```bash
uv sync --dev
uv run ruff check .     # lint
uv run mypy src         # strict type checking
uv run pytest           # unit + async integration tests
```

Every push is gated on all three.

---

## Status

- ✅ **Domain model + synthetic data** — five failure classes, with varied, sparse, and deliberately confusable incidents.
- ✅ **HTTP API + Postgres persistence** — validated endpoints, async ORM, schema created on boot.
- ✅ **Containerized & deployed** — multi-stage Docker, live on Railway, CI-gated (ruff + mypy strict + pytest against real Postgres).
- ✅ **Retrieval** — full-text search over the incident corpus (`/incidents/similar`).
- ✅ **Diagnosis** — deterministic majority-vote baseline **and** an LLM reasoner over the evidence, both able to abstain; live at `/diagnose`.
- ✅ **Evaluation** — reproducible harness with a disjoint split, honest accuracy/coverage metrics, and a measured baseline.

Possible next steps: vector-embedding retrieval alongside full-text, and a larger, harder eval set to widen the margin the LLM is measured against.

---

I'm a systems person moving into backend and AI engineering. This repo is where I turned eight years of production root-cause work into software — built in the open, tested for real, and measured honestly.
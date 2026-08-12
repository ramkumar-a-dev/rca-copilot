"""Evaluation harness: measure how good the baseline diagnosis actually is.

Generates a labelled corpus and a *disjoint* held-out set, runs each held-out
incident through the real retrieve -> diagnose pipeline, and reports how often
it is right. The held-out incidents are never saved to the corpus, so retrieval
finds similar-but-different past incidents — this measures generalisation, not
memorisation, which is the only honest way to score it.

The RNG is seeded, so the benchmark is reproducible. Run it against a dev
database (it truncates and rebuilds the corpus): `python -m rca_copilot.evals`.
"""

import asyncio
import random
from typing import Any, cast

from pydantic import BaseModel
from sqlalchemy import text

from rca_copilot.cli import incident_to_dict
from rca_copilot.db import async_session, create_tables, save_incidents
from rca_copilot.diagnosis import INSUFFICIENT, diagnose, diagnose_with_llm
from rca_copilot.incidents import random_incident
from rca_copilot.llm import get_llm_client
from rca_copilot.retrieval import flatten_events, retrieve_similar


class EvalReport(BaseModel):
    """The scored outcome of an eval run."""

    total: int
    correct: int
    wrong: int
    abstained: int
    accuracy_when_decided: float  # correct / decided — the primary metric
    coverage: float  # decided / total — the guardrail
    overall_accuracy: float  # correct / total — abstain counted as miss
    confusion: dict[str, dict[str, int]]  # true -> {wrongly predicted -> count}


def score(outcomes: list[tuple[str, str]]) -> EvalReport:
    """Turn (true, predicted) pairs into metrics. Pure — no I/O, easy to test."""
    total = len(outcomes)
    correct = wrong = abstained = 0
    confusion: dict[str, dict[str, int]] = {}
    for true, predicted in outcomes:
        if predicted == INSUFFICIENT:
            abstained += 1
        elif predicted == true:
            correct += 1
        else:
            wrong += 1
            confusion.setdefault(true, {})
            confusion[true][predicted] = confusion[true].get(predicted, 0) + 1
    decided = correct + wrong
    return EvalReport(
        total=total,
        correct=correct,
        wrong=wrong,
        abstained=abstained,
        accuracy_when_decided=correct / decided if decided else 0.0,
        coverage=decided / total if total else 0.0,
        overall_accuracy=correct / total if total else 0.0,
        confusion=confusion,
    )


async def run_eval(
    corpus_size: int = 100,
    test_size: int = 50,
    k: int = 5,
    seed: int = 42,
    use_llm: bool = False,
) -> EvalReport:
    """Build a corpus + disjoint held-out set, run the pipeline, and score it."""
    random.seed(seed)

    await create_tables()
    async with async_session() as session:
        await session.execute(text("TRUNCATE incidents RESTART IDENTITY"))
        await session.commit()

    # Corpus: the first `corpus_size` draws from the seeded stream, persisted.
    await save_incidents(corpus_size)

    # Held-out: the *next* draws — different incidents, never saved to the corpus.
    client = get_llm_client() if use_llm else None
    outcomes: list[tuple[str, str]] = []
    for _ in range(test_size):
        incident = incident_to_dict(random_incident())
        true = cast(str, incident["root_cause"])
        events = cast(list[dict[str, Any]], incident["events"])
        query = flatten_events(events)
        async with async_session() as session:
            matches = await retrieve_similar(session, query, k)
        if client is not None:
            predicted = (await diagnose_with_llm(client, events, matches)).root_cause
        else:
            predicted = diagnose(matches, k).root_cause
        outcomes.append((true, predicted))

    return score(outcomes)


def format_report(report: EvalReport, *, k: int, seed: int) -> str:
    """Render an EvalReport as a readable text block."""
    lines = [
        "=== RCA Copilot — baseline diagnosis eval ===",
        f"held-out: {report.total}   k: {k}   seed: {seed}",
        "",
        f"decided:    {report.correct + report.wrong}/{report.total}"
        f"   (coverage {report.coverage:.0%})",
        f"  correct:  {report.correct}",
        f"  wrong:    {report.wrong}",
        f"abstained:  {report.abstained}",
        "",
        f"accuracy when it commits: {report.accuracy_when_decided:.1%}   <- primary",
        f"overall (abstain = miss): {report.overall_accuracy:.1%}",
    ]
    if report.confusion:
        lines.append("")
        lines.append("confusion (true -> predicted, wrong calls):")
        for true, preds in report.confusion.items():
            for predicted, n in preds.items():
                lines.append(f"  {true} -> {predicted}: {n}")
    return "\n".join(lines)


def main() -> None:
    import sys

    use_llm = "--llm" in sys.argv[1:]
    k, seed = 5, 42
    report = asyncio.run(run_eval(k=k, seed=seed, use_llm=use_llm))
    print(("LLM reasoner" if use_llm else "baseline") + ":")
    print(format_report(report, k=k, seed=seed))


if __name__ == "__main__":
    main()
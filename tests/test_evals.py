"""Tests for the eval harness: pure scoring plus one end-to-end run."""

from collections.abc import AsyncIterator

import pytest

from rca_copilot.db import engine
from rca_copilot.diagnosis import INSUFFICIENT
from rca_copilot.evals import EvalReport, run_eval, score

POOL = "connection_pool_exhaustion"
FILE = "empty_upstream_file"


# --- pure scoring (no database) ---------------------------------------------


def test_score_counts_and_ratios() -> None:
    report = score(
        [
            (POOL, POOL),  # correct
            (POOL, POOL),  # correct
            (POOL, FILE),  # wrong
            (FILE, INSUFFICIENT),  # abstained
        ]
    )
    assert report.total == 4
    assert report.correct == 2
    assert report.wrong == 1
    assert report.abstained == 1
    assert report.accuracy_when_decided == pytest.approx(2 / 3)  # of the 3 decided
    assert report.coverage == pytest.approx(3 / 4)
    assert report.overall_accuracy == pytest.approx(2 / 4)


def test_score_records_confusion() -> None:
    report = score([(POOL, FILE), (POOL, FILE)])
    assert report.confusion == {POOL: {FILE: 2}}


def test_score_all_abstained_has_zero_accuracy_not_crash() -> None:
    report = score([(POOL, INSUFFICIENT)])
    assert report.accuracy_when_decided == 0.0
    assert report.coverage == 0.0


# --- end-to-end run (needs Postgres) ----------------------------------------


@pytest.fixture(autouse=True)
async def _fresh_engine_pool() -> AsyncIterator[None]:
    yield
    await engine.dispose()


async def test_run_eval_produces_a_sane_report() -> None:
    report = await run_eval(corpus_size=40, test_size=15, k=5, seed=7)
    assert isinstance(report, EvalReport)
    assert report.total == 15
    assert report.correct + report.wrong + report.abstained == 15
    assert 0.0 <= report.accuracy_when_decided <= 1.0
    assert 0.0 <= report.coverage <= 1.0
    # distinct failure vocabularies -> when it commits, it should be right often
    if report.correct + report.wrong > 0:
        assert report.accuracy_when_decided >= 0.5
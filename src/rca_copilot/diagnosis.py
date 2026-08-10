"""Diagnosis: reason over retrieved incidents to name a root cause — or abstain.

Stage 4 baseline: a k-nearest-neighbour majority vote over the retrieved
incidents' labels. A cause is named only if it holds a true majority of the k
requested neighbours (> k / 2); otherwise the evidence is too thin or too split
to call, and we abstain. Over-calling a root cause sends responders down the
wrong path, so silence beats a guess.

This deterministic reasoner is intentionally simple. It is also the benchmark
the LLM reasoner (Stage 4b) will have to beat, measured in Stage 5.
"""

from collections import Counter

from pydantic import BaseModel

from rca_copilot.retrieval import RetrievedIncident

INSUFFICIENT = "insufficient_evidence"


class Diagnosis(BaseModel):
    """A proposed root cause with the evidence and reasoning behind it."""

    root_cause: str  # the named cause, or "insufficient_evidence"
    confidence: str  # low / medium / high
    evidence: list[RetrievedIncident]  # incidents considered, even when abstaining
    reasoning: str


def diagnose(matches: list[RetrievedIncident], k: int) -> Diagnosis:
    """Name a root cause by majority vote over retrieved incidents, or abstain."""
    if not matches:
        return Diagnosis(
            root_cause=INSUFFICIENT,
            confidence="low",
            evidence=[],
            reasoning="No similar incidents found in the corpus.",
        )

    votes = Counter(m.root_cause for m in matches)
    winner, winner_votes = votes.most_common(1)[0]

    # Require a true majority of the k *requested* neighbours — not just of those
    # that happened to come back. Sparse evidence (few matches) therefore fails
    # the bar even when it agrees with itself, which is the intended discipline.
    if winner_votes <= k / 2:
        breakdown = ", ".join(f"{cause}={n}" for cause, n in votes.most_common())
        return Diagnosis(
            root_cause=INSUFFICIENT,
            confidence="low",
            evidence=matches,
            reasoning=(
                f"No cause holds a majority of the {k} nearest incidents "
                f"({breakdown}). Evidence is too thin or split to call."
            ),
        )

    ratio = winner_votes / len(matches)
    confidence = "high" if ratio == 1.0 else "medium" if ratio >= 0.66 else "low"
    return Diagnosis(
        root_cause=winner,
        confidence=confidence,
        evidence=matches,
        reasoning=(
            f"{winner_votes} of the {len(matches)} nearest incidents point to "
            f"'{winner}', a majority of the {k} requested."
        ),
    )
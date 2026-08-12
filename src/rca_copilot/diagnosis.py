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
from typing import Any

from pydantic import BaseModel

from rca_copilot.llm import LLMClient
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

# --- Stage 4b: LLM reasoner ------------------------------------------------

_VALID_CONFIDENCE = {"low", "medium", "high"}

_SYSTEM_PROMPT = (
    "You are a root-cause analysis assistant for a large retail store-systems "
    "estate — point-of-sale, order orchestration, payments, and middleware.\n\n"
    "You are given a new incident's log events together with the most similar "
    "past incidents, each with a known root cause and a short narrative.\n\n"
    "Name the single root cause best supported by the evidence, choosing only "
    "from the causes that appear in the retrieved incidents. You may commit to a "
    "cause even when the retrieved causes are mixed — but only when you can point "
    "to specific events or narratives that justify it. In particular, recognise "
    "when a surface symptom (such as a timeout) is downstream of a different "
    "underlying cause, and diagnose the cause rather than the symptom.\n\n"
    "Return 'insufficient_evidence' only when the evidence genuinely does not "
    "support any single cause. Always cite the specific evidence behind your call."
)


def _build_user_prompt(
    events: list[dict[str, Any]], matches: list[RetrievedIncident]
) -> str:
    lines = ["NEW INCIDENT EVENTS:"]
    for event in events:
        lines.append(f"- {event.get('source', '?')}: {event.get('message', '')}")
    lines.append("")
    lines.append("RETRIEVED SIMILAR INCIDENTS (most similar first):")
    for i, match in enumerate(matches, start=1):
        lines.append(f"[{i}] root_cause={match.root_cause} (relevance {match.score:.4f})")
        lines.append(f"    {match.narrative}")
    return "\n".join(lines)


async def diagnose_with_llm(
    client: LLMClient,
    events: list[dict[str, Any]],
    matches: list[RetrievedIncident],
) -> Diagnosis:
    """Reason over the new events and retrieved evidence to name a cause or abstain.

    Assertive but grounded: the model may commit on a mixed/hard case when it can
    justify the call from the evidence, but its answer is constrained to the
    causes actually present in the retrieved incidents (anything off-script is
    treated as an abstention rather than trusted).
    """
    if not matches:
        return Diagnosis(
            root_cause=INSUFFICIENT,
            confidence="low",
            evidence=[],
            reasoning="No similar incidents found in the corpus.",
        )

    result = await client.diagnose(
        system=_SYSTEM_PROMPT, user=_build_user_prompt(events, matches)
    )

    allowed = {match.root_cause for match in matches} | {INSUFFICIENT}
    root_cause = str(result.get("root_cause", INSUFFICIENT))
    if root_cause not in allowed:
        root_cause = INSUFFICIENT
    confidence = str(result.get("confidence", "low"))
    if confidence not in _VALID_CONFIDENCE:
        confidence = "low"
    reasoning = str(result.get("reasoning", "")).strip() or "No reasoning provided."
    return Diagnosis(
        root_cause=root_cause,
        confidence=confidence,
        evidence=matches,
        reasoning=reasoning,
    )
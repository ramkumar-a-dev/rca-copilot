"""An incident: a labelled sequence of log events with a known root cause.

Each pattern varies its wording (so two incidents of the same type are not
byte-identical) while keeping a few stable anchor terms, so same-pattern
incidents still retrieve one another. A minority of incidents also carry a
misleading *distractor* event borrowed from another pattern's symptoms — the
true root cause is unchanged, but the surface signal becomes genuinely
confusable. That is what gives a naive majority vote something to get wrong,
and what a reasoning layer has to see through.
"""

import random
from dataclasses import dataclass
from datetime import datetime, timedelta

from rca_copilot.models import LogEvent, Severity


@dataclass(frozen=True, slots=True)
class Incident:
    """A generated incident. The root_cause is the ground-truth label."""

    root_cause: str
    narrative: str
    events: list[LogEvent]


def _choose(*options: str) -> str:
    return random.choice(options)


def _normal_pos_event(store_id: str, at: datetime) -> LogEvent:
    """One healthy, routine POS transaction. The background noise of a store."""
    txn_id = random.randint(1000, 9999)
    return LogEvent(
        timestamp=at,
        source=f"xstore-pos-{store_id}",
        severity=Severity.INFO,
        message=f"Transaction {txn_id} completed",
    )


def generate_infra_shutdown() -> Incident:
    """A managed server dies — but the cause is a platform event, not the app."""
    store_id = f"{random.randint(1, 2700):04d}"
    start = datetime(2026, 3, 14, 14, 30, 0)
    events = [
        _normal_pos_event(store_id, start),
        _normal_pos_event(store_id, start + timedelta(seconds=12)),
        LogEvent(
            timestamp=start + timedelta(seconds=45),
            source="weblogic-ms1",
            severity=Severity.WARN,
            message=_choose(
                "Datasource connection to store DB lost",
                "Store DB datasource dropped, server losing connectivity",
                "Datasource to store database went down",
            ),
        ),
        LogEvent(
            timestamp=start + timedelta(seconds=45),
            source="azure-platform",
            severity=Severity.INFO,
            message=_choose(
                "VM deallocated: scheduled maintenance event",
                "Underlying VM deallocated by platform for maintenance",
                "Host VM taken down: planned maintenance window",
            ),
        ),
        LogEvent(
            timestamp=start + timedelta(seconds=48),
            source="weblogic-ms1",
            severity=Severity.FATAL,
            message=_choose(
                "Managed server shutting down: JVM terminated",
                "JVM terminated, managed server shutdown in progress",
                "Server halted: JVM process killed by host",
            ),
        ),
    ]
    return Incident(
        root_cause="infra_shutdown",
        narrative=(
            "The WebLogic managed server did not crash on its own. The Azure "
            "platform deallocated the underlying VM for a maintenance event, "
            "which killed the JVM. The datasource error and FATAL are symptoms."
        ),
        events=events,
    )


def generate_half_open_channel() -> Incident:
    """A pinpad connection stays 'open' but silently stops responding."""
    store_id = f"{random.randint(1, 2700):04d}"
    start = datetime(2026, 4, 2, 11, 15, 0)
    events = [
        _normal_pos_event(store_id, start),
        LogEvent(
            timestamp=start + timedelta(seconds=8),
            source=f"eftlink-sbh-{store_id}",
            severity=Severity.INFO,
            message=_choose(
                "Tender initiated: card present",
                "Card-present tender started at pinpad",
            ),
        ),
        LogEvent(
            timestamp=start + timedelta(seconds=8),
            source=f"eftlink-sbh-{store_id}",
            severity=Severity.WARN,
            message=_choose(
                "No response from pinpad, retry 1 of 3",
                "Pinpad silent, no response, retrying (1/3)",
                "Pinpad not responding, attempt 1 of 3",
            ),
        ),
        LogEvent(
            timestamp=start + timedelta(seconds=18),
            source=f"eftlink-sbh-{store_id}",
            severity=Severity.WARN,
            message=_choose(
                "No response from pinpad, retry 3 of 3",
                "Pinpad still silent after final retry (3/3)",
                "Pinpad not responding, attempt 3 of 3",
            ),
        ),
        LogEvent(
            timestamp=start + timedelta(seconds=38),
            source=f"eftlink-sbh-{store_id}",
            severity=Severity.ERROR,
            message=_choose(
                "Tender timeout after 30s, transaction voided",
                "Pinpad tender timed out at 30s, tender voided",
                "Timeout waiting on pinpad response, tender cancelled",
            ),
        ),
        LogEvent(
            timestamp=start + timedelta(seconds=40),
            source="weblogic-ms1",
            severity=Severity.INFO,
            message=_choose("Health check OK", "Server health check passed"),
        ),
    ]
    return Incident(
        root_cause="half_open_channel",
        narrative=(
            "The EFTLink-to-pinpad channel is half-open: the socket is alive but "
            "the pinpad stopped responding. There is no connection error — only "
            "silence and timeouts. The healthy WebLogic health check confirms the "
            "server is fine, ruling out infrastructure."
        ),
        events=events,
    )


def generate_empty_upstream_file() -> Incident:
    """A batch job reports success — but processed nothing: the input was empty."""
    start = datetime(2026, 5, 20, 3, 0, 0)
    events = [
        LogEvent(
            timestamp=start,
            source="order-broker-batch",
            severity=Severity.INFO,
            message=_choose("Job starting...", "Batch job starting", "Job started"),
        ),
        LogEvent(
            timestamp=start + timedelta(seconds=0),
            source="order-broker-batch",
            severity=Severity.INFO,
            message=_choose(
                "Job completed successfully but 0 records/0 duration",
                "Job finished OK: 0 records processed, 0 duration",
                "Batch completed, but processed 0 records in 0 seconds",
            ),
        ),
        LogEvent(
            timestamp=start + timedelta(hours=2),
            source="datalake-etl",
            severity=Severity.INFO,
            message=_choose(
                "order is missing",
                "expected order not found downstream",
                "order records missing from feed",
            ),
        ),
    ]
    return Incident(
        root_cause="empty_upstream_file",
        narrative=(
            "The order-broker batch job reported success but processed nothing "
            "because the upstream file was empty. Zero record count and zero "
            "duration are the only evidence. There is no error."
        ),
        events=events,
    )


def generate_order_state_divergence() -> Incident:
    """Two systems disagree about an order's state. A sync failed silently."""
    order_id = f"BOPIS-{random.randint(100000, 999999)}"
    start = datetime(2026, 6, 8, 16, 45, 0)
    events = [
        LogEvent(
            timestamp=start,
            source="order-broker",
            severity=Severity.INFO,
            message=_choose(
                f"Order {order_id} marked FULFILLED",
                f"Order {order_id} set to status FULFILLED",
            ),
        ),
        LogEvent(
            timestamp=start + timedelta(seconds=2),
            source="order-broker-Xcenter-replication",
            severity=Severity.WARN,
            message=_choose(
                "Order status sync with Xcenter replication failed",
                "Xcenter replication sync of order status did not complete",
                "Failed to replicate order status to Xcenter",
            ),
        ),
        LogEvent(
            timestamp=start + timedelta(seconds=10),
            source="xstore-pos",
            severity=Severity.INFO,
            message=_choose(
                f"Order {order_id} status: PENDING",
                f"Order {order_id} still shows PENDING at register",
            ),
        ),
    ]
    return Incident(
        root_cause="order_state_divergence",
        narrative=(
            "order-broker and xstore disagree on the same order because a sync "
            "failed. Neither errors. The contradiction is the evidence."
        ),
        events=events,
    )


def generate_connection_pool_exhaustion() -> Incident:
    """The WebLogic connection pool hits its ceiling; requests cascade to timeouts."""
    start = datetime(2026, 6, 22, 12, 0, 0)
    events = [
        LogEvent(
            timestamp=start,
            source="weblogic-ms1",
            severity=Severity.WARN,
            message=_choose(
                "Connections are running high 18/20 connections exhausted",
                "Connection pool nearly full: 18 of 20 in use",
                "Pool usage high, 18/20 connections active",
            ),
        ),
        LogEvent(
            timestamp=start + timedelta(seconds=10),
            source="weblogic-ms1",
            severity=Severity.ERROR,
            message=_choose(
                "Connections pool exhausted, 20/20 in use, no connections available",
                "Connection pool at capacity: all 20 connections busy, none free",
                "Pool limit reached, every connection in use, acquisition blocked",
            ),
        ),
        LogEvent(
            timestamp=start + timedelta(seconds=15),
            source=f"xstore-pos-{random.randint(1, 2700):04d}",
            severity=Severity.ERROR,
            message=_choose(
                "Socket timeout exception: Could not acquire DB Connection",
                "Timed out acquiring a pooled DB connection",
                "Connection acquire failed: pool wait timed out",
            ),
        ),
        LogEvent(
            timestamp=start + timedelta(seconds=16),
            source=f"xstore-pos-{random.randint(1, 2700):04d}",
            severity=Severity.ERROR,
            message=_choose(
                "Socket timeout exception: Could not acquire DB Connection",
                "DB connection request timed out waiting on the pool",
            ),
        ),
    ]
    return Incident(
        root_cause="connection_pool_exhaustion",
        narrative=(
            "The WebLogic connection pool reached its maximum of 20 connections. "
            "The socket timeouts across multiple stores are all downstream of that "
            "single ceiling event — the store errors are symptoms, not the cause."
        ),
        events=events,
    )


ALL_GENERATORS = [
    generate_infra_shutdown,
    generate_half_open_channel,
    generate_empty_upstream_file,
    generate_order_state_divergence,
    generate_connection_pool_exhaustion,
]

# Misleading symptoms borrowed from another pattern. Injected into a minority of
# incidents to make the surface signal confusable without changing the true
# cause — e.g. a pool exhaustion that also shows a lone pinpad timeout.
_DISTRACTORS: dict[str, list[tuple[str, str]]] = {
    "connection_pool_exhaustion": [
        ("weblogic-ms1", "Connection wait time climbing, pool pressure rising"),
        ("xstore-pos", "Slow DB connection acquisition observed"),
    ],
    "half_open_channel": [
        ("eftlink-sbh", "No response from pinpad, request timed out"),
        ("eftlink-sbh", "Pinpad silent, tender timeout"),
    ],
    "infra_shutdown": [
        ("weblogic-ms1", "Datasource connection to store DB lost"),
    ],
    "empty_upstream_file": [
        ("datalake-etl", "order records missing downstream"),
    ],
    "order_state_divergence": [
        ("order-broker-Xcenter-replication", "order status replication lagging"),
    ],
}

_DISTRACTOR_PROBABILITY = 0.40
_SPARSE_PROBABILITY = 0.30


def _maybe_add_distractor(incident: Incident) -> Incident:
    """With some probability, splice in one or two misleading symptoms.

    The borrowed events come from other patterns, so the surface signal starts
    to look confusable — but the true root cause is unchanged. On a full
    incident the core signal usually still wins; on a sparse one the distractor
    can genuinely tip the balance, which is the point.
    """
    if random.random() >= _DISTRACTOR_PROBABILITY:
        return incident
    donors = [cause for cause in _DISTRACTORS if cause != incident.root_cause]
    base = incident.events[0].timestamp
    added = []
    for _ in range(random.randint(1, 2)):
        source, message = random.choice(_DISTRACTORS[random.choice(donors)])
        added.append(
            LogEvent(
                timestamp=base + timedelta(seconds=random.randint(5, 40)),
                source=source,
                severity=Severity.WARN,
                message=message,
            )
        )
    events = sorted([*incident.events, *added], key=lambda event: event.timestamp)
    return Incident(
        root_cause=incident.root_cause, narrative=incident.narrative, events=events
    )


def _maybe_make_sparse(incident: Incident) -> Incident:
    """With some probability, thin the incident down to two events.

    Real log bundles are sometimes thin. With little signal, retrieval brings
    back weak or mixed neighbours — which the diagnosis should honestly abstain
    on rather than guess. The true cause is still what it was; there just isn't
    enough evidence to reach it, which is a legitimate thing to measure.
    """
    if len(incident.events) <= 2 or random.random() >= _SPARSE_PROBABILITY:
        return incident
    kept = sorted(
        random.sample(incident.events, 2), key=lambda event: event.timestamp
    )
    return Incident(
        root_cause=incident.root_cause, narrative=incident.narrative, events=kept
    )


def random_incident() -> Incident:
    """Generate one incident of a random type, sometimes thinned and/or confused."""
    incident = random.choice(ALL_GENERATORS)()
    return _maybe_add_distractor(_maybe_make_sparse(incident))
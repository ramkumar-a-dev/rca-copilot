"""An incident: a labelled sequence of log events with a known root cause."""

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
            message="Datasource connection to store DB lost",
        ),
        LogEvent(
            timestamp=start + timedelta(seconds=45),
            source="azure-platform",
            severity=Severity.INFO,
            message="VM deallocated: scheduled maintenance event",
        ),
        LogEvent(
            timestamp=start + timedelta(seconds=48),
            source="weblogic-ms1",
            severity=Severity.FATAL,
            message="Managed server shutting down: JVM terminated",
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
            message="Tender initiated: card present",
        ),
        LogEvent(
            timestamp=start + timedelta(seconds=8),
            source=f"eftlink-sbh-{store_id}",
            severity=Severity.WARN,
            message="No response from pinpad, retry 1 of 3",
        ),
        LogEvent(
            timestamp=start + timedelta(seconds=18),
            source=f"eftlink-sbh-{store_id}",
            severity=Severity.WARN,
            message="No response from pinpad, retry 3 of 3",
        ),
        LogEvent(
            timestamp=start + timedelta(seconds=38),
            source=f"eftlink-sbh-{store_id}",
            severity=Severity.ERROR,
            message="Tender timeout after 30s, transaction voided",
        ),
        LogEvent(
            timestamp=start + timedelta(seconds=40),
            source="weblogic-ms1",
            severity=Severity.INFO,
            message="Health check OK",
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
    """A batch job reports success — but processed nothing, because the input was empty."""
    start = datetime(2026, 5, 20, 3, 0, 0)

    events = [
        LogEvent(
            timestamp=start,
            source="order-broker-batch",
            severity=Severity.INFO,
            message="Job starting...",  # job starting
        ),
        LogEvent(
            timestamp=start + timedelta(seconds=0),
            source="order-broker-batch",
            severity=Severity.INFO,  # ← the trap: it thinks it succeeded
            message="Job completed successfully but 0 records/0 duration",
        ),
        LogEvent(
            timestamp=start + timedelta(hours=2),
            source="datalake-etl",  # some downstream system
            severity=Severity.INFO,
            message="order is missing",  # the consequence: something is missing
        ),
    ]
    return Incident(
        root_cause="empty_upstream_file",
        narrative=(
            "The order-broker batch job reported success but the processed nothing because "
            "the upstream file was empty. Zero record count and zero duration are the only "
            "evidence. There is no error"
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
            message=f"Order {order_id} marked FULFILLED",
        ),
        LogEvent(
            timestamp=start + timedelta(seconds=2),
            source="order-broker-Xcenter-replication",
            severity=Severity.WARN,
            message="Order status sync with Xcenter replication failed",
        ),
        LogEvent(
            timestamp=start + timedelta(seconds=10),
            source="xstore-pos",
            severity=Severity.INFO,
            message=f"Order {order_id} status: PENDING",
        ),
    ]
    return Incident(
        root_cause="order_state_divergence",
        narrative=(
            "order-broker and xstore disagree on the same order because "
            "a sync failed. Neither errors. The contradiction is the evidence. "
        ),
        events=events,
    )
def generate_connection_pool_exhaustion() -> Incident:
    """The WebLogic connection pool hits its ceiling; requests cascade into timeouts."""
    start = datetime(2026, 6, 22, 12, 0, 0)

    events = [
        LogEvent(
            timestamp=start,
            source="weblogic-ms1",
            severity=Severity.WARN,
            message="Connections are running high 18/20 connections exhausted",
        ),
        LogEvent(
            timestamp=start + timedelta(seconds=10),
            source="weblogic-ms1",
            severity=Severity.ERROR,
            message="Connections pool exhausted, 20/20 in use, no connections available",
        ),
        LogEvent(
            timestamp=start + timedelta(seconds=15),
            source=f"xstore-pos-{random.randint(1, 2700):04d}",
            severity=Severity.ERROR,
            message="Socket timeout exception: Could not acquire DB Connection",
        ),
        LogEvent(
            timestamp=start + timedelta(seconds=16),
            source=f"xstore-pos-{random.randint(1, 2700):04d}",
            severity=Severity.ERROR,
            message="Socket timeout exception: Could not acquire DB Connection",
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
    generate_connection_pool_exhaustion
]


def random_incident() -> Incident:
    """Generate one incident of a randomly chosen type."""
    generator = random.choice(ALL_GENERATORS)
    return generator()   

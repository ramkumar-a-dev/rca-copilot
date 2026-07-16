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

ALL_GENERATORS = [
    generate_infra_shutdown,
    generate_half_open_channel,
]


def random_incident() -> Incident:
    """Generate one incident of a randomly chosen type."""
    generator = random.choice(ALL_GENERATORS)
    return generator()    
from datetime import datetime

from rca_copilot.models import LogEvent, Severity


def test_log_event_renders_in_expected_format() -> None:
    event = LogEvent(
        timestamp=datetime(2026, 7, 13, 14, 30, 5, 123000),
        source="weblogic-ms1",
        severity=Severity.ERROR,
        message="Connection pool exhausted",
    )

    assert event.render() == (
        "2026-07-13T14:30:05.123 [ERROR] weblogic-ms1 - Connection pool exhausted"
    )


def test_log_event_is_immutable() -> None:
    event = LogEvent(
        timestamp=datetime(2026, 7, 13, 14, 30, 5),
        source="xstore-pos-0417",
        severity=Severity.WARN,
        message="Tender timeout",
    )

    try:
        event.source = "tampered"  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("LogEvent should be frozen")
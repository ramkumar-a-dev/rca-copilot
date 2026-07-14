"""Core data model: the atom every log line in the system is made of."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class Severity(StrEnum):
    """Log severity, ordered from least to most serious."""

    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    FATAL = "FATAL"


@dataclass(frozen=True, slots=True)
class LogEvent:
    """A single line emitted by one system in the estate."""

    timestamp: datetime
    source: str
    severity: Severity
    message: str

    def render(self) -> str:
        """Render as a log line, the way the real systems emit them."""
        ts = self.timestamp.isoformat(timespec="milliseconds")
        return f"{ts} [{self.severity.value}] {self.source} - {self.message}"
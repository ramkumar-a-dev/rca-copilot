"""Command-line interface for generating incident data."""

import argparse
import json
from pathlib import Path

from rca_copilot.incidents import Incident, random_incident


def incident_to_dict(incident: Incident) -> dict[str, object]:
    """Convert an Incident into a JSON-serialisable dictionary."""
    return {
        "root_cause": incident.root_cause,
        "narrative": incident.narrative,
        "events": [
            {
                "timestamp": event.timestamp.isoformat(),
                "source": event.source,
                "severity": event.severity.value,
                "message": event.message,
            }
            for event in incident.events
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic incidents.")
    parser.add_argument("--count", type=int, default=10, help="How many to generate")
    parser.add_argument("--out", type=Path, default=Path("data/incidents"))
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)

    for i in range(args.count):
        incident = random_incident()
        path = args.out / f"incident_{i:04d}.json"
        path.write_text(json.dumps(incident_to_dict(incident), indent=2))

    print(f"Wrote {args.count} incidents to {args.out}")


if __name__ == "__main__":
    main()
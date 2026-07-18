from rca_copilot.incidents import (
    ALL_GENERATORS,
    generate_connection_pool_exhaustion,
    generate_empty_upstream_file,
    generate_half_open_channel,
    generate_infra_shutdown,
    generate_order_state_divergence,
    random_incident,
)


def test_each_generator_produces_its_own_label() -> None:
    expected = {
        generate_infra_shutdown: "infra_shutdown",
        generate_half_open_channel: "half_open_channel",
        generate_empty_upstream_file: "empty_upstream_file",
        generate_order_state_divergence: "order_state_divergence",
        generate_connection_pool_exhaustion: "connection_pool_exhaustion",
    }

    for generator, label in expected.items():
        assert generator().root_cause == label


def test_all_generators_are_registered() -> None:
    assert len(ALL_GENERATORS) == 5


def test_every_incident_has_events_and_a_narrative() -> None:
    for generator in ALL_GENERATORS:
        incident = generator()
        assert len(incident.events) > 0
        assert incident.narrative.strip() != ""


def test_events_are_in_chronological_order() -> None:
    for generator in ALL_GENERATORS:
        incident = generator()
        timestamps = [event.timestamp for event in incident.events]
        assert timestamps == sorted(timestamps)


def test_random_incident_returns_a_known_root_cause() -> None:
    known = {
        "infra_shutdown",
        "half_open_channel",
        "empty_upstream_file",
        "order_state_divergence",
        "connection_pool_exhaustion",
    }

    for _ in range(50):
        assert random_incident().root_cause in known
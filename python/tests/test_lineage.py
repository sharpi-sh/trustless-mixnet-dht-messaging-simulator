from app.events import Event
from app.lineage import project


def test_safe_projection_whitelists_visible_fields():
    evt = Event(
        event_id="e",
        event_type="fragment_stored",
        simulation_id="s",
        sequence=1,
        simulation_time_ms=400,
        source_id="dht",
        target_id="vault",
        message_id="m",
        payload={"fragment_id": "f", "container": "envelope", "secret": "unsafe-test-marker"},
    )
    row = project(evt)
    assert row.location == "vault" and row.artefact == "f" and row.container == "envelope"
    assert "unsafe-test-marker" not in row.model_dump_json()

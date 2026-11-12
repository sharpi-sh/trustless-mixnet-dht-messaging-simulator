import json

import pytest
from pydantic import ValidationError

from app.api_models import Command, Delta, MessageEdits, MixDTO, NodeDetails, Snapshot
from app.config import Config
from app.engine import Intervention
from app.lab import Laboratory


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "bogus"},
        {"type": "set_node_availability", "target": "mix-1"},
        {"type": "set_node_availability", "enabled": True},
        {"type": "set_polling_enabled", "enabled": "false"},
        {"type": "set_playback_delay"},
        {"type": "set_playback_delay", "delay_ms": -1},
        {"type": "block_stage_boundary", "target": " "},
        {"type": "set_staged_messages", "messages": {"msg-1": "  "}},
        {"type": "set_staged_messages", "messages": {}},
        {"type": "set_staged_messages"},
        {"type": "run", "messages": {"msg-1": "unexpected"}},
        {"type": "restore_network_path", "target": "x", "drop_in_flight": True},
        {"type": "subscribe", "after_sequence": -1},
        {"type": "run", "epoch": -1},
        {"type": "resume", "simulation_id": None},
        {"type": "ping", "command_id": " "},
    ],
)
def test_command_rejects_unknown_or_incomplete_arguments(payload):
    with pytest.raises(ValidationError):
        Command.model_validate({"command_id": "c-1", "simulation_id": "s-1", **payload})


def test_preconnection_ping_and_scoped_interventions():
    assert Command(type="ping", command_id="p").simulation_id is None
    args = {"command_id": "c", "simulation_id": "s"}
    assert (
        Command.model_validate({**args, "type": "set_polling_enabled", "enabled": False}).target == ""
    )
    assert Command.model_validate(
        {**args, "type": "block_network_path", "target": "edge", "drop_in_flight": True}
    ).drop_in_flight
    text = " Alice's edited text. "
    assert MessageEdits(messages={"msg-1": text}).messages["msg-1"] == text
    Command.model_validate({**args, "type": "set_staged_messages", "messages": {"msg-1": text}})


def test_real_snapshot_preserves_mixes_and_hides_runtime_message_text():
    lab = Laboratory(Config(random_seed=128))
    initial = Snapshot.model_validate(lab.snapshot())
    assert initial.epoch == 0 and initial.status == "ready"
    public = json.loads(initial.model_dump_json())
    assert all(m["text"] for m in public["messages"])
    mixes = [node for node in initial.topology.nodes if isinstance(node, MixDTO)]
    assert len(mixes) == 6
    assert all(m.adjacent_peers and not m.delayed_packets for m in mixes)
    for node in initial.topology.nodes:
        details = NodeDetails.model_validate(lab.inspect(node.id))
        assert details.node.id == node.id and details.profile.operations
    lab.lifecycle("run")
    running = Snapshot.model_validate(lab.snapshot())
    assert all("text" not in m.model_dump(exclude_unset=True) for m in running.messages)
    assert running.simulation_id == initial.simulation_id
    unsafe = initial.devices[0].model_dump()
    unsafe["private_key"] = "secret"
    with pytest.raises(ValidationError):
        Snapshot.model_validate({**lab.snapshot(), "devices": [unsafe]})


def test_delta_accepts_real_command_events_and_changed_entities_without_sharing_arrays():
    lab = Laboratory(Config(random_seed=12))
    snap = Snapshot.model_validate(lab.snapshot())
    path = next(iter(lab.topology.paths.values()))
    lab.intervene(Intervention(command="path", target=path.id, enabled=False, token="test-block"))
    clock = {
        "simulation_id": lab.id,
        "epoch": 1,
        "initialised": lab.initialised,
        "sequence": len(lab.events),
        "status": lab.status,
        "simulation_time_ms": lab.now,
        "next_step_ms": None,
        "step_delay_ms": lab.step_delay_ms,
    }
    delta = Delta.model_validate(
        {
            **clock,
            "events": lab.events,
            "paths": [path.model_dump()],
            "nodes": [snap.topology.nodes[0].model_dump()],
        }
    )
    assert delta.paths[0].blocked and delta.paths[0].blocked_by == "test-block"
    assert any(event.event_type == "network_path_blocked" for event in delta.events)
    assert Delta.model_validate(clock).paths == []
    wire = json.loads(delta.model_dump_json())
    assert wire["epoch"] == 1 and wire["outcomes"] == {} and wire["lineage"] == []

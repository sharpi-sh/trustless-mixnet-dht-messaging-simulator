from copy import deepcopy

import pytest

from app.config import Config
from app.engine import Intervention
from app.lab import Laboratory
from app.stream import delta, snapshot


def apply(state, patch):
    for key in (
        "sequence",
        "simulation_time_ms",
        "first_message_hop_sequence",
        "status",
        "step_delay_ms",
        "next_step_ms",
        "initialised",
    ):
        state[key] = patch[key]
    for key, container in (
        ("nodes", state["topology"]),
        ("paths", state["topology"]),
        ("devices", state),
        ("messages", state),
    ):
        changed = {record["id"]: record for record in patch[key]}
        container[key] = [changed.get(record["id"], record) for record in container[key]]
    state["lineage"].extend(patch["lineage"])
    state["outcomes"].update(patch["outcomes"])


def test_patch_a_staged_plan_then_erase_all_previews_on_first_single_step():
    lab = Laboratory(Config(random_seed=18, receiver_count=2), "stream-lab")
    state = snapshot(lab, 2).model_dump(mode="json")
    assert state["devices"][0]["logs"]

    def check():
        update = delta(lab, 2, state["sequence"]).model_dump(mode="json")
        apply(state, update)
        assert state == snapshot(lab, 2).model_dump(mode="json")
        return update

    lab.intervene(Intervention(command="polling", target="receiver-1", enabled=False, token="toggle"))
    first = check()
    assert [d["id"] for d in first["devices"]] == ["receiver-1"]
    assert not first["paths"] and not first["messages"]
    lab.edit_messages({"msg-1": "A private staged edit."})
    edit = check()
    assert [m["id"] for m in edit["messages"]] == ["msg-1"]
    assert [d["id"] for d in edit["devices"]] == ["sender-1"]
    lab.lifecycle("step")
    started = check()
    assert started["initialised"] and all(message["text"] is None for message in started["messages"])
    assert all(entry["state"] != "staged" for device in started["devices"] for entry in device["logs"])


def test_incremental_projection_matches_topology_clock_and_lineage_as_run_progresses():
    lab = Laboratory(
        Config(
            random_seed=56,
            min_nodes=10,
            max_nodes=10,
            dht_nodes=2,
            storage_nodes=2,
            payload_rate_per_minute=600,
            mu_per_second=100,
            client_loop_rate_per_minute=0.001,
            mix_loop_rate_per_minute=0.001,
            drop_cover_rate_per_minute=0.001,
            polling_interval_ms=100,
            base_transit_delay_ms=2,
            jitter_min_ms=0,
            jitter_max_ms=0,
        )
    )
    baseline = snapshot(lab, 0).model_dump(mode="json")
    state = deepcopy(baseline)
    lab.lifecycle("run")
    stable = delta(lab, 0, state["sequence"]).model_dump(mode="json")
    apply(state, stable)
    assert state == snapshot(lab, 0).model_dump(mode="json")
    for step_no in range(1, 3001):
        previous = state["sequence"]
        lab.advance()
        patch = delta(lab, 0, previous).model_dump(mode="json")
        assert [e["sequence"] for e in patch["events"]] == list(
            range(previous + 1, patch["sequence"] + 1)
        )
        assert len(patch["paths"]) < len(lab.topology.paths)
        apply(state, patch)
        if step_no % 40 == 0 or lab.status != "running":
            assert state == snapshot(lab, 0).model_dump(mode="json")
        if lab.status != "running":
            break
    assert lab.status == "completed" and state["lineage"]
    assert baseline["lineage"] == [] and baseline["sequence"] == 0


def test_boundary_paths_outages_empty_and_invalid_cursor():
    lab = Laboratory(Config(random_seed=74))
    path = next(iter(lab.topology.paths.values()))
    lab.intervene(
        Intervention(token="offline", command="availability", target=path.source_id, enabled=False)
    )
    patch = delta(lab, 3, 0)
    assert {n.id for n in patch.nodes} == {path.source_id}
    cursor = patch.sequence
    lab.intervene(Intervention(token="block", command="boundary", target=path.boundary, enabled=False))
    patch = delta(lab, 3, cursor)
    assert {p.id for p in patch.paths} == {
        p.id for p in lab.topology.paths.values() if p.boundary == path.boundary
    }
    assert all(p.blocked for p in patch.paths)
    empty = delta(lab, 3, patch.sequence)
    assert not any(
        (
            empty.events,
            empty.nodes,
            empty.paths,
            empty.lineage,
            empty.outcomes,
            empty.devices,
            empty.messages,
        )
    )
    for cursor in (-1, patch.sequence + 1):
        with pytest.raises(ValueError, match="Sequence"):
            delta(lab, 3, cursor)

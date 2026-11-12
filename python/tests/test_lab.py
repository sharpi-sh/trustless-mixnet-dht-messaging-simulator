import pytest

from app.config import Config
from app.engine import Intervention
from app.lab import Laboratory


def config(**changes):
    return Config(
        **{
            "random_seed": 13,
            "dht_nodes": 3,
            "storage_nodes": 3,
            "min_nodes": 10,
            "max_nodes": 10,
            "payload_rate_per_minute": 48,
            "client_loop_rate_per_minute": 0.1,
            "drop_cover_rate_per_minute": 0.1,
            "mix_loop_rate_per_minute": 0.1,
            "base_transit_delay_ms": 3,
            "jitter_max_ms": 0,
            "mu_per_second": 70,
            "polling_interval_ms": 500,
            "ack_timeout_ms": 10,
            **changes,
        }
    )


def test_atomic_staged_edits_lifecycle_lock_and_reset():
    lab = Laboratory(config(exchanges=2))
    original = {m["id"]: m["text"] for m in lab.snapshot()["messages"]}
    first, second, *_ = original
    with pytest.raises((ValueError, KeyError)):
        lab.edit_messages({first: "Changed before validation", second: " "})
    assert {m["id"]: m["text"] for m in lab.snapshot()["messages"]} == original
    lab.edit_messages({first: "A new forward.", second: "A new reply."})
    lab.lifecycle("step")
    with pytest.raises(ValueError):
        lab.edit_messages({first: "Changed during a run."})
    lab.lifecycle("reset")
    snapshot = lab.snapshot()
    assert snapshot["status"] == "ready" and snapshot["simulation_time_ms"] == 0
    assert not snapshot["initialised"] and not snapshot["lineage"]
    assert {m["id"] for m in snapshot["messages"]} == set(original)
    assert all(row["state"] == "staged" for device in snapshot["devices"] for row in device["logs"])
    lab.edit_messages({first: "New run, edited again."})
    assert lab.clients.messages[first].text == "New run, edited again."


@pytest.mark.parametrize(
    "strategy,senders,receivers,expected",
    [
        ("one_to_one_pairs", 2, 2, {("sender-1", "receiver-1"), ("sender-2", "receiver-2")}),
        ("one_to_all", 1, 2, {("sender-1", "receiver-1"), ("sender-1", "receiver-2")}),
    ],
)
def test_alternate_conversations_finish_and_respect_each_devices_visibility(
    strategy, senders, receivers, expected
):
    lab = Laboratory(config(sender_count=senders, receiver_count=receivers, pairing_strategy=strategy))
    forwards = [m for m in lab.clients.messages.values() if m.direction == "forward"]
    assert {(m.sender_id, m.target_id) for m in forwards} == expected
    edits = {m.id: f"Private from {m.sender_id} for {m.target_id}" for m in forwards}
    lab.edit_messages(edits)
    lab.lifecycle("run")
    for _ in lab.drain(10000):
        if lab.status != "running":
            break
    assert lab.status == "completed"
    for device in lab.snapshot()["devices"]:
        got = [entry for entry in device["logs"] if entry["state"] == "received"]
        expected_messages = [m for m in lab.clients.messages.values() if m.target_id == device["id"]]
        assert sorted(row["message_id"] for row in got) == sorted(m.id for m in expected_messages)
        assert {row["text"] for row in got} == {edits.get(m.id, m.text) for m in expected_messages}


def test_unreachable_sender_finishes_with_bounded_failure():
    lab = Laboratory(config(max_retries=1))
    first = next(m for m in lab.clients.messages.values() if m.direction == "forward")
    lab.intervene(
        Intervention(command="availability", target=first.sender_id, enabled=False, token="power-off")
    )
    lab.lifecycle("run")
    for _ in lab.drain(3000):
        if lab.status != "running":
            break
    assert lab.status == "failed"
    attempts = [
        e for e in lab.events if e.event_type == "mixnet_route_constructed" and e.message_id == first.id
    ]
    assert [e.payload["attempt"] for e in attempts] == [1, 2]
    logs = [
        entry for p in lab.clients.people.values() for entry in p.logs if entry.message_id == first.id
    ]
    assert any(entry.state == "failed" for entry in logs)
    assert all(entry.state != "received" for entry in logs)

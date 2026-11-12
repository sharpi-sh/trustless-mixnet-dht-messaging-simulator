import json
from hashlib import sha256
from random import Random

import pytest
from pydantic import ValidationError

from app.config import Config
from app.participants import DeviceLog, People, Person, TorNetwork


def test_each_participant_owns_independent_key_tor_and_log():
    people = People(Config(polling_enabled=False), Random(7)).people
    alice, bob = people.values()
    assert isinstance(alice, Person) and isinstance(bob, Person)
    assert alice.label == "Alice" and bob.label == "Bob"
    assert alice.public_key != bob.public_key and len(alice.public_key) == 32
    assert alice.fingerprint == sha256(alice.public_key).hexdigest()
    assert alice.polling_enabled and not bob.polling_enabled
    assert isinstance(alice.tor, TorNetwork) and alice.tor.owner_id == alice.id
    assert alice.tor.id == "tor-sender-1" and bob.tor.id == "tor-receiver-1"
    alice.tor.enter()
    alice.tor.exit()
    assert alice.tor.entry_count == alice.tor.exit_count == 1
    assert bob.tor.entry_count == bob.tor.exit_count == 0
    alice.logs.append(
        DeviceLog(
            message_id="msg-1",
            conversation_id="conv-1",
            direction="forward",
            state="sent",
            simulation_time_ms=200,
            text="Only on Alice's device",
        )
    )
    assert bob.device()["logs"] == []
    public = alice.device()
    assert set(public) == {
        "id",
        "label",
        "role",
        "channel",
        "channel_id",
        "tor_id",
        "fingerprint",
        "signing_fingerprint",
        "polling_enabled",
        "logs",
    }
    assert "Only on Alice's device" in json.dumps(public)
    assert alice.signing_public_key not in {alice.public_key, bob.signing_public_key}
    assert alice.signing_fingerprint == sha256(alice.signing_public_key).hexdigest()
    assert alice.signing_private_key.private_bytes_raw().hex() not in json.dumps(public)
    assert alice.private_key.private_bytes_raw().hex() not in json.dumps(public)


@pytest.mark.parametrize(
    "strategy, expected",
    [
        ("all_to_one", [("sender-1", "receiver-1"), ("sender-2", "receiver-1")]),
        ("one_to_all", [("sender-1", "receiver-1"), ("sender-1", "receiver-2")]),
        ("one_to_one_pairs", [("sender-1", "receiver-1"), ("sender-2", "receiver-2")]),
    ],
)
def test_pairings_have_reversed_replies_and_distinct_messages(strategy, expected):
    cfg = Config(sender_count=2, receiver_count=2, pairing_strategy=strategy, exchanges=10)
    population = People(cfg, Random(0))
    messages = list(population.messages.values())
    assert len(messages) == len(expected) * 20
    for index, pair in enumerate(expected, 1):
        plan = [m for m in messages if m.conversation_id == f"conv-{index}"]
        for exchange in range(1, 11):
            forward, reply = [m for m in plan if m.exchange == exchange]
            assert (forward.sender_id, forward.target_id) == pair
            assert (reply.sender_id, reply.target_id) == pair[::-1]
            assert forward.direction == "forward" and reply.direction == "reply"
    assert len({m.id for m in messages}) == len(messages)


def test_seed_reproduces_pairing_and_plan_but_never_keys():
    cfg = Config(sender_count=3, receiver_count=4, pairing_strategy="random_pairs", pair_count=7)
    first = People(cfg, Random(24))
    replay = People(cfg, Random(24))
    assert first.messages == replay.messages
    assert first.people["sender-1"].public_key != replay.people["sender-1"].public_key
    assert (
        len({(m.sender_id, m.target_id) for m in first.messages.values() if m.direction == "forward"})
        == 7
    )
    assert all(3 <= len(m.text.split()) <= 10 for m in first.messages.values())
    assert first.messages != People(cfg, Random(25)).messages


def test_edits_replace_only_one_message_after_validation():
    population = People(Config(), Random(1))
    staged = population.messages["msg-1"]
    original_reply = population.messages["msg-2"]
    updated = population.edit(staged.id, "  This is my message.  ")
    assert updated.text == "  This is my message.  "
    assert updated.conversation_id == staged.conversation_id
    for bad in ["   ", ""]:
        with pytest.raises(ValidationError):
            population.edit(staged.id, bad)
        assert population.messages[staged.id] == updated
    with pytest.raises(KeyError):
        population.edit("missing", "Unknown")
    assert population.messages["msg-2"] == original_reply


def test_polling_defaults_and_receiver_overrides():
    cfg = Config(receiver_count=2, polling_enabled=False, polling_overrides={"receiver-2": True})
    people = People(cfg, Random(1)).people
    assert not people["receiver-1"].polling_enabled and people["receiver-2"].polling_enabled
    with pytest.raises(ValueError, match="configured receiver"):
        People(Config(polling_overrides={"receiver-3": True}), Random())

"""Exercise the recipient boundary with attacker-created, valid AEAD envelopes."""

from hashlib import sha256

import msgpack
import pytest

from app.config import Config
from app.crypto import decode_bundle, encode_bundle, seal, unseal
from app.lab import Compose, Laboratory
from app.mailbox import BundleDelivered

_SIGNED_PREFIX = b"MXSB\x02"
_BODY_OFFSET = len(_SIGNED_PREFIX) + 32 + 64


def make_lab(**overrides):
    return Laboratory(
        Config(
            random_seed=29,
            min_nodes=10,
            max_nodes=10,
            dht_nodes=3,
            storage_nodes=3,
            base_transit_delay_ms=3,
            jitter_max_ms=0,
            payload_rate_per_minute=90,
            polling_interval_ms=500,
            mu_per_second=70,
            **overrides,
        )
    )


def deliver(lab, msg, ciphertext, target=None):
    lab.handle(
        BundleDelivered(
            source="tor-" + (target or msg.target_id),
            target=target or msg.target_id,
            message_id=msg.id,
            lane=msg.direction,
            ciphertext=ciphertext,
        )
    )


def assert_rejected(lab, msg):
    owner = lab.clients.people[msg.target_id]
    assert lab.outcomes[msg.id] == "failed"
    assert msg.id not in lab.devices.received[owner.id]
    assert (owner.id, msg.conversation_id, msg.exchange) not in lab.devices.learned
    assert not any(row.message_id == msg.id for row in owner.logs)
    assert not any(
        event.message_id == msg.id
        and event.event_type
        in {
            "message_decrypted",
            "sender_signature_verified",
            "reply_key_learned",
        }
        for event in lab.events
    )
    assert lab.outcomes["msg-2"] == "skipped"
    assert not any(
        isinstance(step.action, Compose) and step.action.message_id == "msg-2"
        for _, _, step in lab.queue
    )


@pytest.mark.parametrize(
    "attack", ["unsigned", "altered text", "altered reply key", "altered signature"]
)
def test_recipient_rejects_valid_encryption_with_invalid_authentication(attack):
    lab = make_lab()
    msg = lab.clients.messages["msg-1"]
    owner = lab.clients.people[msg.target_id]
    wire, _ = lab.devices.prepare(msg)
    signed = unseal(owner.private_key, wire[32:], "bundle")
    assert signed.startswith(_SIGNED_PREFIX)
    transcript = msgpack.unpackb(signed[_BODY_OFFSET:], raw=False)
    content = decode_bundle(transcript[-1])
    if attack == "unsigned":
        forged = transcript[-1]
    elif attack in {"altered text", "altered reply key"}:
        text = "Attacker-controlled text" if attack == "altered text" else content.text
        reply_key = owner.public_key if attack == "altered reply key" else content.reply_public_key
        transcript[-1] = encode_bundle(msg.id, text, reply_key)
        forged = signed[:_BODY_OFFSET] + msgpack.packb(transcript, use_bin_type=True)
    else:
        signature_offset = len(_SIGNED_PREFIX) + 32
        forged = (
            signed[:signature_offset]
            + bytes([signed[signature_offset] ^ 1])
            + signed[signature_offset + 1 :]
        )
    ciphertext = seal(owner.public_key, forged, "bundle")
    assert unseal(owner.private_key, ciphertext, "bundle") == forged
    deliver(lab, msg, ciphertext)
    assert_rejected(lab, msg)


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", "msg-999"),
        ("conversation_id", "conv-999"),
        ("exchange", 5),
        ("direction", "reply"),
        ("sender_id", "sender-2"),
        ("target_id", "receiver-2"),
    ],
)
def test_valid_signature_for_another_context_cannot_approve_this_exchange(field, value):
    lab = make_lab(sender_count=2, receiver_count=2)
    msg = lab.clients.messages["msg-1"]
    alternate = msg.model_copy(update={field: value})
    if field == "direction":
        # A valid reply signed by Alice for Bob still cannot authorise a forward.
        lab.devices.learned[(msg.sender_id, msg.conversation_id, msg.exchange)] = lab.clients.people[
            msg.target_id
        ].public_key
    wire, _ = lab.devices.prepare(alternate)
    # Re-encryption to Bob removes outer recipient binding as an explanation for rejection.
    signed = unseal(lab.clients.people[alternate.target_id].private_key, wire[32:], "bundle")
    deliver(lab, msg, seal(lab.clients.people[msg.target_id].public_key, signed, "bundle"))
    assert_rejected(lab, msg)


def test_unexpected_recipient_callback_cannot_invoke_another_devices_private_key():
    lab = make_lab(receiver_count=2)
    msg = lab.clients.messages["msg-1"]
    wire, _ = lab.devices.prepare(msg)
    deliver(lab, msg, wire[32:], target="receiver-2")
    assert_rejected(lab, msg)


def test_forged_sender_is_rejected_after_actual_mix_storage_lookup_and_reconstruction():
    lab = make_lab()
    msg = lab.clients.messages["msg-1"]
    lab.lifecycle("run")
    outbox = lab.packets.outbox[msg.sender_id]
    for _ in lab.drain(5000):
        if outbox:
            break
    uid, target, wire, lane = outbox.popleft()
    bob = lab.clients.people[target]
    # Anyone with Bob's public contact can produce a well-formed encrypted envelope.
    unsigned = encode_bundle(uid, "Forged by a third party", bob.public_key)
    forged = seal(bob.public_key, unsigned, "bundle")
    outbox.append((uid, target, wire[:32] + forged, lane))
    for _ in lab.drain(20000):
        if lab.status == "failed":
            break
    assert lab.status == "failed"
    records = {row["operation"]: row for row in lab.lineage if row["message_id"] == uid}
    assert {
        "fragment_stored",
        "manifest_published",
        "manifest_retrieved",
        "fragment_retrieved",
    } <= records.keys()
    assert records["message_reconstructed"]["artefact"] == sha256(forged).hexdigest()
    assert records["message_signed"]["container"] != records["message_reconstructed"]["artefact"]
    assert_rejected(lab, msg)


def test_verified_events_bind_both_devices_and_deduplicate_replayed_delivery():
    lab = make_lab()
    msg = lab.clients.messages["msg-1"]
    lab.compose(Compose(message_id=msg.id))
    _, _, wire, _ = lab.packets.outbox[msg.sender_id].popleft()
    deliver(lab, msg, wire[32:])
    deliver(lab, msg, wire[32:])
    events = [e for e in lab.events if e.message_id == msg.id]
    for operation, location in (
        ("message_signed", msg.sender_id),
        ("sender_signature_verified", msg.target_id),
    ):
        [event] = [e for e in events if e.event_type == operation]
        sender = lab.clients.people[msg.sender_id]
        assert event.source_id == location and event.payload["signer_id"] == msg.sender_id
        assert event.payload["signing_fingerprint"] == sha256(sender.signing_public_key).hexdigest()
        assert event.payload["container"] == sha256(wire[32:]).hexdigest()
    assert [r.state for r in lab.clients.people[msg.target_id].logs] == ["delivered", "received"]
    assert sum(isinstance(s.action, Compose) for _, _, s in lab.queue) == 1
    assert all(msg.text not in str(e.payload) for e in events)

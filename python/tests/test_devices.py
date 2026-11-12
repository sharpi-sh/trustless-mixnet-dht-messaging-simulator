from random import Random

import pytest

from app.config import Config
from app.devices import DeviceProtocol
from app.participants import People


def test_reply_uses_key_learned_only_at_decryption_and_suppresses_duplicates():
    clients = People(Config(), Random(10))
    device = DeviceProtocol(clients)
    forward, reply = clients.messages.values()
    with pytest.raises(KeyError):
        device.prepare(reply)
    wire, _ = device.prepare(forward)
    alice = clients.people[forward.sender_id]
    bob = clients.people[forward.target_id]
    assert alice.public_key not in wire and not bob.logs
    assert device.accept(forward, wire[32:], 310) == alice.fingerprint
    assert device.accept(forward, wire[32:], 320) is None
    assert [row.state for row in bob.logs] == ["delivered", "received"]
    assert bob.logs[-1].text == forward.text
    assert bob.logs[-1].verified_signer_id == alice.id
    assert bob.logs[-1].signing_fingerprint == alice.signing_fingerprint
    response, _ = device.prepare(reply)
    assert device.accept(reply, response[32:], 530) == bob.fingerprint
    assert alice.logs[-1].verified_signer_id == bob.id
    assert alice.logs[-1].signing_fingerprint == bob.signing_fingerprint


def test_signed_context_can_be_read_from_the_envelope_and_verified_independently():
    import msgpack
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    from app.crypto import decode_bundle, unseal

    clients = People(Config(), Random(17))
    device = DeviceProtocol(clients)
    msg = clients.messages["msg-1"]
    alice, bob = clients.people.values()
    wire, _ = device.prepare(msg)
    envelope = unseal(bob.private_key, wire[32:], "bundle")
    assert envelope[:5] == b"MXSB\x02"
    key, signature, statement = envelope[5:37], envelope[37:101], envelope[101:]
    assert key == device.published[alice.id].signing_public_key
    Ed25519PublicKey.from_public_bytes(key).verify(signature, statement)
    domain, uid, conversation, exchange, direction, sender, recipient, target, payload = (
        msgpack.unpackb(statement, raw=False)
    )
    assert (domain, uid, conversation, exchange, direction, sender, recipient, target) == (
        b"mixnet-laboratory/device-message/Ed25519/v2",
        msg.id,
        msg.conversation_id,
        msg.exchange,
        msg.direction,
        alice.id,
        bob.id,
        bob.public_key,
    )
    assert decode_bundle(payload).text == msg.text
    assert decode_bundle(payload).reply_public_key == alice.public_key

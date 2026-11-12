import msgpack
import pytest
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from app.crypto import Bundle, decode_bundle, encode_bundle, seal, unseal


def test_hidden_reply_key_is_learned_after_decryption_and_can_receive_reply():
    alice, bob = X25519PrivateKey.generate(), X25519PrivateKey.generate()
    a, b = alice.public_key().public_bytes_raw(), bob.public_key().public_bytes_raw()
    text = "Private 🌊\nverbatim text"
    bundle = encode_bundle("example-message-42", text, a)
    envelope = seal(b, bundle, "bundle")
    for secret in (
        text.encode(),
        b"example-message-42",
        alice.private_bytes_raw(),
        bob.private_bytes_raw(),
        a,
        b,
    ):
        assert secret not in envelope
    opened = decode_bundle(unseal(bob, envelope, "bundle"))
    assert opened == Bundle("example-message-42", text, a)
    assert text not in repr(opened)
    reply = seal(opened.reply_public_key, b"reply", "bundle")
    assert unseal(alice, reply, "bundle") == b"reply"


@pytest.mark.parametrize("purpose", ["bundle", "manifest"])
def test_fresh_ephemeral_material_and_nonce_on_every_call(purpose):
    key = X25519PrivateKey.generate()
    public = key.public_key().public_bytes_raw()
    envelopes = [seal(public, b"same input", purpose) for _ in range(6)]
    assert len({x[6:38] for x in envelopes}) == len(envelopes)
    assert len({x[38:50] for x in envelopes}) == len(envelopes)
    assert all(unseal(key, each, purpose) == b"same input" for each in envelopes)
    assert unseal(key, seal(public, b"", purpose), purpose) == b""


def test_swapped_purpose_wrong_key_tampering_and_versions_are_rejected():
    key = X25519PrivateKey.generate()
    envelope = seal(key.public_key().public_bytes_raw(), b'{"fragments": []}', "manifest")
    with pytest.raises(ValueError, match="authentication"):
        unseal(X25519PrivateKey.generate(), envelope, "manifest")
    with pytest.raises(ValueError, match="purpose"):
        unseal(key, envelope, "bundle")
    # Rewriting the purpose byte to match the caller cannot turn a manifest into a bundle.
    with pytest.raises(ValueError, match="authentication"):
        unseal(key, envelope[:5] + bytes([1]) + envelope[6:], "bundle")
    for pos in (6, 38, 50, len(envelope) - 1):
        altered = bytearray(envelope)
        altered[pos] ^= 1
        with pytest.raises(ValueError, match="authentication"):
            unseal(key, bytes(altered), "manifest")
    for pos in (0, 4):
        altered = bytearray(envelope)
        altered[pos] ^= 1
        with pytest.raises(ValueError, match="format or version"):
            unseal(key, bytes(altered), "manifest")
    with pytest.raises(ValueError, match="Truncated"):
        unseal(key, envelope[:55], "manifest")
    with pytest.raises(ValueError):
        seal(bytes(32), b"data", "bundle")


def test_bundle_format_validation_preserves_text_and_rejects_ambiguous_inputs():
    key = X25519PrivateKey.generate().public_key().public_bytes_raw()
    assert decode_bundle(encode_bundle("id", "  text  ", key)).text == "  text  "
    for fields in (
        [True, "id", "text", key],
        [2, "id", "text", key],
        [1, "", "text", key],
        [1, "id", "  ", key],
        [1, "id", "text", b"short"],
        [1, "id", b"text", key],
        {"message": "x"},
    ):
        with pytest.raises(ValueError):
            decode_bundle(msgpack.packb(fields, use_bin_type=True))
    with pytest.raises(ValueError):
        decode_bundle(b"\xc1")

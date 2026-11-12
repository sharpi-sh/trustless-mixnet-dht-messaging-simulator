"""Recipient envelopes for local message bundles and manifests, version 1.

A fresh ephemeral X25519 key and 96-bit nonce accompany each AES-256-GCM
ciphertext. The version selects the algorithm suite. Purpose, both public keys
and the nonce bind key derivation to this recipient and use of the envelope.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from secrets import token_bytes
from struct import Struct
from typing import Literal

import msgpack
from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .participants import StagedMessage

Purpose = Literal["bundle", "manifest", "retrieval"]
_HEADER = Struct("!4sBB32s12s")
_MAGIC = b"MXRE"
_VERSION = 1
_PURPOSE_ID: dict[Purpose, int] = {"bundle": 1, "manifest": 2, "retrieval": 3}
_DOMAIN = b"mixnet-laboratory/recipient-envelope/X25519-HKDF-SHA256-AES256GCM\x00"


def _purpose_id(purpose: Purpose) -> int:
    if purpose not in _PURPOSE_ID:
        raise ValueError("Unknown recipient envelope purpose")
    return _PURPOSE_ID[purpose]


def _aead(shared: bytes, nonce: bytes, header: bytes, recipient: bytes) -> AESGCM:
    key = HKDF(
        algorithm=hashes.SHA256(), length=32, salt=nonce, info=_DOMAIN + header + recipient
    ).derive(shared)
    return AESGCM(key)


def seal(public_key: bytes, data: bytes, purpose: Purpose) -> bytes:
    """Encrypt opaque bytes to a recipient without disclosing its public key in the header."""
    kind = _purpose_id(purpose)
    recipient = X25519PublicKey.from_public_bytes(public_key)
    ephemeral = X25519PrivateKey.generate()
    nonce = token_bytes(12)
    header = _HEADER.pack(_MAGIC, _VERSION, kind, ephemeral.public_key().public_bytes_raw(), nonce)
    cipher = _aead(ephemeral.exchange(recipient), nonce, header, public_key)
    return header + cipher.encrypt(nonce, data, header)


def unseal(private_key: X25519PrivateKey, envelope: bytes, purpose: Purpose) -> bytes:
    kind = _purpose_id(purpose)
    if len(envelope) < _HEADER.size + 16:
        raise ValueError("Truncated recipient envelope")
    header = envelope[: _HEADER.size]
    magic, version, encoded_kind, ephemeral, nonce = _HEADER.unpack(header)
    if magic != _MAGIC or version != _VERSION:
        raise ValueError("Unsupported recipient envelope format or version")
    if encoded_kind != kind:
        raise ValueError("Incorrect recipient envelope purpose")
    try:
        shared = private_key.exchange(X25519PublicKey.from_public_bytes(ephemeral))
        cipher = _aead(shared, nonce, header, private_key.public_key().public_bytes_raw())
        return cipher.decrypt(nonce, envelope[_HEADER.size :], header)
    except (InvalidTag, ValueError) as exc:
        raise ValueError("Recipient envelope authentication failed") from exc


@dataclass(frozen=True, slots=True)
class Bundle:
    message_id: str
    text: str = field(repr=False)
    reply_public_key: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.message_id, str) or not self.message_id.strip():
            raise ValueError("Invalid bundle message ID")
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("Invalid bundle text")
        if not isinstance(self.reply_public_key, bytes) or len(self.reply_public_key) != 32:
            raise ValueError("Invalid bundle reply key")


def encode_bundle(message_id: str, text: str, reply_public_key: bytes) -> bytes:
    bundle = Bundle(message_id, text, reply_public_key)
    return msgpack.packb(
        (1, bundle.message_id, bundle.text, bundle.reply_public_key), use_bin_type=True
    )


def decode_bundle(data: bytes) -> Bundle:
    try:
        fields = msgpack.unpackb(data, raw=False)
    except (ValueError, TypeError) as exc:
        raise ValueError("Malformed message bundle") from exc
    if not isinstance(fields, list) or len(fields) != 4 or type(fields[0]) is not int or fields[0] != 1:
        raise ValueError("Unsupported message bundle format or version")
    return Bundle(fields[1], fields[2], fields[3])


_SIGNED_HEADER = Struct("!5s32s64s")
_SIGNED_VERSION = b"MXSB\x02"
_SIGNATURE_DOMAIN = b"mixnet-laboratory/device-message/Ed25519/v2"


def _signature_input(message: StagedMessage, recipient_key: bytes, bundle: bytes) -> bytes:
    # Ordered, length-delimited fields. Only the decrypted bundle supplies the text.
    return msgpack.packb(
        (
            _SIGNATURE_DOMAIN,
            message.id,
            message.conversation_id,
            message.exchange,
            message.direction,
            message.sender_id,
            message.target_id,
            recipient_key,
            bundle,
        ),
        use_bin_type=True,
    )


def sign_bundle(
    message: StagedMessage, recipient_key: bytes, reply_key: bytes, signing_key: Ed25519PrivateKey
) -> bytes:
    bundle = encode_bundle(message.id, message.text, reply_key)
    statement = _signature_input(message, recipient_key, bundle)
    signature = signing_key.sign(statement)
    return (
        _SIGNED_HEADER.pack(_SIGNED_VERSION, signing_key.public_key().public_bytes_raw(), signature)
        + statement
    )


def verify_bundle(
    message: StagedMessage, recipient_key: bytes, trusted_key: bytes, signed: bytes
) -> Bundle:
    if len(signed) <= _SIGNED_HEADER.size:
        raise ValueError("Missing sender signature")
    version, enclosed_key, signature = _SIGNED_HEADER.unpack_from(signed)
    if version != _SIGNED_VERSION or enclosed_key != trusted_key:
        raise ValueError("Sender signature format or identity key mismatch")
    statement = signed[_SIGNED_HEADER.size :]
    try:
        Ed25519PublicKey.from_public_bytes(trusted_key).verify(signature, statement)
    except InvalidSignature as exc:
        raise ValueError("Invalid sender signature") from exc
    try:
        fields = msgpack.unpackb(statement, raw=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("Malformed signed message context") from exc
    if not isinstance(fields, list) or len(fields) != 9 or not isinstance(fields[-1], bytes):
        raise ValueError("Invalid signed message context")
    bundle = fields[-1]
    if statement != _signature_input(message, recipient_key, bundle):
        raise ValueError("Sender signature does not match the expected delivery context")
    return decode_bundle(bundle)

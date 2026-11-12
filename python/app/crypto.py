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
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

Purpose = Literal["bundle", "manifest"]
_HEADER = Struct("!4sBB32s12s")
_MAGIC = b"MXRE"
_VERSION = 1
_PURPOSE_ID: dict[Purpose, int] = {"bundle": 1, "manifest": 2}
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

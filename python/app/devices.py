"""Device-owned plaintext, published contacts, signed reply keys and safe provenance."""

from dataclasses import dataclass
from hashlib import sha256
from types import MappingProxyType
from typing import Literal

from .config import Model
from .crypto import seal, sign_bundle, unseal, verify_bundle
from .participants import DeviceLog, People, StagedMessage


@dataclass(frozen=True)
class PublishedContact:
    public_key: bytes
    provider: str
    signing_public_key: bytes


class Lineage(Model):
    simulation_time_ms: int
    message_id: str
    operation: str
    location: str
    artefact: str
    container: str | None = None
    detail: str = ""


class DeviceProtocol:
    def __init__(self, clients: People):
        self.clients = clients
        self.published = MappingProxyType(
            {
                p.id: PublishedContact(
                    p.public_key,
                    "provider-west" if p.role == "sender" else "provider-east",
                    p.signing_public_key,
                )
                for p in clients.people.values()
            }
        )
        self.learned: dict[tuple[str, str, int], bytes] = {}
        self.received: dict[str, set[str]] = {p: set() for p in clients.people}

    def prepare(self, msg: StagedMessage) -> tuple[bytes, str]:
        sender = self.clients.people[msg.sender_id]
        if msg.direction == "reply":
            target = self.learned[(sender.id, msg.conversation_id, msg.exchange)]
        else:
            target = self.published[msg.target_id].public_key
        content = sign_bundle(msg, target, sender.public_key, sender.signing_private_key)
        # Egress needs only the recipient manifest-wrapping key and ciphertext.
        # Sphinx protects this destination key from intermediate relays.
        wire = target + seal(target, content, "bundle")
        return wire, sha256(target).hexdigest()

    def accept(self, msg: StagedMessage, ciphertext: bytes, now: int) -> str | None:
        owner = self.clients.people[msg.target_id]
        if msg.id in self.received[owner.id]:
            return None
        trusted_key = self.published[msg.sender_id].signing_public_key
        signed = unseal(owner.private_key, ciphertext, "bundle")
        bundle = verify_bundle(msg, owner.public_key, trusted_key, signed)
        if bundle.message_id != msg.id:
            raise ValueError("Encrypted message ID does not match the retrieved handle")
        self.learned[(owner.id, msg.conversation_id, msg.exchange)] = bundle.reply_public_key
        self.received[owner.id].add(msg.id)
        self.log(msg, owner.id, "delivered", now, "")
        self.log(
            msg,
            owner.id,
            "received",
            now,
            bundle.text,
            verified_signer_id=msg.sender_id,
            signing_fingerprint=sha256(trusted_key).hexdigest(),
        )
        return sha256(bundle.reply_public_key).hexdigest()

    def log(
        self,
        msg: StagedMessage,
        owner: str,
        state: Literal["staged", "sent", "received", "delivered", "replied", "failed"],
        now: int,
        text: str,
        *,
        verified_signer_id: str | None = None,
        signing_fingerprint: str | None = None,
    ) -> None:
        self.clients.people[owner].logs.append(
            DeviceLog(
                message_id=msg.id,
                conversation_id=msg.conversation_id,
                direction=msg.direction,
                state=state,
                simulation_time_ms=now,
                text=text,
                verified_signer_id=verified_signer_id,
                signing_fingerprint=signing_fingerprint,
            )
        )

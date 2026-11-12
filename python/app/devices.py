"""Device-owned plaintext, published contacts, unverified reply keys and safe provenance."""
from dataclasses import dataclass
from hashlib import sha256
from typing import Literal
from .config import Model
from .crypto import decode_bundle, encode_bundle, seal, unseal
from .participants import DeviceLog, People, StagedMessage


@dataclass(frozen=True)
class PublishedContact:
    public_key: bytes
    provider: str


class Lineage(Model):
    simulation_time_ms: int
    message_id: str
    operation: str
    location: str
    artefact: str
    container: str | None = None
    detail: str = ""


class DeviceProtocol:
    def __init__(self,clients: People):
        self.clients=clients
        self.published={p.id:PublishedContact(p.public_key,
                   "provider-west" if p.role=="sender" else "provider-east") for p in clients.people.values()}
        self.learned: dict[tuple[str,str,int],bytes]={}
        self.received: dict[str,set[str]]={p:set() for p in clients.people}

    def prepare(self,msg: StagedMessage) -> tuple[bytes,str]:
        sender=self.clients.people[msg.sender_id]
        if msg.direction=="reply":
            target=self.learned[(sender.id,msg.conversation_id,msg.exchange)]
        else:
            target=self.published[msg.target_id].public_key
        content=encode_bundle(msg.id,msg.text,sender.public_key)
        # Egress needs only the recipient manifest-wrapping key and ciphertext.
        # Sphinx protects this destination key from intermediate relays.
        wire=target+seal(target,content,"bundle")
        return wire,sha256(target).hexdigest()

    def accept(self,msg: StagedMessage,ciphertext: bytes,now: int) -> str | None:
        owner=self.clients.people[msg.target_id]
        if msg.id in self.received[owner.id]:
            return None
        bundle=decode_bundle(unseal(owner.private_key,ciphertext,"bundle"))
        if bundle.message_id!=msg.id:
            raise ValueError("Encrypted message ID does not match the retrieved handle")
        self.learned[(owner.id,msg.conversation_id,msg.exchange)]=bundle.reply_public_key
        self.received[owner.id].add(msg.id)
        self.log(msg,owner.id,"received",now,bundle.text)
        return sha256(bundle.reply_public_key).hexdigest()

    def log(self,msg: StagedMessage,owner: str,state: Literal["staged","sent","received","delivered","replied","failed"],
            now: int,text: str) -> None:
        self.clients.people[owner].logs.append(DeviceLog(message_id=msg.id,
            conversation_id=msg.conversation_id,direction=msg.direction,state=state,
            simulation_time_ms=now,text=text))

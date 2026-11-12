"""Participant-owned identities, Tor boundaries and editable conversation plans."""

from dataclasses import dataclass, field
from hashlib import sha256
from itertools import product
from random import Random
from typing import Literal

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from pydantic import Field, field_validator

from app.config import Config, Model

Role = Literal["sender", "receiver"]
Direction = Literal["forward", "reply"]
DeliveryState = Literal["staged", "sent", "delivered", "received", "replied", "failed"]
_WORDS = [
    "lorem",
    "ipsum",
    "dolor",
    "sit",
    "amet",
    "consectetur",
    "adipiscing",
    "elit",
    "sed",
    "do",
    "eiusmod",
    "tempor",
    "incididunt",
    "ut",
    "labore",
    "et",
    "dolore",
    "magna",
    "aliqua",
    "ut",
    "enim",
    "ad",
    "minim",
    "veniam",
    "quis",
    "nostrud",
    "exercitation",
    "ullamco",
    "laboris",
    "nisi",
    "ut",
    "aliquip",
    "ex",
    "ea",
    "commodo",
    "consequat",
]
_NAMES = {
    "sender": ("Alice", "Carol", "David", "Eve", "Frank", "Grace", "Heidi", "Ivan", "Judy", "Kai"),
    "receiver": ("Bob", "Lena", "Mira", "Noah", "Olivia", "Pete", "Quinn", "Rosa", "Sam", "Tess"),
}


class StagedMessage(Model):
    id: str
    conversation_id: str
    sender_id: str
    target_id: str
    exchange: int = Field(ge=1)
    direction: Direction
    text: str = Field(min_length=1)

    @field_validator("text")
    @classmethod
    def meaningful_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message must contain visible text")
        return value


class DeviceLog(Model):
    message_id: str
    conversation_id: str
    direction: Direction
    state: DeliveryState
    simulation_time_ms: int = Field(ge=0)
    text: str


@dataclass(slots=True)
class TorNetwork:
    id: str
    owner_id: str
    entry_count: int = 0
    exit_count: int = 0

    def enter(self) -> None:
        self.entry_count += 1

    def exit(self) -> None:
        self.exit_count += 1


@dataclass(slots=True)
class Person:
    id: str
    label: str
    role: Role
    tor: TorNetwork
    polling_enabled: bool
    private_key: X25519PrivateKey = field(default_factory=X25519PrivateKey.generate, repr=False)
    logs: list[DeviceLog] = field(default_factory=list, repr=False)

    @property
    def public_key(self) -> bytes:
        return self.private_key.public_key().public_bytes_raw()

    @property
    def fingerprint(self) -> str:
        return sha256(self.public_key).hexdigest()

    def device(self) -> dict[str, object]:
        return {
            "id": self.id,
            "label": self.label,
            "role": self.role,
            "tor_id": self.tor.id,
            "fingerprint": self.fingerprint,
            "polling_enabled": self.polling_enabled,
            "logs": [entry.model_dump(mode="json") for entry in self.logs],
        }


def _default_text(rng: Random) -> str:
    count = rng.randint(3, 10)
    offset = rng.randrange(len(_WORDS) - count + 1)
    return " ".join(_WORDS[offset : offset + count]).capitalize() + "."


class People:
    def __init__(self, config: Config, rng: Random):
        self.people: dict[str, Person] = {}
        self.messages: dict[str, StagedMessage] = {}
        senders = self._create_role("sender", config.sender_count, config)
        receivers = self._create_role("receiver", config.receiver_count, config)
        if set(config.polling_overrides).difference(receivers):
            raise ValueError("Polling overrides must refer to a configured receiver")
        if config.pairing_strategy == "one_to_one_pairs":
            pairs = list(zip(senders, receivers, strict=True))
        elif config.pairing_strategy == "all_to_one":
            pairs = [(sender, receivers[0]) for sender in senders]
        elif config.pairing_strategy == "one_to_all":
            pairs = [(senders[0], receiver) for receiver in receivers]
        else:
            pairs = rng.sample(list(product(senders, receivers)), config.pair_count)

        for index, (sender, receiver) in enumerate(pairs, start=1):
            conversation = f"conv-{index}"
            for exchange in range(1, config.exchanges + 1):
                self._stage(conversation, exchange, "forward", sender, receiver, rng)
                self._stage(conversation, exchange, "reply", receiver, sender, rng)

    def _create_role(self, role: Role, count: int, config: Config) -> list[str]:
        ids = []
        for index in range(count):
            person_id = f"{role}-{index + 1}"
            polling = role == "sender" or config.polling_overrides.get(
                person_id, config.polling_enabled
            )
            tor = TorNetwork(id=f"tor-{person_id}", owner_id=person_id)
            self.people[person_id] = Person(person_id, _NAMES[role][index], role, tor, polling)
            ids.append(person_id)
        return ids

    def _stage(
        self,
        conversation: str,
        exchange: int,
        direction: Direction,
        sender: str,
        target: str,
        rng: Random,
    ) -> None:
        message_id = f"msg-{len(self.messages) + 1}"
        self.messages[message_id] = StagedMessage(
            id=message_id,
            conversation_id=conversation,
            sender_id=sender,
            target_id=target,
            exchange=exchange,
            direction=direction,
            text=_default_text(rng),
        )

    def edit(self, message_id: str, text: str) -> StagedMessage:
        message = self.messages[message_id]
        updated = StagedMessage.model_validate({**message.model_dump(), "text": text})
        self.messages[message_id] = updated
        return updated

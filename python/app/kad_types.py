"""Kademlia protocol messages and the effects consumed by the event scheduler."""

from dataclasses import dataclass, field
from typing import Any, Literal

from .buckets import Contact, Probe

Method = Literal["PING", "STORE", "FIND_NODE", "FIND_VALUE"]


@dataclass(frozen=True)
class Record:
    value: bytes = field(repr=False)
    published_at: int
    expires_at: int


@dataclass(frozen=True)
class Rpc:
    source: str
    target: str
    rpc_id: int
    method: Method
    reply: bool
    sender: Contact
    key: int = 0
    contacts: tuple[Contact, ...] = ()
    record: Record | None = None
    cached: bool = False


@dataclass(frozen=True)
class Timer:
    at: int
    rpc_id: int


@dataclass(frozen=True)
class Notice:
    kind: str
    peer: str
    details: dict[str, Any]


@dataclass(frozen=True)
class Complete:
    op_id: str
    success: bool
    value: bytes | None = field(repr=False)
    peers: tuple[str, ...]


Effect = Rpc | Timer | Notice | Complete


@dataclass
class Outstanding:
    request: Rpc
    op_id: str = ""
    probe: Probe | None = None
    expired: bool = False


@dataclass
class Search:
    op_id: str
    origin: str
    key: int
    purpose: str
    record: Record | None = None
    contacts: dict[str, Contact] = field(default_factory=dict)
    queried: set[str] = field(default_factory=set)
    responded: set[str] = field(default_factory=set)
    silent: set[str] = field(default_factory=set)
    round_peers: set[str] = field(default_factory=set)
    round_best: int = 1 << 160
    final_sweep: bool = False
    storing: bool = False
    store_pending: set[str] = field(default_factory=set)
    stored: set[str] = field(default_factory=set)

    def nearest(self) -> list[Contact]:
        return sorted((c for c in self.contacts.values() if c.peer not in self.silent),
                      key=lambda c: c.node_id ^ self.key)

    def add(self, contacts: tuple[Contact, ...] | list[Contact]) -> None:
        for contact in contacts:
            if contact.peer != self.origin:
                self.contacts.setdefault(contact.peer, contact)

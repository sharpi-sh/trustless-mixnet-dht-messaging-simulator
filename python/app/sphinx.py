"""Local node keys and the reference-compatible 2017 Loopix forward packet."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from hmac import compare_digest
from math import isfinite
from os import urandom

from Crypto.PublicKey import ECC

from .sphinx_ref.client import (
    Dest_flag,
    Nenc,
    PFdecode,
    Relay_flag,
    create_forward_message,
    create_header,
    pad_body,
    receive_forward,
)
from .sphinx_ref.node import sphinx_process
from .sphinx_ref.params import SphinxParams
from .sphinx_ref.wire import SphinxException, decode, encode

PARAMS = SphinxParams(header_len=1024, body_len=1024)
WIRE_BYTES = 2079
MAX_REPLY_BYTES = PARAMS.m - PARAMS.k - 1
# One MessagePack array byte and three binary body-prefix bytes surround the header.
_HEADER_BYTES = WIRE_BYTES - PARAMS.m - 4
_SURB_FLAG = b"\xf2"


@dataclass(frozen=True, slots=True)
class ReplyBlock:
    """Bearer material sent to the responder. The first hop is public."""

    first_node: str
    header: bytes = field(repr=False)
    payload_key: bytes = field(repr=False)

    def __post_init__(self) -> None:
        try:
            if not isinstance(self.first_node, str) or not 1 <= len(self.first_node.encode()) <= 127:
                raise ValueError("Invalid first hop")
            if not isinstance(self.payload_key, bytes) or len(self.payload_key) != PARAMS.k:
                raise ValueError("Invalid payload key")
            if not isinstance(self.header, bytes) or len(self.header) != _HEADER_BYTES:
                raise ValueError("Invalid header length")
            point, routing, mac = decode(self.header)
            if (
                not PARAMS.group.in_group(point)
                or not isinstance(routing, bytes)
                or len(routing) != PARAMS.max_len - 32
                or not isinstance(mac, bytes)
                or len(mac) != PARAMS.k
                or self.header != encode((point, routing, mac))
            ):
                raise ValueError("Invalid reply header")
        except (ValueError, TypeError, IndexError, KeyError) as exc:
            raise SphinxException("Malformed reply block") from exc

    def to_bytes(self) -> bytes:
        return encode((self.first_node, self.header, self.payload_key))

    @classmethod
    def from_bytes(cls, data: bytes) -> ReplyBlock:
        try:
            # The first-hop identifier is bounded by one signed routing length byte.
            if not isinstance(data, bytes) or len(data) > _HEADER_BYTES + 127 + PARAMS.k + 8:
                raise ValueError("Invalid serialised block size")
            first_node, header, key = decode(data)
            return cls(first_node, header, key)
        except (ValueError, TypeError, IndexError, KeyError) as exc:
            raise SphinxException("Malformed reply block") from exc


@dataclass(slots=True, repr=False)
class ReplySecret:
    """Kept only by the request originator, separate from the bearer block."""

    reply_id: bytes
    _keys: tuple[bytes, ...]

    def open(self, reply_id: bytes | None, body: bytes) -> bytes:
        if not isinstance(reply_id, bytes) or reply_id != self.reply_id or not self._keys:
            raise SphinxException("Unknown or spent reply secret")
        if not isinstance(body, bytes) or len(body) != PARAMS.m:
            raise SphinxException("Invalid reply body length")
        # Each mix removed a LIONESS layer. Undo these transforms in reverse order.
        for key in reversed(self._keys[1:]):
            body = PARAMS.pi(key, body)
        key = self._keys[0]
        clear = PARAMS.pii(key, body)
        mac, padded = clear[: PARAMS.k], clear[PARAMS.k :]
        if not compare_digest(mac, PARAMS.mu(key, padded)):
            raise SphinxException("Modified reply body")
        unpadded = padded.rstrip(b"\xff")
        if not unpadded.endswith(b"\x7f"):
            raise SphinxException("Invalid reply padding")
        self._keys = ()
        return unpadded[:-1]


@dataclass(frozen=True, slots=True)
class Hop:
    next_id: str | None
    delay_ms: int
    packet: bytes | None
    payload: bytes | None
    replay_tag: bytes
    drop: bool = False
    reply_id: bytes | None = None
    reply_destination: str | None = None


@dataclass(slots=True)
class _Node:
    key: ECC.EccKey = field(default_factory=lambda: ECC.generate(curve="P-224"), repr=False)
    seen: set[bytes] = field(default_factory=set, repr=False)


class SphinxNetwork:
    def __init__(self, node_ids: list[str]) -> None:
        self._spent_headers: set[bytes] = set()
        self._nodes = {node_id: _Node() for node_id in node_ids}

    def replay_count(self, node_id: str) -> int:
        return len(self._nodes[node_id].seen)

    def _routing_commands(
        self,
        route: list[str],
        delays_ms: list[int],
        drop_at: int | None = None,
    ) -> list[bytes]:
        if route and len(delays_ms) == len(route) and delays_ms[-1] == 0:
            delays_ms = delays_ms[:-1]
        if not route or len(delays_ms) != len(route) - 1:
            raise ValueError("Specify one delay per forwarding hop and an optional terminal zero")
        if any(type(delay) is not int or delay < 0 for delay in delays_ms):
            raise ValueError("Hop delays must be non-negative integer milliseconds")
        if drop_at is not None and not 0 <= drop_at < len(route):
            raise ValueError("Drop command must be addressed to a route node")
        if any(node not in self._nodes for node in route):
            raise ValueError("Unknown Sphinx route node")
        routing = []
        for index, node_id in enumerate(route):
            # Upstream puts the next node's address alongside the processing node's delay.
            delay_seconds = delays_ms[index - 1] / 1000 if index else 0.0
            drop = drop_at is not None and index == drop_at + 1
            command = Nenc(((b"127.0.0.1", 0), drop, None, delay_seconds, node_id.encode()))
            if len(command) > 127:
                raise ValueError("Node address exceeds the Sphinx command capacity")
            routing.append(command)
        return routing

    def build(
        self, route: list[str], delays_ms: list[int], payload: bytes, *, drop_at: int | None = None
    ) -> bytes:
        """Encode forwarding delays. An optional terminal zero denotes immediate handoff."""
        routing = self._routing_commands(route, delays_ms, drop_at)
        destination = (b"127.0.0.1", 0, route[-1].encode())
        if (
            not isinstance(payload, bytes)
            or PARAMS.k + len(encode((destination, payload))) + 1 > PARAMS.m
        ):
            raise ValueError("Payload exceeds the fixed Sphinx body capacity")
        keys = [self._nodes[node].key.pointQ for node in route]
        if drop_at == len(route) - 1:
            # In the 2017 packet a provider drops a relay command addressed to a
            # dummy recipient. Its extra onion layer is never sent or processed.
            cover_recipient = b"cover-recipient"
            routing.append(Nenc(((b"127.0.0.1", 0), True, None, 0.0, cover_recipient)))
            keys.append(ECC.generate(curve="P-224").pointQ)
            destination = (b"127.0.0.1", 0, cover_recipient)
        return encode(create_forward_message(PARAMS, routing, keys, destination, payload))

    def create_surb(
        self,
        route: list[str],
        delays_ms: list[int],
        *,
        destination: str | None = None,
    ) -> tuple[ReplyBlock, ReplySecret]:
        routing = self._routing_commands(route, delays_ms)
        receiver = route[-1] if destination is None else destination
        reply_id = urandom(PARAMS.k)
        terminal = encode((_SURB_FLAG, receiver.encode(), reply_id))
        if not receiver or len(terminal) > 127:
            raise ValueError("Invalid reply destination")
        header, shared = create_header(
            PARAMS, routing, [self._nodes[n].key.pointQ for n in route], terminal
        )
        key = urandom(PARAMS.k)
        block = ReplyBlock(route[0], encode(header), key)
        secret = ReplySecret(reply_id, (key, *(PARAMS.hpi(s) for s in shared)))
        return block, secret

    def use_surb(self, block: ReplyBlock, payload: bytes) -> bytes:
        if not isinstance(payload, bytes) or len(payload) > MAX_REPLY_BYTES:
            raise ValueError("Reply payload exceeds the fixed Sphinx body capacity")
        fingerprint = sha256(block.header).digest()
        if fingerprint in self._spent_headers:
            raise SphinxException("Reply block already spent")
        padded = pad_body(PARAMS.m - PARAMS.k, payload)
        key = block.payload_key
        body = PARAMS.pi(key, PARAMS.mu(key, padded) + padded)
        packet = encode((decode(block.header), body))
        self._spent_headers.add(fingerprint)
        return packet

    def peel(self, node_id: str, packet: bytes) -> Hop:
        if node_id not in self._nodes or not isinstance(packet, bytes) or len(packet) != WIRE_BYTES:
            raise SphinxException("Invalid Sphinx node or packet size")
        node = self._nodes[node_id]
        try:
            (point, beta, gamma), body = decode(packet)
            if not isinstance(beta, bytes) or len(beta) != PARAMS.max_len - 32:
                raise SphinxException("Invalid Sphinx routing field")
            if (
                not isinstance(gamma, bytes)
                or len(gamma) != PARAMS.k
                or not isinstance(body, bytes)
                or len(body) != PARAMS.m
            ):
                raise SphinxException("Invalid Sphinx MAC or body")
            tag, routing, inner = sphinx_process(PARAMS, int(node.key.d), (point, beta, gamma), body)
            if tag in node.seen:
                raise SphinxException("Sphinx replay")
            command = PFdecode(PARAMS, routing)
            if command[0] == Relay_flag:
                (_, _port), drop, _, seconds, next_name = command[1]
                if (
                    type(drop) is not bool
                    or type(seconds) not in (float, int)
                    or not isfinite(seconds)
                    or seconds < 0
                ):
                    raise SphinxException("Invalid Sphinx forwarding command")
                if drop:
                    hop = Hop(None, 0, None, None, tag, True)
                else:
                    hop = Hop(next_name.decode(), round(seconds * 1000), encode(inner), None, tag)
            elif command[0] == _SURB_FLAG:
                _, destination, reply_id = command
                if not isinstance(reply_id, bytes) or len(reply_id) != PARAMS.k:
                    raise SphinxException("Invalid reply identifier")
                hop = Hop(
                    None,
                    0,
                    None,
                    inner[1],
                    tag,
                    reply_id=reply_id,
                    reply_destination=destination.decode(),
                )
            elif command == [Dest_flag]:
                dest, payload = receive_forward(PARAMS, inner[1])
                if dest[2] != node_id.encode() or not isinstance(payload, bytes):
                    raise SphinxException("Invalid Sphinx delivery")
                hop = Hop(None, 0, None, payload, tag)
            else:
                raise SphinxException("Unknown Sphinx command")
        except SphinxException:
            raise
        except (TypeError, ValueError, IndexError, KeyError, OverflowError, AttributeError) as exc:
            raise SphinxException("Malformed Sphinx packet") from exc
        node.seen.add(tag)
        return hop

"""Local node keys and the reference-compatible 2017 Loopix forward packet."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite

from Crypto.PublicKey import ECC

from .sphinx_ref.client import (
    Dest_flag,
    Nenc,
    PFdecode,
    Relay_flag,
    create_forward_message,
    receive_forward,
)
from .sphinx_ref.node import sphinx_process
from .sphinx_ref.params import SphinxParams
from .sphinx_ref.wire import SphinxException, decode, encode

PARAMS = SphinxParams(header_len=1024, body_len=1024)
WIRE_BYTES = 2079


@dataclass(frozen=True, slots=True)
class Hop:
    next_id: str | None
    delay_ms: int
    packet: bytes | None
    payload: bytes | None
    replay_tag: bytes
    drop: bool = False


@dataclass(slots=True)
class _Node:
    key: ECC.EccKey = field(default_factory=lambda: ECC.generate(curve="P-224"), repr=False)
    seen: set[bytes] = field(default_factory=set, repr=False)


class SphinxNetwork:
    def __init__(self, node_ids: list[str]) -> None:
        self._nodes = {node_id: _Node() for node_id in node_ids}

    def replay_count(self, node_id: str) -> int:
        return len(self._nodes[node_id].seen)

    def build(
        self, route: list[str], delays_ms: list[int], payload: bytes, *, drop_at: int | None = None
    ) -> bytes:
        """Encode forwarding delays. An optional terminal zero denotes immediate handoff."""
        if route and len(delays_ms) == len(route) and delays_ms[-1] == 0:
            delays_ms = delays_ms[:-1]
        if not route or len(delays_ms) != len(route) - 1:
            raise ValueError("Specify one delay per forwarding hop and an optional terminal zero")
        if any(type(delay) is not int or delay < 0 for delay in delays_ms):
            raise ValueError("Hop delays must be non-negative integer milliseconds")
        if drop_at is not None and not 0 <= drop_at < len(delays_ms):
            raise ValueError("Drop command must be read by a forwarding hop")
        if any(node not in self._nodes for node in route):
            raise ValueError("Unknown Sphinx route node")
        destination = (b"127.0.0.1", 0, route[-1].encode())
        if (
            not isinstance(payload, bytes)
            or PARAMS.k + len(encode((destination, payload))) + 1 > PARAMS.m
        ):
            raise ValueError("Payload exceeds the fixed Sphinx body capacity")
        routing = []
        for index, node_id in enumerate(route):
            # Upstream puts the next node's address alongside the processing node's delay.
            delay_seconds = delays_ms[index - 1] / 1000 if index else 0.0
            drop = drop_at is not None and index == drop_at + 1
            command = Nenc(((b"127.0.0.1", 0), drop, None, delay_seconds, node_id.encode()))
            if len(command) > 127:
                raise ValueError("Node address exceeds the Sphinx command capacity")
            routing.append(command)
        keys = [self._nodes[node].key.pointQ for node in route]
        return encode(create_forward_message(PARAMS, routing, keys, destination, payload))

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
                hop = Hop(next_name.decode(), round(seconds * 1000), encode(inner), None, tag, drop)
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

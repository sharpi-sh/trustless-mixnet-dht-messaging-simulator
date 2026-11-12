"""Event-driven Kademlia 2002. Only arrived RPCs can reveal remote peer state."""

from dataclasses import dataclass, field
from random import Random
from typing import Any

from .buckets import ID_BITS, ID_SPACE, Contact, DHTRoutingTable, K, Probe
from .kad_types import Complete, Effect, Method, Notice, Outstanding, Record, Rpc, Search, Timer

ALPHA = 3
HOUR = 3_600_000
DAY = 24 * HOUR


@dataclass
class DHTNode:
    peer_id: str
    node_id: int
    address: str
    table: DHTRoutingTable = field(init=False, compare=False)
    records: dict[int, Record] = field(default_factory=dict, repr=False)
    originals: dict[int, Record] = field(default_factory=dict, repr=False)
    replica_due: dict[int, int] = field(default_factory=dict, repr=False)
    observations: dict[str, dict[str, Any]] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self.table = DHTRoutingTable(self.node_id)

    @property
    def contact(self) -> Contact:
        return Contact(self.peer_id, self.node_id)

    def record(self, key: int, now: int) -> Record | None:
        value = self.records.get(key)
        if value and value.expires_at <= now:
            del self.records[key]
            self.replica_due.pop(key, None)
            return None
        return value


class DHTNetwork:
    def __init__(self, rng: Random, timeout_ms: int = 2000) -> None:
        if timeout_ms <= 0:
            raise ValueError("RPC timeout must be positive")
        self.rng = rng
        self.timeout_ms = timeout_ms
        self.nodes: dict[str, DHTNode] = {}
        self._allocated_ids: set[int] = set()
        self._calls: dict[int, Outstanding] = {}
        self._searches: dict[str, Search] = {}
        self._join_refresh: dict[str, set[str]] = {}
        self._serial = 0

    def add_node(self, peer_id: str, node_id: int | None = None) -> DHTNode:
        if not peer_id or peer_id in self.nodes:
            raise ValueError("A DHT peer requires a unique non-empty name")
        if node_id is None:
            node_id = self.rng.getrandbits(ID_BITS)
            while node_id in self._allocated_ids:
                node_id = self.rng.getrandbits(ID_BITS)
        if not 0 <= node_id < ID_SPACE or node_id in self._allocated_ids:
            raise ValueError("Expected a unique unsigned 160-bit node ID")
        node = DHTNode(peer_id, node_id, f"sim://{peer_id}")
        self._allocated_ids.add(node_id)
        self.nodes[peer_id] = node
        return node

    def inspect(self, peer: str, now: int) -> dict[str, Any]:
        node = self.nodes[peer]
        searches = [
            {
                "op_id": s.op_id,
                "key": f"{s.key:040x}",
                "purpose": s.purpose,
                "shortlist": [
                    {
                        "peer": c.peer,
                        "distance": f"{c.node_id ^ s.key:040x}",
                        "queried": c.peer in s.queried,
                        "responded": c.peer in s.responded,
                        "timed_out": c.peer in s.silent,
                    }
                    for c in sorted(s.contacts.values(), key=lambda c: c.node_id ^ s.key)
                ],
                "final_sweep": s.final_sweep,
            }
            for s in self._searches.values()
            if s.origin == peer
        ]
        return {
            "peer_id": node.peer_id,
            "node_id": f"{node.node_id:040x}",
            "address": node.address,
            "simulation_time_ms": now,
            "k": K,
            "alpha": ALPHA,
            "buckets": node.table.inspect(now),
            "active_lookups": searches,
            "observations": node.observations.copy(),
            "record_ids": [f"{key:040x}" for key, r in node.records.items() if r.expires_at > now],
        }

    @staticmethod
    def _notice(wire: Rpc, sent: bool) -> Notice:
        return Notice(
            "kademlia_rpc_sent" if sent else "kademlia_rpc_received",
            wire.source if sent else wire.target,
            {
                "rpc_id": f"{wire.rpc_id:040x}",
                "method": wire.method,
                "reply": wire.reply,
                "source_id": wire.source,
                "target_id": wire.target,
                "key": f"{wire.key:040x}",
            },
        )

    def _send(
        self,
        source: str,
        target: str,
        method: Method,
        now: int,
        key: int = 0,
        record: Record | None = None,
        op_id: str = "",
        probe: Probe | None = None,
        cached: bool = False,
    ) -> list[Effect]:
        token = self.rng.getrandbits(ID_BITS)
        while token in self._calls:
            token = self.rng.getrandbits(ID_BITS)
        request = Rpc(
            source,
            target,
            token,
            method,
            False,
            self.nodes[source].contact,
            key,
            record=record,
            cached=cached,
        )
        self._calls[token] = Outstanding(request, op_id, probe)
        return [self._notice(request, True), request, Timer(now + self.timeout_ms, token)]

    def _probe(self, peer: str, probe: Probe | None, now: int) -> list[Effect]:
        if probe is None:
            return []
        return self._send(peer, probe.old.peer, "PING", now, probe=probe)

    def _hear(self, node: DHTNode, contact: Contact, now: int) -> list[Effect]:
        first_seen = contact.peer not in node.observations
        observation = node.observations.setdefault(contact.peer, {"failures": 0})
        observation.update(last_contact_ms=now, status="responded")
        probe = node.table.observe(contact, now)
        effects: list[Effect] = [
            Notice("kademlia_bucket_updated", node.peer_id, {"contact": contact.peer}),
            *self._probe(node.peer_id, probe, now),
        ]
        if first_seen:
            # Only the previous closest holder transfers records to a newly learnt peer (§2.5).
            for key in list(node.replica_due):
                record = node.record(key, now)
                others = [c for c in node.table.closest(key, K + 1) if c.peer != contact.peer]
                if (
                    record
                    and all(node.node_id ^ key < c.node_id ^ key for c in others)
                    and sum(c.node_id ^ key < contact.node_id ^ key for c in [*others, node.contact])
                    < K
                ):
                    effects.extend(self._send(node.peer_id, contact.peer, "STORE", now, key, record))
        return effects

    def _store(
        self, node: DHTNode, key: int, record: Record, now: int, cached: bool = False
    ) -> list[Effect]:
        previous = node.record(key, now)
        if record.expires_at <= now or (previous and previous.published_at > record.published_at):
            return []
        # A cache copy of the same publication must not shorten an existing replica's lifetime.
        if previous and previous.published_at == record.published_at:
            if cached and key in node.replica_due:
                return []
            if previous.expires_at > record.expires_at:
                record = previous
        node.records[key] = record
        if cached:
            node.replica_due.pop(key, None)
            return []
        due = now + HOUR
        node.replica_due[key] = due
        return (
            [Timer(due, peer=node.peer_id, kind="replica", key=key)] if due < record.expires_at else []
        )

    def receive(self, wire: Rpc, now: int) -> list[Effect]:
        if wire.sender.peer != wire.source or wire.target not in self.nodes:
            return []
        node = self.nodes[wire.target]
        call = self._calls.get(wire.rpc_id)
        if wire.reply:
            if call is None or (call.request.source, call.request.target, call.request.method) != (
                wire.target,
                wire.source,
                wire.method,
            ):
                return []
            del self._calls[wire.rpc_id]
        effects: list[Effect] = [self._notice(wire, False)]
        effects.extend(self._hear(node, wire.sender, now))
        if wire.reply:
            assert call is not None
            effects.extend(self._settle(call, wire, now))
            return effects
        contacts: tuple[Contact, ...] = ()
        record = None
        if wire.method == "STORE" and wire.record:
            effects.extend(self._store(node, wire.key, wire.record, now, wire.cached))
        if wire.method == "FIND_VALUE":
            record = node.record(wire.key, now)
        if wire.method in ("FIND_VALUE", "FIND_NODE") and record is None:
            contacts = tuple(node.table.closest(wire.key, K))
        reply = Rpc(
            wire.target,
            wire.source,
            wire.rpc_id,
            wire.method,
            True,
            node.contact,
            wire.key,
            contacts,
            record,
        )
        return [*effects, self._notice(reply, True), reply]

    def wake(self, timer: Timer, now: int) -> list[Effect]:
        if timer.kind != "rpc":
            if now < timer.at:
                return []
            node = self.nodes[timer.peer]
            if timer.kind == "publisher":
                record = node.originals.get(timer.key)
                if record and record.published_at + DAY <= now:
                    return self.publish(
                        self._internal("publisher"), timer.peer, timer.key, record.value, now
                    )
            elif timer.kind == "replica":
                return self._republish(node, timer.key, now)
            return []
        call = self._calls.get(timer.rpc_id)
        if call is None or call.expired or now < timer.at:
            return []
        call.expired = True
        wire = call.request
        if not call.op_id or wire.method not in ("FIND_NODE", "FIND_VALUE"):
            del self._calls[timer.rpc_id]
        observation = self.nodes[wire.source].observations.setdefault(wire.target, {"failures": 0})
        observation.update(status="unresponsive", failures=observation["failures"] + 1)
        return [
            Notice(
                "kademlia_rpc_timeout",
                wire.source,
                {"peer": wire.target, "rpc_id": f"{wire.rpc_id:040x}", "method": wire.method},
            ),
            *self._settle(call, None, now),
        ]

    def lookup(self, op_id: str, peer: str, key: int, now: int) -> list[Effect]:
        return self._start(Search(op_id, peer, key, "value"), now)

    def find_nodes(self, op_id: str, peer: str, key: int, now: int) -> list[Effect]:
        return self._start(Search(op_id, peer, key, "nodes"), now)

    def publish(self, op_id: str, peer: str, key: int, value: bytes, now: int) -> list[Effect]:
        record = Record(value, now, now + DAY)
        effects = self._start(Search(op_id, peer, key, "publish", record), now)
        self.nodes[peer].originals[key] = record
        return [*effects, Timer(now + DAY, peer=peer, kind="publisher", key=key)]

    def _internal(self, operation: str) -> str:
        self._serial += 1
        return f"kademlia/{operation}/{self._serial}"

    def join(self, peer: str, bootstrap: str | None, now: int) -> list[Effect]:
        node = self.nodes[peer]
        op_id = f"join-{peer}"
        if bootstrap is None:
            return [Complete(op_id, True, None, ())]
        contact = self.nodes[bootstrap].contact  # The single out-of-band bootstrap address.
        effects = self._probe(peer, node.table.observe(contact, now), now)
        return [*effects, *self._start(Search(op_id, peer, node.node_id, "join"), now)]

    def _republish(self, node: DHTNode, key: int, now: int) -> list[Effect]:
        record = node.record(key, now)
        due = node.replica_due.get(key)
        if record is None or due is None or now < due:
            return []
        node.replica_due[key] = now + HOUR
        return self._start(
            Search(self._internal("replica"), node.peer_id, key, "republish", record), now
        )

    def maintenance(self, peer: str, now: int) -> list[Effect]:
        node = self.nodes[peer]
        effects: list[Effect] = []
        for target in node.table.refresh_targets(now, self.rng):
            effects.extend(self._start(Search(self._internal("refresh"), peer, target, "refresh"), now))
        for key, record in list(node.originals.items()):
            if record.published_at + DAY <= now:
                effects.extend(self.publish(self._internal("publisher"), peer, key, record.value, now))
        for key in list(node.records):
            effects.extend(self._republish(node, key, now))
        return effects

    def _start(self, search: Search, now: int) -> list[Effect]:
        if not 0 <= search.key < ID_SPACE or search.op_id in self._searches:
            raise ValueError("A lookup requires a 160-bit key and a distinct active operation ID")
        node = self.nodes[search.origin]
        self._searches[search.op_id] = search
        node.table.mark_lookup(search.key, now)
        if search.purpose == "value" and (record := node.record(search.key, now)) is not None:
            return self._finish(search, True, record.value, (node.peer_id,), now)
        # Keep reserve contacts for timeouts, but only query the current k closest viable nodes.
        search.add(node.table.closest(search.key, ID_SPACE))
        return self._drive(search, now)

    def _drive(self, search: Search, now: int) -> list[Effect]:
        nearest = search.nearest()[:K]
        if all(c.peer in search.responded for c in nearest):
            peers = tuple(c.peer for c in nearest)
            if search.purpose in ("publish", "republish"):
                return self._replicate(search, peers, now)
            return self._finish(search, search.purpose != "value", None, peers, now)
        pending = search.queried - search.responded - search.silent
        if not search.round_peers and search.queried:
            search.final_sweep |= nearest[0].node_id ^ search.key >= search.round_best
        available = K if search.final_sweep else max(0, ALPHA - len(pending))
        selection = [c for c in nearest if c.peer not in search.queried][:available]
        effects: list[Effect] = []
        for contact in selection:
            search.queried.add(contact.peer)
            effects.extend(
                self._send(
                    search.origin,
                    contact.peer,
                    "FIND_VALUE" if search.purpose == "value" else "FIND_NODE",
                    now,
                    search.key,
                    op_id=search.op_id,
                )
            )
        if not search.round_peers:
            search.round_peers = pending | {c.peer for c in selection}
            search.round_best = nearest[0].node_id ^ search.key
        return effects

    def _replicate(self, search: Search, peers: tuple[str, ...], now: int) -> list[Effect]:
        node = self.nodes[search.origin]
        holders = [search.contacts[peer] for peer in peers] + [node.contact]
        holders.sort(key=lambda c: c.node_id ^ search.key)
        effects: list[Effect] = []
        assert search.record is not None
        search.storing = True
        for holder in holders[:K]:
            if holder.peer == node.peer_id:
                effects.extend(self._store(node, search.key, search.record, now))
                search.stored.add(holder.peer)
            else:
                search.store_pending.add(holder.peer)
                effects.extend(
                    self._send(
                        node.peer_id,
                        holder.peer,
                        "STORE",
                        now,
                        search.key,
                        record=search.record,
                        op_id=search.op_id,
                    )
                )
        if not search.store_pending:
            effects.extend(
                self._finish(search, bool(search.stored), None, tuple(sorted(search.stored)), now)
            )
        return effects

    def _settle(self, call: Outstanding, reply: Rpc | None, now: int) -> list[Effect]:
        q = call.request
        if call.probe is not None:
            table = self.nodes[q.source].table
            return self._probe(q.source, table.resolve(call.probe, reply is not None, now), now)
        search = self._searches.get(call.op_id)
        if search is None:
            return []
        if q.method == "STORE":
            search.store_pending.discard(q.target)
            if reply is not None:
                search.stored.add(q.target)
            if not search.store_pending:
                return self._finish(
                    search, bool(search.stored), None, tuple(sorted(search.stored)), now
                )
            return []
        if search.storing:
            return []
        search.round_peers.discard(q.target)
        if reply is None:
            search.silent.add(q.target)
        else:
            search.silent.discard(q.target)
            if reply.record and reply.record.expires_at > now and q.method == "FIND_VALUE":
                effects: list[Effect] = []
                misses = [c for c in search.nearest() if c.peer in search.responded]
                if misses:
                    cache = misses[0]
                    rank = sum(
                        c.node_id ^ search.key < cache.node_id ^ search.key
                        for c in search.contacts.values()
                    )
                    # §2.3 specifies exponential expiry by rank, without prescribing a base.
                    expires = min(reply.record.expires_at, now + max(1, DAY >> rank))
                    copy = Record(reply.record.value, reply.record.published_at, expires)
                    effects.extend(
                        self._send(
                            q.source, cache.peer, "STORE", now, search.key, record=copy, cached=True
                        )
                    )
                return [*effects, *self._finish(search, True, reply.record.value, (q.target,), now)]
            search.responded.add(q.target)
            search.add(reply.contacts)
        return self._drive(search, now)

    def _finish(
        self, search: Search, success: bool, value: bytes | None, peers: tuple[str, ...], now: int
    ) -> list[Effect]:
        del self._searches[search.op_id]
        for token in [t for t, call in self._calls.items() if call.op_id == search.op_id]:
            call = self._calls[token]
            if call.expired:
                del self._calls[token]
            else:
                # Remaining replies may still update local contacts after a first value hit.
                call.op_id = ""
        if search.purpose == "join":
            if not peers:
                return [Complete(search.op_id, False, None, ())]
            targets = self.nodes[search.origin].table.refresh_targets(now, self.rng, joining=True)
            refreshes = [(self._internal("join-refresh"), target) for target in targets]
            if refreshes:
                self._join_refresh[search.origin] = {op for op, target in refreshes}
                effects: list[Effect] = []
                for op, target in refreshes:
                    effects.extend(self._start(Search(op, search.origin, target, "join-refresh"), now))
                return effects
        if search.purpose == "join-refresh":
            remaining = self._join_refresh[search.origin]
            remaining.discard(search.op_id)
            if remaining:
                return []
            del self._join_refresh[search.origin]
            return [Complete(f"join-{search.origin}", True, None, peers)]
        return [Complete(search.op_id, success, value, peers)]

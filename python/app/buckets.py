"""Original Kademlia 2002 prefix-tree leaves and direct-contact ordering."""

from dataclasses import dataclass, field
from random import Random

ID_BITS = 160
ID_SPACE = 1 << ID_BITS
K = 20
REFRESH_MS = 3_600_000


def _check_id(value: int) -> None:
    if type(value) is not int or not 0 <= value < ID_SPACE:
        raise ValueError("Expected an unsigned 160-bit ID")


def xor_distance(a: int, b: int) -> int:
    _check_id(a)
    _check_id(b)
    return a ^ b


@dataclass(frozen=True, slots=True)
class Contact:
    peer: str
    node_id: int

    def __post_init__(self) -> None:
        _check_id(self.node_id)
        if not self.peer:
            raise ValueError("A contact requires a peer name")


@dataclass(frozen=True, slots=True)
class Probe:
    old: Contact
    candidate: Contact
    serial: int
    observed_at: int


@dataclass(slots=True)
class _Seen:
    contact: Contact
    last_seen_ms: int


@dataclass(slots=True)
class _Bucket:
    start: int
    end: int  # exclusive
    # Dict insertion order is the least-to-most-recently-seen order.
    entries: dict[int, _Seen] = field(default_factory=dict)
    pending: Probe | None = None
    last_lookup_ms: int = 0
    recent_targets: dict[int, int] = field(default_factory=dict)

    def contains(self, node_id: int) -> bool:
        return self.start <= node_id < self.end


class DHTRoutingTable:
    def __init__(self, owner_id: int):
        _check_id(owner_id)
        self.owner_id = owner_id
        self._buckets = [_Bucket(0, ID_SPACE)]
        self._serial = 0

    def _bucket(self, node_id: int) -> _Bucket:
        return next(bucket for bucket in self._buckets if bucket.contains(node_id))

    def _may_split(self, bucket: _Bucket) -> bool:
        if bucket.contains(self.owner_id):
            return True
        # The common ancestor's owner-side child is closer in prefix distance.
        # If it has fewer than k neighbours, section 2.4 retains all contacts
        # in this unbalanced local subtree, including disjoint sibling leaves.
        bit = (self.owner_id ^ bucket.start).bit_length() - 1
        width = 1 << bit
        own_start = self.owner_id & ~(width - 1)
        closer_neighbours = sum(
            len(leaf.entries) for leaf in self._buckets if own_start <= leaf.start < own_start + width
        )
        return closer_neighbours < K

    def _split(self, bucket: _Bucket) -> None:
        middle = (bucket.start + bucket.end) // 2
        left, right = _Bucket(bucket.start, middle), _Bucket(middle, bucket.end)
        for uid, seen in bucket.entries.items():
            (left if uid < middle else right).entries[uid] = seen
        for target, when in bucket.recent_targets.items():
            used = left if target < middle else right
            used.recent_targets[target] = when
            used.last_lookup_ms = max(when, used.last_lookup_ms)
        index = self._buckets.index(bucket)
        self._buckets[index : index + 1] = [left, right]

    def observe(self, contact: Contact, now: int) -> Probe | None:
        """Call only when a message comes directly from the contact."""
        uid = contact.node_id
        if uid == self.owner_id:
            return None
        bucket = self._bucket(uid)
        if uid in bucket.entries:
            # A direct observation supersedes an outstanding liveness check.
            if bucket.pending is not None and bucket.pending.old.node_id == uid:
                bucket.pending = None
            del bucket.entries[uid]
        while len(bucket.entries) == K and self._may_split(bucket):
            self._split(bucket)
            bucket = self._bucket(uid)
        if len(bucket.entries) < K:
            bucket.entries[uid] = _Seen(contact, now)
            return None
        if bucket.pending is not None:
            return None
        old = next(iter(bucket.entries.values())).contact
        self._serial += 1
        bucket.pending = Probe(old, contact, self._serial, now)
        return bucket.pending

    def cancel_probe(self, probe: Probe) -> None:
        """A local outage cannot establish the reachability of either remote contact."""
        bucket = self._bucket(probe.old.node_id)
        if bucket.pending == probe:
            bucket.pending = None

    def resolve(self, probe: Probe, live: bool, now: int) -> Probe | None:
        bucket = self._bucket(probe.old.node_id)
        if bucket.pending != probe:
            return None
        bucket.pending = None
        if live:
            return self.observe(probe.old, now)
        del bucket.entries[probe.old.node_id]
        candidate = probe.candidate
        bucket.entries[candidate.node_id] = _Seen(candidate, probe.observed_at)
        bucket.entries = dict(sorted(bucket.entries.items(), key=lambda item: item[1].last_seen_ms))
        return None

    def closest(self, target: int, limit: int = K) -> list[Contact]:
        _check_id(target)
        if limit < 0:
            raise ValueError("Contact limit cannot be negative")
        contacts = (item.contact for bucket in self._buckets for item in bucket.entries.values())
        return sorted(contacts, key=lambda c: c.node_id ^ target)[:limit]

    def mark_lookup(self, target: int, now: int) -> None:
        _check_id(target)
        bucket = self._bucket(target)
        bucket.last_lookup_ms = now
        bucket.recent_targets = {
            key: stamp for key, stamp in bucket.recent_targets.items() if now - stamp < REFRESH_MS
        }
        bucket.recent_targets[target] = now

    def refresh_targets(self, now: int, rng: Random, joining: bool = False) -> list[int]:
        nearest = self.closest(self.owner_id, 1)
        if joining and not nearest:
            return []
        targets = []
        for bucket in self._buckets:
            if joining:
                suffix_mask = bucket.end - bucket.start - 1
                min_distance = (bucket.start ^ self.owner_id) & ~suffix_mask
                if min_distance <= (nearest[0].node_id ^ self.owner_id):
                    continue
            elif now - bucket.last_lookup_ms < REFRESH_MS:
                continue
            targets.append(rng.randrange(bucket.start, bucket.end))
        return targets

    def inspect(self, now: int) -> list[dict[str, object]]:
        """Expose fixed-width IDs and inclusive bounds, safe for JSON/JavaScript."""
        return [
            {
                "range_start": f"{bucket.start:040x}",
                "range_end": f"{bucket.end - 1:040x}",
                "last_lookup_ms": bucket.last_lookup_ms,
                "refresh_due": now - bucket.last_lookup_ms >= REFRESH_MS,
                "contacts": [
                    {
                        "peer": item.contact.peer,
                        "node_id": f"{uid:040x}",
                        "xor_distance": f"{uid ^ self.owner_id:040x}",
                        "last_seen_ms": item.last_seen_ms,
                    }
                    for uid, item in bucket.entries.items()
                ],
            }
            for bucket in self._buckets
        ]

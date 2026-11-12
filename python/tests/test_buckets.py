from random import Random

import pytest

from app.buckets import Contact, DHTRoutingTable, ID_SPACE, K, REFRESH_MS, xor_distance


def peer(uid):
    return Contact(f"peer-{uid:x}", uid)


def full_distant_bucket():
    table = DHTRoutingTable(0)
    top = ID_SPACE // 2
    for uid in list(range(1, K + 1)) + list(range(top, top + K)):
        assert table.observe(peer(uid), uid % top) is None
    return table, top


def test_xor_distance_and_nearest_order_in_160_bit_space():
    top = 1 << 159
    assert xor_distance(top + 5, top + 3) == 6
    assert xor_distance(0, ID_SPACE - 1) == ID_SPACE - 1
    node = DHTRoutingTable(1)
    for uid in (1, top, 2, 3, 7):
        node.observe(peer(uid), 0)
    assert node.closest(0) == list(map(peer, [2, 3, 7, top]))
    assert node.closest(top + 1, 2) == [peer(top), peer(3)]
    with pytest.raises(ValueError):
        node.closest(ID_SPACE)
    with pytest.raises(ValueError):
        peer(-1)


def test_prefix_partition_is_contiguous_and_recency_survives_splits():
    table = DHTRoutingTable(0)
    for index in reversed(range(1, 68)):
        table.observe(peer(index), 68 - index)
    buckets = table.inspect(0)
    assert buckets[0]["range_start"] == "0" * 40
    assert buckets[-1]["range_end"] == "f" * 40
    assert all(
        int(a["range_end"], 16) + 1 == int(b["range_start"], 16) for a, b in zip(buckets, buckets[1:])
    )
    for bucket in buckets:
        rows = bucket["contacts"]
        assert len(rows) <= K
        dates = [entry["last_seen_ms"] for entry in rows]
        assert dates == sorted(dates)
        for row in rows:
            assert bucket["range_start"] <= row["node_id"] <= bucket["range_end"]
            assert len(row["xor_distance"]) == 40


def test_unbalanced_neighbourhood_splits_nonlocal_prefix_without_dropping_valid_contacts():
    owner = DHTRoutingTable(0)
    # Unique participant in 000, more than k established in neighbouring 001 subtree.
    near = 1 << 157
    other = [near + i for i in range(2 * K)]
    for uid in other:
        assert owner.observe(peer(uid), 0) is None
    assert {c.node_id for c in owner.closest(0, 100)} == set(other)
    assert max(len(bucket["contacts"]) for bucket in owner.inspect(0)) <= K


def test_full_distant_bucket_pings_head_and_keeps_live_old_contacts_mru():
    table, top = full_distant_bucket()
    new = peer(top + K)
    probe = table.observe(new, 100)
    assert probe and probe.old == peer(top) and probe.candidate == new
    assert new not in table.closest(top, K)
    table.resolve(probe, True, 111)
    rows = table.inspect(111)[-1]["contacts"]
    assert rows[-1]["peer"] == probe.old.peer and rows[-1]["last_seen_ms"] == 111
    assert new not in table.closest(top, K)
    next_probe = table.observe(new, 200)
    assert next_probe and next_probe.old == peer(top + 1)
    table.resolve(next_probe, False, 220)
    contacts = table.closest(top, K)
    assert new in contacts and next_probe.old not in contacts
    assert table.inspect(220)[-1]["contacts"][-1]["last_seen_ms"] == 200


def test_delayed_negative_probe_cannot_evict_peer_observed_since_probe():
    table, top = full_distant_bucket()
    candidate = peer(top + 25)
    pending = table.observe(candidate, 100)
    assert pending and pending.old == peer(top)
    table.observe(pending.old, 101)
    other = table.observe(candidate, 102)
    assert other and other.old != pending.old
    table.resolve(pending, False, 104)
    assert pending.old in table.closest(top, K)
    assert candidate not in table.closest(top, K)
    table.resolve(other, False, 105)
    assert candidate in table.closest(top, K)
    table.resolve(pending, False, 106)
    assert pending.old in table.closest(top, K)


def test_refreshes_use_correct_clock_and_join_refreshes_only_farther_ranges():
    table, top = full_distant_bucket()
    assert table.refresh_targets(REFRESH_MS - 1, Random(3)) == []
    table.mark_lookup(top + 3, REFRESH_MS - 3)
    targets = table.refresh_targets(REFRESH_MS, Random(3))
    assert all(t < top for t in targets)
    assert len(targets) == len(table.inspect(REFRESH_MS)) - 1
    all_ranges = table.inspect(REFRESH_MS)
    joining = table.refresh_targets(0, Random(12), joining=True)
    assert len(joining) == len(all_ranges) - 1
    for t, bucket in zip(joining, all_ranges[1:]):
        assert int(bucket["range_start"], 16) <= t <= int(bucket["range_end"], 16)
    assert DHTRoutingTable(0).refresh_targets(0, Random(3), joining=True) == []


def test_lookups_prior_to_a_split_keep_both_resulting_buckets_fresh():
    table = DHTRoutingTable(0)
    top = ID_SPACE // 2
    table.mark_lookup(2, 100)
    table.mark_lookup(top, 200)
    for uid in list(range(1, K + 1)) + [top]:
        table.observe(peer(uid), 300)
    assert len(table.inspect(300)) == 2
    assert table.refresh_targets(REFRESH_MS + 99, Random(23)) == []

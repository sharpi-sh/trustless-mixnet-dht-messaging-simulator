import json
from hashlib import sha256
from random import Random

import pytest
from pydantic import ValidationError

from app.storage import MessageManifest, StorageNetwork


def test_seeded_plan_and_independent_replicas_store_ciphertext_only():
    stores = StorageNetwork(["a", "b", "c", "d"])
    data = b"private opaque envelope data"
    manifest = stores.plan("msg-42", data, Random(99), 5, 2)
    assert manifest == stores.plan("msg-42", data, Random(99), 5, 2)
    assert manifest == MessageManifest.model_validate_json(manifest.model_dump_json())
    assert manifest.digest == sha256(data).hexdigest() and manifest.size == len(data)
    assert "msg-42" not in manifest.model_dump_json()
    assert len({f.id for f in manifest.fragments}) == 6
    assert [f.offset for f in manifest.fragments] == list(range(0, len(data), 5))
    for fragment in manifest.fragments:
        assert len(set(fragment.replicas)) == 2
        chunk = data[fragment.offset : fragment.offset + fragment.size]
        for node in fragment.replicas:
            assert fragment.id not in stores.nodes[node].fragments
            stores.put(node, fragment, chunk)
            assert stores.get(node, fragment) == chunk
    parts = {f.id: stores.get(f.replicas[-1], f) for f in reversed(manifest.fragments)}
    assert stores.reconstruct(manifest, parts) == data
    for node in stores.nodes:
        inspection = stores.inspect(node)
        assert "private" not in json.dumps(inspection) and "msg-42" not in json.dumps(inspection)
        assert all(
            f["used_in_reconstruction"] and f["integrity"] == "verified"
            for f in inspection["fragments"]
        )
        assert all(
            f["placement"] == "stored" and node in f["replicas"] for f in inspection["fragments"]
        )


def test_replica_unavailable_corrupt_or_missing_then_alternative_succeeds():
    stores = StorageNetwork(["a", "b", "c"])
    manifest = stores.plan("msg", b"cipher", Random(77), 12, 3)
    (f,) = manifest.fragments
    a, b, c = f.replicas
    stores.put(a, f, b"cipher")
    stores.put(b, f, b"cipher")
    stores.nodes[a].fragments[f.id] = b"broken"
    stores.record_unavailable(c, f)
    with pytest.raises(ValueError, match="missing"):
        stores.get(c, f)
    with pytest.raises(ValueError, match="SHA-256"):
        stores.get(a, f)
    with pytest.raises(ValueError, match="exactly"):
        stores.reconstruct(manifest, {})
    assert not stores.inspect(b)["fragments"][0]["used_in_reconstruction"]
    assert stores.reconstruct(manifest, {f.id: stores.get(b, f)}) == b"cipher"
    assert stores.inspect(a)["fragments"][0]["integrity"] == "failed"
    assert stores.inspect(a)["fragments"][0]["last_failure"] == "integrity"
    assert stores.inspect(c)["fragments"][0]["retrieval_attempts"] == 2


def test_capacity_integrity_and_idempotent_replica_writes():
    stores = StorageNetwork(["a", "b"], capacity_bytes=4)
    manifest = stores.plan("msg", b"abcdXY", Random(5), 4, 2)
    first, second = manifest.fragments
    stores.put("a", first, b"abcd")
    stores.put("a", first, b"abcd")
    with pytest.raises(ValueError, match="capacity"):
        stores.put("a", second, b"XY")
    with pytest.raises(ValueError, match="SHA-256"):
        stores.put("a", first, b"BAD!")
    assert stores.get("a", first) == b"abcd" and stores.nodes["a"].used_bytes == 4
    assert second.id not in stores.nodes["a"].fragments
    stores.put("b", second, b"XY")
    parts = {first.id: b"abcd", second.id: b"XY"}
    tampered = manifest.model_copy(update={"digest": "0" * 64})
    with pytest.raises(ValueError, match="Reconstructed ciphertext"):
        stores.reconstruct(tampered, parts)
    with pytest.raises(ValueError, match="SHA-256"):
        stores.reconstruct(manifest, {**parts, first.id: b"wxyz"})
    with pytest.raises(ValidationError, match="contiguous"):
        MessageManifest.model_validate({**manifest.model_dump(), "fragments": [second, first]})
    assert not any(p["used_in_reconstruction"] for p in stores.inspect("a")["fragments"])


def test_empty_payload_different_chunk_sizes_and_invalid_placement():
    stores = StorageNetwork(["a"])
    m = stores.plan("id", b"", Random(1), 7, 1)
    (f,) = m.fragments
    stores.put("a", f, b"")
    assert stores.reconstruct(m, {f.id: stores.get("a", f)}) == b""
    for size, replicas in [(0, 1), (4, 0), (4, 2)]:
        with pytest.raises(ValueError):
            stores.plan("id", b"stuff", Random(1), size, replicas)
    with pytest.raises(ValueError, match="assigned"):
        stores.get("non-member", f)


def test_replanning_chunk_boundaries_cannot_overwrite_an_earlier_manifest():
    stores = StorageNetwork(["a", "b"])
    data = b"same encrypted message"
    original = stores.plan("id", data, Random(1), 3, 2)
    revised = stores.plan("id", data, Random(1), 5, 2)
    assert original.id != revised.id
    for manifest in (original, revised):
        for f in manifest.fragments:
            stores.put("a", f, data[f.offset : f.offset + f.size])
    for manifest in (original, revised):
        assert (
            stores.reconstruct(manifest, {f.id: stores.get("a", f) for f in manifest.fragments}) == data
        )
    f = original.fragments[0]
    forged = f.model_copy(update={"digest": sha256(b"xyz").hexdigest()})
    with pytest.raises(ValueError, match="conflicts"):
        stores.put("a", forged, b"xyz")

import base64
import json
from hashlib import sha256
from pathlib import Path

import pytest
from Crypto.PublicKey import ECC

from app.sphinx import PARAMS, WIRE_BYTES, SphinxNetwork
from app.sphinx_ref.client import PFdecode, receive_forward
from app.sphinx_ref.node import sphinx_process
from app.sphinx_ref.wire import SphinxException, decode, encode


def test_python2_reference_datagram_matches_every_intermediate_wire_packet_and_tag():
    reference = json.loads(Path(__file__).with_name("test_sphinx_reference.json").read_text())
    packet = base64.b64decode(reference["packet"], validate=True)
    names = [b"in", b"m1", b"m2", b"m3", b"out"]
    for index, scalar in enumerate([137, 253, 397, 439, 577]):
        assert len(packet) == WIRE_BYTES
        header, body = decode(packet)
        tag, info, inner = sphinx_process(PARAMS, scalar, header, body)
        assert tag == base64.b64decode(reference["tags"][index])
        packet = encode(inner)
        assert sha256(packet).hexdigest() == reference["states"][index]
        command = PFdecode(PARAMS, info)
        if index < len(names) - 1:
            assert command == [
                b"\xf0",
                [[b"127.0.0.1", 7001 + index], False, None, (index + 1) / 8, names[index + 1]],
            ]
        else:
            assert command == [b"\xf1"]
            assert receive_forward(PARAMS, inner[1]) == [
                [b"127.0.0.1", 7004, b"out"],
                b"interoperability",
            ]


def test_cross_runtime_reference_recreated_byte_for_byte(monkeypatch):
    # Entropy controls only the reproducible test vector. Live construction always uses the OS.
    from app.sphinx_ref import client
    from app.sphinx_ref.wire import Group

    reference = json.loads(Path(__file__).with_name("test_sphinx_build_reference.json").read_text())
    monkeypatch.setattr(Group, "gensecret", lambda self: 587)
    monkeypatch.setattr(client, "urandom", lambda size: b"\x5a" * size)
    names = [b"in", b"m1", b"m2", b"m3", b"out"]
    commands = [
        client.Nenc(((b"127.0.0.1", 7000 + i), False, None, i / 8, name))
        for i, name in enumerate(names)
    ]
    keys = [ECC.construct(curve="P-224", d=scalar).pointQ for scalar in (137, 253, 397, 439, 577)]
    packet = encode(
        client.create_forward_message(
            PARAMS, commands, keys, (b"127.0.0.1", 7004, b"out"), b"interoperability"
        )
    )
    assert packet == base64.b64decode(reference["packet"])


def test_node_scope_and_rejections_do_not_poison_replay_state():
    route = ["ingress", "one", "two", "three", "egress"]
    network = SphinxNetwork(route)
    packet = network.build(route, [0, 7, 55, 1502], b"application")
    assert packet != network.build(route, [0, 7, 55, 1502], b"application")
    assert b"application" not in packet and b"egress" not in packet
    header, body = decode(packet)
    header[1] = bytes([header[1][0] ^ 1]) + header[1][1:]
    with pytest.raises(SphinxException, match="MAC"):
        network.peel(route[0], encode((header, body)))
    with pytest.raises(SphinxException, match="MAC"):
        network.peel(route[1], packet)
    for index, name in enumerate(route):
        assert len(packet) == WIRE_BYTES and network.replay_count(name) == 0
        result = network.peel(name, packet)
        assert network.replay_count(name) == 1
        with pytest.raises(SphinxException, match="replay"):
            network.peel(name, packet)
        if index < 4:
            assert result.next_id == route[index + 1]
            assert result.delay_ms == [0, 7, 55, 1502][index]
            assert result.payload is None and result.packet is not None
            packet = result.packet
        else:
            assert result.payload == b"application" and result.packet is None and result.next_id is None


def test_bounds_and_drop_command():
    network = SphinxNetwork(["p", "m"])
    for route, delays, payload in [
        ([], [], b""),
        (["p"], [3], b""),
        (["p"], [], b"a" * 1024),
        (["p", "x"], [2], b""),
        (["p", "m"], [-1], b""),
    ]:
        with pytest.raises(ValueError):
            network.build(route, delays, payload)
    packet = network.build(["p", "m", "p"], [7, 8, 0], b"noise", drop_at=1)
    first = network.peel("p", packet)
    assert first.drop is False and first.packet is not None
    second = network.peel("m", first.packet)
    assert second.drop and second.next_id == "p"

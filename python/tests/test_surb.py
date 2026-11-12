import pytest

from app.sphinx import MAX_REPLY_BYTES, WIRE_BYTES, ReplyBlock, SphinxNetwork
from app.sphinx_ref.wire import SphinxException, decode, encode

ROUTE = ["disclosed-first", "hidden-mix-two", "hidden-mix-three", "hidden-gateway"]


def test_serialised_surb_routes_and_unwraps_once_without_disclosing_destination():
    network = SphinxNetwork(ROUTE)
    block, private = network.create_surb(ROUTE, [12, 8, 24], destination="private-device")
    wire = block.to_bytes()
    assert ROUTE[0].encode() in wire
    for secret in [*ROUTE[1:], "private-device"]:
        assert secret.encode() not in wire
    assert private.reply_id not in wire
    copy = ReplyBlock.from_bytes(wire)
    payload = b"fragment" + b"\xff" * (MAX_REPLY_BYTES - 8)
    with pytest.raises(ValueError, match="capacity"):
        network.use_surb(copy, payload + b"x")
    packet = network.use_surb(copy, payload)
    with pytest.raises(SphinxException, match="spent"):
        network.use_surb(ReplyBlock.from_bytes(wire), b"another reply")
    for i, name in enumerate(ROUTE):
        assert len(packet) == WIRE_BYTES and payload not in packet
        hop = network.peel(name, packet)
        with pytest.raises(SphinxException, match="replay"):
            network.peel(name, packet)
        if i < len(ROUTE) - 1:
            assert hop.reply_id is hop.reply_destination is None
            assert hop.next_id == ROUTE[i + 1]
            assert hop.delay_ms == [12, 8, 24][i]
            packet = hop.packet
    assert hop.reply_destination == "private-device" and hop.reply_id == private.reply_id
    assert hop.payload != payload
    with pytest.raises(SphinxException, match="Unknown"):
        private.open(b"unrelated", hop.payload)
    assert private.open(hop.reply_id, hop.payload) == payload
    with pytest.raises(SphinxException, match="spent"):
        private.open(hop.reply_id, hop.payload)


def test_tampered_body_wrong_creator_and_fresh_network_cannot_open_reply():
    network = SphinxNetwork(ROUTE)
    block, private = network.create_surb(ROUTE, [0, 1, 0])
    other, other_secret = network.create_surb(ROUTE, [0, 1, 0])
    assert block.header != other.header and private.reply_id != other_secret.reply_id
    packet = network.use_surb(block, b"payload")
    with pytest.raises(SphinxException):
        SphinxNetwork(ROUTE).peel(ROUTE[0], packet)
    header, payload = decode(packet)
    packet = encode((header, bytes([payload[0] ^ 1]) + payload[1:]))
    for node in ROUTE:
        hop = network.peel(node, packet)
        packet = hop.packet
    with pytest.raises(SphinxException, match="Modified"):
        private.open(hop.reply_id, hop.payload)
    with pytest.raises(SphinxException, match="Unknown"):
        other_secret.open(hop.reply_id, hop.payload)


@pytest.mark.parametrize("invalid", [b"invalid", encode(["a", b"bad", b"key"]), encode([1, 2, 3])])
def test_malformed_serialised_block_is_rejected(invalid):
    with pytest.raises(SphinxException, match="Malformed"):
        ReplyBlock.from_bytes(invalid)


def test_reply_header_rejects_invalid_point_fields_and_noncanonical_encoding():
    network = SphinxNetwork(ROUTE)
    block, _ = network.create_surb(ROUTE, [0, 0, 0])
    point, routing, mac = decode(block.header)
    for bad_header in (
        encode(([], routing, mac)),
        encode((point, routing[:-1], mac)),
        encode((point, routing[1:], mac + b"x")),
        b"\xff" * len(block.header),
    ):
        with pytest.raises(SphinxException, match="Malformed"):
            ReplyBlock.from_bytes(encode((ROUTE[0], bad_header, block.payload_key)))
    for bad_wire in (
        b"",
        block.to_bytes() + b"extra",
        bytes(2000),
        encode(("", block.header, block.payload_key)),
    ):
        with pytest.raises(SphinxException, match="Malformed"):
            ReplyBlock.from_bytes(bad_wire)


def test_ill_framed_body_and_authenticated_invalid_padding_do_not_accept_empty_reply():
    from app.sphinx import PARAMS

    net = SphinxNetwork(["mix"])
    block, secret = net.create_surb(["mix"], [])
    for body in (None, b"", bytes(PARAMS.m - 1)):
        with pytest.raises(SphinxException, match="length"):
            secret.open(secret.reply_id, body)
    # A block holder could craft a correctly MACed body with no end marker.
    padded = bytes(PARAMS.m - PARAMS.k)
    encrypted = PARAMS.pi(block.payload_key, PARAMS.mu(block.payload_key, padded) + padded)
    hop = net.peel("mix", encode((decode(block.header), encrypted)))
    with pytest.raises(SphinxException, match="padding"):
        secret.open(hop.reply_id, hop.payload)
    fresh, fresh_secret = net.create_surb(["mix"], [])
    valid = net.peel("mix", net.use_surb(fresh, b""))
    assert fresh_secret.open(valid.reply_id, valid.payload) == b""

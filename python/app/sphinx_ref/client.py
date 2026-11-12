# Copyright 2011 Ian Goldberg
# Copyright 2016 George Danezis (UCL InfoSec Group)
#
# This file is part of Sphinx.
#
# Sphinx is free software: you can redistribute it and/or modify
# it under the terms of version 3 of the GNU Lesser General Public
# License as published by the Free Software Foundation.
#
# Sphinx is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with Sphinx.  If not, see
# <http://www.gnu.org/licenses/>.


# Adapted for the simulator in 2026: forward packets only, current crypto backend.
from collections import namedtuple
from os import urandom
from struct import pack

from .wire import SphinxException, decode, encode

# FLAGS

#: Routing flag indicating message is to be relayed.
Relay_flag = b"\xf0"

#: Routing flag indicating message is to be delivered.
Dest_flag = b"\xf1"

# Padding/unpadding of message bodies: a 0 bit, followed by as many 1
# bits as it takes to fill it up

header_record = namedtuple("header_record", ["alpha", "s", "b", "aes"])


def pad_body(msgtotalsize, body):
    """Pad the Sphinx message body."""
    body = body + b"\x7f"
    body = body + (b"\xff" * (msgtotalsize - len(body)))

    if (msgtotalsize - len(body)) < 0:
        raise SphinxException("Insufficient space for body")

    return body


def unpad_body(body):
    """Unpad a Sphinx message body."""
    body = bytes(body)
    l = len(body) - 1
    x_marker = b"\x7f"[0]
    f_marker = b"\xff"[0]
    while body[l] == f_marker and l > 0:
        l -= 1

    if body[l] == x_marker:
        ret = body[:l]
    else:
        ret = b""

    return ret


# Prefix-free encoding/decoding of node names and destinations


# Sphinx nodes
def Nenc(idnum):
    """The encoding of mix names."""
    return Route_pack((Relay_flag, idnum))


def Route_pack(info):
    return encode(info)


# Decode the prefix-free encoding.  Return the type, value, and the
# remainder of the input string
def PFdecode(param, packed):
    """Decoder of prefix free encoder for commands received by mix or clients."""
    assert type(packed) is bytes
    return decode(packed)


def create_header(params, nodelist, keys, dest):
    """Internal function, creating a Sphinx header, given parameters, a node list (path),
    a pki mapping node names to keys, a destination, and a message identifier."""

    node_meta = [pack("b", len(n)) + n for n in nodelist]

    p = params
    nu = len(nodelist)
    max_len = p.max_len

    group = p.group
    x = group.gensecret()

    blind_factor = x
    asbtuples = []

    for k in keys:
        alpha = group.expon(group.g, blind_factor)
        s = group.expon(k, blind_factor)
        aes_s = p.get_aes_key(s)

        b = p.hb(alpha, aes_s)
        blind_factor = (blind_factor * b) % group.order

        hr = header_record(alpha, s, b, aes_s)
        asbtuples.append(hr)

    # Compute the filler strings
    phi = b""
    min_len = max_len - 32
    for i in range(1, nu):
        plain = phi + (b"\x00" * (p.k + len(node_meta[i])))
        phi = p.xor_rho(p.hrho(asbtuples[i - 1].aes), (b"\x00" * min_len) + plain)
        phi = phi[min_len:]

        min_len -= len(node_meta[i]) + p.k

    assert len(phi) == sum(map(len, node_meta[1:])) + (nu - 1) * p.k

    # Compute the (beta, gamma) tuples
    # The os.urandom used to be a string of 0x00 bytes, but that's wrong

    final_routing = pack("b", len(dest)) + dest

    len_meta = sum(map(len, node_meta[1:]))
    random_pad_len = (max_len - 32) - len_meta - (nu - 1) * p.k - len(final_routing)

    if random_pad_len < 0:
        raise SphinxException("Insufficient space routing info")

    beta = final_routing + urandom(random_pad_len)
    beta = p.xor_rho(p.hrho(asbtuples[nu - 1].aes), beta) + phi

    gamma = p.mu(p.hmu(asbtuples[nu - 1].aes), beta)

    for i in range(nu - 2, -1, -1):
        node_id = node_meta[i + 1]

        plain_beta_len = (max_len - 32) - p.k - len(node_id)

        plain = node_id + gamma + beta[:plain_beta_len]

        beta = p.xor_rho(p.hrho(asbtuples[i].aes), plain)
        gamma = p.mu(p.hmu(asbtuples[i].aes), beta)

    return (asbtuples[0].alpha, beta, gamma), [x.aes for x in asbtuples]


def create_forward_message(params, nodelist, keys, dest, msg):
    """Creates a forward Sphix message, ready to be processed by a first mix.

    It takes as parameters a node list of mix information, that will be provided to each mix, forming the path of the message;
    a list of public keys of all intermediate mixes; a destination and a message (byte arrays)."""

    p = params
    nu = len(nodelist)
    assert len(dest) < 128 and len(dest) > 0
    assert p.k + 1 + len(dest) + len(msg) < p.m

    # Compute the header and the secrets

    final = Route_pack((Dest_flag,))
    header, secrets = create_header(params, nodelist, keys, final)

    body = pad_body(p.m, (b"\x00" * p.k) + encode((dest, msg)))

    # Compute the delta values
    delta = p.pi(p.hpi(secrets[nu - 1]), body)
    for i in range(nu - 2, -1, -1):
        delta = p.pi(p.hpi(secrets[i]), delta)

    return header, delta


def receive_forward(params, delta):
    """Decodes the body of a forward message."""

    if delta[: params.k] != b"\x00" * params.k:
        raise SphinxException("Modified Body")

    delta = unpad_body(delta[params.k :])
    return decode(delta)

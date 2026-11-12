#!/usr/bin/env python

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

from os import urandom
from struct import unpack
from binascii import hexlify

from hmac import compare_digest

from .wire import SphinxException


# Adapted in 2026: constant-time header MAC comparison.
# Core Process function -- devoid of any chrome
def sphinx_process(params, secret, header, delta):
    """The heart of a Sphinx server, that processes incoming messages.
    It takes a set of parameters, the secret of the server,
    and an incoming message header and body.

    """
    p = params
    group = p.group
    alpha, beta, gamma = header

    # Check that alpha is in the group
    if not group.in_group(alpha):
        raise SphinxException("Alpha not in Group.")

    # Compute the shared secret
    s = group.expon(alpha, secret)
    aes_s = p.get_aes_key(s)

    assert len(beta) == p.max_len - 32
    if not compare_digest(gamma, p.mu(p.hmu(aes_s), beta)):
        raise SphinxException("MAC mismatch.")

    beta_pad = beta + (b"\x00" * (2 * p.max_len))
    B = p.xor_rho(p.hrho(aes_s), beta_pad)

    length = B[0]
    routing = B[1 : 1 + length]
    rest = B[1 + length :]

    tag = p.htau(aes_s)
    b = p.hb(alpha, aes_s)
    alpha = group.expon(alpha, b)
    gamma = rest[: p.k]
    beta = rest[p.k : p.k + (p.max_len - 32)]
    delta = p.pii(p.hpi(aes_s), delta)

    ret = (tag, routing, ((alpha, beta, gamma), delta))
    return ret

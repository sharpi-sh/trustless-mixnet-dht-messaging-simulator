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
import hmac
from hashlib import sha256

from Crypto.Cipher import AES

from .wire import Group, SphinxException


class SphinxParams:
    def __init__(self, group=None, header_len=192, body_len=1024):

        self.max_len = header_len
        self.m = body_len
        self.k = 16

        self.group = group
        if not group:
            self.group = Group()

    # The LIONESS PRP

    def aes_ctr(self, k, m, iv=b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"):
        k = bytes(k)
        m = bytes(m)
        assert type(k) is bytes and type(m) is bytes
        c = AES.new(k, AES.MODE_CTR, nonce=b"", initial_value=iv).encrypt(m)
        return bytes(c)

    def lioness_enc(self, key, message):
        assert len(key) == self.k
        assert len(message) >= self.k * 2

        # Round 1
        k1 = self.hash(message[self.k :] + key + b"1")[: self.k]
        c = self.aes_ctr(key, message[: self.k], iv=k1)
        r1 = c + message[self.k :]

        # Round 2
        c = self.aes_ctr(key, r1[self.k :], iv=r1[: self.k])
        r2 = r1[: self.k] + c

        # Round 3
        k3 = self.hash(r2[self.k :] + key + b"3")[: self.k]
        c = self.aes_ctr(key, r2[: self.k], iv=k3)
        r3 = c + r2[self.k :]

        # Round 4
        c = self.aes_ctr(key, r3[self.k :], r3[: self.k])
        r4 = r3[: self.k] + c

        return r4

    def lioness_dec(self, key, message):
        assert len(key) == self.k
        assert len(message) >= self.k * 2

        r4 = message
        r4_short, r4_long = r4[: self.k], r4[self.k :]

        # Round 4
        r3_long = self.aes_ctr(key, r4_long, iv=r4_short)
        r3_short = r4_short

        # Round 3
        k2 = self.hash(r3_long + key + b"3")[: self.k]
        r2_short = self.aes_ctr(key, r3_short, iv=k2)
        r2_long = r3_long

        # Round 2
        r1_long = self.aes_ctr(key, r2_long, iv=r2_short)
        r1_short = r2_short

        # Round 1
        k0 = self.hash(r1_long + key + b"1")[: self.k]
        c = self.aes_ctr(key, r1_short, iv=k0)
        r0 = c + r1_long

        return r0

    def xor_rho(self, key, plain):
        assert len(key) == self.k
        return self.aes_ctr(key, plain)

    # The HMAC; key is of length k, output is of length k
    def mu(self, key, data):
        mac = hmac.new(key, data, digestmod=sha256).digest()[: self.k]
        return mac

    # The PRP; key is of length k, data is of length m
    def pi(self, key, data):
        assert len(key) == self.k
        if len(data) != self.m:
            raise SphinxException("Invalid body length")

        return self.lioness_enc(key, data)

    # The inverse PRP; key is of length k, data is of length m
    def pii(self, key, data):
        assert len(key) == self.k
        if len(data) != self.m:
            raise SphinxException("Invalid body length")

        return self.lioness_dec(key, data)

    # The various hashes

    def hash(self, data):
        return sha256(data).digest()

    def get_aes_key(self, s):
        group = self.group
        return self.hash(b"aes_key:" + group.printable(s))[: self.k]

    def derive_key(self, k, flavor):
        iv = flavor
        m = b"\x00" * self.k
        K = AES.new(k, AES.MODE_CTR, nonce=b"", initial_value=iv).encrypt(m)
        return K

    def hb(self, alpha, k):
        "Compute a hash of alpha and s to use as a blinding factor"
        K = self.derive_key(k, b"hbhbhbhbhbhbhbhb")
        return self.group.makeexp(K)

    def hrho(self, k):
        "Compute a hash of s to use as a key for the PRG rho"
        K = self.derive_key(k, b"hrhohrhohrhohrho")
        return K

    def hmu(self, k):
        "Compute a hash of s to use as a key for the HMAC mu"
        K = self.derive_key(k, b"hmu:hmu:hmu:hmu:")
        return K

    def hpi(self, k):
        "Compute a hash of s to use as a key for the PRP pi"
        K = self.derive_key(k, b"hpi:hpi:hpi:hpi:")
        return K

    def htau(self, k):
        "Compute a hash of s to use to see if we've seen s before"
        K = self.derive_key(k, b"htauhtauhtauhtau")
        return K

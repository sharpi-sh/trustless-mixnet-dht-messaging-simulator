# Sphinx forward-packet source

The forward-packet construction, one-hop processing and parameter functions in
`client.py`, `node.py` and `params.py` derive from UCL sphinxmix 0.0.6,
copyright 2011 Ian Goldberg and 2016 George Danezis (UCL InfoSec Group).
The upstream files and README specify LGPL version 3. The licence and
associated GPL text accompany this source. [Pinned source](https://github.com/UCL-InfoSec/sphinx/tree/25cdf24bf0233b3fb1502a80d3f64f91c71ebe3e)

This project maintains the Python 3 port. It replaces petlib's OpenSSL
bindings with PyCryptodome and current MessagePack, uses constant-time header
MAC comparison, preserves the binary route flags used by the Python 2
prototype and omits SURBs. The algorithm uses NIST P-224, AES-128-CTR, the
UCL LIONESS construction, HMAC-SHA-256 truncated to 16 bytes and a per-hop
16-byte replay tag. The application envelope supplies separate authenticated
content encryption. [2017 Loopix implementation](https://github.com/UCL-InfoSec/loopix/tree/440db95fdd2bcb28d76aca1b86f072715ef7005a)

The simulator uses local node identifiers within the Loopix routing commands.
The terminal Sphinx hop delivers opaque application bytes to the simulated
egress-to-storage bridge. Upstream client delivery included another recipient
Sphinx layer after the egress provider.

The compatibility fixture uses unmodified sphinxmix 0.0.6 on Python 2.7.15,
petlib 0.0.45, OpenSSL 1.1.1w and MessagePack 0.6.2. It records the serialised
input, SHA-256 of the serialised output at every hop, and all replay tags.
It uses test-only node scalars 137, 253, 397, 439 and 577. The original PyPI
archive SHA-256 is
`5655d079c1130343eecd20b254971a6f449b425253322f050a903d62947e83c9`.

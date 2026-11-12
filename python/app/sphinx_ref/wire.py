"""P-224 operations and petlib-compatible MessagePack encoding."""

from Crypto.PublicKey import ECC
from Crypto.PublicKey.ECC import EccPoint
import msgpack


class SphinxException(ValueError):
    """Invalid Sphinx packet, route or replay."""


# SEC 2, secp224r1 subgroup order.
ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFF16A2E0B8F03E13DD29455C5C2A3D


def point_bytes(point, compressed):
    key = ECC.construct(curve="P-224", point_x=point.x, point_y=point.y)
    return key.export_key(format="SEC1", compress=compressed)


class Group:
    order = ORDER
    g = ECC.construct(curve="P-224", d=1).pointQ

    def gensecret(self):
        return int(ECC.generate(curve="P-224").d)

    def expon(self, base, scalar):
        return base * scalar

    def makeexp(self, binary):
        return int.from_bytes(binary, "big") % self.order

    def in_group(self, point):
        return (
            isinstance(point, EccPoint)
            and point.curve == "NIST P-224"
            and not point.is_point_at_infinity()
        )

    def printable(self, point):
        return point_bytes(point, False)


def encode(value):
    def extension(point):
        if not isinstance(point, EccPoint):
            raise TypeError("unsupported extension")
        # Original petlib used msgpack 0.x defaults inside the extension.
        data = msgpack.packb((713, point_bytes(point, True)), use_bin_type=False)
        return msgpack.ExtType(2, data)

    return msgpack.packb(value, default=extension, use_bin_type=True)


def decode(data):
    def extension(code, value):
        if code != 2:
            raise ValueError("unsupported extension")
        nid, compressed = msgpack.unpackb(value, raw=True)
        if nid != 713 or not isinstance(compressed, bytes) or len(compressed) != 29:
            raise ValueError("invalid point")
        return ECC.import_key(compressed, curve_name="P-224").pointQ

    return msgpack.unpackb(data, raw=False, ext_hook=extension)

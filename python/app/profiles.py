"""Public references and simulator boundaries served with each generated network."""

from typing import Any

from .config import Config, Model


class Profile(Model):
    id: str
    name: str
    year: int | None = None
    reference: str | None = None
    parameters: dict[str, Any]
    operations: list[str]
    boundaries: list[str]


def _channel_profiles(c: Config, all_channels: bool) -> list[Profile]:
    selected = (
        {"tor", "shadowsocks", "direct"} if all_channels else {c.sender_channel, c.recipient_channel}
    )
    channels = []
    if "tor" in selected:
        channels.append(
            Profile(
                id="tor-abstraction",
                name="Tor abstraction",
                reference="https://community.torproject.org/relay/types-of-relays/",
                parameters={"ingress": "Guard IP", "egress": "Distinct exit IP"},
                operations=["Device to guard", "Exit to destination"],
                boundaries=[
                    "The guard and exit have distinct simulated addresses. Circuit construction, internal relays and onion encryption are outside the model."
                ],
            )
        )
    if "shadowsocks" in selected:
        channels.append(
            Profile(
                id="shadowsocks-abstraction",
                name="Outline Shadowsocks proxy abstraction",
                reference="https://github.com/OutlineFoundation/tunnel-server",
                parameters={"ingress": "Proxy server IP", "egress": "Same proxy server IP"},
                operations=["Device to proxy", "Proxy to destination"],
                boundaries=[
                    "One simulated proxy can observe its client and destination. Wire encryption, protocol negotiation and actual proxy traffic are outside the model."
                ],
            )
        )
    if "direct" in selected:
        channels.append(
            Profile(
                id="direct-connection",
                name="Direct connection",
                parameters={"ingress": "Device IP", "egress": "Same device IP"},
                operations=["Local interface handoff", "Device to destination"],
                boundaries=[
                    "The interface shares the device’s simulated IP. Downstream peers can observe that address."
                ],
            )
        )
    return channels


def profiles(c: Config, *, all_channels: bool = False) -> list[Profile]:
    return [
        Profile(
            id="loopix-usenix-2017",
            name="Mixnet — Loopix (USENIX 2017)",
            year=2017,
            reference="https://www.usenix.org/system/files/conference/usenixsecurity17/sec17-piotrowska.pdf",
            parameters={
                "layers": 3,
                "mu_per_second": c.mu_per_second,
                "payload_rate_per_minute": c.payload_rate_per_minute,
                "client_loop_rate_per_minute": c.client_loop_rate_per_minute,
                "drop_cover_rate_per_minute": c.drop_cover_rate_per_minute,
                "mix_loop_rate_per_minute": c.mix_loop_rate_per_minute,
                "poll_interval_ms": c.polling_interval_ms,
                "poll_slots": c.poll_batch,
                "sphinx": "UCL sphinxmix 0.0.6 forward packet, NIST P-224",
            },
            operations=[
                "Uniform per-layer sampling",
                "Sphinx integrity, replay and forwarding",
                "Independent exponential per-hop delays",
                "Poisson payload, loop and drop streams",
            ],
            boundaries=[
                "Local logical datagrams and millisecond clock.",
                "Experimental egress adapter hands ciphertext to replicated storage. The egress is the final Sphinx hop for application packets.",
                "Provider association uses an ephemeral local identifier. Poll suppression is a user intervention.",
            ],
        ),
        Profile(
            id="kademlia-2002",
            name="DHT — Kademlia (2002)",
            year=2002,
            reference="https://pdos.csail.mit.edu/~petar/papers/maymounkov-kademlia-lncs.pdf",
            parameters={
                "id_bits": 160,
                "k": 20,
                "alpha": 3,
                "nodes": c.dht_nodes,
                "rpc_timeout_ms": c.rpc_timeout_ms,
            },
            operations=["XOR lookup", "PING", "STORE", "FIND_NODE", "FIND_VALUE"],
            boundaries=[
                "Simulated RPC transport and clock. Mailbox records are an experimental application format."
            ],
        ),
        *_channel_profiles(c, all_channels),
        Profile(
            id="anonymous-retrieval",
            name="Anonymous retrieval — Nym-inspired Sphinx reply blocks",
            year=2021,
            reference="https://nymtech.net/nym-whitepaper.pdf#page=15",
            parameters={"mix_layers": 3, "reply_block_uses": 1},
            operations=[
                "Send a manifest or fragment request through the mixnet",
                "Supply a precomputed, independently selected return route",
                "Receive the encrypted response through single-use reply blocks",
            ],
            boundaries=[
                "Local retrieval protocol using the simulator’s Sphinx packet format. "
                "Live Nym compatibility and network anonymity are outside the model.",
                "A storage service can correlate repeated identifiers and request timing. "
                "The simulator event trace can correlate both legs of an exchange.",
            ],
        ),
        Profile(
            id="replicated-storage",
            name="Replicated chunk-storage model",
            parameters={"replicas": c.replicas, "chunk_bytes": c.chunk_bytes},
            operations=["Ciphertext chunk replication", "Hash-checked reconstruction"],
            boundaries=[
                "All distinct chunks are required. Storage operators can correlate sizes, timing and repeated identifiers."
            ],
        ),
        Profile(
            id="device",
            name="Participant device",
            reference="https://www.rfc-editor.org/rfc/rfc8032.html#section-5.1",
            parameters={
                "encryption": "X25519 / HKDF-SHA-256 / AES-256-GCM",
                "signature": "Ed25519",
                "verification_key_source": "Per-run simulated directory pin for the expected sender ID",
            },
            operations=[
                "Sign message context, text and reply key",
                "Encrypt signed bundle for recipient",
                "Decrypt and verify against the expected sender pin before accepting",
            ],
            boundaries=[
                "Sender verification relies on the simulator's trusted binding between participant ID and signing key.",
                "External identity assurance, whole-system forward secrecy and anonymity remain outside the model.",
            ],
        ),
    ]

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


def profiles(c: Config) -> list[Profile]:
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
        Profile(
            id="tor-abstraction",
            name="Tor abstraction",
            parameters={},
            operations=["Local entry and egress"],
            boundaries=[
                "One independent boundary per device; circuits and relays are outside this model."
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

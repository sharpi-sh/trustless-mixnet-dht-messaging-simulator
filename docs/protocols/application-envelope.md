# Application encryption and visibility

Each device generates its own X25519 private key from operating-system entropy. A simulated public webpage provides a recipient’s public key and provider address. Sending requires neither prior contact nor a shared secret. The deterministic seed reproduces simulation decisions. Keys, authenticated ciphertext and ciphertext-derived hashes vary between runs.

The device uses an ephemeral X25519 exchange, HKDF-SHA-256 and AES-256-GCM. Bundle and manifest envelopes use separate purpose labels. The sender’s reply public key sits inside the encrypted bundle. The receiving device records that key only after reconstruction and authenticated decryption, then uses it to encrypt the reply. Anyone can supply a reply key. The simulator cannot verify ownership or authenticate the sender.

| Actor | Locally visible data |
|---|---|
| Sender | Its staged plaintext, outgoing content, published recipient contact |
| Mix | One authenticated forwarding command, local timing, packet and replay state |
| Egress adapter | Opaque message ciphertext, recipient manifest-wrapping public key and storage handoff |
| Kademlia peer | Opaque lookup key, encrypted manifest, sizes, contacts and RPC timing |
| Vault | Encrypted chunks, hashes, replica placement, size and retrieval activity |
| Recipient | Plaintext and unverified reply key after successful authenticated decryption |

Application message IDs are deduplicated at the recipient. Sphinx replay tags are checked separately by each processing node. The local composition, mailbox metadata, provider correlation, key retention, forward secrecy and adversary capabilities require further protocol design. The inert observer has no access to these records.

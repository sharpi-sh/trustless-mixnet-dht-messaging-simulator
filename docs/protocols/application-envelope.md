# Application encryption and sender verification

Each simulated device generates two independent key pairs from operating-system entropy. Its Ed25519 private key signs outgoing messages. Its X25519 private key opens incoming envelopes. The simulation publishes each participant’s public contact and pins their verification key to their participant ID for that run. Alice can obtain Bob’s encryption key and provider address from the simulated public webpage before they have exchanged any messages. Reset generates fresh keys even with the same simulation seed. [Ed25519, RFC 8032 §5.1](https://www.rfc-editor.org/rfc/rfc8032.html#section-5.1) · [X25519, RFC 7748 §6.1](https://www.rfc-editor.org/rfc/rfc7748.html#section-6.1)

Alice signs the message text and its context, including the sender and recipient IDs, message and conversation IDs, exchange number, direction, Bob’s X25519 recipient public key and the X25519 public key she designates for replies. Her device encrypts the signed bundle to Bob using a fresh ephemeral X25519 key, HKDF-SHA-256 and AES-256-GCM. Message bundles and manifests have separate encryption purpose labels.

Inside the encrypted envelope, the signed format begins with the four bytes `MXSB` and version byte `0x02`, followed by the 32-byte Ed25519 public key, a 64-byte signature and the signed MessagePack array. In order, the array contains the domain label `mixnet-laboratory/device-message/Ed25519/v2`, message ID, conversation ID, exchange number, direction, sender ID, recipient ID, recipient encryption key and encoded inner bundle. The inner bundle carries its version, message ID, text and reply key.

Bob reconstructs and decrypts the bundle. He compares the enclosed signing key with the expected sender’s directory pin, verifies the signature over the supplied array, then checks its contents against the expected delivery context. Only then does his device accept the text and learn the reply key. Bob signs his reply using his own Ed25519 private key and encrypts it to Alice’s verified reply address. A forged signature, a substituted reply key or a bundle presented in the wrong conversation fails verification.

The device log identifies the verified signer and the SHA-256 fingerprint of their Ed25519 public key. The separate reply-key fingerprint identifies the X25519 encryption key.

The binding between the signing public key and participant ID is a trusted input supplied by the simulator. Success attributes the message to the holder of that run’s pinned private signing key. The simulator provides no external assurance about a person operating the device. Compromise of a device or its trusted directory is outside this model.

| Actor | Locally visible data |
|---|---|
| Sender | Its staged plaintext, outgoing content and published recipient contact |
| Mix | One authenticated forwarding command, local timing, packet and replay state |
| Egress adapter | Opaque message ciphertext, recipient manifest-wrapping public key and storage handoff |
| Kademlia peer | Opaque lookup key, encrypted manifest, sizes, contacts and RPC timing |
| Vault | Encrypted chunks, hashes, replica placement, size and retrieval activity |
| Recipient | Accepted plaintext and the sender-designated reply key after decryption and signature verification |

The recipient deduplicates accepted application message IDs. Each Sphinx processing node separately checks packet replay tags. Key retention, provider correlation, access patterns and whole-system forward secrecy remain outside the security assurance. The inert observer has no access to device records.

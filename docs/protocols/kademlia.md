# DHT and storage

Each Kademlia peer has a random 160-bit identifier, local routing buckets and a local record store. Requests and replies travel separately over the simulator’s paths. Timeouts affect the requesting peer’s observation. The inspector displays each peer’s known contacts, ordered buckets and in-progress searches. Simulated connectivity between two DHT addresses alone does not create a routing-table entry.

The DHT uses integer XOR distance, a bucket capacity of 20 and three concurrent discovery requests. Each joining peer begins with one bootstrap contact. The logical clock drives timeout, refresh, expiry and republishing. For a small demonstration network, the closest set can contain fewer than 20 responsive nodes.

The application publishes an encrypted manifest under an opaque lookup key. Vault nodes separately store replicas of encrypted chunks and expose hashes, lengths and placement results. A reader needs one verified copy of every chunk. It checks the reconstructed ciphertext hash before device decryption. Replication and Kademlia record replication are independent.

The simulator can display the entire path for instructional inspection. Individual protocol actors retain their own observations. Sizes, lookup-key reuse, addresses, timing and placement remain observable within the stated boundaries. The simulator does not establish resistance to correlation.

[Kademlia paper, 2002](https://pdos.csail.mit.edu/~petar/papers/maymounkov-kademlia-lncs.pdf)

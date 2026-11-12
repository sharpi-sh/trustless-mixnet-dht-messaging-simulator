# DHT and storage

Each Kademlia peer has a random 160-bit identifier, local routing buckets and a local record store. Requests and replies travel separately over the simulator’s paths. Timeouts affect the requesting peer’s observation. The inspector displays each peer’s known contacts, ordered buckets and in-progress searches. Simulated connectivity between two DHT addresses alone does not create a routing-table entry.

The DHT uses integer XOR distance, a bucket capacity of 20 and three concurrent discovery requests. Each joining peer begins with one bootstrap contact. The logical clock drives timeout, refresh, expiry and republishing. For a small demonstration network, the closest set can contain fewer than 20 responsive nodes.

A joining peer learns one bootstrap address out of band. It performs a lookup of its own ID and refreshes eligible buckets. If the joining peer starts offline it joins on recovery. A peer whose bootstrap fails to answer retries over the simulated paths with a backoff that doubles to a maximum of 60 seconds. The RPC timeout is the larger of 2,000 ms and twice the maximum one-way path delay plus the acknowledgement margin. Recovery retains known contacts and stored records and checks stale buckets, expiry and overdue republication against logical time. The inspector exposes the active timeout.

A publisher renews its original record daily. Ordinary replicas redistribute hourly and expire relative to the original publication. When a lookup finds a value, the nearest queried peer that missed can receive a cached copy. The paper specifies exponential expiry by distance rank and leaves the base open. This implementation halves the cache lifetime for each closer contact, subject to the original record’s expiry.

The application publishes an encrypted manifest under an opaque lookup key. Vault nodes separately store replicas of encrypted chunks and expose hashes, lengths and placement results. A reader needs one verified copy of every chunk. It checks the reconstructed ciphertext hash before device decryption. Replication and Kademlia record replication are independent.

The simulator can display the entire path for instructional inspection. Individual protocol actors retain their own observations. Sizes, lookup-key reuse, addresses, timing and placement remain observable within the stated boundaries. The simulator does not establish resistance to correlation.

[Kademlia paper, 2002](https://pdos.csail.mit.edu/~petar/papers/maymounkov-kademlia-lncs.pdf)

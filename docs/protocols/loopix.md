# Loopix packet and traffic profile

The engine models the stratified network from *The Loopix Anonymity System* (USENIX Security 2017). A client is associated with a provider. Each new payload attempt independently chooses one mix per layer. The source samples each relay delay from an exponential distribution and encodes it in that relay’s Sphinx command. A relay can read its own command. Successful processing consumes one layer.

The client payload, client loop, drop and per-mix loop clocks are independent Poisson processes. Payload opportunities without queued content produce cover. A mix loop wraps from the final layer through a provider and returns to its originating mix. Provider retrieval uses a fixed interval and padded cells. A local experiment can suppress polling or block transport paths while the logical clocks continue.

The packet implementation targets the original UCL forward-packet format using P-224. The simulator’s egress adapter receives a terminal packet and passes its opaque application payload to the experimental storage workflow. This replaces the prototype’s final device-delivery boundary. The local simulator uses millisecond logical delays and in-memory datagrams. Its lower reply lane is a visual convention for an independently built packet.

The observer has identity and lifecycle only. Running the model establishes neither anonymity nor traffic-analysis resistance. Application-level sender verification uses the simulated directory’s per-run key pins. [Application envelope](application-envelope.md)

[Loopix paper](https://www.usenix.org/system/files/conference/usenixsecurity17/sec17-piotrowska.pdf) · [UCL prototype](https://github.com/UCL-InfoSec/loopix)

### Mailbox discovery

The experimental adapter can place an opaque lookup handle in the associated provider’s local inbox after the encrypted manifest has been published. The device must poll its own provider before learning that handle. The handle opens a Kademlia lookup for an encrypted manifest. This keeps application lookup separate from Sphinx forwarding and avoids requiring a prearranged mailbox secret. Recipients separately use the per-run device directory for signature verification. A provider can correlate its local client, handle and timing.

### What appears first on the diagram

The DHT bootstraps at logical time zero. Each sender queues its encrypted message and waits for its own Loopix payload clock to fire. That packet starts at the sender’s device and crosses its selected connection channel before reaching the provider. At the default payload rate of three opportunities per minute, the mean wait is 20 simulated seconds and the actual wait varies with the seed. The DHT and payload clocks run independently. Ordinary Run advances through initial maintenance without a playback delay and preserves every event in the timeline. The default diagram follows message traffic. **All transports** includes maintenance traffic.

### Providers and retrieval privacy

West and East indicate the client groups served by the two simulated provider servers. Both can receive packets from clients and act as egress for the other group. Each client has one provider association. An outage interrupts service for dependent clients, even when the mix relays and vault replicas are healthy.

An extension for independent operators would need a directory of signed provider descriptors, authenticated addresses and keys, admission rules that limit Sybil registrations, and a client selection policy using capacity and availability. Clients could register with multiple providers. Failover of existing mailboxes would also require replicated encrypted mailbox state, duplicate suppression and a way to find the new provider. A load balancer alone only distributes work within one provider service. Multiple providers holding the same mailbox state would gain additional opportunities for correlation. These are proposed changes to the experimental application.

### Anonymous retrieval

After polling its provider for a handle, the reading device sends manifest and fragment requests through its access channel, provider and three mix layers. The service receives the request through its own provider. The request carries single-use reply blocks (SURBs) prepared by the reader. Each block contains a precomputed encrypted Sphinx header, a first hop and a key for inserting the reply payload. The reader retains the private material needed to recover that payload. The service can send back an encrypted manifest page or fragment without learning the reader’s network address from the block. Reusing the same reply packet at a mix triggers replay detection. The application-level signed reply is a separate message.

Each retry prepares fresh reply blocks. The reader requests manifest pages and can use several blocks for a fragment that spans multiple cells. Blocks expire on the simulation clock. Their validity window and the per-run mix keys are local modelling choices. This retrieval feature does not implement Nym’s network-wide key epochs or its gateway acknowledgement protocol.

The DHT still performs ordinary Kademlia peer discovery and storage still uses replica identifiers. The vault can recognise repeated reads. The providers see adjacent connections, traffic volumes and timing. The local laboratory deliberately exposes a cross-hop trace for inspection. The experiment uses local Sphinx parameters and its own mailbox protocol. Wire compatibility with Nym, Nym’s infrastructure and protection against traffic correlation are outside its scope. [Nym whitepaper, section 4.5](https://nymtech.net/nym-whitepaper.pdf#page=15)


Tor is the default device channel. The Outline Shadowsocks profile represents a proxy that learns the client IP and connects to the next service from its own IP. Direct access exposes the device IP to that service. All addresses are simulated. [Outline security and privacy](https://support.getoutline.org/about/security-and-privacy/)

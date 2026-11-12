# Loopix packet and traffic profile

The engine models the stratified network from *The Loopix Anonymity System* (USENIX Security 2017). A client is associated with a provider. Each new payload attempt independently chooses one mix per layer. The source samples each relay delay from an exponential distribution and encodes it in that relay’s Sphinx command. A relay can read its own command. Successful processing consumes one layer.

The client payload, client loop, drop and per-mix loop clocks are independent Poisson processes. Payload opportunities without queued content produce cover. A mix loop wraps from the final layer through a provider and returns to its originating mix. Provider retrieval uses a fixed interval and padded cells. A local experiment can suppress polling or block transport paths while the logical clocks continue.

The packet implementation targets the original UCL forward-packet format using P-224. The simulator’s egress adapter receives a terminal packet and passes its opaque application payload to the experimental storage workflow. This replaces the prototype’s final device-delivery boundary. The local simulator uses millisecond logical delays and in-memory datagrams. Its lower reply lane is a visual convention for an independently built packet.

The observer has identity and lifecycle only. No anonymity, sender authentication or traffic-analysis resistance is established by running the model.

[Loopix paper](https://www.usenix.org/system/files/conference/usenixsecurity17/sec17-piotrowska.pdf) · [UCL prototype](https://github.com/UCL-InfoSec/loopix)

### Mailbox discovery

The experimental adapter can place an opaque lookup handle in the associated provider’s local inbox after the encrypted manifest has been published. The device must poll its own provider before learning that handle. The handle opens a Kademlia lookup for an encrypted manifest. This keeps application lookup separate from Sphinx forwarding and avoids requiring a prearranged secret or a shared sender directory. A provider can correlate its local client, handle and timing.

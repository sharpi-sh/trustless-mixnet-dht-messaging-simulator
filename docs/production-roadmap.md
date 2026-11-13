# Production roadmap and deployment gaps

The laboratory is an in-process Python simulation. It demonstrates protocol decisions and failure behaviour, but it is not deployable anonymous-messaging infrastructure. The items below describe the work still required before separate operators could run a real network.

## Can one VPS perform every network role?

Technically, yes. Mix relay, client provider, DHT and encrypted-vault services could be implemented in one Python codebase and enabled as separate roles on one VPS. The simulator already executes all of those logical roles inside one Python process.

That is not the preferred privacy deployment. A machine hosting several roles becomes one failure and observation point: its operator can correlate local timing, an outage removes several services together, and compromise exposes every co-located role. Production software should allow operators to enable roles independently, publish the roles they provide, and make clients prefer operator and network diversity. Python can implement the control plane and protocol services, although performance-sensitive cryptography or packet handling may later use audited native libraries.

## 1. Dynamic ephemeral mix nodes

**Meaning:** mix relays would register for a limited lifetime, publish their keys and capacity, renew while healthy, and disappear cleanly when their lease expires.

**Current state:** the simulator creates a fixed set of mix nodes when a run starts. Nodes can go offline, but they cannot join, renew or leave the directory.

**Production work:** define signed relay descriptors, key lifetimes, health checks, admission and Sybil resistance, directory agreement, and rules preventing routes from using expired relays. Lambda, Workers and similar short-lived functions could model ephemeral processing, but their execution limits, variable startup time and lack of durable queues or long-lived connections make them a poor default for delayed mix packets.

## 2. Decentralised provider registration, selection, replication and failover

**Meaning:** anyone meeting the network’s admission rules could operate a client provider. Clients would select providers without relying on one central list and could recover when a provider disappears.

**Current state:** three fixed sender-associated client providers and one fixed recipient-associated client provider use seeded, stable assignments. All four client providers can originate or terminate payload routes for their associated devices; the East and West labels describe diagram roles rather than one-way capability. A fifth provider-role node is the separate anonymous service gateway for DHT and vault reads. Mailbox handles are not replicated between client providers, and provider failure does not trigger client failover.

**Production work:** add signed provider records, authenticated addresses and keys, capacity information, expiry, client-side selection, replicated encrypted mailbox state, duplicate suppression and recovery. A conventional load balancer only spreads requests within one operator; it does not provide decentralisation. Replication improves availability but gives more providers an opportunity to compare timing.

## 3. Full Nym-compatible reply protocol

**Meaning:** anonymous replies would interoperate with Nym’s live packet formats, key epochs, gateways, acknowledgements and reply-block lifecycle.

**Current state:** retrieval uses Nym-inspired, single-use Sphinx reply blocks within the simulator. It is not wire-compatible with Nym and makes no claim of Nym network anonymity.

**Production work:** implement and test the complete versioned protocol against independent Nym software, including key rotation, reply reliability, replay handling, gateway behaviour and failure recovery. Using the term SURB alone is not compatibility evidence.

## 4. Production identity enrolment and key lifecycle

**Meaning:** devices need an authenticated way to publish identity and encryption keys, replace lost or compromised keys, revoke old keys and warn contacts about changes.

**Current state:** each run creates fresh Ed25519 signing keys and X25519 encryption and reply keys. It trusts a local, per-run directory that pins each participant ID to its signing key and provider assignment. This proves which simulated device signed a message, not who controls that device in the real world.

**Production work:** define enrolment, key transparency or another auditable directory, device addition, recovery, revocation, compromise notifications and safe contact verification. The design must avoid turning the identity service into a central activity log.

## 5. Stronger DHT metadata privacy

**Meaning:** encrypting message contents is not enough; observers should learn less from lookup keys, repeated access, object sizes, replica placement and request timing.

**Current state:** manifests and fragments are encrypted. Client providers observe adjacent client timing and volume, while the dedicated service gateway, DHT peers and vaults observe their own adjacent operations. Repeated handles or fragment identifiers, object sizes and timing may still be correlated.

**Production work:** evaluate rotating or blinded lookup capabilities, fixed-size objects, access-pattern protection, private information retrieval, decoy reads, expiry and replica-selection policies. Each option changes bandwidth, latency and deletion behaviour. Encryption alone does not hide access patterns.

## 6. Real multi-host deployment and operator discovery

**Meaning:** each role would run as a network service on independently operated machines with durable state, authenticated discovery and upgrade procedures.

**Current state:** paths are in-memory logical datagrams and all state belongs to one local Python service.

**Production work:** define network transports, service APIs, persistent queues and storage, node discovery, configuration, observability, version negotiation, rolling upgrades, backups and abuse controls. Multi-host tests must cover partitions, restarts, clock differences and incompatible versions.

## 7. Optional batch or pool shuffling profile

**Meaning:** an additional research profile could collect packets into a batch or pool and explicitly randomise their release order, with measurements showing how much reordering occurred.

**Current state:** the faithful Loopix 2017 profile does not perform a batch shuffle. It applies independent exponentially distributed holding times at each mix, Poisson payload and cover clocks, and path delay with jitter. Concurrent packets can therefore leave in a different order naturally, but no code deliberately shuffles a batch.

**Production work:** implement this only as a separately named mix profile with its own paper, parameters, threat model and tests. It must not silently change the behaviour while retaining the Loopix 2017 label.

## 8. Provider endpoint discovery and gateway routing

**Meaning:** a device needs a safe way to turn its selected provider identity into a reachable IPv4, IPv6, DNS or onion-service endpoint. This is the bootstrap step before Tor, Outline Shadowsocks or a direct connection can hand packets to that provider.

**Current state:** there is no deployable DNS, IP or onion-service discovery. Python gives each sender a seeded, stable assignment to one of three West-side providers and assigns each recipient to the East-side provider inside the generated topology. Nodes receive simulated addresses for inspection, not public endpoints. West and East are diagram roles, not geographic routing decisions.

**Production work:** publish signed, expiring provider descriptors containing the provider identity key, supported endpoint types, ports, transport keys, capacity and validity period. Clients should obtain matching descriptors from several independent directory sources, verify the signature, select a provider, and then connect using the participant's chosen channel. A Tor client should resolve a provider name through Tor or use an onion endpoint so local DNS does not reveal the destination. A direct connection exposes the device IP to the provider; an Outline connection exposes it to the proxy. DNS can be a convenient bootstrap mechanism, but a single DNS zone, CDN or reverse proxy creates a central control and observation point. Production clients should support multiple bootstrap sources, direct signed IP endpoints and key pinning rather than trusting DNS alone.

## 9. Large-scale reliability and fault campaign

**Meaning:** exercise at least 100,000 message journeys across many reproducible random seeds while injecting packet loss, path delay, blocked links, node outages, storage-replica loss, polling interruptions, network partitions and process restarts.

**Current state:** unit, integration and browser acceptance tests cover bounded seeded failures, retries, blocked paths and recovery. There is no sustained 100,000-message campaign, streaming event archive or performance baseline.

**Production work:** build a headless runner that streams every authoritative Python event to compressed, rotated JSONL files rather than retaining an unbounded trace in memory. Each run must record its configuration, seed, fault schedule, result and resource measurements. Automated invariants should detect silent corruption, duplicate delivery, invalid signatures, processing by offline nodes, unbounded retries, missing failure reasons, queue growth and incomplete recovery. Run independent campaigns in parallel, reduce every failure to a deterministic regression test, fix it, and rerun the affected and complete campaigns. Report delivery rate, explicit failure rate, retry distribution, latency percentiles, throughput, CPU, memory and storage use. Passing this campaign demonstrates behaviour only for the tested fault model; it does not prove anonymity or production security.

## 10. Adversarial nodes and global-observer campaign

**Meaning:** test deliberately malicious providers, mix relays, DHT peers, vaults and colluding operators rather than modelling every unavailable node as merely failed. Activate a separate global-observer experiment that attempts to correlate traffic across all visible links.

**Current state:** nodes can become unavailable and paths can fail or be blocked, but they do not yet execute malicious strategies. The `GlobalObserver` object is intentionally inert. The laboratory records local IP-hop observations for explanation, not as an implemented adversary model.

**Production work:** add explicitly labelled adversary profiles and keep them separate from the faithful Loopix and Kademlia implementations. Test providers and connection channels attempting to learn source IP addresses; mixes delaying, dropping, duplicating, replaying, reordering or selectively forwarding packets; DHT peers returning false contacts or values; vaults withholding, corrupting or correlating fragments; and colluding operators combining timing, volume, route and identifier observations. The global observer should receive only information available at the selected observation points, run documented correlation attacks, and report guesses with confidence and false-positive rates. Tests must confirm that tampering is detected, replayed packets are rejected, compromised storage cannot forge signed plaintext, failures remain explicit, and no component is credited with information it could not observe. Results must distinguish content confidentiality, sender or recipient anonymity, relationship anonymity and availability; failure to identify a sender in a finite simulation is not proof of anonymity.

## 11. Dynamic vault membership, durability and replica repair

**Meaning:** an independent operator could install the network software, enable the vault role, register available capacity for a limited period and later drain or leave the network. A production vault would be a persistent encrypted-blob service on a VPS, dedicated server or durable object-storage platform. It should receive only opaque fragment capabilities, fixed-size ciphertext and expiry information, never plaintext or participant private keys.

**Storage boundary:** vaults are bulk ciphertext stores, not Kademlia peers, mailboxes or mix relays. A vault accepts an opaque fragment capability, fixed-size encrypted bytes, integrity information and an expiry policy; it persists and returns those exact bytes. It should not receive the decryption key, intended recipient, conversation position or complete file manifest. The DHT maps opaque handles to small encrypted manifests, providers queue message handles for polling, and vaults provide the capacity and availability for the referenced ciphertext fragments.

**Current state:** vaults are fixed in-memory Python objects created with each simulation. Each stores fragment bytes, placements and read, write and integrity counters within a configured 16 MiB capacity. The engine places encrypted fragments across distinct logical vault IDs and can read an alternative replica after an outage, but vaults cannot join, renew, drain or leave. There is no durable disk or object store, membership directory, retention enforcement, automatic replica repair or proof that two vault IDs belong to different operators. Abrupt loss of enough configured replicas makes a fragment unavailable.

**Production work:** define signed, expiring vault descriptors containing the operator identity, storage key, endpoints, capacity, supported object sizes and retention limits. Admission must include Sybil resistance and independent reachability and capacity checks rather than trusting self-declared identities. Placement must spread replicas across operators, subnets, regions and failure domains; several vault IDs owned by one operator must not count as independent replicas. Add authenticated capability-based writes and reads, fixed-size encrypted objects, signed storage receipts, durable expiry and deletion, quotas, abuse controls and key rotation. Detect expired or unresponsive vaults and restore the required replica count from a healthy ciphertext copy without exposing plaintext. Planned shutdown should enter a draining state and stop accepting new fragments until repairs are acknowledged. Evaluate erasure coding separately from whole-fragment replication and document its availability, repair-bandwidth and metadata consequences. Permissionless entry and exit are safe only while monitoring and repair keep sufficient independent copies available.

## 12. Loopix route-health measurement and failure investigation

**Meaning:** senders need current evidence that eligible providers and mix relays are reachable and forwarding Sphinx packets, without allowing an unavailable or malicious relay to mark itself healthy. This health system selects a route before Sphinx packet construction; it must not imply that a relay can divert an already constructed packet around a failed next hop.

**Current state:** every payload attempt chooses one relay from each configured layer, including relays currently marked offline. A failed Sphinx packet stops and the sender may build a fresh packet with a new random route, but it does not exclude a relay already observed as unavailable. The default permits two retries. Python's authoritative scheduler detects blocked or offline hops and applies an internal per-hop timeout; this is not a destination-originated acknowledgement travelling back through the network. Mix relays generate Loopix loop packets that return to their origin, but those loops are cover traffic rather than a shared health consensus. A missing loop proves only that the selected route failed; it does not identify which hop failed.

**Production work:** create a separately labelled experimental directory protocol using signed, short-lived relay descriptors and periodically threshold-signed network snapshots. Independent monitors should sample routes with authenticated Sphinx loop packets that are indistinguishable from ordinary traffic, while relays may also measure their own returning loops. Combine observations from several operators into rolling reachability, latency and forwarding scores; no single relay should be able to certify itself or remove a competitor. Publish aggregate, time-bucketed health results rather than per-message traces, which would expose useful timing metadata. New route construction should exclude expired and sufficiently corroborated unavailable relays, retain random selection among healthy candidates and prefer operator and network diversity. End-to-end anonymous acknowledgements can trigger a fresh route, but a timeout cannot safely assign blame to an individual hop. Test selective black-hole relays that forward probes but drop user traffic, colluding monitors, false accusations, Sybil identities and partitions. Compare externally generated probes, relay-originated loops and real delivery outcomes, and record false-positive and false-negative rates. This subsystem combines active measurement, directory consensus and reputation; it is not part of the Loopix 2017 algorithm and must not be presented as such.

## 13. Mix-path failure detection and recovery

**Meaning:** determine whether rebuilding and retrying a complete Sphinx route is sufficient when a packet reaches an unavailable next hop, and define how the sender can learn that an ordinary message was delivered or lost. A mix relay cannot redirect an existing Sphinx packet because its encrypted header identifies the next hop in advance.

**Current state:** the simulator has no destination-originated delivery acknowledgement for an ordinary payload. Its authoritative Python scheduler observes each simulated traversal, declares blocked or offline hops failed after an internal acknowledgement timeout and queues a fresh Sphinx packet when retries remain. That internal knowledge would not exist for a real sender merely because no reply arrived. Silence is ambiguous: the packet may be delayed, dropped, awaiting recipient polling or delivered to a recipient who chose not to reply.

**Production work:** compare anonymous destination receipts carried by single-use reply blocks, provider-level durable acceptance receipts, bounded fresh-route retries, redundant routes and erasure-coded packet groups. Any receipt must be unlinkable, replay-resistant and independent of a conversational reply. Define idempotency and duplicate suppression before introducing redundant delivery. Measure how each option changes latency, bandwidth, correlation exposure and delivery probability under dead relays. Do not add mid-route diversion and still label the result as ordinary Sphinx routing. Route-health snapshots from the preceding section can reduce failures before construction, but cannot prove delivery after the route has been selected.

## 14. Cloud deployment templates and proof of concept

**Meaning:** demonstrate the proposed roles on real, separately reachable infrastructure using repeatable infrastructure-as-code rather than a single in-process laboratory.

**Current state:** the repository has no containers, deployment manifests, infrastructure templates or hosted proof of concept. All protocol roles, storage and simulated addresses belong to one local Python process, with the Svelte client started separately.

**Production work:** package provider, mix, DHT, vault, service-gateway and monitoring roles as independently configurable services. Produce an AWS CloudFormation example for AWS and Terraform/OpenTofu or provider-native equivalents for Cloudflare and DigitalOcean; CloudFormation itself is AWS-specific. A DigitalOcean proof of concept can use separate droplets or containers for long-lived relays and providers. A Cloudflare proof of concept can evaluate Workers for short request handlers and R2 for durable encrypted fragments, but Workers should not be assumed suitable for delayed mix packets, durable queues or long-lived connections. Include DNS and key bootstrapping, TLS, secret rotation, persistent volumes, health checks, logs, cost limits, teardown and a documented threat model. Co-located roles are acceptable for a demonstration only when the resulting correlation and failure boundaries are explicit.

## 15. Optional Tor-to-DHT direct retrieval profile

**Meaning:** evaluate whether a Tor-connected participant should reach a service gateway or DHT lookup path directly instead of sending every manifest and fragment request through the Loopix mix layers.

**Current state:** every anonymous retrieval request travels from the selected participant channel to that participant's provider, through all three mix layers and the dedicated anonymous service gateway, then to the DHT or vault. Responses return through single-use reply blocks. Selecting Tor changes the participant's access channel; it does not bypass the mixnet for retrieval.

**Production work:** implement direct Tor retrieval only as a separately named experimental profile and compare it with mixed retrieval under an explicit threat model. A Tor-to-service-gateway path would reduce mix delay, bandwidth and failure probability, while relying on Tor's anonymity set and exposing request timing and volume directly to the gateway. Calling DHT peers themselves requires authenticated peer discovery and may expose lookup targets, repeated keys and peer-selection patterns. The mixed path adds independent delays, cover traffic and separation from the participant's Tor circuit at greater cost and latency. Test both designs against gateway, DHT, Tor-exit and timing observers before selecting a default.

## 16. Decentralised DHT discovery, assignment and enrolment

**Meaning:** allow independently operated Kademlia peers to enrol, publish authenticated endpoints, discover several bootstrap peers and assume responsibility for keys according to XOR distance without a centrally generated topology.

**Current state:** all DHT peers are created when a simulation starts, receive locally generated random 160-bit IDs and `sim://` addresses, and join through the first generated peer as a fixed bootstrap seed. An online peer can retry a failed bootstrap and retain learned contacts, but external operator enrolment, signed descriptors, bootstrap diversity and decentralised admission do not exist.

**Production work:** bind each DHT node ID to a cryptographic identity or verifiable derivation so an operator cannot freely position many Sybil nodes around a target key. Publish signed, expiring descriptors containing endpoints, protocol versions, keys, capacity and operator or failure-domain information. Clients and joining peers should obtain several bootstrap records from independent sources, verify them, perform ordinary Kademlia self-lookups and reject conflicting identities or stale endpoints. Define admission, rate limits, eclipse resistance, operator diversity, churn handling, record repair and revocation. Kademlia's XOR metric should determine record responsibility; a central service should not assign individual messages to preferred peers. Align this work with [provider registration and failover](#2-decentralised-provider-registration-selection-replication-and-failover), [provider endpoint discovery](#8-provider-endpoint-discovery-and-gateway-routing) and the relay-health directory without collapsing those roles into one trusted registry.

## 17. Large encrypted files and public content distribution

**Meaning:** support files larger than an ordinary message by streaming them into bounded chunks, storing the bulk ciphertext in replicated vaults and publishing only a compact, versioned manifest through the DHT. Private distribution would encrypt with a random content key, wrap that key for one or more recipient public keys and expose a random or blinded capability. Public distribution could publish a signed, content-addressed manifest or publisher namespace that anyone with the public address can resolve and verify. Public content may remain unencrypted, or use a disclosed content key when encryption is required only for transport and storage.

**Current state:** the product and API expose text-message envelopes, not file attachments. The underlying storage model can already split arbitrary ciphertext into ordered fragments, hash every fragment, select distinct vault replicas, publish an encrypted manifest to Kademlia and reconstruct the ciphertext only after fragment and complete-payload digests pass. Defaults are deliberately small for simulation: 128-byte chunks, two replicas and 16 MiB per vault, with a maximum configured chunk size of 4,096 bytes. There is no filename or media-type metadata, streaming API, range resume, progress UI, public address, recipient access-control list, deletion protocol or production capacity model.

**Production work:** keep bulk chunks out of Kademlia values so DHT replication, refresh and lookup remain bounded. Define a signed manifest containing version, encrypted filename and media type where private, total length, chunk or erasure-shard map, per-part digest or Merkle root, replica capabilities, publisher identity, expiry and content-key envelopes. Add streaming authenticated encryption, bounded memory, back-pressure, resumable upload and download, partial verification, replica repair and garbage collection. Compare whole-chunk replication with erasure coding under vault churn. Private addresses should be unguessable capabilities with recipient key wrapping; public addresses may use a content hash or signed publisher namespace. Avoid convergent encryption by default because it reveals when encrypted files are equal. Define quota, abuse, copyright-reporting and malware-handling boundaries without claiming that vault operators can inspect encrypted plaintext.

## 18. Message sequencing, gaps and concurrent devices

**Meaning:** define how a conversation detects duplicates, missing messages and causal relationships when mix delays, retries, DHT retrieval and recipient polling can deliver valid messages out of order.

**Current state:** each staged message has a conversation ID, exchange number and direction, and the signed envelope binds its delivery context. The deterministic scenario advances a conversation after the preceding message reaches the receiving device, while device logs and conversation panes preserve actual append and arrival order. This is scenario orchestration, not a distributed ordering protocol. There is no signed per-device sequence chain, predecessor hash, gap request, out-of-order buffer, multi-device merge rule or replay window spanning separate runs.

**Production work:** give every message a unique identifier and bind a signed, encrypted per-conversation sender or device sequence plus previous-message hash or causal parent. Deduplicate by message ID, detect gaps without treating later valid messages as corrupt, retain late arrivals and represent permanently missing entries explicitly. Replies should reference the message they answer rather than depending only on display order. Define independent chains and merge rules for concurrent devices, device restoration, key rotation and simultaneous sends. Keep protocol ordering separate from presentation: the client may offer causal grouping, but it must not silently reorder evidence using an untrusted wall-clock timestamp. Test duplicates, replay, gaps, late delivery, simultaneous messages, device loss, key changes and permanent fragment loss.

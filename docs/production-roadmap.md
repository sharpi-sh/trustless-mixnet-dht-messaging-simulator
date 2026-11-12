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

**Current state:** West and East are fixed client providers. A separate fixed service gateway handles anonymous DHT and vault reads. Mailbox handles are not replicated between client providers.

**Production work:** add signed provider records, authenticated addresses and keys, capacity information, expiry, client-side selection, replicated encrypted mailbox state, duplicate suppression and recovery. A conventional load balancer only spreads requests within one operator; it does not provide decentralisation. Replication improves availability but gives more providers an opportunity to compare timing.

## 3. Full Nym-compatible reply protocol

**Meaning:** anonymous replies would interoperate with Nym’s live packet formats, key epochs, gateways, acknowledgements and reply-block lifecycle.

**Current state:** retrieval uses Nym-inspired, single-use Sphinx reply blocks within the simulator. It is not wire-compatible with Nym and makes no claim of Nym network anonymity.

**Production work:** implement and test the complete versioned protocol against independent Nym software, including key rotation, reply reliability, replay handling, gateway behaviour and failure recovery. Using the term SURB alone is not compatibility evidence.

## 4. Production identity enrolment and key lifecycle

**Meaning:** devices need an authenticated way to publish identity and encryption keys, replace lost or compromised keys, revoke old keys and warn contacts about changes.

**Current state:** each run creates fresh keys and trusts a local, per-run mapping between participant IDs and signing keys. This proves which simulated device signed a message, not who controls that device in the real world.

**Production work:** define enrolment, key transparency or another auditable directory, device addition, recovery, revocation, compromise notifications and safe contact verification. The design must avoid turning the identity service into a central activity log.

## 5. Stronger DHT metadata privacy

**Meaning:** encrypting message contents is not enough; observers should learn less from lookup keys, repeated access, object sizes, replica placement and request timing.

**Current state:** manifests and fragments are encrypted, but providers, DHT peers and vaults can observe their adjacent requests. Repeated identifiers and timing may be correlated.

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

**Current state:** there is no DNS or IP discovery. Python assigns every sender to the fixed West provider and every recipient to the fixed East provider inside the generated topology. West and East are diagram roles, not geographic routing decisions or public server addresses.

**Production work:** publish signed, expiring provider descriptors containing the provider identity key, supported endpoint types, ports, transport keys, capacity and validity period. Clients should obtain matching descriptors from several independent directory sources, verify the signature, select a provider, and then connect using the participant's chosen channel. A Tor client should resolve a provider name through Tor or use an onion endpoint so local DNS does not reveal the destination. A direct connection exposes the device IP to the provider; an Outline connection exposes it to the proxy. DNS can be a convenient bootstrap mechanism, but a single DNS zone, CDN or reverse proxy creates a central control and observation point. Production clients should support multiple bootstrap sources, direct signed IP endpoints and key pinning rather than trusting DNS alone.

## 9. Large-scale reliability and fault campaign

**Meaning:** exercise at least 100,000 message journeys across many reproducible random seeds while injecting packet loss, path delay, blocked links, node outages, storage-replica loss, polling interruptions, network partitions and process restarts.

**Current state:** unit, integration and browser acceptance tests cover bounded seeded failures, retries, blocked paths and recovery. There is no sustained 100,000-message campaign, streaming event archive or performance baseline.

**Production work:** build a headless runner that streams every authoritative Python event to compressed, rotated JSONL files rather than retaining an unbounded trace in memory. Each run must record its configuration, seed, fault schedule, result and resource measurements. Automated invariants should detect silent corruption, duplicate delivery, invalid signatures, processing by offline nodes, unbounded retries, missing failure reasons, queue growth and incomplete recovery. Run independent campaigns in parallel, reduce every failure to a deterministic regression test, fix it, and rerun the affected and complete campaigns. Report delivery rate, explicit failure rate, retry distribution, latency percentiles, throughput, CPU, memory and storage use. Passing this campaign demonstrates behaviour only for the tested fault model; it does not prove anonymity or production security.

## 10. Adversarial nodes and global-observer campaign

**Meaning:** test deliberately malicious providers, mix relays, DHT peers, vaults and colluding operators rather than modelling every unavailable node as merely failed. Activate a separate global-observer experiment that attempts to correlate traffic across all visible links.

**Current state:** nodes can become unavailable and paths can fail or be blocked, but they do not yet execute malicious strategies. The `GlobalObserver` object is intentionally inert. The laboratory records local IP-hop observations for explanation, not as an implemented adversary model.

**Production work:** add explicitly labelled adversary profiles and keep them separate from the faithful Loopix and Kademlia implementations. Test providers and connection channels attempting to learn source IP addresses; mixes delaying, dropping, duplicating, replaying, reordering or selectively forwarding packets; DHT peers returning false contacts or values; vaults withholding, corrupting or correlating fragments; and colluding operators combining timing, volume, route and identifier observations. The global observer should receive only information available at the selected observation points, run documented correlation attacks, and report guesses with confidence and false-positive rates. Tests must confirm that tampering is detected, replayed packets are rejected, compromised storage cannot forge signed plaintext, failures remain explicit, and no component is credited with information it could not observe. Results must distinguish content confidentiality, sender or recipient anonymity, relationship anonymity and availability; failure to identify a sender in a finite simulation is not proof of anonymity.

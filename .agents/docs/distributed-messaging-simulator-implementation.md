# Implementation Specification: Distributed Mixnet Messaging Simulator

**Document type:** Spec Kit feature specification / implementation brief  
**Status:** Draft for implementation  
**Feature name:** Distributed Messaging Network Simulation Laboratory  
**Primary audience:** OpenAI Codex / Astra coding harness  
**Implementation principle:** Python owns and executes the simulation. SvelteKit is the control panel and visualisation client.

---

## 0. Instructions to the implementation agent

Build the application described in this document. Treat this document as the source of truth for the first implementation.

### Non-negotiable architecture

1. **Python is the simulation engine.** All simulated people, Tor abstractions, mixnet nodes, DHT nodes, storage nodes, routing tables, node availability, routing decisions, message processing, chunking, manifests, polling, retries and simulation events are implemented in Python.
2. **SvelteKit is the frontend.** It provides the connection screen, configuration controls, D3 network visualisation, node inspector, routing-table inspector, event stream, timeline and playback controls.
3. **FastAPI exposes the Python HTTP API and WebSocket.** The browser sends commands to Python and receives events from Python.
4. **Do not implement a second simulation engine in JavaScript.** JavaScript must not independently decide routes, generate node availability, perform DHT lookups, select storage nodes or simulate message delivery.
5. **The Python process starts separately from SvelteKit.** The developer starts Python in one terminal, then starts SvelteKit with `npm run dev` in another.
6. **The Python process chooses an available port and prints the actual endpoint.** The developer copies the printed port or endpoint into the SvelteKit connection screen. Do not silently assume port 8000.
7. **The simulation is generated only after the user connects and presses the create/run control.** Connecting to the backend must not automatically create the network.
8. **The playback delay is a display/execution pacing delay between simulation steps.** It is not a simulation-time multiplier and must not be conflated with outage durations or network timeouts.
9. **The first implementation is a local simulator.** It does not connect to the real Tor network, real DHT peers, public mixnet operators or real distributed storage.
10. **Do not claim the simulator proves anonymity or production security.** It is a model for exploring and testing protocol behaviour and failure cases.

### Implementation discipline

- Build in dependency order: Python domain model and tests first, then API/WebSocket, then frontend connection/configuration, then visualisation and interaction.
- Keep modules small and responsibilities explicit.
- Use typed models for API commands, configuration, events and domain state.
- Use deterministic random seeds so a scenario can be reproduced.
- Commit in logical implementation stages if working in a Git repository.
- Run tests after each logical stage and provide a test/coverage report.
- Do not silently invent protocol rules where this specification marks a decision as unresolved. Implement an explicit interface or documented MVP assumption instead.
- Do not add authentication, registration, contact approval, a central identity directory or a pre-shared secret as a prerequisite for Alice to send Bob a message. The intended starting model is that Bob publishes a public key on a public webpage and Alice retrieves it.

---

# 1. Feature overview

## 1.1 Purpose

Create a locally running, interactive simulation laboratory for exploring a distributed encrypted messaging architecture.

The user should be able to:

- Start a Python simulation backend locally.
- Start a SvelteKit frontend locally.
- Copy the backend port printed by Python into the frontend connection form.
- Connect the frontend to the Python HTTP and WebSocket endpoints.
- Configure how many people participate, how many mixnet nodes exist, how conversations are formed, how many message exchanges occur and how quickly the simulation advances.
- Press **Create simulation** to make Python generate the people and network objects.
- Press **Run** to execute the simulation.
- Watch messages travel through randomly selected network nodes.
- Inspect each node's local routing table and current knowledge of peers.
- Watch nodes go offline and recover for independently randomised periods.
- Observe routing failures, timeouts, retries and alternative paths.
- Observe Bob polling for messages rather than receiving unsolicited server push notifications.
- Inspect the information visible to each simulated participant or node.
- Replay a scenario using the same random seed.

The application is intended to make the internal behaviour visible and inspectable. The UI should show what each step did, what data was passed, which node made a decision, what alternatives were available and why a route failed or succeeded.

## 1.2 Product form

A local engineering dashboard with a technical, restrained, graphite-grey visual design.

The application consists of two separately started local processes:

| Process | Technology | Default address |
|---|---|---|
| Simulation backend | Python + FastAPI | Dynamically selected port, starting search at 8000 |
| Frontend | SvelteKit + Vite | `http://localhost:5173` by default |
| Backend HTTP API | FastAPI | `http://127.0.0.1:<actual-port>` |
| Backend WebSocket | FastAPI | `ws://127.0.0.1:<actual-port>/ws` |

The backend may use 8000, 8001, 8002 or another available port. The frontend must not assume 8000.

## 1.3 Out of scope for the first implementation

- Connecting to the actual Tor network.
- Implementing Tor onion routing or Tor relay cryptography.
- Deploying actual public mixnet infrastructure.
- Connecting to a production Kademlia network.
- Running real peer-to-peer sockets between simulated nodes.
- Production message delivery or a real-world messaging service.
- Mobile applications.
- Cloud deployment, user accounts or multi-tenant hosting.
- Proving resistance to a global passive adversary.
- Implementing a production-grade mixnet protocol without further protocol specification.
- Treating a diagram as evidence that a real network is secure.

The simulator may model network addresses and independent node operators, but those are simulated properties. It must not pretend that random private IP addresses are real routable Internet endpoints.

---

# 2. User scenarios and acceptance criteria

## Scenario 1: Start the Python backend

**As a developer**, I want to start Python in a terminal and have it tell me which port it is listening on, so that I can connect the frontend without assuming a port is free.

### Acceptance criteria

- Running `python main.py` starts the FastAPI application.
- The backend tries port 8000 first.
- If port 8000 is unavailable, it tries the next configured port, for example 8001, 8002 and so on.
- The port is selected by successfully binding the server socket, not by merely checking whether a port appears unused.
- The backend prints the actual HTTP URL and WebSocket URL after it has successfully bound.
- The backend prints a clear ready message.
- The backend remains running until interrupted.
- If no port in the configured range is available, startup fails with a clear error.
- The selected port is not hardcoded into the frontend.

Example terminal output:

```text
========================================
      DISTRIBUTED NETWORK SIMULATOR
========================================

Backend status: RUNNING
HTTP API:       http://127.0.0.1:8001
WebSocket:      ws://127.0.0.1:8001/ws
Health check:   http://127.0.0.1:8001/health

Ready for frontend connection.
Copy the backend port or URL into the SvelteKit connection screen.
========================================
```

The example port is illustrative. The real output must show the port actually selected.

## Scenario 2: Start the SvelteKit frontend

**As a developer**, I want to start the frontend independently using NPM.

### Acceptance criteria

- The frontend starts with `npm run dev`.
- The default Vite development URL is shown in the terminal.
- The developer opens the displayed URL in a browser.
- The frontend does not require Python to be running merely to render the connection screen.
- If the backend is unavailable, the frontend remains usable and displays a disconnected state.

## Scenario 3: Connect to the Python endpoint

**As a user**, I want to paste the Python endpoint or port into the first screen so that the UI can connect to the correct backend.

### Acceptance criteria

- The initial screen includes a backend endpoint input.
- The user may enter either a port such as `8001` or a full local HTTP URL such as `http://127.0.0.1:8001`.
- If a port is entered, the frontend constructs the HTTP and WebSocket URLs.
- If a full HTTP URL is entered, the frontend derives the WebSocket URL by changing the scheme from HTTP to WS and appending `/ws`.
- HTTPS URLs must derive WSS URLs.
- The UI has a **Test connection** action.
- Test connection calls `/health`.
- The UI displays connecting, connected, disconnected and error states.
- Only after a successful health check should the UI establish the WebSocket.
- The UI must display the resolved HTTP and WebSocket endpoints.
- The user can change the endpoint and reconnect.
- The endpoint is not silently replaced with a hardcoded default.
- The initial implementation may remember the endpoint in browser local storage, but must provide a visible way to edit it. Do not store secrets in local storage.

Example:

```text
Python backend endpoint

[ 8001                         ]

HTTP:      http://127.0.0.1:8001
WebSocket: ws://127.0.0.1:8001/ws

[ Test connection ]
Status: Connected
```

The endpoint input is for a local development backend. Do not expose the Python server to the public network by default.

## Scenario 4: Configure and create a simulation

**As a user**, I want to configure the number of participants, network nodes and conversation behaviour before Python creates the simulation.

### Acceptance criteria

- The configuration form is available after connecting to the backend.
- Sender count is configurable from 1 to 10.
- Receiver count is configurable from 1 to 10.
- Mixnet node count is configurable within the initial rule range of 10 to 20.
- The user can choose a fixed mixnet node count or ask Python to randomise the count within the selected minimum and maximum.
- The number of senders and receivers represents the number of separate `Person` instances Python creates.
- A person is not a special Alice-only or Bob-only class. Alice, Bob and later participants are instances of the same `Person` class with different IDs, display names and roles in a communication scenario.
- Each person has an independent client state and their own `TorNetwork` instance.
- Each person has their own cryptographic identity/key material generated by Python for the simulation.
- The configuration includes conversation/message exchange settings.
- The user can configure the number of message exchanges per conversation.
- An exchange means one message followed by a reply. Therefore, five exchanges in a two-person conversation normally means ten message transmissions.
- The UI must label exchanges and total messages clearly so the user does not confuse them.
- The configuration supports one sender to one receiver, multiple senders to one receiver, one sender to multiple receivers, and multiple senders/receivers.
- The communication pairing strategy must be explicit, not inferred from sender and receiver counts alone.
- Initial pairing strategies: `all_to_one`, `one_to_all`, `one_to_one_pairs`, and `random_pairs`.
- The user can configure the number of exchanges per conversation.
- A random seed may be supplied or generated. The seed must be returned in the generated simulation metadata.
- The user presses **Create simulation** to ask Python to generate the objects.
- Python returns a topology snapshot and simulation ID.
- The UI renders the generated topology only after receiving that response.
- Creating the simulation does not automatically start message traffic.
- The user then presses **Run** to begin execution.

## Scenario 5: Watch the generated network

**As a user**, I want to see the network that Python actually generated.

### Acceptance criteria

- The initial graph is generated from the topology snapshot returned by Python.
- D3 is used for graph layout and/or interaction.
- SVG is used for node and edge rendering.
- The UI must not invent nodes or edges that are absent from Python's topology.
- Nodes have stable IDs.
- Nodes are visually grouped by layer/type.
- The graph distinguishes people, their Tor abstractions, mixnet nodes, DHT nodes and storage nodes.
- The user can zoom and pan.
- The user can select a node.
- Selecting a node opens the node inspector.
- Selecting a peer in a routing table highlights the corresponding graph node and connection.
- The graph must remain usable with the initial expected network size and should not assume a fixed number of nodes.

## Scenario 6: Observe message routing

**As a user**, I want to see the actual path selected by Python, including alternative candidates and failed attempts.

### Acceptance criteria

- Python selects the next hop.
- JavaScript does not select or recalculate the route.
- Python emits a routing decision event for each decision.
- The event includes the current node, available candidates, excluded candidates, selected peer and a reason/code for the selection.
- The UI animates the message along the actual selected path.
- The UI distinguishes attempted, successful, failed and retried hops.
- Clicking a routing decision shows the decision details.
- The UI can show candidate peers that were not selected.
- A route is not presented as predetermined or hardcoded.
- A failed hop can cause the sending node to retry through a different eligible peer according to the routing policy.
- The retry policy must have bounded attempts and a clear terminal failure state.
- A retry must not duplicate message delivery without an explicit deduplication policy.

## Scenario 7: Inspect each mixnet node's routing table

**As a user**, I want to inspect what each mixnet node knows about its peers at the moment it makes a routing decision.

### Acceptance criteria

- Every `MixNode` owns a local routing table.
- The `Mixnet` manager may assist with initial bootstrap configuration, but must not silently give every node a complete authoritative list of all nodes.
- Different nodes may have different peer knowledge.
- The routing table changes as peers are discovered, become unreachable, recover or age out.
- The UI shows a selected node's routing table.
- The table shows peer ID, simulated address, status, last-seen time, failure count and relevant routing metadata.
- The table distinguishes a peer known to be offline from a peer that is merely unresponsive or whose status is stale.
- Routing table updates are streamed from Python to the frontend.
- The UI does not fabricate peer entries.

## Scenario 8: Randomised node availability

**As a user**, I want nodes to go offline and come back online for different random periods while the simulation is running.

### Acceptance criteria

- Availability is implemented in Python.
- Each network node has independent availability state.
- Nodes can fail at different simulated times.
- Outage durations are independently generated.
- The model supports short outages such as 500 milliseconds of simulated time and long outages such as 300 or 500 seconds of simulated time.
- A node may be configured to remain offline for the entire simulation.
- A node may be configured to remain online for the entire simulation.
- The simulation can model repeated outages and recoveries.
- The user can configure an outage profile or failure rate.
- The user can configure a minimum and maximum outage duration.
- The user can choose random, bursty or scheduled outage patterns.
- The user can manually take a node offline or bring it back online for testing.
- The random seed makes the same availability schedule reproducible.
- Availability changes are emitted as events and reflected in the graph and node inspector.
- A node that is offline cannot accept or process a message.
- A node that recovers becomes eligible for routing again only after its state has been updated and any configured recovery checks have completed.

### Important timing rule

There are two separate concepts:

1. **Simulation time:** the logical time used to schedule outages, timeouts, polling and network behaviour.
2. **Playback delay:** the real-time pause between simulation steps, controlled by the frontend slider.

The playback delay must not change outage durations.

Example:

- Mix node A goes offline at simulated time 10 seconds for 300 simulated seconds.
- Mix node B goes offline at simulated time 25 seconds for 0.5 simulated seconds.
- Mix node C is offline for the entire run.
- The UI may display these transitions at a user-selected playback pace.

For the first implementation, a deterministic discrete-event scheduler is preferred over tying every outage to real wall-clock sleeps. The scheduler should advance logical simulation time according to scheduled events. The playback controller decides how quickly those events are presented/executed to the user.

Do not implement a confusing time multiplier unless it is explicitly added as a separate feature later.

## Scenario 9: Bob polls for messages

**As a user**, I want Bob to retrieve messages through his own client and Tor abstraction by polling, rather than having the network push a notification to Bob.

### Acceptance criteria

- Bob is an instance of `Person`.
- Bob owns a `TorNetwork` instance.
- Bob's client has a polling interval or polling schedule.
- Bob initiates a poll through his own Tor abstraction.
- The request traverses the simulated network according to the implemented route.
- Bob is not automatically notified by a storage node when a message arrives.
- A message can be stored before Bob polls.
- If Bob polls before the message is available, the poll returns no new message.
- The UI displays Bob's polling events and results.
- The poll request and response are separate observable events.
- Bob retrieves the encrypted manifest/fragments only after discovering that an item is available.
- The simulation records the information visible to each participant/node.

## Scenario 10: Multiple conversations

**As a user**, I want to configure several senders and receivers and observe concurrent or interleaved conversations.

### Acceptance criteria

- The simulation creates the requested number of sender and receiver `Person` instances.
- The system supports multiple communication pairs.
- The pairing strategy is returned in the simulation metadata.
- Each conversation has a unique conversation ID.
- Each message has a unique message ID.
- Messages from different conversations can be interleaved.
- Bob can receive messages from Alice, Carol and David in separate conversations.
- The UI can filter events by participant, conversation, message, node and event type.
- The UI does not assume one sender and one receiver.

---

# 3. Functional requirements

## 3.1 Python backend

### FR-PY-001: Local server startup

Provide a Python entry point:

```bash
python main.py
```

The entry point must:

- Load backend configuration.
- Select an available local port starting at 8000.
- Bind to `127.0.0.1` by default.
- Start FastAPI/Uvicorn on the successfully bound socket.
- Print actual HTTP and WebSocket endpoints.
- Print a ready message.
- Shut down cleanly on Ctrl+C.

Implementation note: avoid a race between checking an available port and starting Uvicorn. Prefer binding a socket first and passing the already-bound socket to the ASGI server, or use an equivalent robust approach.

### FR-PY-002: Health endpoint

`GET /health` returns a small JSON response:

```json
{
  "status": "ok",
  "service": "simulation-backend",
  "api_version": "1",
  "simulation_active": false
}
```

The response may include a current simulation ID when one exists.

### FR-PY-003: Simulation configuration validation

Create typed request/response schemas. Validate:

- Sender count: 1–10.
- Receiver count: 1–10.
- Mixnet node count: initial supported range 10–20.
- Exchange count: positive bounded integer.
- Outage durations: non-negative and logically valid.
- Playback delay: bounded positive integer in milliseconds.
- Pairing strategy: one of the supported enumerated values.
- Random seed: optional integer.
- Configuration values that conflict must return useful validation messages.

### FR-PY-004: Create simulation

Provide an HTTP endpoint such as:

`POST /api/simulations`

It receives a validated configuration and returns:

- `simulation_id`
- `random_seed`
- generated people
- generated Tor instances
- generated mixnet nodes
- generated DHT nodes
- generated storage nodes
- generated initial topology
- conversation/pairing plan
- initial availability state
- initial routing-table snapshots
- configuration summary

The create operation must not start message traffic.

### FR-PY-005: Simulation lifecycle

Support:

- create
- run
- pause
- resume
- step
- stop
- reset

Commands must be idempotent where appropriate. Invalid lifecycle transitions must return clear errors.

### FR-PY-006: Event scheduler

Implement a deterministic event scheduler. It should process one simulation event/step at a time and publish an event to connected frontend clients.

The scheduler must support:

- message processing events
- polling events
- routing decisions
- node state changes
- timeouts
- retries
- batch release events
- storage and DHT events
- message reconstruction/decryption events

Do not scatter arbitrary `asyncio.sleep()` calls throughout domain objects. The scheduler owns pacing and event execution.

### FR-PY-007: Playback delay

The playback delay is a central configuration value, initially 500 ms.

- It is expressed in milliseconds.
- The frontend slider sends updates to Python.
- Python reads the current delay between steps.
- A delay update should affect the next step without restarting the simulation.
- It should not interrupt an operation halfway through.
- The delay is not simulation time.
- The UI should display the current value.
- Suggested slider range: 100–2000 ms, with a sensible step such as 100 ms.
- The backend must validate values.

### FR-PY-008: Deterministic randomisation

Use a per-simulation seeded random-number generator. Do not use unrelated global random calls throughout the code.

All random decisions should use the simulation RNG, including:

- node count if randomised
- node IDs where suitable (cryptographic IDs should use secure randomness where required)
- generated simulated addresses
- initial topology
- peer discovery order
- route candidate selection
- node failure times
- outage durations
- conversation pairing when random
- message scheduling where random

Separate cryptographic randomness from reproducible simulation randomness. A deterministic simulation seed must not make cryptographic keys predictable. Use a cryptographically secure random source for keys, nonces and secret material.

---

# 4. Domain model and Python object architecture

## 4.1 General object design

Use explicit domain classes. The network-level manager owns a collection of node instances; it must not replace the behaviour of the individual nodes.

Prefer composition over inheritance where it improves clarity.

Each simulated object should have:

- stable ID
- type
- state
- relevant configuration
- event/log context
- serialisation method or DTO mapping for frontend display

Do not serialise arbitrary Python objects directly to JSON. Use explicit Pydantic response/event models.

## 4.2 Person

One shared `Person` class represents all users.

Alice, Bob, Carol and David are separate instances, not separate subclasses.

Suggested properties:

- `person_id`
- `display_name`
- `participant_role` or scenario role
- `public_key`
- `private_key_reference`
- `mailbox_id`
- `tor_network_id`
- `outgoing_messages`
- `received_messages`
- `polling_config`
- `client_state`
- `created_at_sim_time`

The private key must never be sent to the frontend as a normal telemetry field. Do not include private key bytes in logs, event payloads or node inspectors.

The frontend may display a key fingerprint and public key, but not private key material.

## 4.3 Alice and Bob behaviour

Alice and Bob use the same `Person` implementation.

Alice may:

- retrieve Bob's published public key from a simulated public webpage/public-key source
- compose a message
- encrypt the message for Bob
- include a sender reply public key inside the encrypted payload/bundle, subject to the protocol limitation described below
- submit the encrypted envelope through her own Tor abstraction
- observe sending progress

Bob may:

- poll for new messages through his own Tor abstraction
- discover an available message/manifest
- retrieve the encrypted manifest and fragments
- reconstruct the encrypted payload
- decrypt using his private key
- read the message
- compose and send a reply using the reply public key carried inside the decrypted bundle

The first implementation may use simulated public-key publication/retrieval. It must not require a pre-existing shared secret or a prior contact registration.

### Security limitation that must be visible in documentation

A public key embedded inside an encrypted message can provide a reply destination after Bob decrypts the message. By itself, it does **not** cryptographically prove that the sender owns that key. Anyone can encrypt a message to Bob's public key and include an arbitrary sender public key.

Do not silently claim sender authentication. For the MVP:
- implement recipient confidentiality;
- carry the sender's reply public key inside the encrypted content;
- label sender identity as unverified unless a separate authentication mechanism is specified;
- document the limitation in the UI or technical notes.

Do not add a signature requirement as a prerequisite to sending in this MVP. Keep an authentication extension point for a later protocol decision.

## 4.4 TorNetwork

Tor must be represented as a proper object for consistency, but it is an abstraction.

Each `Person` owns an independent `TorNetwork` instance:

- `alice.tor_network`
- `bob.tor_network`
- and so on.

Suggested properties:

- `tor_id`
- `owner_person_id`
- `status`
- `entry_event_count`
- `exit_event_count`
- `last_activity`
- `simulated_exit_identity`

Responsibilities:

- accept a request from its owner
- emit a Tor-entry event
- abstractly forward the request to the mixnet ingress
- emit a Tor-exit/delivery event
- return the response to its owner
- model availability/failure if configured

Do not implement Tor circuits, relays, onion encryption, guard selection or real Tor networking. Tor is a single simulated component/function boundary. Its internal relay path is intentionally outside scope.

The diagram must show Alice's Tor and Bob's Tor as separate instances.

## 4.5 Mixnet manager

One `Mixnet` object manages multiple `MixNode` instances.

Responsibilities:

- create and manage mix nodes
- provide configured bootstrap peers
- manage the simulated peer discovery environment without giving nodes omniscient knowledge
- coordinate network-level registration/discovery events
- expose topology snapshots for the UI
- provide access to node lookup by ID for simulation orchestration
- not make every route decision on behalf of a node

The `Mixnet` manager is a simulation-level registry/manager. Do not represent it as a real central production authority.

## 4.6 MixNode

Every mix node is an independent object.

Suggested properties:

- `node_id`
- `simulated_address`
- `operator_id`
- `status`
- `availability_controller`
- `routing_table`
- `inbound_queue`
- `outbound_queue`
- `batch_buffer`
- `known_peers`
- `failed_peers`
- `last_seen_by_peer`
- `failure_count`
- `mixing_config`
- `created_at_sim_time`

A mix node can handle both incoming and outgoing traffic. Do not create separate node classes for sending and receiving unless a future protocol design requires it.

Responsibilities:

- receive an envelope
- validate that it is online and able to process
- add a message to a batch buffer where mixing policy requires it
- shuffle/reorder a batch according to the simulation policy
- decide when a batch is released according to configured policy
- select a next peer from its local eligible routing table
- emit routing decision details
- forward to the selected peer
- handle acknowledgement or timeout
- retry through an alternative eligible peer within a bounded retry policy
- record failure and recovery events
- update local peer status based on observations

A mix node must not have a complete view of all nodes unless the scenario explicitly configures an omniscient test mode. Normal mode uses local peer knowledge.

## 4.7 Mixnet peer discovery and routing tables

Do not conflate mixnet peer discovery with Kademlia DHT lookup.

The mixnet needs a peer discovery/routing mechanism. Kademlia is used for the DHT layer, not automatically as the mixnet's forwarding algorithm.

For the MVP, implement a simple peer discovery model:

- one or more bootstrap peers are provided to a joining mix node;
- the joining node contacts a bootstrap peer;
- the bootstrap peer returns a limited set of known peers;
- the joining node stores those peers in its own local routing table;
- nodes may exchange peer information according to a configurable gossip/discovery policy;
- nodes do not automatically learn every node in the network;
- a node can have stale peer information;
- a peer may be offline even though the routing table still lists it;
- nodes can learn that a peer is unreachable only after a failed attempt or an explicit simulated status update.

A future implementation may adopt a more formal peer-discovery protocol. Keep discovery behind an interface.

### Routing table entry

Suggested fields:

- `peer_node_id`
- `simulated_address`
- `last_seen_sim_time`
- `status_observation`
- `consecutive_failures`
- `successful_contact_count`
- `last_failure_sim_time`
- `routing_metadata`

The UI must distinguish:
- known online
- known offline
- unknown/stale
- unreachable after failed attempts

Do not claim that a node knows a peer's real-time availability unless it has received an observation or the simulation explicitly models a shared oracle.

## 4.8 Routing algorithm and retry

For each forwarding step:

1. The current node examines its own local routing table.
2. It filters out peers that are ineligible according to the current routing policy.
3. It records the candidate list.
4. It selects a next hop according to the configured routing policy.
5. It emits a routing-decision event before attempting delivery.
6. It attempts delivery.
7. If the peer is unavailable or does not acknowledge before timeout, the current node records the failure.
8. The current node updates its local view of that peer.
9. The current node selects another eligible peer, if available.
10. The process repeats until delivery succeeds or the retry limit is reached.

Requirements:

- retry count is bounded;
- no infinite loops;
- prevent immediate selection of the same failed peer unless explicitly configured;
- avoid routing loops using message/route metadata and hop limits;
- expose all decisions and failures to the event stream;
- do not make the UI choose a fallback route;
- do not silently drop messages.

A node cannot know with certainty whether a remote peer is offline merely because one request timed out. Represent the result as a timeout/unresponsive observation, not an omniscient fact.

## 4.9 DHT layer

The DHT is a separate subsystem.

Objects:

- `DHTNetwork`
- `DHTNode`
- `DHTRoutingTable`
- `DHTRecord`
- `MailboxManifestRecord` or equivalent record type

Use a Kademlia-inspired model for DHT lookup and routing.

Each `DHTNode` has:

- unique node ID
- simulated address
- local Kademlia routing table
- locally stored records
- availability state
- peer observation state

Kademlia node IDs and XOR distance are used for DHT peer lookup. Do not describe this as the mixnet's message-forwarding algorithm.

The DHT stores lookup/manifest metadata, not plaintext message content.

The design must avoid a central index that maps Bob's real-world identity directly to every fragment location. The mailbox lookup identifier and record format should be designed as privacy-preserving opaque values. The precise privacy construction is a protocol decision and must be documented rather than invented.

## 4.10 Storage layer

Objects:

- `StorageNetwork`
- `StorageNode`
- `Fragment`
- `MessageManifest`

Each `StorageNode` has:

- `node_id`
- simulated address
- operator ID
- availability state
- local fragment store
- capacity/configuration
- failure history

Storage nodes store encrypted fragments only.

The first implementation should support:
- splitting an encrypted payload into fragments/chunks;
- assigning fragments across multiple storage nodes;
- recording fragment IDs and placement metadata;
- retrieving fragments by ID;
- simulating unavailable storage nodes;
- retrying retrieval from alternative replicas where replicas exist;
- reconstructing the payload once enough valid fragments are retrieved.

Do not claim erasure coding unless it is actually implemented. The MVP may use simple chunk splitting plus replication. If erasure coding is added, define the coding scheme and reconstruction threshold explicitly.

The UI should show:
- fragment ID
- owning storage node(s)
- encrypted size
- placement state
- retrieval attempts
- integrity/hash result
- whether the fragment was used in reconstruction

## 4.11 Message manifest

The manifest describes how Bob can retrieve and reconstruct a message.

Potential fields:

- opaque message/manifest identifier
- encrypted payload metadata
- fragment IDs
- storage placement references or opaque retrieval references
- fragment count
- reconstruction requirements
- cryptographic version/algorithm identifiers
- nonce and ephemeral public key metadata required by the encryption construction
- sender reply public key inside the encrypted content, not exposed as plaintext metadata unless the protocol explicitly allows it

The manifest's privacy properties are not fully specified. Do not assume that encrypting a manifest with Bob's public key automatically solves all metadata leakage. Document which fields are visible to DHT/storage nodes and which are encrypted.

## 4.12 Simulation support objects

Suggested objects:

- `Simulation`
- `SimulationConfig`
- `SimulationRNG`
- `EventScheduler`
- `PlaybackController`
- `EventBus`
- `TopologySnapshotBuilder`
- `AttackerObserver` / `NetworkObserver`

`Simulation` owns a single run and all of its domain objects.

`EventScheduler` orders and executes simulation events.

`PlaybackController` controls the real-time pause between visible steps.

`EventBus` publishes typed events to the WebSocket layer.

`NetworkObserver` records what an observer can see. It must not have access to hidden internal state unless the selected observer model explicitly grants it.

---

# 5. Cryptography requirements

## 5.1 General rule

Cryptography runs in Python for this simulator. The browser is not the cryptographic engine.

Use a maintained, reputable Python cryptography library. Do not implement cryptographic primitives manually.

The initial candidate construction discussed for the project is:

- X25519 for ephemeral key agreement;
- HKDF-SHA-256 for deriving an encryption key;
- AES-256-GCM for authenticated message encryption;
- SHA-256 for hashing/integrity identifiers;
- Ed25519 may be considered for a later authentication/signature extension, but must not become a prerequisite for the MVP send flow.

Use a maintained library such as Python `cryptography` for supported primitives. Confirm the library's actual algorithm support and API version during implementation.

## 5.2 Message encryption flow

For the MVP recipient-confidentiality flow:

1. Bob has an X25519 key pair.
2. Bob's public key is published through a simulated public webpage/public-key source.
3. Alice retrieves Bob's public key.
4. Alice generates an ephemeral X25519 key pair.
5. Alice computes a shared secret using her ephemeral private key and Bob's public key.
6. HKDF derives an AES-256-GCM key.
7. Alice encrypts the message payload using a fresh nonce.
8. The envelope carries the ephemeral public key, nonce, ciphertext and version/algorithm metadata.
9. Bob uses his private key and the ephemeral public key to derive the same shared secret and decrypt.
10. The encrypted content may include Alice's reply public key so Bob can encrypt a reply to Alice.

Do not reuse nonces with the same AES-GCM key.

Use fresh ephemeral key material for each message unless a separately specified session protocol is introduced.

## 5.3 Important protocol limitation

The sender reply public key carried inside the encrypted payload allows Bob to address a reply to that key after decryption. It does not authenticate the sender's identity. The UI and technical documentation must make that distinction clear.

Do not claim forward secrecy for the whole messaging system merely because ephemeral X25519 is used. The exact key lifecycle, private-key retention, replay protection, sender authentication and compromise model need a later protocol review.

## 5.4 Cryptographic data visibility

- Never send private keys to the frontend.
- Never include private keys in logs.
- Do not display plaintext message content in storage-node or DHT inspectors.
- The Person/client inspector may show plaintext only when that client legitimately has decrypted it.
- The event stream should show ciphertext metadata, sizes, hashes and identifiers, not plaintext by default.
- Use redacted payload previews for sensitive data.
- Keep encryption/decryption operations as explicit simulation events.

---

# 6. Simulation time, playback and scheduling

## 6.1 Separate clocks

The implementation must keep these concepts separate:

### Simulation clock

A logical clock used for:
- outage start/end;
- polling intervals;
- timeouts;
- retry backoff;
- batch release;
- message scheduling;
- peer last-seen timestamps.

### Playback delay

A wall-clock pause between simulation steps, configured by the user.

Initial default: 500 ms.

The user can change it while the simulation is running. Python applies the new delay before the next step.

Changing playback delay must not change the simulated duration of an outage or timeout.

## 6.2 Event-driven simulation

Prefer a priority queue of scheduled events ordered by logical simulation time and deterministic sequence number.

Example event types:

- `NODE_GOES_OFFLINE`
- `NODE_RECOVERS`
- `MESSAGE_CREATED`
- `MESSAGE_ENCRYPTED`
- `TOR_ENTRY`
- `TOR_EXIT`
- `MIX_MESSAGE_RECEIVED`
- `MIX_BATCH_RELEASED`
- `ROUTE_SELECTED`
- `FORWARD_ATTEMPT`
- `FORWARD_TIMEOUT`
- `FORWARD_ACKNOWLEDGED`
- `DHT_LOOKUP_STARTED`
- `DHT_LOOKUP_COMPLETED`
- `FRAGMENT_STORED`
- `BOB_POLL_STARTED`
- `BOB_POLL_EMPTY`
- `BOB_POLL_MESSAGE_FOUND`
- `FRAGMENT_RETRIEVAL_STARTED`
- `FRAGMENT_RETRIEVED`
- `MESSAGE_RECONSTRUCTED`
- `MESSAGE_DECRYPTED`
- `REPLY_CREATED`

The scheduler processes the next event, publishes it, and waits the configured playback delay before advancing to the next visible step.

A future fast-forward mode may process many logical events without a playback pause, but it is not required for the first implementation.

## 6.3 Node availability schedule

Each node has an availability controller that schedules transitions.

Support:
- random independent outages;
- bursty/correlated outage scenarios;
- scheduled outages;
- always online;
- always offline;
- manual offline/online commands.

The random outage generator should support:
- configurable failure probability/rate;
- minimum outage duration;
- maximum outage duration;
- minimum online duration between outages;
- optional initial offline probability;
- optional full-run offline probability.

Do not use a uniform random outage duration by default without making the distribution explicit. A configurable distribution is preferable. For the MVP, implement a documented uniform distribution and make the duration distribution an extension point.

A node can recover during a long-running simulation. Availability changes must be scheduled even while the user changes playback delay.

---

# 7. Frontend requirements

## 7.1 Technology

- SvelteKit
- TypeScript
- D3 for graph layout/interaction
- SVG for network nodes, edges and route animation
- CSS variables/design tokens for visual styling
- WebSocket client for Python event stream

Avoid adding a large UI component framework unless there is a clear need. Keep the dashboard technically styled and customisable.

## 7.2 Visual design

The interface should look like a serious infrastructure engineering platform or network operations console.

### Palette

| Token | Suggested value | Usage |
|---|---|---|
| `--bg` | `#17191C` | Main background |
| `--panel` | `#22262B` | Panels |
| `--panel-raised` | `#292D32` | Raised cards |
| `--border` | `#454B53` | Borders/dividers |
| `--text` | `#E5E7EB` | Primary text |
| `--muted` | `#9299A2` | Secondary text |
| `--success` | muted green | Online/success |
| `--warning` | muted amber | Recovering/timeout warning |
| `--danger` | muted red | Offline/failure |
| `--accent` | restrained cool blue/grey | Selection/focus |

Use status colours sparingly. Most of the interface should be monochrome grey.

### Typography

- Clear technical sans-serif for UI labels and headings.
- Monospace for IDs, addresses, hashes, ports, timestamps and event payload metadata.
- Compact but readable data tables.
- Avoid oversized consumer-style cards and bright gradients.

## 7.3 Main application screens/areas

### A. Backend connection screen

Fields/actions:
- Python endpoint or port input.
- Test connection.
- Connect/disconnect.
- Connection status.
- Resolved HTTP URL.
- Resolved WebSocket URL.
- Backend API version.
- Error display.

### B. Simulation configuration

Sections:
1. Network size.
2. Participant counts.
3. Conversation pairing.
4. Message/exchange count.
5. Node failure configuration.
6. Playback delay.
7. Random seed / reproducibility.

### C. Network topology

Main visual area showing:
- people;
- each person's Tor object;
- mixnet manager/network boundary if useful;
- individual mixnet nodes;
- DHT nodes;
- storage nodes;
- connections known to the selected view;
- actual selected message route;
- offline/recovering states.

Use D3 to calculate/maintain graph layout. Use SVG for nodes and edges.

The graph must not imply that every possible network link exists. Display known/observed links according to Python topology and routing-table data.

### D. Node inspector

When a node is selected, show:
- node ID;
- type;
- simulated address;
- operator ID;
- availability state;
- uptime/outage history;
- last state transition;
- inbound/outbound queue counts;
- current batch state if a mix node;
- failure count;
- last activity;
- routing table tab;
- event history tab.

### E. Routing-table inspector

For a selected mixnet node, show:
- peer ID;
- simulated address;
- last seen;
- observed status;
- consecutive failures;
- success count;
- last failure;
- routing eligibility;
- selection/highlight action.

Selecting a peer highlights it in the graph.

### F. Event stream and timeline

Show chronological events with:
- logical simulation time;
- playback sequence number;
- event type;
- source object;
- destination object, if any;
- message/conversation ID, if relevant;
- concise summary;
- expandable details.

Filters:
- all events;
- participants;
- Tor;
- mixnet;
- DHT;
- storage;
- routing;
- availability;
- polling;
- encryption/decryption;
- failures/retries.

### G. Simulation controls

- Create simulation
- Run
- Pause
- Resume
- Step
- Stop
- Reset
- Playback delay slider

The delay slider should remain available during execution.

---

# 8. D3 network visualisation requirements

## 8.1 Data ownership

Python supplies authoritative graph data:
- nodes;
- edges/known peer relationships;
- node types;
- node states;
- route events;
- routing-table updates.

D3 may calculate visual positions and force layout. It must not create authoritative network relationships or make routing decisions.

## 8.2 Node visual treatment

Use distinct but restrained visual treatments for:
- Person
- TorNetwork
- MixNode
- DHTNode
- StorageNode

Each node should have:
- visible short label;
- stable ID in tooltip/inspector;
- status indicator;
- selected state;
- hover state.

## 8.3 Edge visual treatment

Edges should distinguish:
- configured/known peer connection;
- currently selected route;
- attempted route;
- failed route;
- unavailable/stale connection.

Do not draw all nodes as fully connected unless the topology data says so.

## 8.4 Route animation

When Python emits a forwarding event:
- highlight the source node;
- highlight the edge actually used;
- animate a message marker along the edge;
- highlight the destination;
- update the event timeline;
- preserve the route history for inspection.

On failure:
- mark the attempted edge as failed;
- show timeout/rejection;
- then animate the retry route when Python selects it.

The animation is a visual representation of Python events, not a second route simulation.

## 8.5 Performance

- Avoid rerendering the entire graph for every event.
- Apply incremental node/edge/state updates.
- Keep D3 simulation/layout work isolated from Svelte component state where practical.
- Use stable keys/IDs.
- Provide a pause/freeze layout option if useful.
- Ensure the event stream does not cause the graph to become unresponsive.

---

# 9. Backend API and WebSocket contract

The following endpoint names are proposed and may be refined during implementation, but the responsibilities must remain.

## 9.1 HTTP endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Backend health and version |
| GET | `/api/info` | Runtime info, selected port, capabilities |
| POST | `/api/simulations` | Create simulation from config |
| GET | `/api/simulations/{id}` | Read simulation metadata/state |
| GET | `/api/simulations/{id}/topology` | Current topology snapshot |
| POST | `/api/simulations/{id}/run` | Start/resume execution |
| POST | `/api/simulations/{id}/pause` | Pause |
| POST | `/api/simulations/{id}/step` | Execute one step |
| POST | `/api/simulations/{id}/stop` | Stop |
| POST | `/api/simulations/{id}/reset` | Reset/recreate state if supported |

Use Pydantic models for all request and response bodies.

## 9.2 WebSocket

Endpoint:

`ws://127.0.0.1:<actual-port>/ws`

The frontend connects after the health check.

The WebSocket supports commands from frontend to Python and events from Python to frontend.

### Frontend commands

- `subscribe`
- `run`
- `pause`
- `resume`
- `step`
- `stop`
- `set_playback_delay`
- `request_topology`
- `request_node_details`
- `request_routing_table`
- `set_node_availability` (manual test control)
- `ping`

Every command should include a command ID and simulation ID when relevant.

### Backend events

- `backend_ready`
- `simulation_created`
- `simulation_started`
- `simulation_paused`
- `simulation_resumed`
- `simulation_stopped`
- `simulation_step_started`
- `simulation_step_completed`
- `topology_snapshot`
- `node_created`
- `node_status_changed`
- `routing_table_updated`
- `routing_decision`
- `message_forward_attempt`
- `message_forward_failed`
- `message_forward_succeeded`
- `mix_batch_received`
- `mix_batch_released`
- `dht_lookup_started`
- `dht_lookup_completed`
- `fragment_stored`
- `fragment_retrieval_started`
- `fragment_retrieved`
- `bob_poll_started`
- `bob_poll_empty`
- `bob_poll_message_found`
- `message_reconstructed`
- `message_decrypted`
- `playback_delay_updated`
- `simulation_error`

### Event envelope

Use a consistent event envelope:

```json
{
  "event_id": "evt-000001",
  "event_type": "routing_decision",
  "simulation_id": "sim-000001",
  "sequence": 42,
  "simulation_time_ms": 12500,
  "source_id": "mix-node-a",
  "target_id": "mix-node-c",
  "message_id": "msg-000001",
  "conversation_id": "conv-000001",
  "payload": {
    "candidate_peer_ids": ["mix-node-b", "mix-node-c"],
    "excluded_peer_ids": ["mix-node-d"],
    "selected_peer_id": "mix-node-c",
    "selection_reason": "eligible_random_candidate"
  }
}
```

The sample is illustrative. Use typed schemas and stable field names.

### WebSocket reliability

- Handle disconnects cleanly.
- Reconnect with bounded exponential backoff.
- On reconnect, request current simulation state/topology and last known sequence.
- Do not assume every event was received during a disconnect.
- The backend should maintain enough current state to resynchronise the frontend.
- Event history persistence may be in-memory for the MVP.
- A reconnect should not automatically restart or duplicate the simulation.

---

# 10. Configuration schema

Use a typed configuration model. Suggested shape:

```json
{
  "network": {
    "mixnet": {
      "min_nodes": 10,
      "max_nodes": 20,
      "randomize_count": true
    },
    "dht": {
      "node_count": 8
    },
    "storage": {
      "node_count": 12,
      "replication_factor": 2
    }
  },
  "participants": {
    "sender_count": 3,
    "receiver_count": 1
  },
  "conversations": {
    "pairing_strategy": "all_to_one",
    "exchanges_per_conversation": 5
  },
  "messages": {
    "payload_size_bytes": 512
  },
  "availability": {
    "pattern": "random",
    "failure_probability": 0.1,
    "min_outage_duration_ms": 500,
    "max_outage_duration_ms": 500000,
    "min_online_duration_ms": 1000,
    "always_offline_probability": 0.02,
    "always_online_probability": 0.05
  },
  "routing": {
    "max_hops": 12,
    "max_retries_per_hop": 2,
    "ack_timeout_ms": 1000
  },
  "playback": {
    "step_delay_ms": 500
  },
  "random_seed": 12345
}
```

This is a proposed initial schema. Validate ranges and make all defaults visible in the UI. The exact DHT/storage node counts can be configurable even if the first UI uses sensible defaults.

The number of senders and receivers is the number of `Person` instances created. The pairing strategy defines which people communicate.

### Pairing strategy semantics

- `all_to_one`: all senders communicate with one selected receiver. If receiver count is greater than one, the selected receiver must be explicitly chosen or generated according to a documented rule.
- `one_to_all`: one selected sender communicates with all receivers.
- `one_to_one_pairs`: generate one-to-one pairs; validate or explain when counts differ.
- `random_pairs`: generate a configurable set of sender/receiver pairs using the simulation RNG.

Do not silently assume all senders talk to all receivers.

---

# 11. Suggested project structure

Use a monorepo-style local project:

```text
distributed-messaging-simulator/
├── README.md
├── implementation.md
├── pyproject.toml
├── package.json
├── .gitignore
├── backend/
│   ├── main.py
│   ├── app/
│   │   ├── __init__.py
│   │   ├── api/
│   │   │   ├── routes.py
│   │   │   ├── health.py
│   │   │   └── websocket.py
│   │   ├── config/
│   │   │   ├── settings.py
│   │   │   └── simulation_config.py
│   │   ├── domain/
│   │   │   ├── person.py
│   │   │   ├── tor_network.py
│   │   │   ├── mixnet.py
│   │   │   ├── mix_node.py
│   │   │   ├── dht_network.py
│   │   │   ├── dht_node.py
│   │   │   ├── storage_network.py
│   │   │   ├── storage_node.py
│   │   │   ├── fragment.py
│   │   │   ├── manifest.py
│   │   │   └── conversation.py
│   │   ├── simulation/
│   │   │   ├── simulation.py
│   │   │   ├── scheduler.py
│   │   │   ├── event_bus.py
│   │   │   ├── playback.py
│   │   │   ├── availability.py
│   │   │   ├── routing.py
│   │   │   ├── peer_discovery.py
│   │   │   └── topology.py
│   │   ├── crypto/
│   │   │   ├── key_manager.py
│   │   │   ├── encryption.py
│   │   │   └── serialization.py
│   │   ├── schemas/
│   │   │   ├── config.py
│   │   │   ├── commands.py
│   │   │   ├── events.py
│   │   │   └── responses.py
│   │   └── services/
│   │       ├── simulation_service.py
│   │       └── port_discovery.py
│   └── tests/
│       ├── unit/
│       ├── integration/
│       └── fixtures/
└── frontend/
    ├── package.json
    ├── svelte.config.js
    ├── vite.config.ts
    └── src/
        ├── routes/
        │   ├── +page.svelte
        │   └── +layout.svelte
        ├── lib/
        │   ├── api/
        │   │   ├── http.ts
        │   │   └── websocket.ts
        │   ├── components/
        │   │   ├── ConnectionPanel.svelte
        │   │   ├── SimulationConfig.svelte
        │   │   ├── NetworkGraph.svelte
        │   │   ├── NodeInspector.svelte
        │   │   ├── RoutingTable.svelte
        │   │   ├── EventTimeline.svelte
        │   │   └── PlaybackControls.svelte
        │   ├── d3/
        │   │   ├── graph-layout.ts
        │   │   ├── graph-renderer.ts
        │   │   └── route-animation.ts
        │   ├── stores/
        │   │   ├── connection.ts
        │   │   ├── simulation.ts
        │   │   ├── topology.ts
        │   │   └── events.ts
        │   ├── types/
        │   │   ├── api.ts
        │   │   ├── events.ts
        │   │   └── topology.ts
        │   └── styles/
        │       └── tokens.css
        └── app.css
```

The exact file structure may change if the implementation framework conventions require it, but keep the separation of responsibilities.

---

# 12. Testing strategy

## 12.1 Python unit tests

Test at minimum:

### Person and Tor
- Alice and Bob are instances of the same `Person` class.
- Each person has a distinct Tor instance.
- Each person has independent client state.
- A Tor instance forwards abstract requests and emits entry/exit events.
- Tor is not accidentally implemented as a real Tor client.

### Mixnet
- Mixnet creates the configured number of nodes.
- Each node has a unique ID.
- Each node has an independent routing table.
- Nodes do not automatically receive complete network knowledge.
- Peer discovery updates local routing tables.
- A node can select a known eligible peer.
- An offline peer causes a timeout/failure event.
- The node retries using a different eligible peer.
- Retry limits are respected.
- Routing loops are bounded.

### DHT
- DHT nodes have unique IDs.
- XOR distance is calculated correctly.
- DHT routing is separate from mixnet routing.
- Lookup can fail when nodes are unavailable.
- Records can be stored and retrieved.

### Storage
- Fragments are distributed among configured storage nodes.
- A node can become unavailable.
- Retrieval from an unavailable node fails.
- Replicas can be tried when configured.
- Reassembly succeeds when all required fragments are present.
- Reassembly fails clearly when requirements are not met.
- Hash/integrity checks detect corruption.

### Availability
- Same seed produces same availability schedule.
- Different seed normally produces a different schedule.
- Nodes can have 500 ms simulated outages.
- Nodes can have 300–500 second simulated outages.
- A node can remain offline for the entire run.
- A node can remain online for the entire run.
- Recovery makes a node eligible again.
- Playback delay changes do not change logical outage duration.

### Scheduler/playback
- Events execute in logical time order.
- Same seed and same configuration produce reproducible non-cryptographic simulation decisions.
- Playback delay is read between steps.
- Updating delay while running changes the next inter-step pause.
- Pausing prevents the next event from executing.
- Stepping executes exactly one event/step.
- Resume continues from the current state.

### Cryptography
- Alice can encrypt a test message to Bob.
- Bob can decrypt it with his private key.
- A wrong private key cannot decrypt it successfully.
- Fresh nonces/ephemeral keys are used according to the chosen construction.
- Private keys are not included in event payloads or API responses.
- Sender reply public key is recoverable only after decrypting the payload.
- Tests do not claim sender authentication from the embedded reply key.

## 12.2 API and integration tests

- Health endpoint responds.
- Port selection falls back when 8000 is occupied.
- Startup prints the actual bound port.
- Create simulation validates input.
- Create simulation returns generated topology.
- Create simulation does not start message traffic.
- Run starts the scheduler.
- Pause/resume/step/stop work.
- WebSocket receives events.
- Playback-delay command updates the backend.
- Manual node availability commands work.
- Invalid commands return useful errors.
- Reconnect can resynchronise from current state.

## 12.3 Frontend tests

- Connection screen renders without backend.
- Port input resolves endpoint URLs correctly.
- Full HTTP URL input resolves WebSocket URL correctly.
- Health-check failure is displayed.
- WebSocket connection status updates.
- Configuration sliders enforce limits.
- Create simulation sends the expected configuration.
- Topology renders only from backend data.
- Selecting a node opens the correct inspector.
- Routing table updates when backend sends updates.
- Route events animate the actual selected route.
- Offline/recovery events update node status.
- Playback slider sends updates to Python.
- UI remains responsive during event streaming.

## 12.4 End-to-end acceptance scenario

Use a reproducible configuration:

- 3 senders
- 1 receiver
- 15 mixnet nodes
- 5 exchanges per conversation
- 500 ms playback delay
- deterministic seed
- one mix node configured to fail during the run
- one short outage and one long outage

Expected result:

1. Python creates three sender `Person` instances and one receiver `Person` instance.
2. Each person gets an independent Tor abstraction.
3. Python generates the mixnet, DHT and storage nodes.
4. The UI renders the returned topology.
5. Three conversations are created between the senders and the receiver, according to the configured pairing.
6. Messages are encrypted and sent through the simulated Tor/mixnet path.
7. Mix nodes make and publish routing decisions.
8. At least one route attempt encounters an unavailable/unresponsive peer.
9. The sending node retries through another eligible peer, if one exists.
10. Bob polls for available messages.
11. Bob retrieves the required encrypted fragments.
12. Bob reconstructs and decrypts messages.
13. Replies can be sent using the sender reply public key included in the encrypted content.
14. The UI shows all relevant events, route changes, node states and routing-table updates.
15. The same simulation seed reproduces the same non-cryptographic network/failure decisions.

---

# 13. Implementation phases and task order

Implement in this order. Do not start with the D3 UI.

## Phase 1 — Project foundation

- [ ] Create monorepo directory structure.
- [ ] Add Python project configuration and dependencies.
- [ ] Add SvelteKit TypeScript project.
- [ ] Add formatting/lint/test tooling.
- [ ] Add README with two-terminal startup instructions.
- [ ] Add central configuration models.
- [ ] Add typed API and event schemas.
- [ ] Add test infrastructure.

**Exit criteria:** Python and SvelteKit start independently; basic tests pass.

## Phase 2 — Python server and endpoint discovery

- [ ] Implement local port selection starting at 8000.
- [ ] Bind the server socket robustly.
- [ ] Start FastAPI/Uvicorn on the selected socket.
- [ ] Print actual HTTP and WebSocket endpoints.
- [ ] Implement `/health`.
- [ ] Implement `/api/info`.
- [ ] Add startup/shutdown tests.

**Exit criteria:** backend reliably starts on the first available port and prints the correct address.

## Phase 3 — Domain objects

- [ ] Implement `Person`.
- [ ] Implement `TorNetwork`.
- [ ] Implement `Mixnet`.
- [ ] Implement `MixNode`.
- [ ] Implement `DHTNetwork` and `DHTNode`.
- [ ] Implement `StorageNetwork` and `StorageNode`.
- [ ] Implement `Fragment` and `MessageManifest`.
- [ ] Implement `Conversation`.
- [ ] Implement explicit DTO/topology serialisation.
- [ ] Test object identity, ownership and uniqueness.

**Exit criteria:** Python can generate a complete object graph from a configuration without running message traffic.

## Phase 4 — Peer discovery and routing

- [ ] Implement mixnet bootstrap peer configuration.
- [ ] Implement local peer discovery.
- [ ] Implement per-node routing tables.
- [ ] Implement peer observations and stale status.
- [ ] Implement candidate filtering.
- [ ] Implement next-hop selection.
- [ ] Implement bounded retries and timeout outcomes.
- [ ] Implement hop limits and loop prevention.
- [ ] Emit detailed routing-decision events.
- [ ] Test route selection and failure recovery.

**Exit criteria:** each node has local knowledge and can route/retry without a global route decision being made by JavaScript.

## Phase 5 — Availability and scheduler

- [ ] Implement per-node availability controller.
- [ ] Implement seeded failure scheduling.
- [ ] Support short, long, always-offline and always-online cases.
- [ ] Implement deterministic event scheduler.
- [ ] Implement simulation clock.
- [ ] Implement separate playback delay controller.
- [ ] Implement pause/resume/step/stop.
- [ ] Implement manual availability controls.
- [ ] Test reproducibility and timing separation.

**Exit criteria:** nodes change state during a simulation and routing reacts to those changes.

## Phase 6 — DHT and storage

- [ ] Implement Kademlia-inspired DHT node IDs and XOR distance.
- [ ] Implement DHT routing tables and lookup.
- [ ] Implement opaque mailbox/manifest lookup identifiers.
- [ ] Implement encrypted payload chunking.
- [ ] Implement fragment placement and replication.
- [ ] Implement fragment retrieval and retry.
- [ ] Implement reconstruction and integrity checking.
- [ ] Emit storage/DHT events.
- [ ] Test unavailable DHT/storage nodes.

**Exit criteria:** encrypted payloads can be represented by distributed fragments and retrieved through the simulated lookup/storage flow.

## Phase 7 — Cryptographic message flow

- [ ] Select and document the maintained Python cryptography library/version.
- [ ] Implement X25519 key agreement.
- [ ] Implement HKDF-SHA-256 key derivation.
- [ ] Implement AES-256-GCM encryption/decryption.
- [ ] Implement Bob public-key publication/retrieval abstraction.
- [ ] Implement ephemeral sender key material.
- [ ] Include sender reply public key in encrypted content.
- [ ] Ensure private keys never leave the Python backend.
- [ ] Test successful and failed decryption.
- [ ] Document sender-authentication limitation.

**Exit criteria:** Alice can encrypt for Bob, the simulated network carries ciphertext, Bob decrypts, and Bob can address a reply to the embedded reply public key.

## Phase 8 — Conversation and polling workflow

- [ ] Generate sender and receiver `Person` instances from configuration.
- [ ] Implement pairing strategies.
- [ ] Generate conversation IDs.
- [ ] Generate message IDs.
- [ ] Implement configurable exchanges.
- [ ] Implement Bob/client polling.
- [ ] Ensure no unsolicited push notification is delivered to Bob.
- [ ] Implement reply flow.
- [ ] Test multiple senders communicating with one receiver.
- [ ] Test multiple receivers and pairing strategies.

**Exit criteria:** a complete multi-message conversation can run through the simulated network.

## Phase 9 — HTTP API and WebSocket event stream

- [ ] Implement create simulation endpoint.
- [ ] Implement simulation lifecycle endpoints.
- [ ] Implement WebSocket connection manager.
- [ ] Implement typed commands.
- [ ] Implement typed event envelopes.
- [ ] Implement event sequence numbers.
- [ ] Implement current-state/topology resynchronisation.
- [ ] Implement playback-delay updates.
- [ ] Implement manual node availability commands.
- [ ] Test disconnect/reconnect.

**Exit criteria:** a non-visual client can create and control a simulation and receive all events.

## Phase 10 — SvelteKit connection and configuration UI

- [ ] Build technical grey design tokens.
- [ ] Build initial backend connection screen.
- [ ] Accept port or full local endpoint.
- [ ] Derive HTTP and WebSocket URLs.
- [ ] Implement health check.
- [ ] Implement WebSocket connect/disconnect/reconnect.
- [ ] Display backend/API status.
- [ ] Build network/participant/conversation configuration form.
- [ ] Build failure configuration controls.
- [ ] Build playback delay slider.
- [ ] Create simulation through HTTP.
- [ ] Display returned simulation ID and configuration.

**Exit criteria:** frontend can connect to any correctly configured local backend port, create a simulation and control its lifecycle.

## Phase 11 — D3 topology and inspectors

- [ ] Build D3 graph layout.
- [ ] Render backend-supplied nodes and edges.
- [ ] Add zoom and pan.
- [ ] Add node selection.
- [ ] Build node inspector.
- [ ] Build routing-table inspector.
- [ ] Highlight selected peers and links.
- [ ] Apply incremental topology updates.
- [ ] Test graph responsiveness.

**Exit criteria:** the user can inspect the generated network and each node's current local peer knowledge.

## Phase 12 — Live routes, event timeline and final integration

- [ ] Animate actual Python-selected routes.
- [ ] Show attempted/failed/successful hops.
- [ ] Show retry route.
- [ ] Show batch receive/release events.
- [ ] Show node availability transitions.
- [ ] Show Bob polling and retrieval.
- [ ] Show DHT lookup and fragment placement/retrieval.
- [ ] Add event filters and detail panels.
- [ ] Add playback controls and live delay changes.
- [ ] Run end-to-end acceptance scenario.
- [ ] Produce test and coverage report.
- [ ] Update README and architecture notes.

**Exit criteria:** the full Alice-to-Bob multi-message simulation is visible and inspectable from the SvelteKit dashboard.

---

# 14. Operational instructions and developer experience

## 14.1 Start backend

From the repository root, use the documented Python environment/entry point. The intended command is:

```bash
python backend/main.py
```

The implementation may use a package entry point, but the README must provide one simple command.

Python prints the actual selected port.

## 14.2 Start frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open the URL printed by Vite, normally:

`http://localhost:5173`

## 14.3 Connect

- Copy the Python port or full endpoint printed by the backend.
- Paste it into the SvelteKit connection screen.
- Press **Test connection**.
- Press **Connect**.
- Configure the simulation.
- Press **Create simulation**.
- Inspect the generated topology.
- Press **Run**.

The backend and frontend must be independently restartable. Restarting the frontend must not automatically destroy a still-running Python simulation. Reconnecting should request current state.

## 14.4 Local security

- Bind to loopback (`127.0.0.1`) by default.
- Do not expose the backend on `0.0.0.0` by default.
- Do not enable permissive cross-origin access for arbitrary origins.
- Configure CORS for the local SvelteKit development origin.
- Validate WebSocket commands.
- Do not accept arbitrary filesystem paths or shell commands through the API.
- Do not expose private keys or plaintext message payloads in telemetry by default.

---

# 15. Open protocol decisions — do not silently invent answers

These decisions should remain explicit and be isolated behind interfaces until the user approves a protocol choice.

1. **Mixnet routing protocol:** the MVP uses local peer discovery and a documented selection policy. A production mixnet routing protocol has not been selected.
2. **Mixing policy:** batch size, minimum batch wait, cover traffic, dummy messages and release conditions require protocol decisions. The MVP should expose configurable simple batch/shuffle behaviour without claiming formal mixnet security.
3. **DHT privacy:** exact mailbox lookup-key construction and protection against metadata correlation require a separate design.
4. **Manifest confidentiality:** decide precisely which manifest fields are public, opaque or encrypted. Do not assume every field is hidden merely because the message payload is encrypted.
5. **Storage redundancy:** the MVP may use replication. Erasure coding is not implied and must not be claimed unless implemented.
6. **Sender authentication:** the embedded sender reply public key permits replies but does not authenticate the sender. No signature prerequisite is to be added to the MVP without approval.
7. **Replay protection:** define message nonce/ID handling and duplicate suppression.
8. **Polling cadence:** initial default and whether it is fixed, randomised or jittered need a configuration choice.
9. **Adversary model:** the observer views and attacker controls need explicit capabilities. Do not claim global traffic-analysis resistance from this simulator.
10. **Node operator model:** operators may own one or more nodes. Independence should be configurable so the simulator can model correlated failures or collusion later.

---

# 16. Definition of done

The first complete implementation is done when:

- [ ] Python starts locally and prints the actual HTTP/WebSocket port.
- [ ] SvelteKit starts independently with `npm run dev`.
- [ ] The frontend accepts the backend port/endpoint and connects successfully.
- [ ] The user can configure 1–10 senders and 1–10 receivers.
- [ ] The user can configure 10–20 mixnet nodes.
- [ ] The user can configure conversation pairing and message exchanges.
- [ ] Python creates all people and network objects.
- [ ] Every person has an independent Tor abstraction.
- [ ] Mixnet nodes have independent local routing tables.
- [ ] DHT nodes implement a separate Kademlia-inspired lookup model.
- [ ] Storage nodes hold encrypted fragments.
- [ ] Nodes randomly go offline and recover for configurable periods.
- [ ] Simulation time and playback delay are separate.
- [ ] The frontend can change playback delay while the simulation runs.
- [ ] Python makes routing decisions and emits them to the frontend.
- [ ] The UI displays actual message routes, failures and retries.
- [ ] The UI can inspect every node and its routing table.
- [ ] Bob polls for messages through his own client/Tor abstraction.
- [ ] Alice can encrypt a message for Bob and Bob can decrypt it.
- [ ] Bob can address a reply using the sender reply public key carried inside the encrypted message.
- [ ] The UI displays the event timeline and relevant message data without exposing private keys.
- [ ] The same seed reproduces the same non-cryptographic simulation scenario.
- [ ] Unit, integration and end-to-end tests pass.
- [ ] A test coverage report is provided.
- [ ] README documents startup, connection, configuration and controls.

---

# 17. Final instruction to Codex

Implement the specification in the phases above. Do not attempt to generate the entire application in one unstructured change.

Start by:
1. inspecting the repository and existing conventions;
2. reporting any conflicts between this specification and the existing codebase;
3. creating the implementation plan and task checklist;
4. implementing the Python foundation and tests before the UI;
5. committing each logical phase separately if Git is available.

At every phase:
- run relevant tests;
- report what changed;
- report test results;
- report coverage where available;
- identify any unresolved protocol decision;
- do not claim completion for functionality that is only represented visually.

The final product must be a working local simulation whose Python engine is authoritative and whose SvelteKit/D3 frontend faithfully visualises the events and state produced by that engine.

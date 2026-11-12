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

1. **Python is the simulation engine.** All simulated people, Tor abstractions, providers, mixnet nodes, DHT nodes, storage nodes, protocol state, node availability, route construction, message processing, chunking, manifests, polling, retries and simulation events are implemented in Python.
2. **SvelteKit is the web client.** It provides the connection screen, configuration controls, D3 network visualisation, node inspector, protocol-state and algorithm inspector, event stream, timeline and playback controls.
3. **FastAPI exposes the Python HTTP API and WebSocket.** The browser sends commands to Python and receives events from Python.
4. **Do not implement a second simulation engine in JavaScript.** JavaScript must not independently decide routes, generate node availability, perform DHT lookups, select storage nodes or simulate message delivery.
5. **The Python process starts separately from SvelteKit.** The developer starts Python in one terminal, then starts SvelteKit with `npm run dev` in another.
6. **The Python process chooses an available port and prints the actual endpoint.** The developer copies the printed port or endpoint into the SvelteKit connection screen. Do not silently assume port 8000.
7. **The simulation is generated only after the user connects and presses the create/run control.** Connecting to the backend must not automatically create the network.
8. **The playback delay is a display/execution pacing delay between simulation steps.** It is not a simulation-time multiplier and must not be conflated with outage durations or network timeouts.
9. **The first implementation is a local simulator.** It does not connect to the real Tor network, real DHT peers, public mixnet operators or real distributed storage.
10. **Do not claim the simulator proves anonymity or production security.** It is a model for exploring and testing protocol behaviour and failure cases.
11. **Every executable network step is an object.** Routing attempts, node transitions, polling, lookup, storage and retrieval actions must be represented by explicit Python `SimulationStep` objects rather than anonymous callbacks or untyped dictionaries.
12. **Every simulation owns one global observer.** The MVP `GlobalObserver` is a no-op placeholder: it has identity and lifecycle only, performs no observation, receives no privileged state and does not affect the simulation.
13. **Technology names are fidelity claims.** A node labelled as Loopix or Kademlia must execute the named, versioned reference algorithm and expose its parameters. Do not substitute a generic peer-routing or mixing approximation while retaining the technology label.
14. **The repository layout is fixed.** Python code, project metadata and tests live under `python/`; the SvelteKit/Vite client lives under `web/`. Do not create `backend/` or `frontend/` application directories.
15. **Abstractions must be labelled as abstractions.** The existing Tor boundary is a `Tor abstraction`, not a Tor implementation. Apply the same rule to any future component that does not execute a complete named reference protocol.
16. **Every traversable connection is a `NetworkPath` object.** It owns endpoints, transport label, state and simulated transit delay so Python can represent a message as in transit between nodes. Transit delay is separate from Loopix mix delay, logical outage duration and playback pacing.
17. **Tests are part of each implementation step.** Stop after each logical unit, write or update its tests, run the focused tests and inspect expected outputs before implementing the next unit. Do not defer tests until a phase or the full codebase is complete.

### Implementation discipline

- Build in dependency order: Python domain model and tests first, then API/WebSocket, then frontend connection/configuration, then visualisation and interaction.
- Keep modules small and responsibilities explicit.
- Use typed models for API commands, configuration, events and domain state.
- Use deterministic random seeds so a scenario can be reproduced.
- Commit in logical implementation stages if working in a Git repository.
- Run tests after each logical stage and provide a test/coverage report.
- Work in short test/implementation/verification loops. A logical component is incomplete until its focused tests pass and its observable output has been checked.
- Do not silently invent protocol rules where this specification marks a decision as unresolved. Implement an explicit interface or documented MVP assumption instead.
- Allow first contact using Bob’s published encryption key and provider address. Python provisions independent signing keys and pins their public keys to each simulated participant ID. Sending requires no account, prior contact approval, real-world identity service or pre-shared secret.
- Keep a protocol registry in Python containing the exact algorithm name, reference, version/date, parameters and declared simulation boundaries. Return it through the API and display it in the UI.

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
- See when a message is queued at a node, travelling on a network path or delivered to the next node.
- Inspect each node's protocol-specific state: Loopix layer adjacency or Kademlia routing buckets.
- Watch nodes go offline and recover for independently randomised periods.
- Observe routing failures, timeouts, retries and alternative paths.
- Observe Bob polling for messages rather than receiving unsolicited server push notifications.
- Inspect the information visible to each simulated participant or node.
- Replay a scenario using the same random seed.
- Edit each sender's staged message before running, configure 1–10 exchanges and inspect device-local send/reply logs.
- Disable or enable receiver polling and block or restore network paths while a simulation is running.

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
- Claiming that the experimental composition of Loopix, Kademlia and distributed storage inherits the formal security properties of any component.
- Treating a diagram as evidence that a real network is secure.

The simulator may model network addresses and independent node operators, but those are simulated properties. It must not pretend that random private IP addresses are real routable Internet endpoints.

---

# 2. User scenarios and acceptance criteria

## Scenario 1: Start the Python backend

**As a developer**, I want to start Python in a terminal and have it tell me which port it is listening on, so that I can connect the frontend without assuming a port is free.

### Acceptance criteria

- Running `python python/main.py` from the repository root starts the FastAPI application.
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
- Mixnet node count is configurable within the range of 6 to 20, defaulting to 6.
- Network setup lists senders in individual rows followed by recipient rows. Each group has an add button below its participants. Each row identifies the participant and their connection channel. The mix count follows the two groups.
- The user can choose a fixed mixnet node count or ask Python to randomise the count within the selected minimum and maximum.
- The number of senders and receivers represents the number of separate `Person` instances Python creates.
- A person is not a special Alice-only or Bob-only class. Alice, Bob and later participants are instances of the same `Person` class with different IDs, display names and roles in a communication scenario.
- Each person has an independent client state and their own selected connection channel.
- Each person has their own cryptographic identity/key material generated by Python for the simulation.
- The configuration includes conversation/message exchange settings.
- The user can configure 1–10 message exchanges per conversation.
- An exchange means one message followed by a reply. Therefore, five exchanges in a two-person conversation normally means ten message transmissions.
- The UI must label exchanges and total messages clearly so the user does not confuse them.
- The configuration supports one sender to one receiver, multiple senders to one receiver, one sender to multiple receivers, and multiple senders/receivers.
- The communication pairing strategy must be explicit, not inferred from sender and receiver counts alone.
- Initial pairing strategies: `all_to_one`, `one_to_all`, `one_to_one_pairs`, and `random_pairs`.
- A random seed may be supplied or generated. The seed must be returned in the generated simulation metadata.
- The user presses **Create simulation** to ask Python to generate the objects.
- Python returns a topology snapshot and simulation ID.
- The UI renders the generated topology only after receiving that response.
- Creating the simulation does not automatically start message traffic.
- After creation and before **Run**, the UI shows the staged outgoing messages for every sender and permits the user to edit them.
- **Reset** recreates or restores the staged run, returns to this editable pre-run state and does not start traffic automatically.
- The user then presses **Run** to begin execution.

## Scenario 5: Watch the generated network

**As a user**, I want to see the network that Python actually generated.

### Acceptance criteria

- The initial graph is generated from the topology snapshot returned by Python.
- D3 is used for graph layout and/or interaction.
- SVG is used for node and edge rendering.
- The UI must not invent nodes or edges that are absent from Python's topology.
- Nodes have stable IDs.
- Nodes are visually grouped into stable left-to-right protocol-stage columns.
- The graph distinguishes people, their connection channels, Loopix providers and mix nodes, Kademlia DHT nodes and generic replicated-storage nodes.
- The user can zoom and pan.
- The user can select a node.
- Selecting a node opens the node inspector.
- Selecting a peer in a protocol-state table highlights the corresponding graph node and connection.
- Sender devices occupy the left edge and recipient devices the right edge.
- Forward message routes use the upper route lane and travel visually from the upper-left towards the right.
- Reply routes use a lower route lane, originate visually from the lower-right and return towards the sender without duplicating any node card.
- The graph must remain usable with the initial expected network size and should not assume a fixed number of nodes.

## Scenario 6: Observe message routing

**As a user**, I want to see the actual Loopix source route selected by Python, including eligible candidates and failed end-to-end attempts.

### Acceptance criteria

- Python selects an independent source route for every packet using the Loopix 2017 stratified topology: ingress provider, one randomly selected mix from each ordered layer, then egress provider.
- Each Sphinx routing layer determines the next hop. An intermediate mix node must not invent or recalculate a route.
- JavaScript does not select or recalculate routes.
- Python emits route-construction and per-hop packet-processing events.
- Route-construction events include the algorithm identifier, ordered layers, eligible candidates, excluded candidates, selected node per layer and seeded random decision context.
- The UI animates the message along the actual selected path.
- Every traversed edge is a Python-owned `NetworkPath` object with its own simulated transit delay and state.
- Python emits `path_transit_started` and `path_transit_completed` events so the UI can leave the message marker visibly travelling between nodes for the logical path delay.
- Node queueing/mixing delay and path transit delay are displayed separately.
- The UI distinguishes attempted, successful, failed and retried hops.
- Clicking a routing decision shows the decision details.
- The UI can show candidate peers that were not selected.
- A route is source-routed per packet but is not hardcoded or reused silently between messages.
- A failed hop terminates that packet attempt. Reliability is an end-to-end application concern; a bounded retry creates a new packet with a newly sampled independent source route.
- The end-to-end retry policy must have bounded attempts and a clear terminal failure state.
- A retry must not duplicate message delivery without an explicit deduplication policy.

## Scenario 7: Inspect each mixnet node's protocol state

**As a user**, I want to inspect each mixnet node's layer, adjacent-layer connectivity and Sphinx packet-processing state.

### Acceptance criteria

- Every `MixNode` belongs to exactly one Loopix layer and owns adjacency state for the nodes in the immediately preceding and following layers.
- Adjacent-layer connectivity follows the Loopix 2017 stratified topology; do not replace it with gossip discovery, Kademlia or arbitrary next-hop selection.
- The UI shows the selected node's layer, adjacent peers, Sphinx replay-tag state, queued packets and configured exponential-delay parameter.
- The adjacency table shows peer ID, simulated address, layer, observed availability, last contact and failure count.
- The table distinguishes configured topology from observed reachability.
- State updates are streamed from Python to the web client, which must not fabricate peer entries.

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

Keep these concepts separate:

1. **Simulation time:** the logical clock used for outages, timeouts, polling and all network behaviour.
2. **Path transit delay:** logical time spent travelling across a `NetworkPath` between two node objects.
3. **Loopix mix delay:** logical time a packet remains queued at a mix according to its source-selected exponential delay.
4. **Playback delay:** the real-time pause between displayed simulation steps, controlled by the web client.

Playback delay must not change path transit, mix or outage durations. Path transit delay must not be reused as Loopix mixing delay.

Example:

- Mix node A goes offline at simulated time 10 seconds for 300 simulated seconds.
- Mix node B goes offline at simulated time 25 seconds for 0.5 simulated seconds.
- Mix node C is offline for the entire run.
- The UI may display these transitions at a user-selected playback pace.

For the first implementation, a deterministic discrete-event scheduler is preferred over tying every outage to real wall-clock sleeps. The scheduler should advance logical simulation time according to scheduled events. The playback controller decides how quickly those events are presented/executed to the user.

Do not implement a confusing time multiplier unless it is explicitly added as a separate feature later.

## Scenario 9: Bob polls for messages

**As a user**, I want Bob to retrieve messages through his own client and connection channel by polling, rather than having the network push a notification to Bob.

### Acceptance criteria

- Bob is an instance of `Person`.
- Bob owns a connection channel.
- Bob’s enabled, online client initiates a poll on each fixed timer tick, including while the mailbox is empty and while an earlier request is in flight. The graph shows poll traffic, the last request time and the last result.
- Receiver polling can be enabled or disabled in configuration and toggled while the simulation is running.
- When polling is disabled, stored messages remain undiscovered and the receiver cannot generate replies until polling resumes and retrieval completes.
- Bob initiates a poll through his own connection channel.
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

## Scenario 11: Block and restore network paths in real time

**As a user**, I want to block links or boundaries between protocol stages while the simulation runs so I can observe exact failure and retry behaviour.

### Acceptance criteria

- The UI allows a user to select a `NetworkPath` or a stage boundary and issue **Block route** or **Restore route**.
- The web client sends a typed command to Python; it never changes authoritative path state locally.
- Blocking a stage boundary applies to the Python-owned paths crossing that boundary.
- A block takes effect at a deterministic simulation event and prevents new transits from starting.
- A packet already in transit completes by default. An explicit `drop_in_flight` test option may terminate it, but that behaviour must be visible and logged.
- Blocked paths remain visible, use a distinct failure treatment and expose who blocked them and at what simulation time.
- Route restoration is observable and makes the path eligible again according to the relevant protocol.

## Scenario 12: Edit messages and inspect device logs

**As a user**, I want to edit staged messages before a run and inspect the resulting conversation on each participant's device.

### Acceptance criteria

- After **Create simulation** or **Reset**, each sender has editable staged text for every configured exchange.
- The user may replace any generated message before pressing **Run**.
- Default messages and replies are deterministic random strings of 3–10 words selected from the first few sentences of Lorem ipsum, using the simulation RNG.
- One exchange contains one sender message and one recipient reply; the configured range is 1–10 exchanges.
- A run uses the final staged text returned to Python, not stale browser-only state.
- Each participant portrait opens its chronological conversation log in the adjacent pane.
- A log row shows direction, simulation timestamp and plaintext available to that device, for example `SEND 11:23 pm  Hi Bob, how are you?` or `REPLY 11:40 pm  Lorem ipsum dolor`.
- Logs distinguish staged, sent, delivered, received and replied states without exposing plaintext in network-node inspectors or general telemetry.

## Scenario 13: Inspect cryptographic data lineage

**As a user**, I want to see where public keys, encrypted payloads, manifests and fragments move without exposing secret material.

### Acceptance criteria

- Python emits typed lineage events for public-key retrieval, reply-key encapsulation, encryption, chunking, manifest publication, fragment storage, retrieval, reconstruction and decryption.
- The UI can highlight the current location and containment relationship of each safe-to-display artefact.
- Alice's reply public key travels inside the encrypted message content. It may be represented as accompanying encrypted chunks and the encrypted manifest, but it must not be shown as plaintext stored in the DHT.
- Bob accepts the reply public key only after retrieval, reconstruction, decryption and verification against Alice’s pinned signing key.
- The UI identifies the reply key as authenticated by the signature of the pinned simulated sender. It explains the scope of that pin.
- Private keys and plaintext network payloads never appear in path, DHT, storage or mixnet telemetry.

---

# 3. Functional requirements

## 3.1 Python backend

### FR-PY-001: Local server startup

Provide a Python entry point:

```bash
python python/main.py
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
- Mixnet node count: supported range 6–20, default 6.
- Exchange count: integer from 1 to 10.
- Receiver polling enabled: boolean, with optional per-receiver overrides.
- Network-path transit delay and jitter values: non-negative and within configured safety limits.
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
- generated connection channel instances
- generated mixnet nodes
- generated DHT nodes
- generated storage nodes
- generated `NetworkPath` objects
- generated initial topology
- conversation/pairing plan
- editable staged message plans
- initial availability state
- protocol registry and initial per-node protocol-state snapshots
- configuration summary

The create operation must not start message traffic. It returns enough state for the web client to render the topology, device editors and generated default messages before **Run**.

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

`reset` returns the simulation to an editable pre-run state, clears runtime message/device logs, restores configured path state and regenerates or restores staged messages according to the reset request and seed.

### FR-PY-006: Event scheduler

Implement a deterministic event scheduler. It should process one simulation event/step at a time and publish an event to connected frontend clients.

The scheduler must support:

- message processing events
- polling events
- Loopix route construction and Sphinx packet-processing events
- network-path transit start/completion/failure events
- node state changes
- path block/restore events
- timeouts
- retries
- Poisson-mix delayed-release events
- storage and DHT events
- message reconstruction/decryption events
- cryptographic lineage and device-log events

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
- layer assignment and initial Kademlia bucket state
- per-packet Loopix source-route sampling
- exponential delays and Poisson traffic schedules
- Kademlia lookup scheduling where concurrent responses need deterministic ordering
- node failure times
- outage durations
- conversation pairing when random
- message scheduling where random

Separate cryptographic randomness from reproducible simulation randomness. A deterministic simulation seed must not make cryptographic keys predictable. Use a cryptographically secure random source for keys, nonces and secret material.

### FR-PY-009: Staged messages and deterministic defaults

- Generate default sender messages and recipient replies from the first few sentences of a bundled Lorem ipsum corpus.
- Each generated text contains 3–10 consecutive or seeded-selected words and uses the simulation RNG.
- Provide a typed pre-run command or endpoint to replace staged text per sender, conversation and exchange.
- Reject message-plan edits after execution starts unless the simulation is reset.
- Validate that every configured exchange has one sender message and one reply template or generated reply.
- Include the final accepted message plan in run metadata without exposing plaintext to network-node telemetry.

### FR-PY-010: Runtime intervention controls

Provide typed Python commands for:

- enabling/disabling polling globally or per receiver;
- blocking/restoring one `NetworkPath`;
- blocking/restoring every path across a selected stage boundary;
- choosing whether a test-only block drops existing in-flight transits;
- requesting current participant device logs and artefact-lineage state.

Every intervention is a `SimulationStep`, receives a command ID and effective simulation timestamp, emits a result event and is deterministic when replayed with the same command sequence.

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

Every executable network action must be represented by a `SimulationStep` object. A step is part of the domain model, not merely a UI event or scheduler callback. Concrete step types may represent routing, delivery attempts, availability transitions, polling, DHT lookups, fragment placement and fragment retrieval.

Each step should expose:

- stable `step_id`
- step type
- simulation ID
- scheduled simulation time
- lifecycle state
- involved object IDs
- typed inputs
- typed result or failure details after execution
- event/log context
- explicit DTO mapping for frontend display

The scheduler queues and executes step objects. It must not encode network behaviour in anonymous callbacks, and a step must remain distinguishable from the events it emits.

### Protocol fidelity and references

The selected reference profiles are:

- `loopix-usenix-2017`: [The Loopix Anonymity System](https://www.usenix.org/system/files/conference/usenixsecurity17/sec17-piotrowska.pdf), USENIX Security 2017.
- `kademlia-2002`: [Kademlia: A Peer-to-peer Information System Based on the XOR Metric](https://pdos.csail.mit.edu/~petar/papers/maymounkov-kademlia-lncs.pdf), 2002.

For each profile, maintain conformance tests for its routing state machine, data structures, selection rules, timing distributions and termination conditions. API metadata and the web UI must distinguish exact reference behaviour, configurable reference parameters, experimental deviations and simulator-only transport boundaries.

Never display a generic category alone when a concrete algorithm is being simulated. Use labels such as `Mixnet — Loopix (USENIX 2017)` and `DHT — Kademlia (2002)`. Use `Tor abstraction` and `Replicated chunk-storage model` for components that are not complete implementations of named protocols.

## 4.2 Person

One shared `Person` class represents all users.

Alice, Bob, Carol and David are separate instances, not separate subclasses.

Suggested properties:

- `person_id`
- `display_name`
- `participant_role` or scenario role
- `public_key`
- `private_key_reference` for X25519 recipient decryption
- an independently generated Ed25519 signing private key and its public verification key
- `mailbox_id`
- `channel_id`
- `outgoing_messages`
- `received_messages`
- `staged_message_plan`
- `device_message_log`
- `polling_config`
- `polling_enabled`
- `client_state`
- `created_at_sim_time`

Both private keys must remain on the simulated device. Do not include private key bytes in logs, event payloads or node inspectors.

The frontend may display a key fingerprint and public key, but not private key material.

`staged_message_plan` is editable only before a run starts or after reset. `device_message_log` is Python-owned chronological state containing direction, message ID, conversation ID, logical timestamp, delivery state and plaintext visible to that participant. The frontend renders this state in the selected participant’s conversation pane.

## 4.3 Alice and Bob behaviour

Alice and Bob use the same `Person` implementation.

Alice may:

- retrieve Bob's published public key from a simulated public webpage/public-key source
- compose a message
- sign the text, message context and designated X25519 reply public key with her Ed25519 private key
- encrypt the signed bundle for Bob
- submit the encrypted envelope through her own connection channel
- observe sending progress

Bob may:

- poll for new messages through his own connection channel
- discover an available message/manifest
- retrieve the encrypted manifest and fragments
- reconstruct the encrypted payload
- decrypt using his private key
- verify the signed context, content and designated reply key against the expected sender’s pinned signing key
- read the accepted message and send a signed, encrypted reply to its verified reply key

The first implementation may use simulated public-key publication/retrieval. It must not require a pre-existing shared secret or a prior contact registration.

### Sender authentication within one simulation

Each device signs every forward message and reply with its own Ed25519 private key. A trusted, simulated directory pins each expected participant ID to its public verification key for the run. After decryption, the recipient checks the signature and expected message context before accepting the plaintext or learning the enclosed reply key. An attacker who knows the recipient’s public encryption key can create ciphertext but cannot impersonate the pinned sender without its signing private key.

The application assumes authentic directory pins at setup. Display names and participant IDs represent simulated devices. External identity verification, device compromise and directory compromise remain outside the model.

## 4.4 Participant connection channels

Each participant owns a connection channel. Each individual sender and recipient can independently select Tor (the default), Outline Shadowsocks or a direct request. The creation API accepts a `participant_channels` map keyed by device ID. Devices without an entry inherit their role default for compatibility. References elsewhere to participant Tor boundaries describe the default profile. The selected channel applies to message transmission, provider polling, DHT access, vault retrieval and replies originating at that device.

- Tor models a single boundary with distinct guard and exit addresses. Circuit construction, relay selection and onion encryption are outside the simulation.
- Outline Shadowsocks models a proxy with a client-facing address and a server egress address. The proxy sees the device's IP on entry. The next service sees the proxy's IP. The simulation represents address visibility without implementing the Shadowsocks wire protocol.
- Direct requests use the device's own network-facing IP. The diagram can represent its local interface. The first remote service observes the device IP.

Label both channel columns by role and show each device's simulated IP address in its selected conversation header. Each recorded journey segment must expose the source and destination IPs for that direction, identify the observer and preserve the cargo inspection. Transport addresses are independent of signed application identity. A channel choice changes device access to the network. The selected channel connects to the device’s provider. Both manifest and fragment retrieval use mixed forward requests and single-use anonymous reply blocks for the return journey. Service responses must traverse the mix layers before reaching the participant channel.

## 4.5 Mixnet manager

One `Mixnet` object manages multiple `MixNode` instances.

The MVP mixnet algorithm is the Loopix construction published at USENIX Security 2017. Implement the protocol behaviour described by that paper: providers, a stratified topology, independent per-packet source routes, Sphinx packet processing, replay-tag rejection, source-selected exponentially distributed per-hop delays, client and mix loop traffic, drop cover traffic and fixed-size polling responses. Real sockets may be replaced by deterministic simulation steps, but the Sphinx and routing algorithms must not be replaced by placeholders. If any required part is abstracted, label the subsystem `Loopix routing model`, list the deviation in protocol metadata and do not claim a complete Loopix implementation.

Loopix users are associated with providers. In this simulator that association uses an ephemeral network identifier and provider assignment; it must not introduce a username/password account, external identity service or prior contact approval. Bob's published contact data must include the provider/network location required to construct a route without exposing Bob's physical location.

Responsibilities:

- create and manage mix nodes
- create ingress and egress `ProviderNode` instances required by the Loopix topology
- assign every mix node to one ordered layer
- build complete adjacency between consecutive layers, including providers at ingress and egress
- expose eligible nodes so the sender can sample one node independently from each layer for every packet
- expose topology snapshots for the UI
- provide access to node lookup by ID for simulation orchestration
- publish the exact Loopix reference and active parameters through protocol metadata

The `Mixnet` manager is a simulation-level registry/manager. Do not represent it as a real central production authority or as a router in the simulated protocol.

## 4.6 MixNode

Every mix node is an independent object.

Suggested properties:

- `node_id`
- `simulated_address`
- `operator_id`
- `layer_index`
- `status`
- `availability_controller`
- `adjacent_peers`
- `inbound_queue`
- `outbound_queue`
- `delayed_packet_queue`
- `seen_replay_tags`
- `failure_count`
- `poisson_mix_config`
- `created_at_sim_time`

A mix node can handle both incoming and outgoing traffic. Do not create separate node classes for sending and receiving unless a future protocol design requires it.

Responsibilities:

- receive an envelope
- validate that it is online and able to process
- process the Sphinx packet layer and validate its integrity
- reject a previously seen replay tag
- unwrap exactly one Sphinx routing layer
- enqueue the packet for the source-selected delay sampled independently from the configured exponential distribution
- forward to the next-hop address encoded in that routing layer after the delay
- emit packet-processing and forwarding events
- generate mix loop cover traffic using the configured Poisson process
- record failure and recovery events
- update local peer status based on observations

A mix node does not choose the next hop. The sender source-routes each packet, and the mix learns only the next routing command exposed by its Sphinx layer. Do not describe or implement batch shuffling as Loopix: Loopix uses independent exponential delays and is modelled as a Poisson mix.

## 4.7 Loopix topology and adjacency state

Do not conflate the Loopix topology with Kademlia DHT lookup. Loopix 2017 does not define the ad-hoc bootstrap/gossip discovery model previously proposed for this simulator, so the MVP must not invent one and call it Loopix.

The topology is stratified:

- providers form the ingress and egress boundaries;
- mix nodes are assigned to one fixed ordered layer;
- every mix is connected to every mix in the immediately preceding and following layers;
- providers connect to all nodes in the first or final mix layer as appropriate;
- the sender independently samples one eligible node from each layer for each packet;
- the complete ordered route and per-hop delays are encoded into the Sphinx packet before transmission.

### Adjacency entry

Suggested fields:

- `peer_node_id`
- `simulated_address`
- `layer_index`
- `last_seen_sim_time`
- `status_observation`
- `consecutive_failures`
- `successful_contact_count`
- `last_failure_sim_time`
- `topology_metadata`

The UI must distinguish:
- known online
- known offline
- unknown/stale
- unreachable after failed attempts

Configured adjacency is not proof of current reachability. Do not claim that a node knows a peer's real-time availability unless it has received an observation or the simulation explicitly models a shared oracle.

## 4.8 Routing algorithm and retry

For each packet attempt:

1. The sender obtains the ordered Loopix layers and their eligible nodes.
2. The sender samples one node uniformly from each layer using the seeded simulation RNG.
3. The sender samples an independent per-hop delay from the configured exponential distribution with public parameter `mu`.
4. The sender constructs the Sphinx routing layers for the ingress provider, selected mixes and egress provider.
5. Each processing node verifies its packet-integrity result and replay tag, unwraps one routing layer, waits the encoded delay and forwards to the encoded next hop.
6. If a hop is unavailable or times out, that packet attempt fails; an intermediate node does not rewrite the source route.
7. If the application retry budget remains, the sender constructs a fresh packet attempt with an independently sampled route and delays.

Requirements:

- retry count is bounded;
- no infinite loops;
- a retry uses a new packet/replay tag and independently sampled source route;
- exact-once delivery is protected by message IDs and recipient deduplication;
- expose all decisions and failures to the event stream;
- do not make the UI or an intermediate mix choose a fallback route;
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

Implement the original Kademlia algorithm described by Maymounkov and Mazières in 2002, not a Kademlia-inspired approximation.

Required MVP parameters and behaviour:

- random 160-bit node IDs and keys;
- integer XOR distance `d(x, y) = x XOR y`;
- dynamically split, least-recently-seen `k`-buckets with `k = 20`;
- live-old-contact preference and ping-before-eviction;
- `PING`, `STORE`, `FIND_NODE` and `FIND_VALUE` RPC semantics;
- parallel asynchronous lookup with concurrency `alpha = 3`;
- lookup termination after the `k` closest seen nodes have responded, following the paper's iterative procedure;
- storage at the `k` closest nodes;
- join by bootstrap contact, self-lookup and required bucket refreshes;
- refresh and republishing behaviour represented in simulation time.

Each `DHTNode` has:

- unique node ID
- simulated address
- local Kademlia routing table
- locally stored records
- availability state
- peer observation state

The simulated transport does not need real UDP sockets, but its RPC state transitions, bucket maintenance, lookup ordering and termination must match the reference algorithm. Do not describe Kademlia as the mixnet's message-forwarding algorithm.

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
- safe lineage metadata stating that an encrypted reply-key field is contained in the encrypted bundle, without revealing its value before recipient decryption

The manifest's privacy properties are not fully specified. Do not assume that encrypting a manifest with Bob's public key automatically solves all metadata leakage. Document which fields are visible to DHT/storage nodes and which are encrypted.

The lineage view may show that Alice's encrypted message bundle contains a reply public key and that its encrypted chunks were indexed through the DHT. It must not show or store Alice's reply public key as plaintext DHT metadata. Bob accepts the value only after successful reconstruction, decryption and signature verification. The UI identifies the trusted, per-run signing-key pin.

## 4.12 Simulation support objects

Suggested objects:

- `Simulation`
- `SimulationConfig`
- `SimulationRNG`
- `SimulationStep` and concrete step types
- `EventScheduler`
- `PlaybackController`
- `EventBus`
- `TopologySnapshotBuilder`
- `GlobalObserver`
- `NetworkPath`

`Simulation` owns a single run and all of its domain objects.

`EventScheduler` orders and executes `SimulationStep` objects. Each step may publish one or more typed events, but events are records of execution and are not substitutes for the step object.

`PlaybackController` controls the real-time pause between visible steps.

`EventBus` publishes typed events to the WebSocket layer.

`GlobalObserver` is instantiated once and owned by `Simulation`. In the MVP it is deliberately inert: it does not subscribe to events, inspect nodes, record traffic, receive hidden state or influence execution. It exists only as an explicit extension point for a future approved observer or adversary model.

## 4.13 NetworkPath

Every traversable connection between simulated objects is an explicit `NetworkPath` object. Do not represent a message jump as an instantaneous event or infer authoritative connections from D3 edges.

Suggested properties:

- `path_id`
- `source_id`
- `target_id`
- `stage_from` and `stage_to`
- `transport_label`
- `protocol_profile`
- `status`: `available`, `blocked`, `unresponsive` or `offline`
- `base_transit_delay_ms`
- optional seeded jitter configuration
- active transit IDs
- block metadata and effective simulation time
- counters for attempted, completed, failed and dropped transits

Starting a transit schedules a `PathTransitStep` at the current simulation time and a corresponding completion step at `current_time + transit_delay`. Emit start, progress metadata and completion/failure events. The web client uses those events and timestamps to animate the marker for the correct proportion of playback time while Python remains authoritative.

Use explicit transport labels in the diagram:

- participant device to its channel: Tor guard connection, Shadowsocks client to proxy or local direct interface handoff;
- Tor egress to Loopix ingress provider: `Tor egress → Loopix provider`;
- Loopix provider and mix-layer paths: `Loopix datagram`;
- Kademlia paths: `Kademlia RPC`;
- storage paths: `encrypted fragment transfer`.

These labels describe simulation boundaries and must not claim that the entire composed system uses one transport protocol.

---

# 5. Cryptography requirements

## 5.1 General rule

Cryptography runs in Python for this simulator. The browser is not the cryptographic engine.

Use a maintained, reputable Python cryptography library. Do not implement cryptographic primitives manually.

The application uses these primitives.

- X25519 for ephemeral key agreement;
- HKDF-SHA-256 for deriving an encryption key;
- AES-256-GCM for authenticated message encryption;
- SHA-256 for hashing/integrity identifiers;
- Ed25519 for signing and verifying application messages and replies against per-run signing-key pins. [RFC 8032 §5.1](https://www.rfc-editor.org/rfc/rfc8032.html#section-5.1)

Use a maintained library such as Python `cryptography` for supported primitives. Confirm the library's actual algorithm support and API version during implementation.

## 5.2 Message encryption flow

1. Alice and Bob each generate independent Ed25519 signing and X25519 encryption key pairs. The simulated directory pins their signing public keys to their respective participant IDs.
2. Alice retrieves Bob’s published X25519 public key and provider address.
3. Alice signs the text, her designated X25519 reply key, both participant IDs, the target encryption key, the conversation and message IDs, the exchange and its direction.
4. She uses a fresh ephemeral X25519 key and Bob’s X25519 public key for agreement. HKDF-SHA-256 derives the AES-256-GCM key. She encrypts the signed bundle with a fresh nonce.
5. The envelope carries the ephemeral public key, nonce, ciphertext and version/algorithm metadata.
6. Bob reconstructs the ciphertext and decrypts with his X25519 private key. He checks the signature using the expected participant’s pinned Ed25519 verification key and the expected message context.
7. After successful verification, Bob accepts the text and enclosed reply address. A malformed bundle, context mismatch or invalid signature cannot update his received messages or learned reply keys.
8. Bob signs his reply with his own Ed25519 private key and encrypts it to the verified X25519 reply key. Alice verifies his signature in the same way.

Do not reuse nonces with the same AES-GCM key.

Use fresh ephemeral key material for each message unless a separately specified session protocol is introduced.

## 5.3 Important protocol limitation

The signature binds the designated reply address to the signing key pinned to Alice’s participant ID for this simulation. That pin is a simulator trust assumption. The UI and technical documentation must explain that real-world identity assurance requires an independent trust mechanism.

Do not claim forward secrecy for the whole messaging system merely because ephemeral X25519 is used. Key retention, compromise recovery and stronger replay guarantees require a separate protocol review.

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

## 6.1 Separate timing dimensions

The implementation must keep these concepts separate:

### Simulation clock

A logical clock used for:
- outage start/end;
- polling intervals;
- timeouts;
- retry backoff;
- Poisson-mix delayed release;
- network-path transit start/completion;
- message scheduling;
- peer last-seen timestamps.

### Playback delay

A wall-clock pause between simulation steps, configured by the user.

Initial default: 500 ms.

The user can change it while the simulation is running. Python applies the new delay before the next step.

Changing playback delay must not change the simulated duration of an outage or timeout.

### Path transit delay

A logical duration owned by each `NetworkPath`. It begins after the source node releases the packet and ends when the target node can receive it. Seeded jitter may vary the duration per transit. This is not a wall-clock sleep and is not the Loopix mix delay.

### Loopix mix delay

A logical duration encoded for a hop according to the Loopix exponential-delay profile. It begins after the mix processes the Sphinx layer and ends when that mix releases the packet onto the next `NetworkPath`.

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
- `MIX_PACKET_QUEUED`
- `MIX_PACKET_RELEASED`
- `MIXNET_ROUTE_CONSTRUCTED`
- `PATH_TRANSIT_STARTED`
- `PATH_TRANSIT_COMPLETED`
- `PATH_TRANSIT_FAILED`
- `PATH_BLOCKED`
- `PATH_RESTORED`
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
- `POLLING_ENABLED`
- `POLLING_DISABLED`
- `DEVICE_LOG_UPDATED`
- `ARTEFACT_LINEAGE_UPDATED`

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

The interface should look like a precise, modern infrastructure diagram and engineering console on a light canvas.

Use these repository references as visual direction, not pixel-for-pixel layouts:

- [UI style reference](../reference/ui%20style%20reference.png): light background, compact white icon cards, restrained borders/shadows, thin dotted paths, small inline measurements and sparse semantic colour.
- [Network diagram concept](../reference/concept%20for%20network%20diagram%20stlye.png): clearly separated stage columns, grouped network layers, stable topology and labelled connections. Do not copy its devices, density or exact arrangement.

### Palette

| Token | Suggested value | Usage |
|---|---|---|
| `--bg` | `#F7F8F6` | Main canvas |
| `--panel` | `#FFFFFF` | Device/node cards |
| `--panel-subtle` | `#F1F3F2` | Inspectors and grouped regions |
| `--border` | `#E2E5E3` | Card and stage boundaries |
| `--path` | `#C9CECB` | Inactive dotted paths |
| `--text` | `#171A18` | Primary text |
| `--muted` | `#737A76` | Secondary text |
| `--success` | `#22A447` | Available/successful path |
| `--warning` | `#F06424` | Delayed/retrying path |
| `--danger` | `#D83A3A` | Blocked/offline/failure |
| `--accent` | `#4C6FFF` | Selection/focus |

Use status colours sparingly on paths, badges and measurements. Keep the canvas, cards and labels predominantly white, charcoal and soft grey. Cards use modest corner radii, hairline borders and a very soft shadow; avoid glass effects, gradients and heavy elevation.

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
1. Network setup occupies the left half on desktop. Show each sender and recipient with their portrait and channel in this panel, followed by the mix node count. Group the remaining configuration sections in the right half and stack the columns on narrow screens.
2. Receiver polling controls, including the initial enabled state.
3. Conversation pairing.
4. Message/exchange count from 1–10.
5. Node failure configuration.
6. Playback delay.
7. Random seed / reproducibility.
8. Protocol parameters, with fixed reference defaults and visibly labelled experimental overrides.

After **Create simulation** and after **Reset**, replace the setup form's message summary with per-sender editable staged-message fields while retaining a route back to network configuration. **Run** remains disabled until Python validates and accepts the staged message plan.

### C. Network topology

Main visual area showing:
- participant portrait endpoints beside selectable conversation panes;
- each person's selected connection channel;
- mixnet manager/network boundary if useful;
- Loopix ingress and egress providers;
- individual mixnet nodes;
- DHT nodes;
- storage nodes;
- connections known to the selected view;
- actual selected message route;
- active message markers held at nodes or travelling on paths;
- offline/recovering states.

Arrange the topology in stable left-to-right stage columns. The baseline sequence is participant device, sender connection channel, Loopix ingress provider, ordered Loopix mix layers, Loopix egress provider, Kademlia/DHT lookup, encrypted storage vault, recipient connection channel and recipient device. Render message journey lines with a thin visible stroke and a wider invisible pointer target for inspection. The actual Python topology may add or omit columns, but stage order must remain explicit.

Use an upper forward lane for sender-to-recipient traffic. Use a lower reply lane for recipient-to-sender traffic. Reply lines enter from the lower-right and curve back through the same node instances; never render duplicate node cards solely for the reply journey.

Use D3 to calculate and maintain constrained graph layout. Use SVG for nodes, edges, labels and route animation.

The graph must distinguish configured protocol topology from observed traffic. For Loopix, display the ordered layers and adjacency between consecutive layers. For Kademlia, display contacts known through each selected node's local `k`-buckets. Do not invent links in the web client.

Label the access link for the selected channel and identify local interface handoffs. Channel egress connects to the Loopix ingress `ProviderNode`; the provider is the mixnet ingestion point. Do not label a first-layer mix node as the ingestion provider.

Place runtime controls inside the network topology header row, centred between the receiver polling summary and the transport and zoom controls. Group node availability with the selected node’s glyph or portrait and show its availability button in red while offline. Provide direct graph controls for **Block route**, **Restore route**, **Disable polling** and **Enable polling**. Controls dispatch typed commands to Python and show pending, applied or rejected state.

### D. Node inspector

Use one selector for nodes and paths, with participant portraits and node glyphs. Place it above the white information panel in the left half of the desktop workspace. Show event and lineage records in the right half. Stack these panels on narrow screens.

When a node is selected, show:
- node ID;
- type;
- simulated address;
- operator ID;
- availability state;
- uptime/outage history;
- last state transition;
- inbound/outbound queue counts;
- current delayed-packet queue and Poisson-mix parameters if a mix node;
- failure count;
- last activity;
- protocol-state tab;
- active/inbound path transits;
- safe cryptographic artefact-lineage tab;
- event history tab.

### E. Protocol-state and algorithm inspector

For a selected Loopix mix node, show:
- peer ID;
- simulated address;
- local layer and peer layer;
- last seen;
- observed status;
- consecutive failures;
- success count;
- last failure;
- configured adjacency;
- selection/highlight action.

For a selected Kademlia node, show its 160-bit node ID, bucket ranges, least-to-most-recent contact order, XOR distances, active lookup shortlist, queried/responded state and `k`/`alpha` parameters.

The inspector must always show:

- exact algorithm name;
- reference paper and publication year;
- implementation profile/version;
- active parameters;
- which operations are exact state-machine simulations and which lower-level transport or cryptographic operations are abstracted;
- a link from the displayed algorithm identifier to the bundled reference metadata.

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
- connection channels;
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
- Enable/disable polling globally or for the selected receiver
- Block/restore the selected path or stage boundary

The delay slider should remain available during execution.

### H. Participant portraits and conversation logs

Render participants as circular photo endpoints at the edges of their conversation panes. Centre each vertical stack and connect each portrait to its own channel. A green ring identifies the participant selected on each side. Selecting a portrait opens its chat, IP address and latest send and receive times. Keep the device details available in the node inspector. Display incoming contacts as selectable portraits with red badges counting messages received by the selected device. Selecting a contact filters both directions in device-log order.

Log rows use the participant's perspective:

```text
SEND   11:23 pm   Hi Bob, how are you?
REPLY  11:40 pm   Lorem ipsum dolor
```

Use logical simulation timestamps formatted for humans, with the precise logical value available in details. Do not expose another participant's plaintext until the selected device has legitimately received and decrypted it.

---

# 8. D3 network visualisation requirements

## 8.1 Data ownership

Python supplies authoritative graph data:
- nodes;
- configured topology edges and locally known Kademlia contacts;
- node types;
- node states;
- route events;
- protocol-state updates;
- `NetworkPath` state and transit events;
- safe artefact-lineage state.

D3 may calculate visual positions and force layout. It must not create authoritative network relationships or make routing decisions.

## 8.2 Node visual treatment

Use distinct but restrained visual treatments for:
- Person
- Participant connection channel
- ProviderNode
- MixNode
- DHTNode
- StorageNode

Each node should have:
- visible short label;
- stable ID in tooltip/inspector;
- status indicator;
- selected state;
- hover state.

## 8.3 Column and lane layout physics

Use D3 forces as constrained layout assistance, not as an unconstrained force-directed graph:

- assign every node a stable `stage_index` from Python topology metadata;
- use a strong `forceX` target for the centre of its protocol-stage column;
- use `forceY` bands for the forward/upper and reply/lower route lanes while keeping one shared node position;
- use collision radii derived from measured card dimensions plus minimum whitespace;
- use link force only to improve local spacing within a stage or between adjacent stages, never to reorder columns;
- apply cluster separation for multiple mix nodes within the same Loopix layer and multiple DHT/storage nodes within their columns;
- retain positions across incremental updates and use low-alpha reheating to avoid disruptive jumps;
- route reply edges as lower cubic Bézier paths that rise from the bottom-right and return through the existing nodes;
- route forward edges from the upper-left across the upper lane;
- allow responsive horizontal scrolling or zoom before collapsing stage order.

Tune and test collision strength, link distance, charge strength, alpha decay and column gap against the expected 6–20 mix-node range. The result should have clear edges, even whitespace, readable labels and minimal crossings, informed by the diagram reference without copying it.

## 8.4 Edge visual treatment

Edges should distinguish:
- configured/known peer connection;
- currently selected route;
- attempted route;
- failed route;
- unavailable/stale connection;
- blocked connection;
- active in-transit message.

Do not draw all nodes as fully connected unless the topology data says so.

Use thin dotted neutral lines for inactive paths, green for successful/available flow, orange for delayed/retrying flow and red for blocked/failed flow. Show compact labels for transport type, transit delay and current state where space permits.

## 8.5 Route animation

When Python emits a forwarding event:
- highlight the source node;
- highlight the edge actually used;
- animate a message marker along the edge;
- highlight the destination;
- update the event timeline;
- preserve the route history for inspection.

On `path_transit_started`, keep the marker between nodes until `path_transit_completed` or `path_transit_failed`. The start event includes logical start/completion times and the path delay. Pause freezes the marker; stepping and playback changes must not alter the underlying logical completion time.

On failure:
- mark the attempted edge as failed;
- show timeout/rejection;
- then animate the new independently source-routed packet attempt when Python constructs it.

The animation is a visual representation of Python events, not a second route simulation.

## 8.6 Performance

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
| GET | `/api/info` | Runtime info, selected port, capabilities and protocol registry |
| POST | `/api/simulations` | Create simulation from config |
| GET | `/api/simulations/{id}` | Read simulation metadata/state |
| GET | `/api/simulations/{id}/topology` | Current topology snapshot |
| PUT | `/api/simulations/{id}/messages` | Validate and replace staged pre-run messages |
| GET | `/api/simulations/{id}/device-logs` | Read participant device logs |
| GET | `/api/simulations/{id}/lineage` | Read safe cryptographic artefact lineage |
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
- `request_protocol_state`
- `set_node_availability` (manual test control)
- `set_polling_enabled`
- `block_network_path`
- `restore_network_path`
- `block_stage_boundary`
- `restore_stage_boundary`
- `set_staged_messages`
- `request_device_logs`
- `request_artefact_lineage`
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
- `network_path_blocked`
- `network_path_restored`
- `path_transit_started`
- `path_transit_completed`
- `path_transit_failed`
- `mixnet_adjacency_updated`
- `mixnet_route_constructed`
- `sphinx_layer_processed`
- `message_forward_attempt`
- `message_forward_failed`
- `message_forward_succeeded`
- `mix_packet_queued`
- `mix_packet_released`
- `cover_packet_generated`
- `kademlia_bucket_updated`
- `kademlia_rpc_sent`
- `kademlia_rpc_received`
- `dht_lookup_started`
- `dht_lookup_completed`
- `fragment_stored`
- `fragment_retrieval_started`
- `fragment_retrieved`
- `bob_poll_started`
- `bob_poll_empty`
- `bob_poll_message_found`
- `receiver_polling_enabled`
- `receiver_polling_disabled`
- `message_reconstructed`
- `message_decrypted`
- `staged_messages_updated`
- `device_log_updated`
- `artefact_lineage_updated`
- `playback_delay_updated`
- `simulation_error`

### Event envelope

Use a consistent event envelope:

```json
{
  "event_id": "evt-000001",
  "event_type": "mixnet_route_constructed",
  "simulation_id": "sim-000001",
  "sequence": 42,
  "simulation_time_ms": 12500,
  "source_id": "person-alice",
  "target_id": "provider-bob",
  "message_id": "msg-000001",
  "conversation_id": "conv-000001",
  "payload": {
    "algorithm": "loopix-usenix-2017",
    "ordered_route": ["provider-a", "mix-l1-b", "mix-l2-c", "mix-l3-a", "provider-b"],
    "selected_by_layer": {"1": "mix-l1-b", "2": "mix-l2-c", "3": "mix-l3-a"},
    "mu_per_second": 1.0
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
      "algorithm": "loopix-usenix-2017",
      "min_nodes": 6,
      "max_nodes": 20,
      "randomize_count": true,
      "layer_count": 3,
      "mu_per_second": 1.0,
      "payload_rate_per_minute": 3.0,
      "client_loop_rate_per_minute": 1.0,
      "drop_cover_rate_per_minute": 1.0,
      "mix_loop_rate_per_minute": 1.0
    },
    "dht": {
      "algorithm": "kademlia-2002",
      "node_count": 8,
      "id_bits": 160,
      "k": 20,
      "alpha": 3
    },
    "storage": {
      "node_count": 12,
      "replication_factor": 2
    },
    "paths": {
      "base_transit_delay_ms": 250,
      "jitter_min_ms": 0,
      "jitter_max_ms": 150
    }
  },
  "participants": {
    "sender_count": 3,
    "receiver_count": 1,
    "receiver_polling_enabled": true
  },
  "conversations": {
    "pairing_strategy": "all_to_one",
    "exchanges_per_conversation": 5
  },
  "messages": {
    "payload_size_bytes": 512,
    "default_source": "lorem_ipsum",
    "generated_word_count_min": 3,
    "generated_word_count_max": 10
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
  "delivery": {
    "max_end_to_end_retries": 2,
    "ack_timeout_ms": 1000
  },
  "playback": {
    "step_delay_ms": 500
  },
  "random_seed": 12345
}
```

Validate ranges and make all defaults visible in the UI. Reference-profile parameters are fixed by default. Any experimental override must be visibly marked as a deviation in configuration, API metadata, events and the UI; it must never be presented as the unmodified reference algorithm.

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
trustless-mixnet-dht-messaging-simulator/
├── README.md
├── AGENTS.md
├── docs/
├── .agents/
│   └── instructions/
│       └── distributed-messaging-simulator-implementation.md
├── .gitignore
├── python/
│   ├── pyproject.toml
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
│   │   │   ├── provider_node.py
│   │   │   ├── dht_network.py
│   │   │   ├── dht_node.py
│   │   │   ├── storage_network.py
│   │   │   ├── storage_node.py
│   │   │   ├── network_path.py
│   │   │   ├── fragment.py
│   │   │   ├── manifest.py
│   │   │   └── conversation.py
│   │   ├── simulation/
│   │   │   ├── simulation.py
│   │   │   ├── steps.py
│   │   │   ├── scheduler.py
│   │   │   ├── event_bus.py
│   │   │   ├── playback.py
│   │   │   ├── availability.py
│   │   │   ├── path_transit.py
│   │   │   ├── loopix_routing.py
│   │   │   ├── kademlia.py
│   │   │   ├── poisson_process.py
│   │   │   ├── global_observer.py
│   │   │   ├── protocol_registry.py
│   │   │   └── topology.py
│   │   ├── crypto/
│   │   │   ├── key_manager.py
│   │   │   ├── encryption.py
│   │   │   ├── sphinx.py
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
└── web/
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
        │   │   ├── MessagePlanEditor.svelte
        │   │   ├── NetworkGraph.svelte
        │   │   ├── ParticipantDevice.svelte
        │   │   ├── DeviceMessageLog.svelte
        │   │   ├── NodeInspector.svelte
        │   │   ├── ProtocolInspector.svelte
        │   │   ├── ArtefactLineage.svelte
        │   │   ├── RouteControls.svelte
        │   │   ├── EventTimeline.svelte
        │   │   └── PlaybackControls.svelte
        │   ├── d3/
        │   │   ├── graph-layout.ts
        │   │   ├── graph-renderer.ts
        │   │   └── route-animation.ts
        │   ├── stores/
        │   │   ├── connection.ts
        │   │   ├── simulation.ts
        │   │   ├── messages.ts
        │   │   ├── lineage.ts
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

Implementation is iterative: write the smallest focused test for a logical behaviour, implement it, run that test, inspect its expected output, then run the affected integration tests before continuing. Do not generate a phase's code first and add tests afterwards.

## 12.1 Python unit tests

Test at minimum:

### Person and connection channel
- Alice and Bob are instances of the same `Person` class.
- Each person has a distinct channel instance.
- Each person has independent client state.
- A Tor instance forwards abstract requests and emits entry/exit events.
- Tor is not accidentally implemented as a real Tor client.

### Mixnet
- Mixnet creates the configured number of nodes.
- Each node has a unique ID.
- Providers and mix nodes form the exact configured Loopix stratified topology.
- Every packet independently samples one node from each layer.
- Each hop delay is independently sampled from the configured exponential distribution.
- A mix unwraps one Sphinx layer, checks integrity/replay state and follows the encoded next hop.
- Client payload, loop and drop-cover traffic follow their configured Poisson processes.
- Mix loop traffic follows its configured Poisson process.
- A failed hop terminates the packet attempt; an application retry creates a fresh route.
- Fixed-size polling responses are padded with dummy messages when required.
- Deterministic test fixtures validate route, delay and traffic generation against reference equations.

### DHT
- DHT nodes have unique IDs.
- Node IDs and keys are exactly 160 bits.
- XOR distance is calculated against reference vectors.
- `k = 20` bucket ordering, splitting and ping-before-eviction match Kademlia 2002.
- `PING`, `STORE`, `FIND_NODE` and `FIND_VALUE` match the defined RPC semantics.
- Parallel lookup uses `alpha = 3` and terminates according to the reference algorithm.
- Join, refresh, caching, storage and republishing transitions match the reference algorithm in simulation time.
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

### Network paths and interventions
- Every topology edge resolves to a `NetworkPath` object.
- Transit start and completion are separated by the configured logical path delay.
- Path delay, Loopix mix delay and playback delay remain independent.
- A marker can remain in transit across multiple rendered frames without the web client inventing state.
- Blocking a path prevents new transits.
- Existing transits complete by default; `drop_in_flight` produces the documented failure event.
- Blocking/restoring a stage boundary updates exactly the Python-owned paths crossing that boundary.

### Scheduler/playback
- Every scheduled network action is a `SimulationStep` object with stable identity and typed execution state.
- Step execution emits events without conflating the step object with those event records.
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
- Tests reject a forged signature, a substituted reply key and a valid signature presented under a different participant or message context before accepting text or storing a reply key.
- Lineage shows the reply key as encrypted content through DHT/storage and reveals it only after Bob decrypts and verifies the sender.

### Messages, polling and device logs
- Generated default messages contain 3–10 words from the bundled Lorem ipsum corpus.
- The same seed produces the same default message plan.
- Pre-run edits replace Python's staged plan and edits are rejected after run starts.
- One to ten exchanges produce the expected sender/reply transmission counts.
- Disabling polling leaves messages stored and prevents retrieval/reply generation.
- Re-enabling polling permits later retrieval.
- Device logs use correct direction, logical timestamp, state and participant-visible plaintext.

## 12.2 API and integration tests

- Health endpoint responds.
- Port selection falls back when 8000 is occupied.
- Startup prints the actual bound port.
- Create simulation validates input.
- Create simulation returns generated topology.
- Create simulation returns `NetworkPath` objects and staged messages.
- Create simulation does not start message traffic.
- Staged-message update and reset behaviour work.
- Run starts the scheduler.
- Pause/resume/step/stop work.
- WebSocket receives events.
- Playback-delay command updates the backend.
- Manual node availability commands work.
- Polling enable/disable commands work during execution.
- Path and stage-boundary block/restore commands work during execution.
- Device-log and lineage endpoints return only authorised safe state.
- Invalid commands return useful errors.
- Reconnect can resynchronise from current state.

## 12.3 Frontend tests

- Connection screen renders without backend.
- Port input resolves endpoint URLs correctly.
- Full HTTP URL input resolves WebSocket URL correctly.
- Health-check failure is displayed.
- WebSocket connection status updates.
- Configuration sliders enforce limits.
- Sender, receiver and mixnet-node counts share the network setup panel.
- Create simulation sends the expected configuration.
- Staged generated messages render and edits are accepted before run.
- Topology renders only from backend data.
- Stage columns remain ordered and node cards do not overlap at 6 and 20 mix nodes.
- Reply routes reuse the same node cards and render in the lower lane from right to left.
- Path transit markers remain between endpoints until completion events.
- Selecting a node opens the correct inspector.
- Protocol-state updates render when Python sends them.
- Route events animate the actual selected route.
- Offline/recovery events update node status.
- Playback slider sends updates to Python.
- Polling and path controls show pending/applied/rejected command state.
- Participant device logs show direction, formatted time and message text.
- Key/manifest/fragment lineage never exposes private keys or premature plaintext reply keys.
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
- receiver polling initially disabled, then enabled during the run
- one path blocked and restored during the run
- edited staged text for at least one sender

Expected result:

1. Python creates three sender `Person` instances and one receiver `Person` instance.
2. Each person gets an independent connection channel.
3. Python generates the mixnet, DHT and storage nodes.
4. The UI renders the returned topology in ordered stage columns with forward and reply lanes.
5. Three conversations are created between the senders and the receiver, according to the configured pairing.
6. Messages are encrypted and sent through the selected channel and simulated mixnet.
7. Python constructs an independent Loopix source route for every packet; mix nodes process their encoded Sphinx layer and delay.
8. At least one route attempt encounters an unavailable/unresponsive peer.
9. The sender performs a bounded end-to-end retry using a fresh packet and independently sampled source route.
10. Bob polls for available messages.
11. Bob retrieves the required encrypted fragments.
12. Bob reconstructs and decrypts messages.
13. Replies are signed and encrypted to the sender reply public key verified in the received content.
14. The UI shows all relevant events, route changes, node states, protocol-state updates and exact algorithm metadata.
15. The same simulation seed reproduces the same non-cryptographic network/failure decisions.
16. Path markers visibly remain in transit for their path delay, independently of mix and playback delays.
17. The blocked path is visibly unavailable, affects delivery, and becomes eligible after restoration.
18. Bob retrieves nothing while polling is disabled and resumes retrieval after it is enabled.
19. Selected conversation panes show timestamped send/reply logs, including the edited message.
20. The lineage view shows the encrypted reply-key relationship without exposing it in DHT/storage plaintext.

---

# 13. Implementation phases and task order

Implement in this order. Do not start with the D3 UI.

Within every phase, treat each checklist item as a testable increment: write or update focused tests, implement the item, run those tests, inspect expected output and only then continue. Run the affected integration suite at each phase exit.

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
- [ ] Implement Tor, Outline Shadowsocks and direct connection channels.
- [ ] Implement `Mixnet`.
- [ ] Implement `MixNode`.
- [ ] Implement Loopix `ProviderNode`.
- [ ] Implement `DHTNetwork` and `DHTNode`.
- [ ] Implement `StorageNetwork` and `StorageNode`.
- [ ] Implement `NetworkPath` and its typed DTO.
- [ ] Implement `Fragment` and `MessageManifest`.
- [ ] Implement `Conversation`.
- [ ] Implement the `SimulationStep` base contract and typed concrete network-step objects.
- [ ] Implement one inert `GlobalObserver` owned by each simulation.
- [ ] Implement participant staged-message and device-log state.
- [ ] Implement explicit DTO/topology serialisation.
- [ ] Test object identity, ownership and uniqueness.

**Exit criteria:** Python can generate a complete object graph from a configuration without running message traffic.

## Phase 4 — Loopix topology and routing

- [ ] Implement providers and ordered mix layers.
- [ ] Implement complete adjacency between consecutive layers.
- [ ] Implement independent per-packet source-route sampling.
- [ ] Implement reference-compatible Sphinx packet construction, processing, integrity checks and replay tags using a maintained implementation.
- [ ] Implement source-selected exponential per-hop delays.
- [ ] Implement payload, client loop, drop-cover and mix loop Poisson processes.
- [ ] Implement fixed-size provider polling responses with dummy padding.
- [ ] Implement packet failure and bounded end-to-end retry with a fresh route.
- [ ] Emit detailed route-construction and packet-processing events.
- [ ] Test the state machine and distributions against the Loopix 2017 reference.

**Exit criteria:** the Python engine faithfully simulates the selected Loopix profile and the web client only visualises its topology, parameters and events.

## Phase 5 — Availability and scheduler

- [ ] Implement per-node availability controller.
- [ ] Implement seeded failure scheduling.
- [ ] Support short, long, always-offline and always-online cases.
- [ ] Implement deterministic event scheduler.
- [ ] Queue and execute `SimulationStep` objects rather than anonymous callbacks or untyped step dictionaries.
- [ ] Implement simulation clock.
- [ ] Implement path-transit steps with independent logical transit delay and seeded jitter.
- [ ] Implement separate playback delay controller.
- [ ] Implement pause/resume/step/stop.
- [ ] Implement manual availability controls.
- [ ] Implement path/stage-boundary block and restore controls, including documented in-flight behaviour.
- [ ] Test reproducibility and timing separation.

**Exit criteria:** nodes change state during a simulation and routing reacts to those changes.

## Phase 6 — DHT and storage

- [ ] Implement Kademlia 2002 160-bit node IDs and XOR distance.
- [ ] Implement `k = 20` buckets with reference splitting, ordering and eviction behaviour.
- [ ] Implement the four Kademlia RPCs and `alpha = 3` parallel lookup.
- [ ] Implement reference join, refresh, caching, storage and republishing behaviour.
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
- [ ] Sign context, content and the designated reply public key with the device’s private Ed25519 key before encryption.
- [ ] Verify against the expected sender’s simulated directory pin before accepting or learning a reply key.
- [ ] Emit safe key, manifest and fragment lineage without exposing private material.
- [ ] Ensure private keys never leave the Python engine.
- [ ] Test successful and failed decryption.
- [ ] Document authenticated per-run participant IDs and the absence of external identity assurance.

**Exit criteria:** Alice can encrypt for Bob, the simulated network carries ciphertext, Bob decrypts and verifies Alice’s signature, then signs his reply and encrypts it to the verified reply public key.

## Phase 8 — Conversation and polling workflow

- [ ] Generate sender and receiver `Person` instances from configuration.
- [ ] Implement pairing strategies.
- [ ] Generate conversation IDs.
- [ ] Generate message IDs.
- [ ] Implement 1–10 configurable exchanges.
- [ ] Generate deterministic 3–10-word Lorem ipsum defaults.
- [ ] Implement pre-run staged-message editing and reset-to-editable behaviour.
- [ ] Implement Bob/client polling.
- [ ] Implement runtime polling enable/disable state.
- [ ] Ensure no unsolicited push notification is delivered to Bob.
- [ ] Implement reply flow.
- [ ] Implement timestamped per-device message logs.
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
- [ ] Implement staged-message, polling, path-blocking, device-log and lineage commands/endpoints.
- [ ] Test disconnect/reconnect.

**Exit criteria:** a non-visual client can create and control a simulation and receive all events.

## Phase 10 — SvelteKit connection and configuration UI

- [ ] Build the light infrastructure-diagram design tokens derived from the visual reference.
- [ ] Build initial backend connection screen.
- [ ] Accept port or full local endpoint.
- [ ] Derive HTTP and WebSocket URLs.
- [ ] Implement health check.
- [ ] Implement WebSocket connect/disconnect/reconnect.
- [ ] Display backend/API status.
- [ ] Build the network setup panel with sender, receiver and mixnet-node counts together.
- [ ] Build polling defaults and 1–10 exchange controls.
- [ ] Build the post-create/reset staged-message editor.
- [ ] Build failure configuration controls.
- [ ] Build playback delay slider.
- [ ] Create simulation through HTTP.
- [ ] Display returned simulation ID and configuration.

**Exit criteria:** frontend can connect to any correctly configured local backend port, create a simulation and control its lifecycle.

## Phase 11 — D3 topology and inspectors

- [ ] Build D3 graph layout.
- [ ] Implement stable protocol-stage columns with strong `forceX` constraints.
- [ ] Implement collision, cluster spacing, stable incremental positions and responsive zoom/scroll.
- [ ] Implement upper forward and lower reply lanes without duplicate node cards.
- [ ] Render backend-supplied nodes and edges.
- [ ] Add zoom and pan.
- [ ] Add node selection.
- [ ] Build node inspector.
- [ ] Build protocol-state and algorithm inspector.
- [ ] Highlight selected peers and links.
- [ ] Apply incremental topology updates.
- [ ] Render participant portraits and selectable message logs.
- [ ] Test layout legibility and responsiveness with 6 and 20 mix nodes.

**Exit criteria:** the user can inspect the generated network, each node's protocol state and the exact algorithm profile and parameters in use.

## Phase 12 — Live routes, event timeline and final integration

- [ ] Animate actual Python-selected routes.
- [ ] Animate path transits for the Python-owned logical transit duration.
- [ ] Show attempted/failed/successful hops.
- [ ] Show each independently source-routed retry packet.
- [ ] Show Poisson-mix queued/released packet and cover-traffic events.
- [ ] Show node availability transitions.
- [ ] Show Bob polling and retrieval.
- [ ] Add runtime polling toggles and path/stage block/restore controls.
- [ ] Show encrypted reply-key, manifest and fragment lineage.
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
python python/main.py
```

The implementation may use a package entry point, but the README must provide one simple command.

Python prints the actual selected port.

## 14.2 Start frontend

In a second terminal:

```bash
cd web
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
- Edit or accept each sender's staged messages.
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

These decisions should remain explicit and be isolated behind interfaces until the user approves a protocol choice. Loopix 2017 and Kademlia 2002 are selected reference algorithms, not open choices.

1. **Loopix-to-storage boundary:** define how the egress provider hands an opaque application packet into the custom DHT/storage subsystem without implying that subsystem is part of Loopix.
2. **Sphinx implementation:** select and pin a maintained, reference-compatible implementation. Do not implement cryptographic primitives manually or claim complete Loopix fidelity while Sphinx is stubbed.
3. **DHT privacy:** exact mailbox lookup-key construction and protection against metadata correlation require a separate design.
4. **Manifest confidentiality:** decide precisely which manifest fields are public, opaque or encrypted. Do not assume every field is hidden merely because the message payload is encrypted.
5. **Storage redundancy:** the MVP may use replication. Erasure coding is not implied and must not be claimed unless implemented.
6. **External identity assurance:** the selected Ed25519 construction verifies messages against the expected participant’s per-run directory pin. Authenticating the directory outside the simulator, enrolling real-world identities and handling compromised keys remain open.
7. **Application replay protection:** Sphinx replay-tag handling protects the mix packet layer; separately define message nonce/ID handling and recipient duplicate suppression.
8. **Polling profile:** Loopix uses fixed-frequency polling and fixed-size padded responses. Select the profile parameters without changing that behaviour silently.
9. **Adversary model:** the observer views and attacker controls need explicit capabilities. Do not claim global traffic-analysis resistance from this simulator.
10. **Node operator model:** operators may own one or more nodes. Independence should be configurable so the simulator can model correlated failures or collusion later.

---

# 16. Definition of done

The first complete implementation is done when:

- [ ] Python starts locally and prints the actual HTTP/WebSocket port.
- [ ] SvelteKit starts independently with `npm run dev`.
- [ ] The frontend accepts the backend port/endpoint and connects successfully.
- [ ] The user can configure 1–10 senders and 1–10 receivers.
- [ ] The user can configure 6–20 mixnet nodes.
- [ ] Sender, receiver and mixnet-node counts appear together in the network setup panel.
- [ ] The user can configure conversation pairing and 1–10 message exchanges.
- [ ] Python creates all people and network objects.
- [ ] Every person has an independent connection channel.
- [ ] Providers and mix nodes implement the selected Loopix 2017 profile, including stratified source routing, Sphinx processing, Poisson mixing and cover traffic.
- [ ] DHT nodes implement the original Kademlia 2002 algorithm with the declared parameters.
- [ ] Storage nodes hold encrypted fragments.
- [ ] Every traversable connection is a `NetworkPath` with independent logical transit delay and block state.
- [ ] Nodes randomly go offline and recover for configurable periods.
- [ ] Path transit delay, Loopix mix delay, outage duration and playback delay remain separate.
- [ ] The frontend can change playback delay while the simulation runs.
- [ ] Python constructs Loopix source routes, executes Kademlia lookups and emits their protocol events to the frontend.
- [ ] The UI displays actual message routes, failures and retries.
- [ ] The UI uses ordered stage columns, an upper forward lane and lower reply lane without duplicated reply nodes.
- [ ] Messages remain visibly in transit between nodes for the Python-owned path delay.
- [ ] D3 collision and stage forces produce readable layouts for 6 and 20 mix nodes.
- [ ] The UI can inspect every node's protocol state and displays the exact algorithm name, reference, profile and parameters.
- [ ] Bob polls for messages through his own client and selected channel.
- [ ] The user can enable or disable receiver polling during a run.
- [ ] The user can block and restore paths or stage boundaries during a run.
- [ ] Generated and edited staged messages work after create/reset and before run.
- [ ] Default messages and replies contain deterministic 3–10-word Lorem ipsum text.
- [ ] Participant conversation panes show timestamped send/reply logs.
- [ ] Alice can encrypt a message for Bob and Bob can decrypt it.
- [ ] Bob can address a signed reply using the X25519 reply key from the successfully verified forward message.
- [ ] The UI shows safe key/manifest/fragment lineage and never exposes the reply key as plaintext DHT/storage metadata.
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
- stop after each logical component, write/update tests, run them and inspect expected output before continuing;
- run relevant tests;
- report what changed;
- report test results;
- report coverage where available;
- identify any unresolved protocol decision;
- do not claim completion for functionality that is only represented visually.

The final product must be a working local simulation whose Python engine is authoritative and whose SvelteKit/D3 frontend faithfully visualises the events and state produced by that engine.

# Local control API

The Python process prints its bound HTTP and WebSocket URLs. A health read or a WebSocket connection leaves the engine idle. The local development origins are `http://localhost:5173` and `http://127.0.0.1:5173`.

| Request | Result |
|---|---|
| `GET /health`, `GET /api/info`, `GET /api/config` | Connection status, protocol registry and actual configuration defaults |
| `POST /api/simulations` | Validate configuration and create an editable snapshot |
| `GET /api/simulations/{id}` | Current authoritative state and reset epoch |
| `GET /api/simulations/{id}/topology` | Nodes and transport paths |
| `GET /api/simulations/{id}/nodes/{node}` | Local observations and protocol details |
| `PUT /api/simulations/{id}/messages` | Atomically edit staged messages |
| `POST /api/simulations/{id}/commands` | Apply a typed command with a command ID |
| `POST /api/simulations/{id}/{operation}` | Run, pause, resume, single-step, stop or reset |
| `GET /api/simulations/{id}/events?after=0&limit=500` | Read an ordered page of safe events |
| `GET /api/simulations/{id}/device-logs` | Read participant-local logs |
| `GET /api/simulations/{id}/lineage` | Read the projected artefact history |

Connect to `/ws`, then send a `subscribe` command with the simulation ID and a unique command ID. The initial response includes a snapshot and recent events. Subsequent deltas contain the updated clock, changed objects and event records. Reconnect using the last epoch and sequence. Reset starts a new epoch. The service holds scenarios in process memory.

Every simulation decision runs in Python. A UI may interpolate a position between the current clock and the next scheduled logical step. Only Python can complete or fail a transit. Interactive request schemas are available at the bound service’s `/docs`.

from random import Random
from secrets import randbits, token_hex
from typing import Any

from .config import Config
from .events import Event
from .kademlia import DHTNetwork
from .participants import People
from .steps import Action, SimulationStep, StepResult
from .storage import StorageNetwork
from .topology import GlobalObserver, Topology


class Simulation:
    def __init__(self, config: Config, simulation_id: str | None = None):
        self.id = simulation_id or "sim-" + token_hex(6)
        self.seed = config.random_seed if config.random_seed is not None else randbits(52)
        self.config = config.model_copy(update={"random_seed": self.seed})
        self.rng = Random(self.seed)
        self.clients = People(self.config, self.rng)
        self.topology = Topology(self.config, self.rng, self.clients)
        self.dht = DHTNetwork(Random(self.rng.getrandbits(160)), timeout_ms=config.rpc_timeout_ms)
        for uid in self.topology.dht_ids:
            self.dht.add_node(uid)
        self.storage = StorageNetwork(self.topology.storage_ids)
        self.observer = GlobalObserver("observer-" + self.id)
        self.status = "ready"
        self.now = 0
        self.events: list[Event] = []
        self.current_step: SimulationStep | None = None
        self.lineage: list[dict[str, Any]] = []
        for outage in config.scheduled_outages:
            if outage.node_id not in self.topology.nodes:
                raise ValueError(f"Unknown outage node {outage.node_id}")

    def perform(self, action: Action) -> StepResult:
        raise ValueError(f"Unsupported action {type(action).__name__}")

    def snapshot(self) -> dict[str, Any]:
        return {
            "simulation_id": self.id,
            "random_seed": self.seed,
            "status": self.status,
            "simulation_time_ms": self.now,
            "sequence": len(self.events),
            "config": self.config.model_dump(),
            "topology": self.topology.snapshot(),
            "devices": [p.device() for p in self.clients.people.values()],
            "messages": [m.model_dump() for m in self.clients.messages.values()],
            "lineage": list(self.lineage),
        }

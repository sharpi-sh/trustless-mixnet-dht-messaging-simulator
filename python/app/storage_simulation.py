from .config import Config
from .dht_runtime import DHTRuntime
from .network import NetworkSimulation
from .steps import Action
from .vault_runtime import VaultRuntime


class StorageSimulation(NetworkSimulation):
    def __init__(self, config: Config, simulation_id: str | None = None):
        super().__init__(config, simulation_id)
        self.rpc = DHTRuntime(self)
        self.vaults = VaultRuntime(self)

    def initialise(self) -> None:
        super().initialise()
        self.rpc.start()

    def change_node(self, uid: str, online: bool, reason: str) -> None:
        changed = self.topology.nodes[uid].online != online
        super().change_node(uid, online, reason)
        if changed:
            self.rpc.availability(uid, online)

    def handle(self, action: Action) -> bool:
        return self.rpc.handle(action) or self.vaults.handle(action) or super().handle(action)

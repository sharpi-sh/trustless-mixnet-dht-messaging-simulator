from .config import Config
from .network import NetworkSimulation
from .dht_runtime import DHTRuntime
from .vault_runtime import VaultRuntime
from .steps import Action


class StorageSimulation(NetworkSimulation):
    def __init__(self,config: Config,simulation_id: str | None=None):
        super().__init__(config,simulation_id)
        self.rpc=DHTRuntime(self)
        self.vaults=VaultRuntime(self)

    def initialise(self) -> None:
        super().initialise()
        self.rpc.start()

    def handle(self,action: Action) -> bool:
        return self.rpc.handle(action) or self.vaults.handle(action) or super().handle(action)

from app.config import Config
from app.engine import Action, Engine
from app.vault_runtime import Placed, Reconstructed, VaultFailed, VaultRuntime


class VaultExperiment(Engine):
    def __init__(self):
        super().__init__(Config(random_seed=37,chunk_bytes=32,storage_nodes=3))
        self.vaults=VaultRuntime(self)
        self.result=None

    def handle(self,action):
        if isinstance(action,(Placed,Reconstructed,VaultFailed)):
            self.result=action
            return True
        return self.vaults.handle(action)

    def run_until_result(self):
        for _ in self.drain(1000):
            if self.result:
                break
        assert self.result is not None
        result,self.result=self.result,None
        return result


def test_replica_failover_on_explicit_paths():
    sim=VaultExperiment()
    sim.lifecycle("run")
    data=b"opaque"*17
    sim.vaults.place(Action(source="dht-1",message_id="msg-1",token="w"),data)
    manifest=sim.run_until_result().manifest
    vault=manifest.fragments[0].replicas[0]
    sim.change_node(vault,False,"test")
    sim.vaults.fetch(Action(source="tor-receiver-1",message_id="msg-1",token="r"),manifest)
    assert sim.run_until_result().ciphertext==data
    assert any(e.event_type=="path_transit_failed" for e in sim.events)
    assert all(e.event_type!="simulation_error" for e in sim.events)


def test_missing_all_copies_reports_terminal_failure():
    sim=VaultExperiment()
    sim.lifecycle("run")
    for uid in sim.storage.nodes:
        sim.change_node(uid,False,"test")
    sim.vaults.place(Action(source="dht-1",message_id="msg-1",token="w"),b"opaque")
    assert isinstance(sim.run_until_result(),VaultFailed)

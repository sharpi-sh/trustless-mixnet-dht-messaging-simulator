"""Runnable network with packet processing, logical transport and per-node inspectors."""
from typing import Any
from .engine import Engine
from .packet_runtime import PacketRuntime
from .profiles import profiles
from .steps import Action
from .topology import MixNode
from .config import Config


class NetworkSimulation(Engine):
    def __init__(self,config: Config,simulation_id: str | None=None):
        super().__init__(config,simulation_id)
        self.packets=PacketRuntime(self)
        self.registry=profiles(self.config)

    def initialise(self) -> None:
        super().initialise()
        self.packets.start()

    def handle(self,action: Action) -> bool:
        return self.packets.handle(action) or super().handle(action)

    def inspect(self,uid: str) -> dict[str,Any]:
        node=self.topology.nodes[uid]
        profile={"person":"device","tor":"tor-abstraction","mix":"loopix-usenix-2017",
                 "provider":"loopix-usenix-2017","dht":"kademlia-2002","storage":"replicated-storage"}[node.kind]
        detail=node.model_dump()
        state: dict[str,Any]={}
        if isinstance(node,MixNode):
            peers=[]
            for adj in node.adjacent_peers.values():
                peer=self.topology.nodes[adj.peer_id]
                peers.append({**adj.model_dump(),"address":peer.simulated_address,"stage":peer.stage,
                              "path_id":self.topology.path_id(uid,peer.id)})
            state.update(adjacent_peers=peers,delayed_packets=node.delayed_packets)
        if node.kind in {"provider","mix"}:
            state.update(replay_tags=self.packets.traffic.sphinx.replay_count(uid),
                         mu_per_second=self.config.mu_per_second)
        elif node.kind=="dht":
            state.update(self.dht.inspect(uid,self.now))
        elif node.kind=="storage":
            state.update(self.storage.inspect(uid))
        elif node.kind=="tor":
            tor=next(p.tor for p in self.clients.people.values() if p.tor.id==uid)
            state.update(owner=tor.owner_id,entries=tor.entry_count,exits=tor.exit_count)
        elif node.kind=="person":
            state.update(self.clients.people[uid].device())
        return {"node":detail,"profile":next(p.model_dump() for p in self.registry if p.id==profile),
                "state":state,"active_paths":[p.id for p in self.topology.paths.values() if p.active and uid in (p.source_id,p.target_id)]}

    def snapshot(self) -> dict[str,Any]:
        return {**super().snapshot(),"profiles":[p.model_dump() for p in self.registry],
                "step_delay_ms":self.step_delay_ms,"initialised":self.initialised,
                "next_step_ms":self.queue[0][0] if self.queue else None}

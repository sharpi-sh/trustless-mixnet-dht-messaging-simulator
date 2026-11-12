"""Loopix source selection and traffic clocks, independent of network transport."""
from dataclasses import dataclass, field
from random import Random
from typing import Literal

from .config import Config
from .topology import Mixnet

Traffic = Literal["payload","client_loop","drop","mix_loop"]


@dataclass(frozen=True)
class Route:
    nodes: list[str]
    delays_ms: list[int]
    layers: list[list[str]]
    seed: int

    def decision(self) -> dict[str,object]:
        return {"algorithm":"loopix-usenix-2017", "ordered_route":self.nodes,
                "layers":[{"eligible":layer,"excluded":[],"selected":next(n for n in self.nodes if n in layer)}
                          for layer in self.layers], "delays_ms":self.delays_ms,"decision_seed":self.seed}


class Loopix:
    def __init__(self, topology: Mixnet, config: Config, rng: Random):
        self.topology = topology
        self.config = config
        self.rng = rng

    def route(self, ingress: str, egress: str, reverse: bool = False) -> Route:
        # The reply lane is visual. Every independent packet traverses the same ordered strata.
        layers = self.topology.layers
        seed = self.rng.getrandbits(52)
        sampler = Random(seed)
        nodes = [ingress, *(sampler.choice(layer) for layer in layers), egress]
        return self._timed(nodes,layers,sampler,seed)

    def mix_loop(self, origin: str) -> Route:
        seed = self.rng.getrandbits(52)
        sampler = Random(seed)
        layers = self.topology.layers
        index = next(i for i,layer in enumerate(layers) if origin in layer)
        cycle = [*layers[index+1:],list(self.topology.providers),*layers[:index]]
        nodes = [*(sampler.choice(group) for group in cycle), origin]
        return self._timed(nodes,cycle,sampler,seed)

    def _timed(self,nodes: list[str], layers: list[list[str]],sampler: Random,seed: int) -> Route:
        delays = [round(1000*sampler.expovariate(self.config.mu_per_second)) for _ in nodes]
        # A terminal recipient does not forward another Sphinx layer.
        delays[-1] = 0
        return Route(nodes,delays,layers,seed)

    def interval(self, kind: Traffic) -> int:
        rates = {"payload":self.config.payload_rate_per_minute,
                 "client_loop":self.config.client_loop_rate_per_minute,
                 "drop":self.config.drop_cover_rate_per_minute,
                 "mix_loop":self.config.mix_loop_rate_per_minute}
        return max(1,round(60000*self.rng.expovariate(rates[kind])))


@dataclass
class ProviderInbox:
    messages: list[bytes] = field(default_factory=list)

    def poll(self, slots: int, width: int) -> tuple[bytes,...]:
        """Fixed-count, fixed-width transport cells; framing is local to the simulation."""
        cells = []
        for message in self.messages[:slots]:
            if len(message)+2 > width:
                raise ValueError("Provider cell capacity exceeded")
            cells.append((len(message).to_bytes(2,"big")+message).ljust(width,b"\x00"))
        del self.messages[:slots]
        cells.extend([bytes(width)]*(slots-len(cells)))
        return tuple(cells)

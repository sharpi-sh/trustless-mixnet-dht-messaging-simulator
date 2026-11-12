"""Translate Kademlia datagrams and timers into independently observable network steps."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .kademlia import Complete, Effect, Notice, Rpc, Timer
from .steps import Action

if TYPE_CHECKING:
    from .engine import Engine


@dataclass(kw_only=True)
class Join(Action):
    bootstrap: str | None = None


@dataclass(kw_only=True)
class Maintenance(Action):
    pass


@dataclass(kw_only=True)
class IncomingRPC(Action):
    wire: Rpc


@dataclass(kw_only=True)
class LostRPC(Action):
    pass


@dataclass(kw_only=True)
class RPCTimer(Action):
    timer: Timer


@dataclass(kw_only=True)
class DHTRequest(Action):
    key: int
    value: bytes | None = None


@dataclass(kw_only=True)
class DHTResult(Action):
    result: Complete


class DHTRuntime:
    def __init__(self, sim: Engine):
        self.sim = sim
        self.pending: dict[str, DHTRequest] = {}

    def start(self) -> None:
        bootstrap = self.sim.topology.dht_ids[0]
        for i, uid in enumerate(self.sim.topology.dht_ids):
            self.sim.schedule(Join(source=uid, bootstrap=bootstrap if i else None))
            self.sim.schedule(Maintenance(source=uid), 3600000 + self.sim.rng.randrange(60000))

    def effects(self, effects: list[Effect], action: Action) -> None:
        for effect in effects:
            if isinstance(effect, Rpc):
                incoming = IncomingRPC(
                    source=effect.source,
                    target=effect.target,
                    wire=effect,
                    token=f"rpc-{effect.rpc_id:040x}",
                    message_id=action.message_id,
                    lane=action.lane,
                )
                self.sim.transit(
                    effect.source,
                    effect.target,
                    incoming,
                    LostRPC(
                        source=effect.source,
                        target=effect.target,
                        token=incoming.token,
                        message_id=action.message_id,
                        lane=action.lane,
                    ),
                    token=incoming.token,
                    lane=action.lane,
                )
            elif isinstance(effect, Timer):
                self.sim.schedule(
                    RPCTimer(
                        source=action.source,
                        timer=effect,
                        message_id=action.message_id,
                        lane=action.lane,
                    ),
                    max(0, effect.at - self.sim.now),
                )
            elif isinstance(effect, Notice):
                self.sim.emit(
                    effect.kind,
                    Action(
                        source=effect.peer,
                        target=action.target,
                        lane=action.lane,
                        message_id=action.message_id,
                        token=action.token,
                    ),
                    **effect.details,
                )
            elif isinstance(effect, Complete):
                request = self.pending.pop(effect.op_id, None)
                if request:
                    self.sim.schedule(
                        DHTResult(
                            source=request.source,
                            target=request.target,
                            token=request.token,
                            message_id=request.message_id,
                            lane=request.lane,
                            result=effect,
                        )
                    )
                elif effect.op_id.startswith("join-"):
                    self.sim.emit(
                        "kademlia_join_completed", action, peer=effect.op_id[5:], success=effect.success
                    )

    def handle(self, action: Action) -> bool:
        sim = self.sim
        dht = sim.dht
        now = sim.now
        if isinstance(action, Join):
            if sim.topology.nodes[action.source].online:
                self.effects(dht.join(action.source, action.bootstrap, now), action)
        elif isinstance(action, Maintenance):
            if sim.topology.nodes[action.source].online:
                self.effects(dht.maintenance(action.source, now), action)
            sim.schedule(action, 3600000)
        elif isinstance(action, DHTRequest):
            self.pending[action.token] = action
            if not sim.topology.nodes[action.source].online:
                effects: list[Effect] = [Complete(action.token, False, None, ())]
            elif action.value is None:
                effects = dht.lookup(action.token, action.source, action.key, now)
            else:
                effects = dht.publish(action.token, action.source, action.key, action.value, now)
            self.effects(effects, action)
        elif isinstance(action, IncomingRPC):
            self.effects(dht.receive(action.wire, now), action)
        elif isinstance(action, RPCTimer):
            owner = action.timer.peer
            if not owner or sim.topology.nodes[owner].online:
                self.effects(dht.wake(action.timer, now), action)
        elif not isinstance(action, LostRPC):
            return False
        return True

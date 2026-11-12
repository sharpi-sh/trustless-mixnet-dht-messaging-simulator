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
    due: int = 0


@dataclass(kw_only=True)
class Maintenance(Action):
    periodic: bool = True


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
        self.joined: set[str] = set()
        self._joining: set[str] = set()
        self._next_join: dict[str, int] = {}
        self._backoff: dict[str, int] = {}
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        for uid in self.sim.topology.dht_ids:
            self._join_later(uid, 0)
            self.sim.schedule(Maintenance(source=uid), 3600000 + self.sim.rng.randrange(60000))

    def _join_later(self, peer: str, delay: int) -> None:
        if peer in self.joined or peer in self._joining or not self.sim.topology.nodes[peer].online:
            return
        due = self.sim.now + delay
        if peer in self._next_join and self._next_join[peer] <= due:
            return
        self._next_join[peer] = due
        self.sim.schedule(Join(source=peer, due=due), delay)

    def availability(self, peer: str, online: bool) -> None:
        if not self._started or peer not in self.sim.dht.nodes:
            return
        if online:
            self._join_later(peer, 0)
            self.sim.schedule(Maintenance(source=peer, periodic=False))
        else:
            self._next_join.pop(peer, None)
            self.effects(self.sim.dht.disconnect(peer), Action(source=peer))

    def _join_finished(self, peer: str, success: bool) -> None:
        self._joining.discard(peer)
        ctx = Action(source=peer)
        self.sim.emit("kademlia_join_completed", ctx, peer=peer, success=success)
        if success:
            self.joined.add(peer)
            self._backoff.pop(peer, None)
        elif self.sim.topology.nodes[peer].online:
            delay = self._backoff.get(peer, min(60_000, self.sim.dht.timeout_ms))
            self._backoff[peer] = min(60_000, 2 * delay)
            self._join_later(peer, delay)
            self.sim.emit("kademlia_join_retry_scheduled", ctx, delay_ms=delay)

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
                    self._join_finished(effect.op_id[5:], effect.success)

    def handle(self, action: Action) -> bool:
        sim = self.sim
        dht = sim.dht
        now = sim.now
        if isinstance(action, Join):
            peer = action.source
            if self._next_join.get(peer) == action.due:
                del self._next_join[peer]
                if sim.topology.nodes[peer].online:
                    self._joining.add(peer)
                    seed = sim.topology.dht_ids[0]
                    self.effects(dht.join(peer, None if peer == seed else seed, now), action)
        elif isinstance(action, Maintenance):
            if sim.topology.nodes[action.source].online:
                self.effects(dht.maintenance(action.source, now), action)
            if action.periodic:
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
            if sim.topology.nodes[action.wire.target].online:
                self.effects(dht.receive(action.wire, now), action)
        elif isinstance(action, RPCTimer):
            owner = action.timer.peer
            if not owner or sim.topology.nodes[owner].online:
                self.effects(dht.wake(action.timer, now), action)
        elif not isinstance(action, LostRPC):
            return False
        return True

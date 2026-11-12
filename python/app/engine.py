"""Discrete-event simulation kernel. Wall-clock pacing belongs to the API runner."""

import heapq
from collections.abc import Iterable
from dataclasses import dataclass
from random import Random
from typing import Any, Literal

from .availability import Availability, AvailabilityChange, AvailabilityTimer
from .config import Config
from .events import Event
from .loopix import ProviderInbox
from .simulation import Simulation
from .steps import Action, SimulationStep, StepResult


@dataclass(kw_only=True)
class Transit(Action):
    success: Action
    failure: Action


@dataclass(kw_only=True)
class Arrival(Action):
    transit: Transit
    transit_id: str


@dataclass(kw_only=True)
class Intervention(Action):
    command: Literal["availability", "polling", "path", "boundary", "delay"]
    enabled: bool = True
    drop_in_flight: bool = False
    delay_ms: int = 500


class Engine(Simulation):
    def __init__(self, config: Config, simulation_id: str | None = None):
        super().__init__(config, simulation_id)
        self.queue: list[tuple[int, int, SimulationStep]] = []
        self.serial = 0
        self.inboxes = {uid: ProviderInbox() for uid in self.clients.people}
        self.in_flight: dict[str, Arrival] = {}
        self.applied: dict[str, StepResult] = {}
        self.initialised = False
        self.step_delay_ms = config.step_delay_ms
        self.availability = Availability(config, self.topology, Random(self.rng.getrandbits(128)))
        for at, action in self.availability.start():
            if isinstance(action, AvailabilityChange) and at == 0:
                self.topology.nodes[action.source].online = action.online
                self.topology.nodes[action.source].history.append((0, action.online))
            else:
                self.schedule(action, at)

    def make_step(self, action: Action, delay_ms: int) -> SimulationStep:
        if delay_ms < 0:
            raise ValueError("Steps cannot precede the current clock")
        self.serial += 1
        return SimulationStep(
            step_id=f"step-{self.serial}",
            simulation_id=self.id,
            scheduled_ms=self.now + delay_ms,
            action=action,
        )

    def schedule(self, action: Action, delay_ms: int = 0) -> None:
        step = self.make_step(action, delay_ms)
        heapq.heappush(self.queue, (step.scheduled_ms, self.serial, step))

    def emit(self, kind: str, action: Action, **details: Any) -> None:
        seq = len(self.events) + 1
        msg = self.clients.messages.get(action.message_id)
        self.events.append(
            Event(
                event_id=f"evt-{seq}",
                event_type=kind,
                simulation_id=self.id,
                sequence=seq,
                simulation_time_ms=self.now,
                source_id=action.source or None,
                target_id=action.target or None,
                message_id=action.message_id or None,
                conversation_id=msg.conversation_id if msg else None,
                step_id=self.current_step.step_id if self.current_step else None,
                payload={"lane": action.lane, "token": action.token, **details},
            )
        )

    def execute(self, step: SimulationStep) -> StepResult:
        self.current_step = step
        self.now = step.scheduled_ms
        self.emit("simulation_step_started", step.action, step=step.dto())
        try:
            result = step.execute(self)
        except (ValueError, KeyError) as exc:
            result = StepResult(outcome="failed", detail=str(exc))
            step.state, step.result = "failed", result
            self.emit("simulation_error", step.action, reason=str(exc))
        self.emit("simulation_step_completed", step.action, step=step.dto())
        self.current_step = None
        return result

    def initialise(self) -> None:
        self.initialised = True

    def lifecycle(self, command: str) -> None:
        if command == "reset":
            type(self).__init__(self, self.config, self.id)
            return
        if command in {"run", "resume", "step"}:
            if self.status not in {"ready", "running", "paused"}:
                raise ValueError(f"Cannot {command} a {self.status} run")
            if command == "resume" and self.status == "ready":
                raise ValueError("Start the staged run first")
            if not self.initialised:
                self.initialise()
            if command == "step":
                self.status = "paused"
                self.advance()
                return
            previous = self.status
            self.status = "running"
            if previous != "running":
                self.emit(
                    "simulation_resumed" if previous == "paused" else "simulation_started", Action()
                )
        elif command == "pause" and self.status in {"running", "paused"}:
            self.status = "paused"
            self.emit("simulation_paused", Action())
        elif command == "stop" and self.status in {"running", "paused", "stopped"}:
            self.status = "stopped"
            self.emit("simulation_stopped", Action())
        else:
            raise ValueError(f"Cannot {command} a {self.status} run")

    def advance(self) -> None:
        if self.queue and self.status in {"running", "paused"}:
            _, _, step = heapq.heappop(self.queue)
            self.execute(step)

    def transit(
        self,
        source: str,
        target: str,
        success: Action,
        failure: Action,
        *,
        token: str,
        lane: Literal["forward", "reply"] = "forward",
    ) -> None:
        self.schedule(
            Transit(
                source=source,
                target=target,
                success=success,
                failure=failure,
                token=token,
                lane=lane,
                message_id=success.message_id or failure.message_id,
            )
        )

    def start_transit(self, action: Transit) -> None:
        path = self.topology.paths[self.topology.path_id(action.source, action.target)]
        path.attempted += 1
        uid = f"transit-{self.serial}-{path.attempted}"
        if path.blocked or not self.topology.nodes[action.source].online:
            path.failed += 1
            self.emit(
                "path_transit_failed",
                action,
                path_id=path.id,
                transit_id=uid,
                reason="blocked" if path.blocked else "source unavailable",
            )
            self.schedule(action.failure, self.config.ack_timeout_ms)
            return
        delay = path.delay(self.rng)
        end = Arrival(
            source=action.source,
            target=action.target,
            token=action.token,
            lane=action.lane,
            message_id=action.message_id,
            transit=action,
            transit_id=uid,
        )
        self.in_flight[uid] = end
        path.active[uid] = {
            "start_ms": self.now,
            "end_ms": self.now + delay,
            "source": action.source,
            "target": action.target,
            "lane": action.lane,
            "token": action.token,
        }
        self.topology.nodes[action.source].last_activity = self.now
        self.emit(
            "path_transit_started",
            action,
            path_id=path.id,
            transit_id=uid,
            delay_ms=delay,
            start_ms=self.now,
            end_ms=self.now + delay,
        )
        self.schedule(end, delay)

    def arrive(self, action: Arrival, drop: bool = False) -> None:
        if not self.in_flight.pop(action.transit_id, None):
            return
        path = self.topology.paths[self.topology.path_id(action.source, action.target)]
        del path.active[action.transit_id]
        if drop or not self.topology.nodes[action.target].online:
            path.failed += 1
            path.dropped += int(drop)
            self.emit(
                "path_transit_failed",
                action,
                path_id=path.id,
                transit_id=action.transit_id,
                reason="dropped in flight" if drop else "unresponsive",
            )
            self.schedule(action.transit.failure, self.config.ack_timeout_ms)
        else:
            path.completed += 1
            self.topology.nodes[action.target].last_activity = self.now
            self.emit("path_transit_completed", action, path_id=path.id, transit_id=action.transit_id)
            self.schedule(action.transit.success)

    def change_node(self, uid: str, online: bool, reason: str) -> None:
        node = self.topology.nodes[uid]
        if node.online != online:
            node.online = online
            node.history.append((self.now, online))
            node.failure_count += int(not online)
            self.emit("node_status_changed", Action(source=uid), online=online, reason=reason)

    def intervene(self, action: Intervention) -> StepResult:
        if not action.token:
            raise ValueError("A command ID is required")
        if action.token not in self.applied:
            self.applied[action.token] = self.execute(self.make_step(action, 0))
        return self.applied[action.token]

    def apply(self, action: Intervention) -> None:
        if action.command == "availability":
            self.change_node(action.target, action.enabled, "manual")
        elif action.command == "polling":
            people = self.clients.people
            selected = (
                [people[action.target]]
                if action.target
                else [p for p in people.values() if p.role == "receiver"]
            )
            for person in selected:
                person.polling_enabled = action.enabled
                self.emit(
                    "receiver_polling_enabled" if action.enabled else "receiver_polling_disabled",
                    action,
                    person_id=person.id,
                )
        elif action.command == "delay":
            if not 1 <= action.delay_ms <= 2000:
                raise ValueError("Playback delay must be 1–2000 ms")
            self.step_delay_ms = action.delay_ms
            self.emit("playback_delay_updated", action, step_delay_ms=self.step_delay_ms)
        else:
            paths = self.topology.paths
            selected_paths = (
                [paths[action.target]]
                if action.command == "path"
                else [p for p in paths.values() if p.boundary == action.target]
            )
            if not selected_paths:
                raise ValueError("Unknown stage boundary")
            for path in selected_paths:
                path.blocked = not action.enabled
                path.blocked_at = self.now if path.blocked else None
                path.blocked_by = action.token if path.blocked else None
                self.emit(
                    "network_path_blocked" if path.blocked else "network_path_restored",
                    action,
                    path_id=path.id,
                    drop_in_flight=action.drop_in_flight,
                )
                if path.blocked and action.drop_in_flight:
                    for uid in list(path.active):
                        self.arrive(self.in_flight[uid], drop=True)

    def perform(self, action: Action) -> StepResult:
        if isinstance(action, AvailabilityChange):
            self.change_node(action.source, action.online, action.reason)
        elif isinstance(action, AvailabilityTimer):
            for at, change in self.availability.execute(action, self.now):
                self.schedule(change, at - self.now)
        elif isinstance(action, Transit):
            self.start_transit(action)
        elif isinstance(action, Arrival):
            self.arrive(action)
        elif isinstance(action, Intervention):
            self.apply(action)
        elif not self.handle(action):
            return super().perform(action)
        return StepResult(outcome="applied")

    def handle(self, action: Action) -> bool:
        return False

    def drain(self, limit: int) -> Iterable[SimulationStep]:
        """Run through the same one-step entry point without wall-clock pacing."""
        for _ in range(limit):
            if not self.queue or self.status != "running":
                break
            step = self.queue[0][2]
            self.advance()
            yield step

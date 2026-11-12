"""Local simulation registry, idempotent controls and independently paced runners."""

import asyncio
from dataclasses import dataclass, field
from typing import Any

from .api_models import Command
from .config import Config
from .engine import Intervention
from .events import Event
from .lab import Laboratory
from .lineage import OPERATIONS
from .steps import Action

FIRST_HOP_STEP_LIMIT = 5000
# Keep controls and the event stream live while stepping over protocol traffic.
STREAM_BATCH_STEPS = 32
IDLE_PLAYBACK_STEPS = 256
# Faster than one display frame: group changes into at most eight projections
# per second, flushing sooner for controls, the first departure or a full batch.
FAST_PLAYBACK_MS = 16
STREAM_INTERVAL = 0.125
STREAM_EVENT_LIMIT = 512
MESSAGE_EVENTS = OPERATIONS.keys() | {
    "path_transit_started",
    "path_transit_completed",
    "path_transit_failed",
    "mix_packet_queued",
    "mix_packet_released",
    "packet_retry_scheduled",
    "device_unavailable",
    "message_delivery_failed",
}


def _message_frame(events: list[Event], first_departure: int | None) -> bool:
    for event in events:
        if first_departure is not None and event.sequence >= first_departure:
            if event.event_type == "poll_message_found":
                return True
            if event.message_id and event.event_type in MESSAGE_EVENTS:
                return True
        elif event.message_id and event.event_type in {
            "path_transit_failed",
            "device_unavailable",
            "message_delivery_failed",
        }:
            # An interrupted first attempt must be visible even before any departure.
            return True
    return False


@dataclass
class _Receipt:
    request: dict[str, Any]
    result: dict[str, Any] | None = None
    error: str | None = None


@dataclass
class _Session:
    lab: Laboratory
    changed: asyncio.Condition = field(default_factory=asyncio.Condition)
    speed_changed: asyncio.Event = field(default_factory=asyncio.Event)
    runner: asyncio.Task[None] | None = None
    published_sequence: int = 0
    control_sequence: int = 0
    first_hop_budget: int = 0
    receipts: dict[str, _Receipt] = field(default_factory=dict)

    def publish(self) -> None:
        # Late subscribers must wait for the same frame boundary as existing ones.
        self.published_sequence = len(self.lab.events)
        self.changed.notify_all()


class Service:
    def __init__(self) -> None:
        self.current: Laboratory | None = None
        self.epochs: dict[str, int] = {}
        self._sessions: dict[str, _Session] = {}
        self._closed = False

    def create(self, config: Config) -> Laboratory:
        if self._closed:
            raise ValueError("Simulation service is closed")
        lab = Laboratory(config)
        lab.emit("simulation_created", Action(), random_seed=lab.seed)
        self._sessions[lab.id] = _Session(lab, published_sequence=len(lab.events))
        self.epochs[lab.id] = 0
        self.current = lab
        return lab

    def get(self, simulation_id: str) -> Laboratory:
        return self._sessions[simulation_id].lab

    async def wait(self, simulation_id: str, epoch: int, seq: int) -> None:
        session = self._sessions[simulation_id]
        async with session.changed:
            await session.changed.wait_for(
                lambda: (
                    self._closed
                    or self.epochs[simulation_id] != epoch
                    or session.published_sequence > seq
                )
            )

    async def wait_stream(self, simulation_id: str, epoch: int, cursor: int, last_sent: float) -> None:
        await self.wait(simulation_id, epoch, cursor)
        session = self._sessions[simulation_id]
        lab = session.lab
        deadline = last_sent + STREAM_INTERVAL

        def flush_now() -> bool:
            return (
                self._closed
                or self.epochs[simulation_id] != epoch
                or lab.status != "running"
                or lab.step_delay_ms > FAST_PLAYBACK_MS
                or cursor < session.control_sequence
                or cursor < (lab.first_message_hop_sequence or 0)
                or session.published_sequence - cursor >= STREAM_EVENT_LIMIT
            )

        async with session.changed:
            if flush_now() or asyncio.get_running_loop().time() >= deadline:
                return
            try:
                async with asyncio.timeout_at(deadline):
                    await session.changed.wait_for(flush_now)
            except TimeoutError:
                pass

    @staticmethod
    def _cancel_runner(session: _Session) -> None:
        if session.runner is not None:
            session.runner.cancel()
            session.runner = None

    @staticmethod
    def _failed(lab: Laboratory, reason: str) -> None:
        lab.status = "failed"
        lab.emit("simulation_failed", Action(), reason=reason)

    async def _play(self, session: _Session) -> None:
        lab = session.lab
        loop = asyncio.get_running_loop()
        background_steps = 0
        try:
            while lab.status == "running" and session.runner is asyncio.current_task():
                async with session.changed:
                    cursor = len(lab.events)
                    if not lab.queue:
                        self._failed(
                            lab, "No steps remain before the simulation reached a terminal state"
                        )
                    else:
                        step = lab.queue[0][2]
                        lab.advance()
                        if step.state == "failed":
                            self._failed(
                                lab,
                                step.result.detail
                                if step.result and step.result.detail
                                else "Simulation step failed",
                            )
                    if session.first_hop_budget and lab.status == "running":
                        session.first_hop_budget -= 1
                        if lab.first_message_hop_sequence is not None or not session.first_hop_budget:
                            lab.lifecycle("pause")
                            lab.emit(
                                "first_message_hop_step_finished",
                                Action(),
                                departure_sequence=lab.first_message_hop_sequence,
                                limit=FIRST_HOP_STEP_LIMIT,
                            )
                    events = lab.events[cursor:]
                    frame = _message_frame(events, lab.first_message_hop_sequence)
                    poll_frame = any(
                        e.event_type.startswith("poll_")
                        or (
                            e.event_type.startswith("path_transit_")
                            and e.payload["token"].startswith("poll-")
                        )
                        for e in events
                    )
                    background_steps = 0 if frame else background_steps + 1
                    # Publish timer-driven polls even before the first payload, without
                    # inserting a playback delay ahead of the first message departure.
                    after_departure = lab.first_message_hop_sequence is not None
                    dwell = frame or (after_departure and background_steps >= IDLE_PLAYBACK_STEPS)
                    if dwell:
                        background_steps = 0
                    if (
                        dwell
                        or poll_frame
                        or (
                            after_departure
                            and (not lab.step_delay_ms or background_steps % STREAM_BATCH_STEPS == 0)
                        )
                        or lab.status != "running"
                    ):
                        session.publish()
                if lab.status != "running":
                    break
                if not dwell or lab.step_delay_ms == 0 or session.first_hop_budget:
                    # All scheduler actions run in order; each one yields to controls.
                    await asyncio.sleep(0)
                    continue
                stepped = loop.time()
                while True:
                    session.speed_changed.clear()
                    remaining = stepped + lab.step_delay_ms / 1000 - loop.time()
                    if remaining <= 0:
                        break
                    try:
                        await asyncio.wait_for(session.speed_changed.wait(), remaining)
                    except TimeoutError:
                        break
        except Exception as exc:  # noqa: BLE001 - a runner fault must reach subscribed clients
            async with session.changed:
                self._failed(lab, f"{type(exc).__name__}: {exc}")
                session.publish()
        finally:
            if session.runner is asyncio.current_task():
                session.runner = None

    def _read(self, lab: Laboratory, cmd: Command) -> dict[str, Any] | None:
        if cmd.type in {"request_state", "subscribe"}:
            return {**lab.snapshot(), "epoch": self.epochs[lab.id]}
        if cmd.type == "request_topology":
            return lab.topology.snapshot()
        if cmd.type in {"request_node_details", "request_protocol_state"}:
            return lab.inspect(cmd.target)
        if cmd.type == "request_device_logs":
            if cmd.target and cmd.target not in lab.clients.people:
                raise KeyError(cmd.target)
            devices = (
                [p.device() for p in lab.clients.people.values()]
                if lab.initialised
                else lab.snapshot()["devices"]
            )
            return {"devices": [p for p in devices if not cmd.target or p["id"] == cmd.target]}
        if cmd.type == "request_artefact_lineage":
            return {
                "lineage": [
                    row for row in lab.lineage if not cmd.target or row["message_id"] == cmd.target
                ]
            }
        if cmd.type == "ping":
            return {"pong": True}
        return None

    def _update(self, session: _Session, cmd: Command) -> None:
        lab = session.lab
        kind = cmd.type
        if kind in {"run", "resume", "step", "pause", "stop", "reset", "step_to_first_message_hop"}:
            seek = kind == "step_to_first_message_hop"
            if seek and (
                lab.status not in {"ready", "paused"} or lab.first_message_hop_sequence is not None
            ):
                raise ValueError(
                    "First-hop stepping requires a ready or paused run before its first message departure"
                )
            lab.lifecycle("run" if seek else kind)
            session.first_hop_budget = FIRST_HOP_STEP_LIMIT if seek else 0
            if seek:
                lab.emit("first_message_hop_step_started", Action(), limit=FIRST_HOP_STEP_LIMIT)
            if kind == "reset":
                self.epochs[lab.id] += 1
                lab.emit("simulation_reset", Action(), epoch=self.epochs[lab.id])
            if lab.status == "running":
                if session.runner is None:
                    session.runner = asyncio.create_task(self._play(session), name=f"play-{lab.id}")
            else:
                self._cancel_runner(session)
            return
        if kind == "set_staged_messages":
            if cmd.messages is None:
                raise ValueError("Staged messages are required")
            lab.edit_messages(cmd.messages)
            return
        if kind == "set_playback_delay" and cmd.delay_ms is not None:
            action = Intervention(
                token=cmd.command_id, target=cmd.target, command="delay", delay_ms=cmd.delay_ms
            )
        elif kind == "set_node_availability" and cmd.enabled is not None:
            action = Intervention(
                token=cmd.command_id, target=cmd.target, command="availability", enabled=cmd.enabled
            )
        elif kind == "set_polling_enabled" and cmd.enabled is not None:
            action = Intervention(
                token=cmd.command_id, target=cmd.target, command="polling", enabled=cmd.enabled
            )
        elif kind in {
            "block_network_path",
            "restore_network_path",
            "block_stage_boundary",
            "restore_stage_boundary",
        }:
            action = Intervention(
                token=cmd.command_id,
                target=cmd.target,
                command="path" if kind.endswith("_path") else "boundary",
                enabled=kind.startswith("restore"),
                drop_in_flight=cmd.drop_in_flight,
            )
        else:
            raise ValueError(f"Unsupported or incomplete command {kind}")
        outcome = lab.intervene(action)
        if outcome.outcome == "failed":
            raise ValueError(outcome.detail or "Control rejected")
        if kind == "set_playback_delay":
            session.speed_changed.set()

    async def command(self, lab: Laboratory, cmd: Command) -> dict[str, Any]:
        if self._closed:
            raise ValueError("Simulation service is closed")
        if cmd.simulation_id and cmd.simulation_id != lab.id:
            raise ValueError("Command simulation ID does not match the selected simulation")
        session = self._sessions[lab.id]
        async with session.changed:
            if (read := self._read(lab, cmd)) is not None:
                return read
            if not cmd.command_id:
                raise ValueError("A mutation requires a command ID")
            request = cmd.model_dump(exclude={"simulation_id"})
            receipt = session.receipts.get(cmd.command_id)
            if receipt:
                if receipt.request != request:
                    raise ValueError("Command ID already identifies a different mutation")
                if receipt.error is not None:
                    raise ValueError(receipt.error)
                assert receipt.result is not None
                return receipt.result.copy()
            try:
                if cmd.epoch is not None and cmd.epoch != self.epochs[lab.id]:
                    raise ValueError("Command belongs to a previous simulation epoch")
                self._update(session, cmd)
            except (KeyError, ValueError) as exc:
                session.receipts[cmd.command_id] = _Receipt(request, error=str(exc))
                raise ValueError(str(exc)) from exc
            finally:
                session.control_sequence = len(lab.events)
                session.publish()
            result = {"status": lab.status}
            session.receipts[cmd.command_id] = _Receipt(request, result=result)
            return result.copy()

    async def close(self) -> None:
        self._closed = True
        runners = []
        for session in self._sessions.values():
            async with session.changed:
                if session.runner is not None:
                    runners.append(session.runner)
                    self._cancel_runner(session)
                session.publish()
        if runners:
            await asyncio.gather(*runners, return_exceptions=True)

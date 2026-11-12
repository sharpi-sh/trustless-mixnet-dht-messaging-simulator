"""Local simulation registry, idempotent controls and independently paced runners."""

import asyncio
from dataclasses import dataclass, field
from typing import Any

from .api_models import Command
from .config import Config
from .engine import Intervention
from .lab import Laboratory
from .steps import Action


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
    receipts: dict[str, _Receipt] = field(default_factory=dict)


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
        self._sessions[lab.id] = _Session(lab)
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
                    or len(session.lab.events) != seq
                )
            )

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
        try:
            while lab.status == "running" and session.runner is asyncio.current_task():
                async with session.changed:
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
                    session.changed.notify_all()
                if lab.status != "running":
                    break
                if lab.step_delay_ms == 0:
                    # Max-speed playback still gives commands and stream readers a turn.
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
                session.changed.notify_all()
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
        if kind in {"run", "resume", "step", "pause", "stop", "reset"}:
            lab.lifecycle(kind)
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
                session.changed.notify_all()
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
                session.changed.notify_all()
        if runners:
            await asyncio.gather(*runners, return_exceptions=True)

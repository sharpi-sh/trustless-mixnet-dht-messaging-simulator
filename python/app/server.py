"""Loopback HTTP control, snapshots, incremental WebSocket events and reconnect."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from anyio import CancelScope
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import Field, ValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .api_models import Command, DeviceDTO, NodeDetails, Snapshot, TopologyDTO
from .config import Config, Model
from .devices import Lineage
from .events import Event
from .profiles import Profile, profiles
from .service import Service
from .stream import delta, snapshot

ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]
service = Service()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global service
    service = Service()
    yield
    await service.close()


app = FastAPI(title="Trustless Mixnet DHT Messaging Simulator", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGINS,
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Content-Type"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"])


@app.middleware("http")
async def local_origin(request: Request, call_next):
    if request.headers.get("origin") and request.headers["origin"] not in ORIGINS:
        return JSONResponse(
            {"detail": "Origin is outside the local development client"}, status_code=403
        )
    return await call_next(request)


class Health(Model):
    status: str = "ok"
    service: str = "simulation-backend"
    api_version: str = "1"
    simulation_active: bool
    simulation_id: str | None


class Info(Model):
    api_version: str = "1"
    port: int | None
    capabilities: list[str]
    protocols: list[Profile]


class Events(Model):
    epoch: int
    sequence: int
    events: list[Event]


class DeviceResponse(Model):
    devices: list[DeviceDTO]


class LineageResponse(Model):
    lineage: list[Lineage]


class Edits(Model):
    messages: dict[str, str]
    command_id: str = Field(default_factory=lambda: uuid4().hex)


class CommandResult(Model):
    command_id: str
    result: dict[str, Any]


@app.get("/health")
async def health() -> Health:
    active = service.current
    return Health(simulation_active=active is not None, simulation_id=active.id if active else None)


@app.get("/api/config")
async def defaults() -> Config:
    return Config.model_validate({})


@app.get("/api/info")
async def info() -> Info:
    cfg = service.current.config if service.current else Config.model_validate({})
    return Info(
        port=getattr(app.state, "port", None),
        capabilities=[
            "configuration",
            "snapshot",
            "stream",
            "run",
            "pause",
            "resume",
            "step",
            "step_to_first_message_hop",
            "stop",
            "reset",
            "polling",
            "path intervention",
            "device logs",
            "lineage",
        ],
        protocols=profiles(cfg),
    )


def get_lab(sid: str):
    try:
        return service.get(sid)
    except KeyError as exc:
        raise HTTPException(404, "Unknown simulation") from exc


@app.post("/api/simulations", status_code=201)
async def create(config: Config) -> Snapshot:
    try:
        lab = service.create(config)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return snapshot(lab, service.epochs[lab.id])


@app.get("/api/simulations/{sid}")
async def state(sid: str) -> Snapshot:
    return snapshot(get_lab(sid), service.epochs[sid])


@app.get("/api/simulations/{sid}/topology")
async def topology(sid: str) -> TopologyDTO:
    return TopologyDTO.model_validate(get_lab(sid).topology.snapshot())


@app.get("/api/simulations/{sid}/nodes/{uid}")
async def node(sid: str, uid: str) -> NodeDetails:
    try:
        return NodeDetails.model_validate(get_lab(sid).inspect(uid))
    except KeyError as exc:
        raise HTTPException(404, "Unknown node") from exc


@app.get("/api/simulations/{sid}/device-logs")
async def devices(sid: str) -> DeviceResponse:
    lab = get_lab(sid)
    return DeviceResponse.model_validate({"devices": [p.device() for p in lab.clients.people.values()]})


@app.get("/api/simulations/{sid}/lineage")
async def lineage(sid: str) -> LineageResponse:
    return LineageResponse.model_validate({"lineage": get_lab(sid).lineage})


@app.get("/api/simulations/{sid}/events")
async def events(
    sid: str, after: int = Query(0, ge=0), limit: int = Query(500, ge=1, le=5000)
) -> Events:
    lab = get_lab(sid)
    return Events(
        epoch=service.epochs[sid], sequence=len(lab.events), events=lab.events[after : after + limit]
    )


async def apply_command(sid: str, cmd: Command) -> CommandResult:
    if cmd.simulation_id and cmd.simulation_id != sid:
        raise HTTPException(409, "Command belongs to a different simulation")
    lab = get_lab(sid)
    try:
        result = await service.command(lab, cmd)
    except (ValueError, KeyError) as exc:
        raise HTTPException(409, str(exc)) from exc
    return CommandResult(command_id=cmd.command_id, result=result)


@app.put("/api/simulations/{sid}/messages")
async def edit(sid: str, edits: Edits) -> CommandResult:
    return await apply_command(
        sid,
        Command(
            type="set_staged_messages",
            simulation_id=sid,
            command_id=edits.command_id,
            messages=edits.messages,
        ),
    )


@app.post("/api/simulations/{sid}/commands")
async def control(sid: str, command: Command) -> CommandResult:
    return await apply_command(sid, command)


@app.post("/api/simulations/{sid}/{operation}")
async def lifecycle(sid: str, operation: str) -> CommandResult:
    if operation not in {
        "run",
        "resume",
        "pause",
        "step",
        "step_to_first_message_hop",
        "stop",
        "reset",
    }:
        raise HTTPException(404, "Unknown lifecycle command")
    return await apply_command(
        sid,
        Command.model_validate({"type": operation, "simulation_id": sid, "command_id": uuid4().hex}),
    )


@app.websocket("/ws")
async def websocket(ws: WebSocket):
    origin = ws.headers.get("origin")
    if origin and origin not in ORIGINS:
        await ws.close(code=1008)
        return
    await ws.accept()
    await ws.send_json({"type": "backend_ready", "api_version": "1"})
    sid: str | None = None
    epoch = cursor = 0
    recv = asyncio.create_task(ws.receive_text())
    change: asyncio.Task | None = None

    async def send_snapshot(history_after: int = 0):
        nonlocal epoch, cursor
        assert sid
        lab = service.get(sid)
        epoch = service.epochs[sid]
        cursor = len(lab.events)
        start = max(history_after, cursor - 1500)
        await ws.send_json(
            {
                "type": "snapshot",
                "state": snapshot(lab, epoch).model_dump(mode="json"),
                "history_after": start,
                "events": [e.model_dump() for e in lab.events[start:cursor]],
            }
        )

    try:
        while True:
            if sid:
                change = asyncio.create_task(service.wait(sid, epoch, cursor))
            pending: set[asyncio.Task[Any]] = {recv}
            if change is not None:
                pending.add(change)
            await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            if change is not None:
                change.cancel()
                await asyncio.gather(change, return_exceptions=True)
                change = None
            if recv.done():
                raw = recv.result()
                recv = asyncio.create_task(ws.receive_text())
                cmd = None
                try:
                    cmd = Command.model_validate_json(raw)
                    if cmd.type == "ping":
                        await ws.send_json({"type": "pong", "command_id": cmd.command_id})
                    elif cmd.type == "subscribe":
                        lab = service.get(cmd.simulation_id or "")
                        sid = lab.id
                        await send_snapshot(
                            cmd.after_sequence
                            if cmd.epoch == service.epochs[sid]
                            and cmd.after_sequence <= len(lab.events)
                            else 0
                        )
                    else:
                        if not sid or sid != cmd.simulation_id:
                            raise ValueError("Subscribe to this simulation first")
                        result = await service.command(service.get(sid), cmd)
                        await ws.send_json(
                            {"type": "ack", "command_id": cmd.command_id, "result": result}
                        )
                except (KeyError, ValueError, ValidationError) as exc:
                    await ws.send_json(
                        {
                            "type": "error",
                            "command_id": cmd.command_id if cmd else None,
                            "detail": str(exc),
                        }
                    )
            if sid:
                lab = service.get(sid)
                if epoch != service.epochs[sid] or len(lab.events) - cursor > 1500:
                    await send_snapshot()
                elif cursor < len(lab.events):
                    update = delta(lab, epoch, cursor)
                    cursor = update.sequence
                    await ws.send_json({"type": "delta", "delta": update.model_dump(mode="json")})
    except (WebSocketDisconnect, OSError, asyncio.CancelledError):
        pass
    finally:
        tasks = [t for t in (recv, change) if t is not None]
        for task in tasks:
            task.cancel()
        with CancelScope(shield=True):
            await asyncio.gather(*tasks, return_exceptions=True)

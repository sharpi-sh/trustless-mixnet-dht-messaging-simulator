"""Transfer each encrypted chunk across actual paths, then verify it at its consumer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .retrieval import RetrievalCallback
from .steps import Action
from .storage import MessageManifest

if TYPE_CHECKING:
    from .storage_simulation import StorageSimulation


@dataclass(kw_only=True)
class VaultWrite(Action):
    index: int


@dataclass(kw_only=True)
class VaultRead(RetrievalCallback):
    index: int
    replica: int
    generation: int = 0


@dataclass(kw_only=True)
class BytesReturned(VaultRead):
    pass


@dataclass(kw_only=True)
class VaultMiss(VaultRead):
    operation: str


@dataclass(kw_only=True)
class Placed(Action):
    manifest: MessageManifest


@dataclass(kw_only=True)
class Reconstructed(Action):
    ciphertext: bytes = field(repr=False)


@dataclass(kw_only=True)
class VaultFailed(Action):
    reason: str


@dataclass
class WriteJob:
    manifest: MessageManifest
    ciphertext: bytes
    waiting: int
    placed: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class ReadJob:
    manifest: MessageManifest
    device: str
    generation: int
    tickets: dict[int, str] = field(default_factory=dict)
    received: dict[str, bytes] = field(default_factory=dict)


class VaultRuntime:
    def __init__(self, sim: StorageSimulation):
        self.sim = sim
        self.writes: dict[str, WriteJob] = {}
        self.reads: dict[str, ReadJob] = {}
        self.generation = 0

    def place(self, action: Action, ciphertext: bytes) -> None:
        """action.source is the DHT/storage gateway where the opaque packet arrived."""
        cfg = self.sim.config
        manifest = self.sim.storage.plan(
            action.message_id, ciphertext, self.sim.rng, cfg.chunk_bytes, cfg.replicas
        )
        self.writes[action.token] = WriteJob(
            manifest, ciphertext, sum(len(f.replicas) for f in manifest.fragments)
        )
        self.sim.emit(
            "message_chunked",
            action,
            artefact_id=manifest.digest,
            count=len(manifest.fragments),
            size=len(ciphertext),
            container=manifest.id,
            contains="encrypted message bundle",
        )
        for i, fragment in enumerate(manifest.fragments):
            for idx, uid in enumerate(fragment.replicas):
                write = VaultWrite(
                    source=action.source,
                    target=uid,
                    lane=action.lane,
                    token=action.token,
                    message_id=action.message_id,
                    index=i,
                )
                miss = VaultMiss(
                    source=action.source,
                    target=uid,
                    lane=action.lane,
                    token=action.token,
                    message_id=action.message_id,
                    index=i,
                    replica=idx,
                    operation="write",
                )
                self.sim.transit(action.source, uid, write, miss, token=action.token, lane=action.lane)

    def _settle_write(self, action: VaultWrite | VaultMiss, ok: bool) -> None:
        job = self.writes[action.token]
        fragment = job.manifest.fragments[action.index]
        if ok:
            job.placed.setdefault(fragment.id, []).append(action.target)
            self.sim.emit(
                "fragment_stored",
                action,
                fragment_id=fragment.id,
                size=fragment.size,
                digest=fragment.digest,
                container=job.manifest.id,
            )
        else:
            self.sim.emit("fragment_placement_failed", action, fragment_id=fragment.id)
        job.waiting -= 1
        if job.waiting:
            return
        del self.writes[action.token]
        if len(job.placed) != len(job.manifest.fragments):
            self.sim.schedule(
                VaultFailed(
                    source=action.source,
                    token=action.token,
                    message_id=action.message_id,
                    lane=action.lane,
                    reason="No successful replica for a required chunk",
                )
            )
            return
        self.sim.schedule(
            Placed(
                source=action.source,
                token=action.token,
                message_id=action.message_id,
                lane=action.lane,
                manifest=job.manifest,
            )
        )

    def cancel_read(self, token: str) -> None:
        job = self.reads.pop(token, None)
        if job is not None:
            for ticket in job.tickets.values():
                self.sim.retrieval.cancel(ticket)

    def fetch(self, action: Action, manifest: MessageManifest) -> None:
        self.generation += 1
        self.reads[action.token] = ReadJob(manifest, action.source, self.generation)
        for i in range(len(manifest.fragments)):
            self._read(action, i, 0)

    def _read(self, action: Action, index: int, replica: int) -> None:
        job = self.reads[action.token]
        fragment = job.manifest.fragments[index]
        if replica >= len(fragment.replicas):
            self.cancel_read(action.token)
            self.sim.schedule(
                VaultFailed(
                    source=job.device,
                    token=action.token,
                    lane=action.lane,
                    message_id=action.message_id,
                    reason="All replicas missing or corrupt",
                )
            )
            return
        service = fragment.replicas[replica]
        read = VaultRead(
            source=service,
            target=service,
            lane=action.lane,
            token=action.token,
            message_id=action.message_id,
            index=index,
            replica=replica,
            generation=job.generation,
        )
        miss = VaultMiss(**vars(read), operation="read")
        self.sim.emit("fragment_retrieval_started", read, fragment_id=fragment.id, replica=replica + 1)
        job.tickets[index] = self.sim.retrieval.request(
            job.device, service, bytes.fromhex(fragment.id), fragment.size + 1, read, miss
        )

    def handle(self, action: Action) -> bool:
        sim = self.sim
        if isinstance(action, VaultWrite):
            write = self.writes[action.token]
            fragment = write.manifest.fragments[action.index]
            try:
                sim.storage.put(
                    action.target,
                    fragment,
                    write.ciphertext[fragment.offset : fragment.offset + fragment.size],
                )
                ok = True
            except (ValueError, KeyError):
                ok = False
            self._settle_write(action, ok)
        elif isinstance(action, VaultMiss):
            if action.operation == "write":
                f = self.writes[action.token].manifest.fragments[action.index]
                sim.storage.record_unavailable(action.target, f, "write")
                self._settle_write(action, False)
            elif (active := self.reads.get(action.token)) and active.generation == action.generation:
                self._read(action, action.index, action.replica + 1)
        elif isinstance(action, BytesReturned):
            job = self.reads.get(action.token)
            if job is None or job.tickets.get(action.index) != action.ticket:
                return True
            fragment = job.manifest.fragments[action.index]
            data = action.data[1:]
            try:
                if action.data[:1] != b"+":
                    raise ValueError("Replica could not return the requested fragment")
                fragment.verify(data)
            except ValueError:
                self._read(action, action.index, action.replica + 1)
                return True
            job.tickets.pop(action.index)
            job.received[fragment.id] = data
            sim.emit(
                "fragment_retrieved",
                action,
                fragment_id=fragment.id,
                integrity="verified",
                container=job.manifest.id,
            )
            if len(job.received) == len(job.manifest.fragments):
                ciphertext = sim.storage.reconstruct(job.manifest, job.received)
                self.cancel_read(action.token)
                sim.schedule(
                    Reconstructed(
                        source=job.device,
                        token=action.token,
                        lane=action.lane,
                        message_id=action.message_id,
                        ciphertext=ciphertext,
                    )
                )
        elif isinstance(action, VaultRead):
            job = self.reads.get(action.token)
            if job is None or job.tickets.get(action.index) != action.ticket:
                return True
            # Resolve only the opaque identifier delivered to this particular vault.
            try:
                fragment = sim.storage.nodes[action.target].placements[action.data.hex()].fragment
                payload = b"+" + sim.storage.get(action.target, fragment)
            except (KeyError, ValueError):
                sim.emit("fragment_retrieval_failed", action, fragment_id=action.data.hex())
                payload = b"-"
            returned = BytesReturned(
                source=job.device,
                target=job.device,
                token=action.token,
                lane=action.lane,
                message_id=action.message_id,
                index=action.index,
                replica=action.replica,
                ticket=action.ticket,
                generation=action.generation,
            )
            miss = VaultMiss(**vars(action), operation="return")
            sim.retrieval.reply(action.ticket, payload, returned, miss)
        else:
            return False
        return True

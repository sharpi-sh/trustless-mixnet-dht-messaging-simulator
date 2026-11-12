"""Experimental egress-to-storage handoff and pull-only recipient retrieval.

A fresh 160-bit handle indexes only an encrypted manifest. The simulator uses
its seeded RNG for reproducible lookup paths, so someone with the scenario
seed can predict handles. DHT and storage expose sizes, timing and access
patterns. The provider queues the handle only after receiving a STORE receipt.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from hashlib import sha256
from typing import TYPE_CHECKING

from .config import Model
from .crypto import seal, unseal
from .dht_runtime import DHTRequest, DHTResult
from .packet_runtime import PacketDelivered
from .polling import MailboxItem
from .steps import Action
from .storage import MessageManifest
from .traffic import Lane
from .vault_runtime import BytesReturned, Placed, Reconstructed, VaultFailed, VaultMiss, VaultRead

if TYPE_CHECKING:
    from .storage_simulation import StorageSimulation


@dataclass(kw_only=True)
class BundleDelivered(Action):
    ciphertext: bytes = field(repr=False)


@dataclass(kw_only=True)
class MailboxFailed(Action):
    reason: str


class _Stage(Enum):
    PLACE = "place ciphertext"
    PUBLISH = "store encrypted manifest"
    DEPOSIT = "queue handle at provider"
    ENTER = "request mailbox lookup"
    LOOKUP = "lookup encrypted manifest"
    RETURN = "return encrypted manifest"
    OPEN = "open manifest on device"
    FETCH = "fetch ciphertext replicas"
    FINISH = "return ciphertext to device"


@dataclass(kw_only=True)
class MailboxStep(Action):
    stage: _Stage
    data: bytes = field(default=b"", repr=False)
    manifest: MessageManifest | None = field(default=None, repr=False)


@dataclass(kw_only=True)
class MailboxTimeout(Action):
    continuation: MailboxStep = field(repr=False)


class _ManifestContents(Model):
    message_id: str
    manifest: MessageManifest


@dataclass(slots=True)
class _Job:
    recipient: str
    handle: bytes
    gateway: str
    message_id: str
    lane: Lane
    token: str
    egress: str = ""
    wrapping_key: bytes = field(default=b"", repr=False)
    retries: int = 0
    pending: MailboxStep | None = field(default=None, repr=False)

    def step(
        self,
        stage: _Stage,
        source: str,
        target: str,
        *,
        data: bytes = b"",
        manifest: MessageManifest | None = None,
    ) -> MailboxStep:
        return MailboxStep(
            stage=stage,
            source=source,
            target=target,
            token=self.token,
            message_id=self.message_id,
            lane=self.lane,
            data=data,
            manifest=manifest,
        )


class MailboxRuntime:
    def __init__(self, sim: StorageSimulation):
        self.sim = sim
        self._jobs: dict[str, _Job] = {}
        self._issued: set[bytes] = set()
        # Simulation-only failure attribution at each provider. Lookup and decryption
        # use the polled handle and recipient key independently of this information.
        self._labels: dict[tuple[str, bytes], str] = {}
        self._reading: set[tuple[str, bytes]] = set()
        self._finished: set[tuple[str, bytes]] = set()
        self._serial = 0

    def _token(self) -> str:
        self._serial += 1
        return f"mailbox-{self._serial}"

    def _move(self, step: MailboxStep) -> None:
        miss = MailboxTimeout(
            source=step.source,
            target=step.target,
            token=step.token,
            message_id=step.message_id,
            lane=step.lane,
            continuation=step,
        )
        self.sim.transit(step.source, step.target, step, miss, token=step.token, lane=step.lane)

    def _end(self, job: _Job) -> None:
        self._jobs.pop(job.token, None)
        if not job.egress:
            self._reading.discard((job.recipient, job.handle))

    def _fail(self, job: _Job, reason: str) -> None:
        self._end(job)
        if not job.egress:
            self._finished.add((job.recipient, job.handle))
        self.sim.schedule(
            MailboxFailed(
                source=job.egress or job.gateway,
                target=job.recipient,
                token=job.token,
                message_id=job.message_id,
                lane=job.lane,
                reason=reason,
            )
        )

    def _retry(self, job: _Job, step: MailboxStep, reason: str, *, transit: bool) -> None:
        if job.retries >= self.sim.config.max_retries:
            self._fail(job, reason)
            return
        job.retries += 1
        self.sim.emit(
            "mailbox_retry", step, attempt=job.retries + 1, stage=step.stage.value, reason=reason
        )
        if transit:
            self._move(step)
        else:
            self.sim.schedule(replace(step, source=step.target), self.sim.config.ack_timeout_ms)

    def _publish(self, action: PacketDelivered) -> None:
        handle = self.sim.rng.getrandbits(160).to_bytes(20, "big")
        while handle in self._issued:
            handle = self.sim.rng.getrandbits(160).to_bytes(20, "big")
        self._issued.add(handle)
        job = _Job(
            action.target,
            handle,
            self.sim.topology.dht_ids[0],
            action.message_id,
            action.lane,
            self._token(),
            action.source,
            action.payload[:32],
        )
        self._jobs[job.token] = job
        if len(action.payload) <= 32:
            self._fail(job, "Missing recipient key or encrypted bundle")
            return
        self._move(job.step(_Stage.PLACE, job.egress, job.gateway, data=action.payload[32:]))

    def _restore(self, job: _Job) -> None:
        self._end(job)
        inbox = self.sim.inboxes[job.recipient].messages
        if job.handle not in inbox:
            inbox.append(job.handle)

    def _read(self, action: MailboxItem) -> None:
        person = self.sim.clients.people[action.source]
        handle = action.handle
        if len(handle) != 20:
            self.sim.schedule(
                MailboxFailed(
                    source=person.id,
                    target=person.id,
                    token=action.token,
                    message_id=action.message_id,
                    lane=action.lane,
                    reason="Invalid lookup handle",
                )
            )
            return
        identity = (person.id, handle)
        if identity in self._finished or identity in self._reading:
            return
        # Start the reader on a different DHT peer so discovery uses normal RPCs.
        job = _Job(
            person.id,
            handle,
            self.sim.topology.dht_ids[-1],
            self._labels.get(identity, ""),
            action.lane,
            self._token(),
        )
        if not person.polling_enabled:
            self._restore(job)
            return
        self._reading.add(identity)
        self._jobs[job.token] = job
        self._move(job.step(_Stage.ENTER, person.id, person.tor.id))

    def _step(self, job: _Job, action: MailboxStep) -> None:
        sim = self.sim
        person = sim.clients.people[job.recipient]
        if action.stage == _Stage.PLACE:
            job.pending = action
            sim.vaults.place(replace(action, source=job.gateway), action.data)
        elif action.stage == _Stage.PUBLISH or action.stage == _Stage.LOOKUP:
            job.pending = action
            writing = action.stage == _Stage.PUBLISH
            if not writing and action.source != action.target:
                sim.channel_crossing(job.recipient, action, entering=False)
            sim.schedule(
                DHTRequest(
                    source=job.gateway,
                    token=job.token,
                    lane=job.lane,
                    message_id=job.message_id,
                    key=int.from_bytes(job.handle, "big"),
                    value=action.data if writing else None,
                )
            )
        elif action.stage == _Stage.DEPOSIT:
            self._labels[job.recipient, job.handle] = job.message_id
            sim.inboxes[job.recipient].messages.append(job.handle)
            self._end(job)
        elif action.stage == _Stage.ENTER:
            sim.channel_crossing(job.recipient, action, entering=True)
            self._move(job.step(_Stage.LOOKUP, person.tor.id, job.gateway))
        elif action.stage == _Stage.RETURN:
            sim.channel_crossing(job.recipient, action, entering=True)
            self._move(job.step(_Stage.OPEN, person.tor.id, person.id, data=action.data))
        elif action.stage == _Stage.OPEN:
            sim.channel_crossing(job.recipient, action, entering=False)
            decrypted = unseal(person.private_key, action.data, "manifest")
            contents = _ManifestContents.model_validate_json(decrypted)
            job.message_id = contents.message_id
            sim.emit(
                "manifest_retrieved",
                replace(action, source=person.id, message_id=job.message_id),
                artefact_id=sha256(action.data).hexdigest(),
                container=contents.manifest.id,
                size=len(action.data),
                integrity="verified",
            )
            self._move(job.step(_Stage.FETCH, person.id, person.tor.id, manifest=contents.manifest))
        elif action.stage == _Stage.FETCH:
            if action.source != action.target:
                sim.channel_crossing(job.recipient, action, entering=True)
            assert action.manifest is not None
            job.pending = action
            sim.vaults.fetch(replace(action, source=person.tor.id), action.manifest)
        elif action.stage == _Stage.FINISH:
            sim.channel_crossing(job.recipient, action, entering=False)
            self._end(job)
            self._finished.add((job.recipient, job.handle))
            sim.schedule(
                BundleDelivered(
                    source=action.source,
                    target=person.id,
                    token=job.token,
                    lane=job.lane,
                    message_id=job.message_id,
                    ciphertext=action.data,
                )
            )

    def handle(self, action: Action) -> bool:
        if isinstance(action, VaultRead):
            owner = self._jobs.get(action.token)
            if owner is not None and not owner.egress and not isinstance(action, VaultMiss):
                # VaultRead success callbacks retain request orientation for replica selection.
                # BytesReturned actually travels from the vault back to the access channel.
                returning = isinstance(action, BytesReturned)
                leg = (
                    replace(action, source=action.target, target=action.source) if returning else action
                )
                self.sim.channel_crossing(owner.recipient, leg, entering=returning)
            return False
        if isinstance(action, PacketDelivered):
            self._publish(action)
            return True
        if isinstance(action, MailboxItem):
            self._read(action)
            return True
        if not isinstance(
            action, (MailboxStep, MailboxTimeout, DHTResult, Placed, Reconstructed, VaultFailed)
        ):
            return False
        job = self._jobs.get(action.token)
        if job is None:
            return isinstance(action, (MailboxStep, MailboxTimeout)) or action.token.startswith(
                "mailbox-"
            )
        if not job.egress and not self.sim.clients.people[job.recipient].polling_enabled:
            self._restore(job)
            return True
        try:
            if isinstance(action, MailboxTimeout):
                self._retry(job, action.continuation, "Mailbox transport unresponsive", transit=True)
            elif isinstance(action, MailboxStep):
                if not self.sim.topology.nodes[action.target].online:
                    self._retry(
                        job,
                        action,
                        "Receiving node unavailable",
                        transit=action.source != action.target,
                    )
                else:
                    self._step(job, action)
            elif isinstance(action, VaultFailed):
                assert job.pending is not None
                self._retry(job, job.pending, action.reason, transit=False)
            elif isinstance(action, Placed):
                job.pending = None
                content = _ManifestContents(message_id=job.message_id, manifest=action.manifest)
                sealed = seal(job.wrapping_key, content.model_dump_json().encode(), "manifest")
                self.sim.schedule(job.step(_Stage.PUBLISH, job.gateway, job.gateway, data=sealed))
            elif isinstance(action, DHTResult):
                assert job.pending is not None
                if not action.result.success or (not job.egress and action.result.value is None):
                    self._retry(job, job.pending, "Mailbox DHT operation failed", transit=False)
                elif job.egress:
                    self.sim.emit(
                        "manifest_published",
                        action,
                        artefact_id=sha256(job.pending.data).hexdigest(),
                        size=len(job.pending.data),
                        replicas=len(action.result.peers),
                    )
                    job.pending = None
                    self._move(job.step(_Stage.DEPOSIT, job.gateway, job.egress))
                else:
                    assert action.result.value is not None
                    job.pending = None
                    channel = self.sim.clients.people[job.recipient].tor.id
                    self._move(job.step(_Stage.RETURN, job.gateway, channel, data=action.result.value))
            elif isinstance(action, Reconstructed):
                channel = self.sim.clients.people[job.recipient].tor.id
                job.pending = None
                self.sim.emit(
                    "message_reconstructed",
                    action,
                    artefact_id=sha256(action.ciphertext).hexdigest(),
                    size=len(action.ciphertext),
                    integrity="verified",
                )
                self._move(job.step(_Stage.FINISH, channel, job.recipient, data=action.ciphertext))
        except ValueError:
            self._fail(job, "Invalid mailbox envelope or manifest")
        return True

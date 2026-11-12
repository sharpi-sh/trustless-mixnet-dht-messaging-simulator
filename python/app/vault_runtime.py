"""Transfer each encrypted chunk across actual paths, then verify it at its consumer."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from .steps import Action
from .storage import MessageManifest

if TYPE_CHECKING:
    from .engine import Engine


@dataclass(kw_only=True)
class VaultWrite(Action):
    index: int


@dataclass(kw_only=True)
class VaultRead(Action):
    index: int
    replica: int


@dataclass(kw_only=True)
class BytesReturned(VaultRead):
    data: bytes = field(repr=False)


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
    placed: dict[str,list[str]] = field(default_factory=dict)


@dataclass
class ReadJob:
    manifest: MessageManifest
    received: dict[str,bytes] = field(default_factory=dict)


class VaultRuntime:
    def __init__(self,sim: Engine):
        self.sim=sim
        self.writes: dict[str,WriteJob]={}
        self.reads: dict[str,ReadJob]={}

    def place(self,action: Action,ciphertext: bytes) -> None:
        """action.source is the DHT/storage gateway where the opaque packet arrived."""
        cfg=self.sim.config
        manifest=self.sim.storage.plan(action.message_id,ciphertext,self.sim.rng,cfg.chunk_bytes,cfg.replicas)
        self.writes[action.token]=WriteJob(manifest,ciphertext,sum(len(f.replicas) for f in manifest.fragments))
        self.sim.emit("message_chunked",action,count=len(manifest.fragments),size=len(ciphertext),
                      container=manifest.id,contains="encrypted message bundle")
        for i,fragment in enumerate(manifest.fragments):
            for idx,uid in enumerate(fragment.replicas):
                write=VaultWrite(source=action.source,target=uid,lane=action.lane,token=action.token,
                                 message_id=action.message_id,index=i)
                miss=VaultMiss(source=action.source,target=uid,lane=action.lane,token=action.token,
                               message_id=action.message_id,index=i,replica=idx,operation="write")
                self.sim.transit(action.source,uid,write,miss,token=action.token,lane=action.lane)

    def _settle_write(self,action: VaultWrite | VaultMiss,ok: bool) -> None:
        job=self.writes[action.token]
        fragment=job.manifest.fragments[action.index]
        if ok:
            job.placed.setdefault(fragment.id,[]).append(action.target)
            self.sim.emit("fragment_stored",action,fragment_id=fragment.id,size=fragment.size,
                          digest=fragment.digest,container=job.manifest.id)
        else:
            self.sim.emit("fragment_placement_failed",action,fragment_id=fragment.id)
        job.waiting-=1
        if job.waiting:
            return
        del self.writes[action.token]
        context=dict(source=action.source,token=action.token,message_id=action.message_id,lane=action.lane)
        if len(job.placed)!=len(job.manifest.fragments):
            self.sim.schedule(VaultFailed(**context,reason="No successful replica for a required chunk"))
            return
        self.sim.schedule(Placed(**context,manifest=job.manifest))

    def fetch(self,action: Action,manifest: MessageManifest) -> None:
        self.reads[action.token]=ReadJob(manifest)
        for i in range(len(manifest.fragments)):
            self._read(action,i,0)

    def _read(self,action: Action,index: int,replica: int) -> None:
        fragment=self.reads[action.token].manifest.fragments[index]
        if replica>=len(fragment.replicas):
            del self.reads[action.token]
            self.sim.schedule(VaultFailed(source=action.source,token=action.token,
                lane=action.lane,message_id=action.message_id,reason="All replicas missing or corrupt"))
            return
        uid=fragment.replicas[replica]
        read=VaultRead(source=action.source,target=uid,lane=action.lane,token=action.token,
                       message_id=action.message_id,index=index,replica=replica)
        miss=VaultMiss(**vars(read),operation="read")
        self.sim.emit("fragment_retrieval_started",read,fragment_id=fragment.id,replica=replica+1)
        self.sim.transit(read.source,uid,read,miss,token=action.token,lane=action.lane)

    def handle(self,action: Action) -> bool:
        sim=self.sim
        if isinstance(action,VaultWrite):
            job=self.writes[action.token]
            fragment=job.manifest.fragments[action.index]
            try:
                sim.storage.put(action.target,fragment,job.ciphertext[fragment.offset:fragment.offset+fragment.size])
                ok=True
            except (ValueError,KeyError):
                ok=False
            self._settle_write(action,ok)
        elif isinstance(action,VaultMiss):
            if action.operation=="write":
                f=self.writes[action.token].manifest.fragments[action.index]
                sim.storage.record_unavailable(action.target,f,"write")
                self._settle_write(action,False)
            elif action.token in self.reads:
                f=self.reads[action.token].manifest.fragments[action.index]
                sim.storage.record_unavailable(action.target,f,"read")
                self._read(action,action.index,action.replica+1)
        elif isinstance(action,BytesReturned):
            if action.token not in self.reads:
                return True
            read=self.reads[action.token]
            f=read.manifest.fragments[action.index]
            read.received[f.id]=action.data
            sim.emit("fragment_retrieved",action,fragment_id=f.id,integrity="verified",container=read.manifest.id)
            if len(read.received)==len(read.manifest.fragments):
                data=sim.storage.reconstruct(read.manifest,read.received)
                del self.reads[action.token]
                sim.schedule(Reconstructed(source=action.source,token=action.token,lane=action.lane,
                                           message_id=action.message_id,ciphertext=data))
        elif isinstance(action,VaultRead):
            if action.token not in self.reads:
                return True
            f=self.reads[action.token].manifest.fragments[action.index]
            try:
                data=sim.storage.get(action.target,f)
            except (ValueError,KeyError):
                sim.emit("fragment_retrieval_failed",action,fragment_id=f.id)
                self._read(action,action.index,action.replica+1)
            else:
                returned=BytesReturned(**vars(action),data=data)
                miss=VaultMiss(**vars(action),operation="read")
                sim.transit(action.target,action.source,returned,miss,token=action.token,lane=action.lane)
        else:
            return False
        return True

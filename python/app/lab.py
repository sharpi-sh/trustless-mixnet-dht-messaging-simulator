"""One laboratory run. Only a successfully decrypted forward message unlocks its reply."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from .config import Config
from .devices import DeviceProtocol
from .engine import Intervention
from .lineage import project
from .mailbox import BundleDelivered, MailboxFailed, MailboxRuntime
from .packet_runtime import PacketFailed
from .participants import DeliveryState, StagedMessage
from .polling import PollRuntime
from .steps import Action
from .storage_simulation import StorageSimulation


@dataclass(kw_only=True)
class Compose(Action):
    pass


class Laboratory(StorageSimulation):
    def __init__(self,config: Config,simulation_id: str | None=None):
        super().__init__(config,simulation_id)
        self.devices=DeviceProtocol(self.clients)
        self.polls=PollRuntime(self)
        self.mailbox=MailboxRuntime(self)
        self.outcomes={uid:"staged" for uid in self.clients.messages}
        self.deferred: dict[str,BundleDelivered]={}
        self.order: dict[str,list[str]]={}
        for msg in self.clients.messages.values():
            self.order.setdefault(msg.conversation_id,[]).append(msg.id)

    def emit(self,kind: str,action: Action,**details: Any) -> None:
        super().emit(kind,action,**details)
        row=project(self.events[-1])
        if row is not None:
            self.lineage.append(row.model_dump())

    def edit_messages(self,updates: dict[str,str]) -> None:
        if self.initialised or self.status!="ready":
            raise ValueError("Reset the simulation before editing messages")
        # Validate the entire command before changing a single device's plan.
        replacements={}
        for uid,text in updates.items():
            if uid not in self.clients.messages:
                raise ValueError(f"Unknown staged message {uid}")
            m=self.clients.messages[uid]
            replacements[uid]=StagedMessage.model_validate({**m.model_dump(),"text":text})
        self.clients.messages.update(replacements)
        self.emit("staged_messages_updated",Action(),message_ids=list(replacements))

    def initialise(self) -> None:
        super().initialise()
        self.polls.start()
        for msgs in self.order.values():
            self.schedule(Compose(message_id=msgs[0]))
        self.emit("simulation_initialised",Action())

    def apply(self,action: Intervention) -> None:
        super().apply(action)
        if action.command=="polling":
            for p in self.clients.people.values():
                if action.target and p.id!=action.target or not action.target and p.role!="receiver":
                    continue
                if not action.enabled:
                    self.polls.cancel(p.id)
                else:
                    for uid,bundle in list(self.deferred.items()):
                        if bundle.target==p.id:
                            del self.deferred[uid]
                            self.schedule(bundle)

    def compose(self,uid: str) -> None:
        msg=self.clients.messages[uid]
        if self.outcomes[uid]!="staged":
            return
        ctx=Action(source=msg.sender_id,target=msg.target_id,message_id=uid,lane=msg.direction)
        wire,fingerprint=self.devices.prepare(msg)
        self.emit("public_key_retrieved",ctx,origin="simulated public webpage" if msg.direction=="forward"
                  else "decrypted unverified reply key",fingerprint=fingerprint)
        self.emit("reply_key_encapsulated",ctx,container=uid,field="encrypted reply public key")
        self.emit("message_encrypted",ctx,size=len(wire)-32,algorithm="X25519/HKDF-SHA-256/AES-256-GCM")
        state: DeliveryState="sent" if msg.direction=="forward" else "replied"
        self.devices.log(msg,msg.sender_id,state,self.now,msg.text)
        self.emit("device_log_updated",ctx,person_id=msg.sender_id,state=state)
        self.packets.outbox[msg.sender_id].append((uid,msg.target_id,wire,msg.direction))
        self.outcomes[uid]="sent"

    def received(self,action: BundleDelivered) -> None:
        msg=self.clients.messages[action.message_id]
        if self.outcomes[msg.id] in {"received","failed","skipped"}:
            return
        if not self.clients.people[msg.target_id].polling_enabled:
            self.deferred[msg.id]=action
            return
        self.devices.log(msg,msg.target_id,"delivered",self.now,"")
        try:
            learned=self.devices.accept(msg,action.ciphertext,self.now)
        except ValueError as exc:
            self.failure(msg.id,str(exc))
            return
        if learned is None:
            return
        ctx=Action(source=msg.target_id,message_id=msg.id,lane=msg.direction)
        self.emit("message_decrypted",ctx,integrity="verified")
        self.emit("reply_key_learned",ctx,fingerprint=learned,authentication="unverified")
        self.emit("device_log_updated",ctx,person_id=msg.target_id,state="received")
        self.outcomes[msg.id]="received"
        series=self.order[msg.conversation_id]
        index=series.index(msg.id)+1
        if index<len(series):
            self.schedule(Compose(message_id=series[index]))
        self.finish_if_terminal()

    def failure(self,uid: str,reason: str) -> None:
        if uid not in self.clients.messages or self.outcomes[uid] in {"received","failed","skipped"}:
            return
        msg=self.clients.messages[uid]
        self.outcomes[uid]="failed"
        self.devices.log(msg,msg.sender_id,"failed",self.now,msg.text)
        ctx=Action(source=msg.sender_id,message_id=uid,lane=msg.direction)
        self.emit("message_delivery_failed",ctx,reason=reason)
        self.emit("device_log_updated",ctx,person_id=msg.sender_id,state="failed")
        for other in self.order[msg.conversation_id]:
            if self.outcomes[other]=="staged":
                self.outcomes[other]="skipped"
        self.finish_if_terminal()

    def finish_if_terminal(self) -> None:
        if all(v in {"received","failed","skipped"} for v in self.outcomes.values()):
            self.status="failed" if "failed" in self.outcomes.values() else "completed"
            self.emit("simulation_"+self.status,Action(),outcomes=self.outcomes.copy())

    def handle(self,action: Action) -> bool:
        if isinstance(action,Compose):
            self.compose(action.message_id)
        elif isinstance(action,BundleDelivered):
            self.received(action)
        elif isinstance(action,(MailboxFailed,PacketFailed)):
            self.failure(action.message_id,action.reason)
        elif not self.polls.handle(action) and not self.mailbox.handle(action):
            return super().handle(action)
        return True

    def snapshot(self) -> dict[str,Any]:
        result=super().snapshot()
        if self.initialised:
            result["messages"]=[m.model_dump(exclude={"text"}) for m in self.clients.messages.values()]
        else:
            for device in result["devices"]:
                device["logs"]=[{"message_id":m.id,"conversation_id":m.conversation_id,"direction":m.direction,
                                 "state":"staged","simulation_time_ms":0,"text":m.text}
                                for m in self.clients.messages.values() if m.sender_id==device["id"]]
        result["outcomes"]=self.outcomes.copy()
        result["observer"]={"id":self.observer.id,"lifecycle":self.observer.lifecycle}
        return result

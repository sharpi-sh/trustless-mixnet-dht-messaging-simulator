"""Cursor-based projections of the laboratory's public state."""

from __future__ import annotations

from .api_models import Delta, DeviceDTO, Snapshot
from .lab import Laboratory
from .lineage import project
from .participants import DeviceLog


def snapshot(lab: Laboratory, epoch: int) -> Snapshot:
    return Snapshot.model_validate({**lab.snapshot(), "epoch": epoch})


def _devices(lab: Laboratory, selected: set[str]) -> list[DeviceDTO]:
    rows = {uid: DeviceDTO.model_validate(lab.clients.people[uid].device()) for uid in sorted(selected)}
    if rows and not lab.initialised:
        for device in rows.values():
            device.logs = []
        for message in lab.clients.messages.values():
            if device := rows.get(message.sender_id):
                device.logs.append(
                    DeviceLog(
                        message_id=message.id,
                        conversation_id=message.conversation_id,
                        direction=message.direction,
                        state="staged",
                        simulation_time_ms=0,
                        text=message.text,
                    )
                )
    return list(rows.values())


def delta(lab: Laboratory, epoch: int, since: int) -> Delta:
    """Return replacement records and append-only events after this epoch's cursor."""
    if type(since) is not int or not 0 <= since <= len(lab.events):
        raise ValueError("Sequence is outside this simulation epoch")
    events = lab.events[since:]
    nodes: set[str] = set()
    paths: set[str] = set()
    devices: set[str] = set()
    messages: set[str] = set()
    outcomes: set[str] = set()
    lineage = []
    for event in events:
        kind = event.event_type
        source, target = event.source_id, event.target_id
        if (
            kind
            in {
                "path_transit_started",
                "node_status_changed",
                "mix_packet_queued",
                "mix_packet_released",
            }
            and source in lab.topology.nodes
        ):
            assert source is not None
            nodes.add(source)
        elif kind == "path_transit_completed" and target in lab.topology.nodes:
            assert target is not None
            nodes.add(target)
        elif kind in {"sphinx_layer_processed", "mixnet_adjacency_updated", "message_forward_failed"}:
            nodes.update(
                uid for uid in (source, target) if uid is not None and uid in lab.topology.nodes
            )

        path_id = event.payload.get("path_id")
        if isinstance(path_id, str) and path_id in lab.topology.paths:
            paths.add(path_id)

        if kind == "simulation_initialised":
            # Staged text disappears from the message list and the per-device previews.
            messages.update(lab.clients.messages)
            devices.update(lab.clients.people)
        elif kind == "staged_messages_updated":
            updated = event.payload["message_ids"]
            messages.update(updated)
            devices.update(lab.clients.messages[uid].sender_id for uid in updated)
        elif kind in {
            "device_log_updated",
            "receiver_polling_enabled",
            "receiver_polling_disabled",
            "poll_started",
            "poll_empty",
            "poll_message_found",
            "poll_failed",
        }:
            uid = event.payload.get("person_id", source)
            if isinstance(uid, str) and uid in lab.clients.people:
                devices.add(uid)
        if event.message_id in lab.outcomes:
            assert event.message_id is not None
            if kind in {"device_log_updated", "message_decrypted", "message_delivery_failed"}:
                outcomes.add(event.message_id)
            if kind == "message_delivery_failed":
                message = lab.clients.messages[event.message_id]
                outcomes.update(lab.order[message.conversation_id])
                devices.add(message.target_id)
        if row := project(event):
            lineage.append(row)

    return Delta.model_validate(
        {
            "simulation_id": lab.id,
            "epoch": epoch,
            "sequence": len(lab.events),
            "simulation_time_ms": lab.now,
            "status": lab.status,
            "initialised": lab.initialised,
            "step_delay_ms": lab.step_delay_ms,
            "next_step_ms": lab.queue[0][0] if lab.queue else None,
            "nodes": [lab.topology.nodes[uid].model_dump() for uid in sorted(nodes)],
            "paths": [lab.topology.paths[uid].model_dump() for uid in sorted(paths)],
            "devices": _devices(lab, devices),
            "messages": [
                lab.clients.messages[uid].model_dump(exclude={"text"} if lab.initialised else set())
                for uid in sorted(messages)
            ],
            "outcomes": {uid: lab.outcomes[uid] for uid in sorted(outcomes)},
            "lineage": lineage,
            "events": events,
        }
    )

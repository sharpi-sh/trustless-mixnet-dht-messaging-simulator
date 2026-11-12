import asyncio

import pytest

from app.api_models import Command
from app.config import Config
from app.lab import Laboratory
from app.service import Service
from app.stream import delta, snapshot


async def wait_for_pause(service, lab):
    async with asyncio.timeout(3):
        while lab.status == "running":
            await service.wait(lab.id, service.epochs[lab.id], len(lab.events))


def control(lab, kind, uid):
    return Command(simulation_id=lab.id, type=kind, command_id=uid)


def test_seek_uses_the_ordinary_seeded_steps_and_pauses_with_message_in_transit():
    async def scenario():
        cfg = Config(random_seed=422, dht_nodes=3, payload_rate_per_minute=600, step_delay_ms=2000)
        reference = Laboratory(cfg)
        reference.lifecycle("run")
        for _ in reference.drain(5000):
            if reference.first_message_hop_sequence is not None:
                break
        assert reference.first_message_hop_sequence is not None

        service = Service()
        lab = service.create(cfg)
        try:
            seek = control(lab, "step_to_first_message_hop", "seek")
            await service.command(lab, seek)
            assert lab.status == "running"
            await wait_for_pause(service, lab)
            assert lab.status == "paused" and lab.step_delay_ms == 2000
            index = lab.first_message_hop_sequence
            assert index is not None
            first = lab.events[index - 1]
            assert (first.event_type, first.source_id, first.target_id, first.message_id) == (
                "path_transit_started",
                "sender-1",
                "tor-sender-1",
                "msg-1",
            )
            assert first.payload["transit_id"] in lab.in_flight
            assert first.payload["transit_id"] in lab.topology.paths[first.payload["path_id"]].active
            assert snapshot(lab, 0).first_message_hop_sequence == index
            assert delta(lab, 0, index - 1).first_message_hop_sequence == index

            # Original delivery order and the clock remain identical up to departure.
            def path_trace(run):
                return [
                    (e.event_type, e.simulation_time_ms, e.source_id, e.target_id)
                    for e in run.events
                    if e.event_type.startswith("path_transit_")
                ]

            assert path_trace(lab) == path_trace(reference)
            with pytest.raises(ValueError, match="before its first message departure"):
                await service.command(lab, control(lab, "step_to_first_message_hop", "again"))
            await service.command(lab, control(lab, "reset", "reset"))
            assert lab.status == "ready" and lab.first_message_hop_sequence is None
        finally:
            await service.close()

    asyncio.run(scenario())


def test_seek_cap_pauses_and_an_operator_can_interrupt_and_resume_it(monkeypatch):
    import app.service as module

    async def scenario():
        monkeypatch.setattr(module, "FIRST_HOP_STEP_LIMIT", 2)
        service = Service()
        lab = service.create(Config(random_seed=42))
        try:
            await service.command(lab, control(lab, "step_to_first_message_hop", "bounded"))
            await wait_for_pause(service, lab)
            assert lab.status == "paused" and lab.first_message_hop_sequence is None
            assert lab.events[-1].payload["limit"] == 2
            assert sum(e.event_type == "simulation_step_completed" for e in lab.events) == 2
            monkeypatch.setattr(module, "FIRST_HOP_STEP_LIMIT", 5000)
            await service.command(lab, control(lab, "step_to_first_message_hop", "more"))
            await asyncio.sleep(0)
            await service.command(lab, control(lab, "pause", "interrupt"))
            before = len(lab.events)
            await asyncio.sleep(0)
            assert lab.status == "paused" and len(lab.events) == before
            await service.command(lab, control(lab, "step_to_first_message_hop", "continue"))
            await wait_for_pause(service, lab)
            assert lab.first_message_hop_sequence is not None
        finally:
            await service.close()

    asyncio.run(scenario())

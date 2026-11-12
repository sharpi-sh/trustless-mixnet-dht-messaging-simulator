import asyncio

from app.api_models import Command
from app.config import Config
from app.lab import Laboratory
from app.service import Service


def command(lab, kind, **fields):
    return Command(type=kind, simulation_id=lab.id, command_id=kind, **fields)


async def until(service, lab, reached):
    async with asyncio.timeout(3):
        while not reached():
            assert lab.status == "running"
            await service.wait(lab.id, service.epochs[lab.id], len(lab.events))


def departures(lab):
    return [
        event for event in lab.events if event.message_id and event.event_type == "path_transit_started"
    ]


def test_run_reaches_the_first_real_hop_holds_it_and_continues_in_seeded_order():
    async def scenario():
        cfg = Config(random_seed=422, dht_nodes=3, payload_rate_per_minute=600, step_delay_ms=150)
        service = Service()
        lab = service.create(cfg)
        try:
            await service.command(lab, command(lab, "run"))
            await until(service, lab, lambda: lab.first_message_hop_sequence is not None)
            first = departures(lab)[0]
            assert (first.source_id, first.target_id) == ("sender-1", "tor-sender-1")
            assert first.payload["transit_id"] in lab.in_flight
            assert any(e.event_type == "path_transit_started" and not e.message_id for e in lab.events)
            cursor = len(lab.events)
            await asyncio.sleep(0.035)
            assert len(lab.events) == cursor and lab.status == "running"

            # The next physical hop must also appear at ordinary speed without intervention.
            await until(service, lab, lambda: len(departures(lab)) >= 2)
            await service.command(lab, command(lab, "pause"))
            reference = Laboratory(cfg)
            reference.lifecycle("run")
            for _ in reference.drain(5000):
                if len(departures(reference)) >= 2:
                    break

            def trace(run):
                return [
                    (event.event_type, event.simulation_time_ms, event.source_id, event.target_id)
                    for event in run.events
                    if event.step_id
                ]

            assert trace(lab) == trace(reference)
            assert len(departures(lab)) == len(departures(reference)) == 2
        finally:
            await service.close()

    asyncio.run(scenario())


def test_failed_first_departure_holds_until_the_operator_restores_and_accelerates():
    async def scenario():
        service = Service()
        lab = service.create(
            Config(random_seed=422, dht_nodes=3, payload_rate_per_minute=600, step_delay_ms=2000)
        )
        path = "sender-1~tor-sender-1"
        try:
            await service.command(lab, command(lab, "block_network_path", target=path))
            await service.command(lab, command(lab, "run"))
            await until(
                service,
                lab,
                lambda: any(e.message_id and e.event_type == "path_transit_failed" for e in lab.events),
            )
            assert lab.first_message_hop_sequence is None and lab.status == "running"
            cursor = len(lab.events)
            await asyncio.sleep(0.02)
            assert len(lab.events) == cursor
            await service.command(lab, command(lab, "restore_network_path", target=path))
            await service.command(lab, command(lab, "set_playback_delay", delay_ms=0))
            async with asyncio.timeout(1):
                await until(service, lab, lambda: lab.first_message_hop_sequence is not None)
            assert departures(lab)[0].source_id == "sender-1"
        finally:
            await service.close()

    asyncio.run(scenario())


def test_stream_waits_for_publication_even_when_background_steps_are_already_queued():
    async def scenario():
        service = Service()
        lab = service.create(Config(random_seed=42))
        cursor = len(lab.events)
        lab.lifecycle("run")
        lab.advance()
        assert len(lab.events) > cursor
        waiting = asyncio.create_task(service.wait(lab.id, 0, cursor))
        await asyncio.sleep(0)
        assert not waiting.done()
        await service.command(lab, command(lab, "pause"))
        await asyncio.wait_for(waiting, 1)
        await service.close()

    asyncio.run(scenario())


def test_timed_polls_publish_before_first_departure_without_dht_only_frames_or_dwell(monkeypatch):
    import app.service as module

    async def scenario():
        # Exercise both old triggers for a background-only frame on a short seed.
        monkeypatch.setattr(module, "FIRST_HOP_STEP_LIMIT", 2)
        monkeypatch.setattr(module, "STREAM_BATCH_STEPS", 1)
        service = Service()
        lab = service.create(
            Config(random_seed=422, dht_nodes=3, polling_interval_ms=1000, step_delay_ms=1000)
        )
        try:
            await service.command(lab, command(lab, "run"))
            cursor = len(lab.events)
            poll_seen = False
            async with asyncio.timeout(2):
                while lab.first_message_hop_sequence is None:
                    await service.wait(lab.id, 0, cursor)
                    if lab.first_message_hop_sequence is None:
                        visible = lab.events[cursor:]
                        assert any(
                            e.event_type.startswith("poll_")
                            or e.event_type.startswith("path_transit_")
                            and e.payload["token"].startswith("poll-")
                            for e in visible
                        )
                        poll_seen = True
                        cursor = len(lab.events)
            assert poll_seen
            departure = lab.first_message_hop_sequence
            assert departure is not None
            assert lab.events[departure - 1].source_id == "sender-1"
            assert lab.events[departure - 1].payload["transit_id"] in lab.in_flight
            assert any(
                e.event_type == "path_transit_completed" and not e.message_id
                for e in lab.events[: departure - 1]
            )
        finally:
            await service.close()

    asyncio.run(scenario())

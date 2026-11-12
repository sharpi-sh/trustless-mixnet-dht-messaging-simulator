import asyncio

import pytest

from app.api_models import Command
from app.config import Config
from app.service import Service


def command(lab, kind, token, **fields):
    fields.setdefault("simulation_id", lab.id)
    return Command(type=kind, command_id=token, **fields)


def test_service_waits_for_steps_and_reset_epochs_with_exactly_once_controls():
    async def scenario():
        service = Service()
        lab = service.create(Config(random_seed=9, step_delay_ms=2000))
        assert service.current is service.get(lab.id) is lab
        original = len(lab.events)
        pending = asyncio.create_task(service.wait(lab.id, 0, original))
        await asyncio.sleep(0)
        assert not pending.done()
        run = command(lab, "run", "start", simulation_id=lab.id)
        first, repeated = await asyncio.gather(service.command(lab, run), service.command(lab, run))
        assert first == repeated == {"status": "running"}
        await asyncio.wait_for(pending, 1)
        await asyncio.wait_for(service.wait(lab.id, 0, original), 1)
        with pytest.raises(ValueError, match="different mutation"):
            await service.command(lab, command(lab, "pause", "start"))
        await service.command(lab, command(lab, "pause", "pause"))
        last = len(lab.events)
        await asyncio.sleep(0.01)
        assert len(lab.events) == last
        await service.command(lab, command(lab, "step", "step"))
        assert len(lab.events) > last and lab.status == "paused"
        wait_reset = asyncio.create_task(service.wait(lab.id, 0, len(lab.events)))
        reset = command(lab, "reset", "reset")
        assert await service.command(lab, reset) == {"status": "ready"}
        await asyncio.wait_for(wait_reset, 1)
        assert await service.command(lab, reset) == {"status": "ready"}
        assert service.get(lab.id) is lab and service.epochs[lab.id] == 1
        assert lab.events[-1].event_type == "simulation_reset"
        await service.close()

    asyncio.run(scenario())


def test_service_reads_mutations_and_independent_runners():
    async def scenario():
        service = Service()
        lab = service.create(Config(random_seed=43, step_delay_ms=2000))
        second = service.create(Config(random_seed=71))
        edit = command(lab, "set_staged_messages", "edit", messages={"msg-1": "New stage"})
        assert await service.command(lab, edit) == {"status": "ready"}
        logs = await service.command(
            lab, command(lab, "request_device_logs", "read", target="sender-1")
        )
        assert logs["devices"][0]["logs"][0]["text"] == "New stage"
        assert (
            await service.command(lab, command(lab, "request_node_details", "read", target="dht-1"))
        )["state"]["k"] == 20
        with pytest.raises(ValueError, match="simulation ID"):
            await service.command(lab, command(lab, "run", "wrong", simulation_id=second.id))
        await service.command(lab, command(lab, "run", "run"))
        await asyncio.sleep(0.005)
        old_seq = len(lab.events)
        await service.command(lab, command(lab, "set_playback_delay", "speed", delay_ms=1))
        speed_seq = len(lab.events)
        await asyncio.wait_for(service.wait(lab.id, 0, speed_seq), 1)
        assert len(lab.events) > old_seq and second.status == "ready" and second.now == 0
        await service.command(lab, command(lab, "stop", "stop"))
        with pytest.raises(ValueError, match="Reset"):
            await service.command(
                lab, command(lab, "set_staged_messages", "locked", messages={"msg-1": "late"})
            )
        with pytest.raises(ValueError, match="different mutation"):
            await service.command(lab, command(lab, "reset", "locked"))
        waiting = asyncio.create_task(service.wait(second.id, 0, len(second.events)))
        await asyncio.sleep(0)
        await service.close()
        await asyncio.wait_for(waiting, 1)

    asyncio.run(scenario())


def test_background_failure_is_terminal_and_observable(monkeypatch):
    async def scenario():
        service = Service()
        lab = service.create(Config(random_seed=11))

        def broken_step():
            raise RuntimeError("Injected step error")

        monkeypatch.setattr(lab, "advance", broken_step)
        await service.command(lab, command(lab, "run", "run"))
        seq = len(lab.events)
        await asyncio.wait_for(service.wait(lab.id, 0, seq), 1)
        assert lab.status == "failed" and lab.events[-1].event_type == "simulation_failed"
        assert "Injected step error" in lab.events[-1].payload["reason"]
        await service.close()

    asyncio.run(scenario())


def test_zero_pacing_yields_between_steps_and_can_be_changed_live(monkeypatch):
    async def scenario():
        service = Service()
        lab = service.create(Config(random_seed=21, step_delay_ms=0, base_transit_delay_ms=345))
        advance = lab.advance
        steps = 0

        def guarded_advance():
            nonlocal steps
            steps += 1
            if steps > 30:
                raise RuntimeError("Runner starved the control task")
            advance()

        monkeypatch.setattr(lab, "advance", guarded_advance)
        try:
            await service.command(lab, command(lab, "run", "start"))
            await asyncio.sleep(0)
            assert 0 < steps < 30 and lab.status == "running"
            await service.command(lab, command(lab, "pause", "pause"))
            paused_steps = steps
            await asyncio.sleep(0)
            assert steps == paused_steps
            await service.command(lab, command(lab, "set_playback_delay", "slow", delay_ms=2000))
            await service.command(lab, command(lab, "resume", "resume"))
            await asyncio.sleep(0)
            before = steps
            await service.command(lab, command(lab, "set_playback_delay", "fast", delay_ms=0))
            await asyncio.wait_for(service.wait(lab.id, 0, len(lab.events)), 0.5)
            assert steps > before and lab.snapshot()["step_delay_ms"] == 0
            assert all(p.base_transit_delay_ms == 345 for p in lab.topology.paths.values())
            await service.command(lab, command(lab, "stop", "stop"))
        finally:
            await service.close()

    asyncio.run(scenario())


def test_fast_stream_combines_published_changes_and_flushes_immediately_on_pause():
    async def scenario():
        service = Service()
        lab = service.create(Config(random_seed=42, step_delay_ms=1))
        lab.lifecycle("run")
        session = service._sessions[lab.id]
        cursor = len(lab.events)
        # Drive actual scheduler steps without a competing background runner.
        async with session.changed:
            for _ in range(8):
                lab.advance()
            session.publish()
        assert len(lab.events) > cursor + 1
        waiting = asyncio.create_task(
            service.wait_stream(lab.id, 0, cursor, asyncio.get_running_loop().time())
        )
        await asyncio.sleep(0)
        assert not waiting.done()
        await service.command(lab, command(lab, "pause", "pause"))
        await asyncio.wait_for(waiting, 0.1)
        from app.stream import delta

        update = delta(lab, 0, cursor)
        assert update.status == "paused"
        assert [e.sequence for e in update.events] == list(range(cursor + 1, update.sequence + 1))
        await service.close()

    asyncio.run(scenario())

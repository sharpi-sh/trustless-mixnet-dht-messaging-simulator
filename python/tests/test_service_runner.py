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

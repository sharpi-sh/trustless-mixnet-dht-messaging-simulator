import pytest
from app.engine import Action, Config, Engine, Intervention


def make():
    sim=Engine(Config(random_seed=14,jitter_max_ms=0))
    sim.lifecycle("run")
    return sim


@pytest.mark.parametrize("drop,expected", [(False,"path_transit_completed"),(True,"path_transit_failed")])
def test_inflight_policy_and_timing(drop,expected):
    sim=make()
    a,b="sender-1","tor-sender-1"
    sim.transit(a,b,Action(),Action(),token="packet")
    sim.advance()
    path=sim.topology.paths[sim.topology.path_id(a,b)]
    assert len(path.active)==1
    cmd=Intervention(target=path.id,token="cmd",command="path",enabled=False,drop_in_flight=drop)
    sim.intervene(cmd)
    assert sim.intervene(cmd).outcome=="applied"
    sim.advance()
    evt=next(e for e in sim.events if e.event_type==expected)
    assert evt.simulation_time_ms==(0 if drop else 250)
    assert not path.active and path.blocked
    sim.transit(a,b,Action(),Action(),token="another")
    while path.attempted<2:
        sim.advance()
    assert path.failed==1+int(drop)


def test_step_pause_reset_and_boundary_scope():
    sim=make()
    sim.lifecycle("pause")
    sim.schedule(Intervention(command="delay",token="delay",delay_ms=20),123)
    sim.lifecycle("step")
    assert (sim.status,sim.now,sim.step_delay_ms)==("paused",123,20)
    boundary="Layer 1 ↔ Layer 2"
    sim.intervene(Intervention(command="boundary",target=boundary,enabled=False,token="b"))
    assert all(p.blocked==(p.boundary==boundary) for p in sim.topology.paths.values())
    sim.lifecycle("reset")
    assert sim.now==0 and sim.status=="ready" and all(not p.blocked for p in sim.topology.paths.values())

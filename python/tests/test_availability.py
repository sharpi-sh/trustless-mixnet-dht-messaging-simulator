from heapq import heappop, heappush
from itertools import count, pairwise
from random import Random

import pytest

from app.availability import Availability, AvailabilityChange, AvailabilityTimer
from app.config import Config, Outage
from app.participants import People
from app.topology import Topology


def planner(config, seed=19):
    rng = Random(seed)
    return Availability(config, Topology(config, rng, People(config, rng)), rng)


def transitions(engine, end):
    queue = []
    serial = count()
    for time, action in engine.start():
        heappush(queue, (time, next(serial), action))
    changes = []
    while queue and queue[0][0] <= end:
        now, _, action = heappop(queue)
        if isinstance(action, AvailabilityChange):
            changes.append((now, action.source, action.online, action.reason))
        else:
            assert isinstance(action, AvailabilityTimer)
            for time, new in engine.execute(action, now):
                heappush(queue, (time, next(serial), new))
    return changes


def test_scheduled_overlaps_and_touching_windows_form_one_outage():
    config = Config(
        pattern="scheduled",
        scheduled_outages=[
            Outage(node_id="mix-1", start_ms=100, duration_ms=500),
            Outage(node_id="mix-1", start_ms=400, duration_ms=500),
            Outage(node_id="mix-1", start_ms=900, duration_ms=300000),
            Outage(node_id="mix-2", start_ms=100, duration_ms=500),
            Outage(node_id="mix-3", start_ms=0, duration_ms=0),
        ],
    )
    assert sorted((t, n, on) for t, n, on, _ in transitions(planner(config), 400000)) == [
        (100, "mix-1", False),
        (100, "mix-2", False),
        (600, "mix-2", True),
        (300900, "mix-1", True),
    ]


def test_random_outages_are_seeded_repeat_independently_and_ignore_playback():
    cfg = Config(
        pattern="random",
        failure_probability=0.4,
        min_online_ms=100,
        min_outage_ms=500,
        max_outage_ms=900,
    )
    first = transitions(planner(cfg), 10000)
    assert first == transitions(planner(cfg.model_copy(update={"step_delay_ms": 2000})), 10000)
    assert first != transitions(planner(cfg, 21), 10000)
    traces = {}
    for uid in ("mix-1", "mix-2"):
        trace = [(t, up) for t, n, up, _ in first if n == uid]
        assert len(trace) > 3
        for (t, up), (t2, up2) in pairwise(trace):
            assert up is not up2
            if up:
                assert t2 - t >= 100
            else:
                assert 500 <= t2 - t <= 900
        traces[uid] = trace
    assert traces["mix-1"] != traces["mix-2"]


def test_bursts_share_onset_by_operator_but_individual_durations():
    engine = planner(
        Config(
            pattern="bursty",
            operator_count=2,
            min_online_ms=100,
            failure_probability=1,
            min_outage_ms=500,
            max_outage_ms=1000,
        )
    )
    nodes = set(engine.topology.nodes)
    stream = transitions(engine, 3400)
    assert {n for t, n, up, _ in stream if t == 100 and not up} == nodes
    for operator in engine.members:
        starts = [
            [t for t, n, up, _ in stream if not up and n == uid] for uid in engine.members[operator]
        ]
        assert len(starts[0]) > 1 and all(seq == starts[0] for seq in starts)
    assert len({t for t, _, up, _ in stream if up and t <= 1100}) > 1


def test_permanent_states_and_zero_failure_rate_do_not_queue_health_checks():
    cfg = Config(pattern="random", always_offline_probability=1, always_online_probability=0)
    engine = planner(cfg)
    changes = transitions(engine, 1000000)
    assert len(changes) == len(engine.topology.nodes)
    assert all(time == 0 and not up for time, _, up, _ in changes)
    assert (
        transitions(
            planner(
                cfg.model_copy(update={"always_offline_probability": 0, "always_online_probability": 1})
            ),
            1000000,
        )
        == []
    )
    assert (
        planner(
            cfg.model_copy(update={"always_offline_probability": 0, "failure_probability": 0})
        ).start()
        == []
    )
    assert planner(Config(pattern="always_online")).start() == []
    engine = planner(Config(pattern="always_offline"))
    assert len(transitions(engine, 1000000)) == len(engine.topology.nodes)


def test_scheduled_outage_extends_initial_random_outage_past_stale_recovery():
    cfg = Config(
        pattern="random",
        failure_probability=0,
        initial_offline_probability=1,
        min_outage_ms=500,
        max_outage_ms=500,
        scheduled_outages=[Outage(node_id="mix-1", start_ms=300, duration_ms=500000)],
    )
    stream = transitions(planner(cfg), 500300)
    assert [(t, up) for t, n, up, _ in stream if n == "mix-1"] == [(0, False), (500300, True)]
    assert [(t, up) for t, n, up, _ in stream if n == "mix-2"] == [(0, False), (500, True)]


def test_unknown_node_is_rejected_and_start_is_idempotent():
    cfg = Config(scheduled_outages=[Outage(node_id="elsewhere", start_ms=0, duration_ms=100)])
    with pytest.raises(ValueError, match="unknown node"):
        planner(cfg).start()
    engine = planner(Config(pattern="always_offline"))
    assert engine.start() and not engine.start()

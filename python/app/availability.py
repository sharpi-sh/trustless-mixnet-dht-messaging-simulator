"""Seeded outages on the logical clock. Only the kernel applies node transitions."""

from collections import defaultdict
from dataclasses import dataclass
from fractions import Fraction
from math import log1p
from random import Random
from typing import Literal

from .config import Config
from .steps import Action
from .topology import Topology


@dataclass(kw_only=True)
class AvailabilityChange(Action):
    online: bool
    reason: str


@dataclass(kw_only=True)
class AvailabilityTimer(Action):
    kind: Literal["outage", "random_outage", "recover", "operator_burst"]
    duration_ms: int = 0
    reason: str


Schedule = list[tuple[int, Action]]


class Availability:
    """Uniform inclusive durations; each min_online_ms period is one Bernoulli trial.

    Random clocks are per node. Bursts share a start across one operator's eligible
    nodes, with durations sampled from each node's own stream. Explicit scheduled
    windows are additional to automatic failures. Generated permanent states take
    precedence. Recovery waits for the latest overlapping outage to end.
    """

    def __init__(self, config: Config, topology: Topology, rng: Random):
        self.config = config
        self.topology = topology
        self.node_rng = {uid: Random(rng.getrandbits(128)) for uid in sorted(topology.nodes)}
        operators = sorted({node.operator_id for node in topology.nodes.values()})
        self.operator_rng = {uid: Random(rng.getrandbits(128)) for uid in operators}
        self.members: dict[str, list[str]] = defaultdict(list)
        self.offline_until: dict[str, int] = {}
        self.permanent: set[str] = set()
        self.started = False

    def _duration(self, rng: Random) -> int:
        return rng.randint(self.config.min_outage_ms, self.config.max_outage_ms)

    def _next(self, rng: Random, now: int, timer: AvailabilityTimer) -> Schedule:
        probability = self.config.failure_probability
        if probability == 0 or self.config.max_outage_ms == 0:
            return []
        trials = 1
        if probability < 1:
            # Invert the geometric CDF instead of scheduling repeated healthy checks.
            trials += Fraction(log1p(-rng.random())) // Fraction(log1p(-probability))
        return [(now + trials * self.config.min_online_ms, timer)]

    def start(self) -> Schedule:
        if self.started:
            return []
        if any(outage.node_id not in self.topology.nodes for outage in self.config.scheduled_outages):
            raise ValueError("Scheduled outage refers to an unknown node")
        self.started = True
        schedule: Schedule = []
        cfg = self.config
        group_ready: dict[str, int] = defaultdict(int)
        for uid, stream in self.node_rng.items():
            always_offline = cfg.pattern == "always_offline"
            if cfg.pattern in {"random", "bursty"}:
                draw = stream.random()
                always_offline = draw < cfg.always_offline_probability
                if (
                    always_offline
                    or draw < cfg.always_offline_probability + cfg.always_online_probability
                ):
                    self.permanent.add(uid)
            if always_offline:
                self.permanent.add(uid)
                schedule.append(
                    (0, AvailabilityChange(source=uid, online=False, reason="permanent outage"))
                )
            if uid in self.permanent or cfg.pattern not in {"random", "bursty"}:
                continue
            operator = self.topology.nodes[uid].operator_id
            self.members[operator].append(uid)
            initial_duration = 0
            if stream.random() < cfg.initial_offline_probability:
                initial_duration = self._duration(stream)
                schedule.append(
                    (
                        0,
                        AvailabilityTimer(
                            kind="outage",
                            source=uid,
                            duration_ms=initial_duration,
                            reason="initial outage",
                        ),
                    )
                )
            group_ready[operator] = max(group_ready[operator], initial_duration)
            if cfg.pattern == "random":
                schedule += self._next(
                    stream,
                    initial_duration,
                    AvailabilityTimer(kind="random_outage", source=uid, reason="random outage"),
                )
        if cfg.pattern == "bursty":
            for operator in self.members:
                schedule += self._next(
                    self.operator_rng[operator],
                    group_ready[operator],
                    AvailabilityTimer(kind="operator_burst", source=operator, reason="operator burst"),
                )
        schedule += self._scheduled()
        return schedule

    def _scheduled(self) -> Schedule:
        windows: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for outage in self.config.scheduled_outages:
            if outage.duration_ms and outage.node_id not in self.permanent:
                windows[outage.node_id].append((outage.start_ms, outage.start_ms + outage.duration_ms))
        schedule: Schedule = []
        for uid, intervals in windows.items():
            merged: list[tuple[int, int]] = []
            for start, end in sorted(intervals):
                if merged and start <= merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(merged[-1][1], end))
                else:
                    merged.append((start, end))
            for start, end in merged:
                schedule.append(
                    (
                        start,
                        AvailabilityTimer(
                            source=uid,
                            kind="outage",
                            duration_ms=end - start,
                            reason="scheduled outage",
                        ),
                    )
                )
        return schedule

    def _outage(self, uid: str, now: int, duration: int, reason: str) -> Schedule:
        if duration == 0:
            return []
        end = now + duration
        active_until = self.offline_until.get(uid)
        if active_until is not None and active_until >= end:
            return []
        self.offline_until[uid] = end
        schedule: Schedule = [(end, AvailabilityTimer(source=uid, kind="recover", reason=reason))]
        if active_until is None:
            schedule.append((now, AvailabilityChange(source=uid, online=False, reason=reason)))
        return schedule

    def execute(self, action: AvailabilityTimer, now: int) -> Schedule:
        uid = action.source
        if action.kind == "recover":
            if self.offline_until.get(uid) != now:
                return []
            del self.offline_until[uid]
            return [(now, AvailabilityChange(source=uid, online=True, reason=action.reason + " ended"))]
        if action.kind == "operator_burst":
            schedule: Schedule = []
            last_end = now
            for member in self.members[uid]:
                duration = self._duration(self.node_rng[member])
                schedule += self._outage(member, now, duration, action.reason)
                last_end = max(last_end, now + duration)
            return schedule + self._next(self.operator_rng[uid], last_end, action)
        if action.kind == "random_outage":
            stream = self.node_rng[uid]
            duration = self._duration(stream)
            return self._outage(uid, now, duration, action.reason) + self._next(
                stream, now + duration, action
            )
        return self._outage(uid, now, action.duration_ms, action.reason)

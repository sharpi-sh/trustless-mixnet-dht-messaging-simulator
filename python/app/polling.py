"""Periodic participant pulls through their own Tor boundary and Loopix provider."""

from dataclasses import dataclass, field

from .engine import Engine
from .participants import Direction
from .steps import Action

CELL_BYTES = 256


@dataclass(kw_only=True)
class PollClock(Action):
    pass


@dataclass(kw_only=True)
class PollHop(Action):
    person_id: str
    hop: int


@dataclass(kw_only=True)
class PollFailure(Action):
    person_id: str


@dataclass(kw_only=True)
class MailboxItem(Action):
    handle: bytes = field(repr=False)


@dataclass
class _Pull:
    token: str
    route: tuple[str, str, str, str, str]
    reserved: list[bytes] = field(default_factory=list, repr=False)
    cells: tuple[bytes, ...] = field(default_factory=tuple, repr=False)


class PollRuntime:
    def __init__(self, sim: Engine):
        self.sim = sim
        self.active: dict[str, _Pull] = {}
        self._serial = 0
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        interval = self.sim.config.polling_interval_ms
        for uid in self.sim.clients.people:
            # Each fixed-frequency clock has a seeded initial phase and survives disable/enable.
            self.sim.schedule(PollClock(source=uid), self.sim.rng.randrange(1, interval + 1))

    def cancel(self, person_id: str) -> None:
        pull = self.active.pop(person_id, None)
        if pull is not None and pull.reserved:
            self.sim.inboxes[person_id].messages[:0] = pull.reserved

    def _enabled(self, uid: str) -> bool:
        return self.sim.clients.people[uid].polling_enabled and self.sim.topology.nodes[uid].online

    def _clock(self, action: PollClock) -> None:
        sim = self.sim
        if sim.status in {"completed", "failed", "stopped"}:
            return
        sim.schedule(action, sim.config.polling_interval_ms)
        uid = action.source
        if not self._enabled(uid) or uid in self.active:
            return
        person = sim.clients.people[uid]
        provider = next(p for p in sim.topology.mixnet.providers
                        if sim.topology.path_id(person.tor.id, p) in sim.topology.paths)
        self._serial += 1
        token = f"poll-{self._serial}"
        pull = _Pull(token, (uid, person.tor.id, provider, person.tor.id, uid))
        self.active[uid] = pull
        sim.emit("poll_started", Action(source=uid, target=provider, token=token),
                 interval_ms=sim.config.polling_interval_ms, provider_id=provider)
        self._transit(pull, 1)

    def _transit(self, pull: _Pull, hop: int) -> None:
        uid = pull.route[0]
        lane: Direction = "reply" if self.sim.clients.people[uid].role == "sender" else "forward"
        source, target = pull.route[hop - 1], pull.route[hop]
        arrival = PollHop(source=source, target=target, lane=lane, token=pull.token, person_id=uid, hop=hop)
        failure = PollFailure(source=source, target=target, lane=lane, token=pull.token, person_id=uid)
        self.sim.transit(source, target, arrival, failure, token=pull.token, lane=lane)

    def _arrive(self, action: PollHop) -> None:
        sim = self.sim
        uid = action.person_id
        pull = self.active.get(uid)
        if pull is None or pull.token != action.token:
            return
        if not self._enabled(uid):
            self.cancel(uid)
            return
        tor = sim.clients.people[uid].tor
        if action.hop in (1, 3):
            tor.enter()
            sim.emit("tor_entry", action)
        else:
            tor.exit()
            sim.emit("tor_exit", action)
        if action.hop == 2:
            inbox = sim.inboxes[uid]
            batch = sim.config.poll_batch
            reserved = inbox.messages[:batch]
            pull.cells = inbox.poll(batch, CELL_BYTES)
            pull.reserved = reserved
            sim.emit("poll_response_prepared", action, slots=batch, cell_bytes=CELL_BYTES,
                     response_bytes=batch * CELL_BYTES)
        if action.hop < 4:
            self._transit(pull, action.hop + 1)
            return
        del self.active[uid]
        found = 0
        for cell in pull.cells:
            length = int.from_bytes(cell[:2], "big")
            if length:
                found += 1
                sim.schedule(MailboxItem(source=uid, token=action.token, handle=cell[2:2 + length],
                                         lane=action.lane))
        sim.emit("poll_message_found" if found else "poll_empty", action, person_id=uid, found=found,
                 slots=len(pull.cells), cell_bytes=CELL_BYTES, response_bytes=len(pull.cells) * CELL_BYTES)

    def handle(self, action: Action) -> bool:
        if isinstance(action, PollClock):
            self._clock(action)
        elif isinstance(action, PollHop):
            self._arrive(action)
        elif isinstance(action, PollFailure):
            pull = self.active.get(action.person_id)
            if pull and pull.token == action.token:
                self.cancel(action.person_id)
                self.sim.emit("poll_failed", action, reason="Path unresponsive")
        else:
            return False
        return True

from app.config import Config
from app.engine import Engine, Intervention
from app.polling import CELL_BYTES, MailboxItem, PollRuntime


class PollLab(Engine):
    def __init__(self, **config):
        super().__init__(
            Config(
                random_seed=83,
                polling_interval_ms=100,
                poll_batch=2,
                jitter_max_ms=0,
                ack_timeout_ms=10,
                **config,
            )
        )
        self.polls = PollRuntime(self)
        self.items = []
        self.clients.people["sender-1"].polling_enabled = False

    def handle(self, action):
        if isinstance(action, MailboxItem):
            self.items.append(action)
            return True
        return self.polls.handle(action)

    def until(self, event, count=1):
        for _ in self.drain(500):
            if sum(e.event_type == event for e in self.events) >= count:
                return
        raise AssertionError(f"Missing {event}")

    def start(self):
        self.lifecycle("run")
        self.polls.start()
        self.polls.start()


def test_fixed_width_empty_loop_and_payload_polls_follow_actual_tor_paths():
    lab = PollLab(base_transit_delay_ms=3)
    uid = "receiver-1"
    lab.inboxes[uid].messages.extend([b"", b"x" * 20])
    lab.start()
    lab.until("poll_empty")
    assert [item.handle for item in lab.items] == [b"x" * 20]
    assert lab.items[0].source == uid and lab.items[0].token.startswith("poll-")
    completed = [
        (e.source_id, e.target_id) for e in lab.events if e.event_type == "path_transit_completed"
    ]
    tor, provider = "tor-receiver-1", "provider-east"
    assert completed[:4] == [(uid, tor), (tor, provider), (provider, tor), (tor, uid)]
    starts = [e.simulation_time_ms for e in lab.events if e.event_type == "poll_started"]
    assert len(starts) == 2 and starts[1] - starts[0] == 100
    responses = [e.payload for e in lab.events if e.event_type == "poll_response_prepared"]
    assert len(responses) == 2 and all(p["response_bytes"] == 2 * CELL_BYTES for p in responses)
    assert lab.clients.people[uid].tor.entry_count == lab.clients.people[uid].tor.exit_count == 4


def test_return_path_failure_restores_fifo_and_retries_next_clock_without_overlapping():
    lab = PollLab(base_transit_delay_ms=40)
    uid = "receiver-1"
    a, b, c = (x * 20 for x in [b"a", b"b", b"c"])
    lab.inboxes[uid].messages.extend([a, b])
    lab.start()
    lab.until("poll_response_prepared")
    lab.inboxes[uid].messages.append(c)
    path = lab.topology.path_id("tor-receiver-1", "provider-east")
    lab.intervene(Intervention(command="path", target=path, token="block", enabled=False))
    lab.until("poll_failed")
    assert not lab.items and lab.inboxes[uid].messages == [a, b, c]
    lab.intervene(Intervention(command="path", target=path, token="restore", enabled=True))
    lab.until("poll_empty")
    assert [item.handle for item in lab.items] == [a, b, c]
    assert len({(item.handle, item.token) for item in lab.items}) == 3
    assert sum(e.event_type == "poll_failed" for e in lab.events) == 1


def test_disabled_midflight_restores_reserved_cells_and_offline_client_suppresses_poll():
    lab = PollLab(base_transit_delay_ms=5)
    uid = "receiver-1"
    handle = b"z" * 20
    lab.inboxes[uid].messages.append(handle)
    lab.start()
    lab.until("poll_response_prepared")
    lab.intervene(Intervention(command="polling", target=uid, token="disable", enabled=False))
    for _ in lab.drain(18):
        pass
    assert not lab.items and uid not in lab.polls.active and lab.inboxes[uid].messages == [handle]
    lab.change_node(uid, False, "test")
    lab.intervene(Intervention(command="polling", target=uid, token="enable", enabled=True))
    before = sum(e.event_type == "poll_started" for e in lab.events)
    for _ in lab.drain(12):
        pass
    assert sum(e.event_type == "poll_started" for e in lab.events) == before
    lab.change_node(uid, True, "test")
    lab.until("poll_empty")
    assert [item.handle for item in lab.items] == [handle]

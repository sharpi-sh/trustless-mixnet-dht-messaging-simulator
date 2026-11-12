from app.config import Config
from app.engine import Intervention
from app.retrieval import RetrievalCallback as Callback
from app.storage_simulation import StorageSimulation


class Harness(StorageSimulation):
    def __init__(self):
        super().__init__(
            Config(random_seed=6, base_transit_delay_ms=3, jitter_max_ms=0, mu_per_second=100)
        )
        self.status = "running"
        self.callbacks: list[Callback] = []

    def handle(self, action):
        if isinstance(action, Callback):
            self.callbacks.append(action)
            return True
        return super().handle(action)

    def next_callback(self):
        for _ in range(2000):
            self.advance()
            if self.callbacks:
                return self.callbacks.pop(0)
        raise AssertionError("Retrieval did not settle")


def test_multicell_request_and_anonymous_response_cross_three_mixes_and_use_actual_bytes():
    sim = Harness()
    device, service = "receiver-1", "storage-1"
    request = bytes(range(251)) * 5
    reply = bytes(range(251)) * 8
    arrived = Callback(token="service")
    delivered = Callback(token="client")
    failed = Callback(token="failure")
    ticket = sim.retrieval.request(device, service, request, len(reply), arrived, failed)
    callback = sim.next_callback()
    assert (callback.ticket, callback.data, callback.token) == (ticket, request, "service")
    sim.retrieval.reply(ticket, reply, delivered, failed)
    assert sim.next_callback() == Callback(token="client", data=reply)
    assert not sim.retrieval._exchanges
    edges = [e for e in sim.events if e.event_type == "path_transit_started"]
    for suffix in ["q0", "r0", "r1", "r2"]:
        trace = [e for e in edges if e.payload["token"] == ticket + "-" + suffix]
        assert [
            sim.topology.nodes[e.target_id].stage_index for e in trace if e.target_id.startswith("mix-")
        ] == [3, 4, 5]
        assert trace[0].source_id == (device if suffix.startswith("q") else service)
        assert trace[-1].target_id == (service if suffix.startswith("q") else device)
    sim.retrieval.reply(ticket, b"replay", delivered, failed)
    assert not sim.callbacks


def test_blocked_service_attachment_fails_read_without_bypassing_mixnet():
    sim = Harness()
    service = "storage-1"
    edge = sim.topology.path_id(sim.topology.service_gateways[service], service)
    sim.intervene(Intervention(command="path", token="blocked", target=edge, enabled=False))
    sim.retrieval.request("receiver-1", service, b"read", 20, Callback(), Callback(token="failure"))
    assert sim.next_callback() == Callback(token="failure")
    assert not sim.retrieval._exchanges
    assert not [e for e in sim.events if e.event_type == "retrieval_request_delivered"]


def test_only_live_single_use_replies_can_reach_the_device():
    sim = Harness()
    service = "storage-2"
    request, reply, failure = (
        Callback(token="request"),
        Callback(token="reply"),
        Callback(token="failure"),
    )
    ticket = sim.retrieval.request("sender-1", service, b"read", 2, request, failure)
    assert sim.next_callback().ticket == ticket
    # The service withholds its response until the scheduler expires the client secret.
    assert sim.next_callback() == failure
    sim.retrieval.reply(ticket, b"OK", reply, failure)
    assert not sim.queue
    assert not sim.retrieval._exchanges
    assert not [e for e in sim.events if e.event_type == "retrieval_reply_received"]


def test_failed_response_retires_unused_surbs_and_runs_only_one_failure_callback():
    sim = Harness()
    service = "storage-2"
    failure = Callback(token="failure")
    ticket = sim.retrieval.request("sender-1", service, b"read", 2048, Callback(), failure)
    assert sim.next_callback().ticket == ticket
    uid = sim.topology.path_id(sim.topology.service_gateways[service], service)
    sim.intervene(Intervention(command="path", target=uid, token="block-response", enabled=False))
    sim.retrieval.reply(ticket, bytes(2048), Callback(token="reply"), failure)
    assert sim.next_callback() == failure
    list(sim.drain(100))
    assert not sim.callbacks
    assert not sim.retrieval._exchanges
    assert sum(e.event_type == "retrieval_transport_failed" for e in sim.events) == 1

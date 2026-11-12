from dataclasses import dataclass

from app.config import Config
from app.engine import Intervention
from app.steps import Action
from app.storage_simulation import StorageSimulation


@dataclass(kw_only=True)
class Callback(Action):
    data: bytes = b""
    ticket: str = ""


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

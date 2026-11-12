from hashlib import sha256

from app.config import Config
from app.crypto import seal, unseal
from app.mailbox import BundleDelivered, MailboxFailed, MailboxRuntime
from app.packet_runtime import PacketDelivered
from app.polling import MailboxItem
from app.steps import Action
from app.storage_simulation import StorageSimulation


class MailboxExperiment(StorageSimulation):
    def __init__(self, **settings):
        super().__init__(
            Config(
                random_seed=41,
                dht_nodes=3,
                storage_nodes=3,
                chunk_bytes=32,
                base_transit_delay_ms=7,
                jitter_min_ms=0,
                jitter_max_ms=0,
                **settings,
            )
        )
        self.mail = MailboxRuntime(self)
        self.result = None
        self.lifecycle("run")

    def initialise(self):
        self.initialised = True
        self.rpc.start()

    def handle(self, action: Action) -> bool:
        if isinstance(action, (BundleDelivered, MailboxFailed)):
            self.result = action
            return True
        return self.mail.handle(action) or super().handle(action)

    def through(self, predicate):
        for _ in self.drain(2500):
            if predicate():
                assert "simulation_error" not in {e.event_type for e in self.events}
                return
        raise AssertionError("Mailbox operation did not finish")

    def send(self, body=b"secret envelope"):
        recipient = self.clients.people["receiver-1"]
        data = seal(recipient.public_key, body, "bundle")
        self.schedule(
            PacketDelivered(
                source="provider-east",
                target=recipient.id,
                token="p",
                message_id="msg-1",
                payload=recipient.public_key + data,
            ),
            100,
        )
        return data

    def poll(self):
        recipient = "receiver-1"
        handle = self.inboxes[recipient].messages.pop(0)
        self.schedule(MailboxItem(source=recipient, token="test-polled", handle=handle))
        return handle


def test_only_handle_is_queued_and_full_read_crosses_owned_links():
    sim = MailboxExperiment()
    ciphertext = sim.send()
    sim.through(lambda: bool(sim.inboxes["receiver-1"].messages))
    events = sim.events
    assert sim.result is None
    (handle,) = sim.inboxes["receiver-1"].messages
    assert len(handle) == 20
    assert not any(e.event_type == "manifest_retrieved" for e in events)
    key = int.from_bytes(handle, "big")
    copies = [
        record.value for n in sim.dht.nodes.values() if (record := n.record(key, sim.now)) is not None
    ]
    assert copies and all(b"msg-1" not in blob and b"fragment" not in blob for blob in copies)
    encrypted_manifest = copies[0]
    recipient = sim.clients.people["receiver-1"]
    assert b"msg-1" in unseal(recipient.private_key, encrypted_manifest, "manifest")
    sim.poll()
    sim.through(lambda: sim.result is not None)
    assert isinstance(sim.result, BundleDelivered)
    assert (
        sim.result.target == "receiver-1"
        and sim.result.message_id == "msg-1"
        and sim.result.ciphertext == ciphertext
    )
    assert unseal(recipient.private_key, sim.result.ciphertext, "bundle") == b"secret envelope"
    edges = {(e.source_id, e.target_id) for e in events if e.event_type == "path_transit_completed"}
    for a, b in [
        ("provider-east", "dht-1"),
        ("dht-1", "provider-east"),
        ("receiver-1", "tor-receiver-1"),
        ("tor-receiver-1", "provider-east"),
        ("provider-east", "tor-receiver-1"),
        ("tor-receiver-1", "receiver-1"),
    ]:
        assert (a, b) in edges
    assert any(a.startswith("provider-") and b.startswith("storage-") for a, b in edges)
    assert any(a.startswith("storage-") and b.startswith("provider-") for a, b in edges)
    assert any(a.startswith("mix-") and b.startswith("mix-") for a, b in edges)
    assert not any(
        (a.startswith(("dht-", "storage-")) and b == recipient.tor.id)
        or (a == recipient.tor.id and b.startswith(("dht-", "storage-")))
        for a, b in edges
    )
    assert recipient.tor.entry_count == recipient.tor.exit_count
    publish = next(e for e in events if e.event_type == "manifest_published")
    fetched = next(e for e in events if e.event_type == "manifest_retrieved")
    assert (
        publish.payload["artefact_id"]
        == fetched.payload["artefact_id"]
        == sha256(encrypted_manifest).hexdigest()
    )
    assert not sim.mail._jobs
    # Replayed provider handle cannot duplicate delivery.
    sim.result = None
    sim.mail.handle(MailboxItem(source=recipient.id, token="repeat", handle=handle))
    assert sim.result is None and not sim.mail._jobs


def test_poll_disabled_mid_fetch_requeues_only_the_handle():
    sim = MailboxExperiment()
    sim.send()
    participant = "receiver-1"
    sim.through(lambda: bool(sim.inboxes[participant].messages))
    handle = sim.poll()
    sim.through(lambda: bool(sim.mail._reading))
    sim.clients.people[participant].polling_enabled = False
    sim.through(lambda: bool(sim.inboxes[participant].messages))
    assert sim.inboxes[participant].messages == [handle] and sim.result is None
    sim.clients.people[participant].polling_enabled = True
    sim.poll()
    sim.through(lambda: sim.result is not None)
    assert isinstance(sim.result, BundleDelivered)


def test_unreachable_egress_and_missing_handle_end_after_bounded_retries():
    sim = MailboxExperiment(max_retries=1)
    path = sim.topology.paths[sim.topology.path_id("provider-east", "dht-1")]
    path.blocked = True
    sim.send()
    sim.through(lambda: sim.result is not None)
    assert isinstance(sim.result, MailboxFailed) and sim.result.message_id == "msg-1"
    assert path.failed == 2 and not sim.inboxes["receiver-1"].messages and not sim.mail._jobs
    sim.result = None
    sim.schedule(MailboxItem(source="receiver-1", token="unknown", handle=bytes(20)))
    sim.through(lambda: sim.result is not None)
    assert isinstance(sim.result, MailboxFailed) and not sim.mail._jobs


def test_foreign_recipient_cannot_open_a_copied_handle():
    sim = MailboxExperiment(max_retries=0)
    sim.send()
    sim.through(lambda: bool(sim.inboxes["receiver-1"].messages))
    sim.schedule(
        MailboxItem(source="sender-1", token="foreign", handle=sim.inboxes["receiver-1"].messages[0])
    )
    sim.through(lambda: sim.result is not None)
    assert isinstance(sim.result, MailboxFailed)
    assert not any(e.event_type == "manifest_retrieved" for e in sim.events)


def test_multi_page_manifest_and_parallel_fragment_returns_reassemble_on_device():
    sim = MailboxExperiment()
    expected = sim.send(bytes(range(256)))
    sim.through(lambda: bool(sim.inboxes["receiver-1"].messages))
    sim.poll()
    sim.through(lambda: sim.result is not None)
    assert isinstance(sim.result, BundleDelivered)
    assert sim.result.source == sim.result.target == "receiver-1"
    assert sim.result.ciphertext == expected
    manifest = next(e for e in sim.events if e.event_type == "manifest_retrieved")
    assert manifest.payload["size"] > 2 * 864
    chunks = [e for e in sim.events if e.event_type == "fragment_retrieved"]
    assert len(chunks) > 1
    assert all(e.source_id == "receiver-1" for e in chunks)
    assert not sim.mail._jobs and not sim.vaults.reads


def test_lost_request_retries_without_any_channel_to_service_fallback():
    sim = MailboxExperiment(max_retries=1)
    sim.send()
    sim.through(lambda: bool(sim.inboxes["receiver-1"].messages))
    channel = sim.clients.people["receiver-1"].tor.id
    path = sim.topology.paths[sim.topology.path_id(channel, "provider-east")]
    path.blocked = True
    sim.poll()
    sim.through(lambda: sim.result is not None)
    assert isinstance(sim.result, MailboxFailed)
    assert any(e.event_type == "mailbox_retry" for e in sim.events)
    assert not any(e.event_type == "manifest_retrieved" for e in sim.events)
    assert not sim.mail._jobs and not sim.vaults.reads

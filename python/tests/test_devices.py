from random import Random
import pytest
from app.config import Config
from app.devices import DeviceProtocol
from app.participants import People


def test_reply_uses_key_learned_only_at_decryption_and_suppresses_duplicates():
    clients=People(Config(),Random(10))
    device=DeviceProtocol(clients)
    forward,reply=clients.messages.values()
    with pytest.raises(KeyError):
        device.prepare(reply)
    wire,_=device.prepare(forward)
    alice=clients.people[forward.sender_id]
    bob=clients.people[forward.target_id]
    assert alice.public_key not in wire and not bob.logs
    assert device.accept(forward,wire[32:],310)==alice.fingerprint
    assert device.accept(forward,wire[32:],320) is None
    assert len(bob.logs)==1 and bob.logs[0].text==forward.text
    response,_=device.prepare(reply)
    assert device.accept(reply,response[32:],530)==bob.fingerprint

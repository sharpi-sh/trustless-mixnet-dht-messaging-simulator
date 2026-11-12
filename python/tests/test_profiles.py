from app.config import Config
from app.profiles import profiles


def test_fidelity_profiles_publish_parameters_and_boundaries():
    registry = {p.id: p for p in profiles(Config(mu_per_second=2))}
    assert registry["loopix-usenix-2017"].parameters["mu_per_second"] == 2
    assert registry["kademlia-2002"].parameters["k"] == 20
    assert all(p.boundaries for p in registry.values())


def test_device_profile_distinguishes_encryption_signatures_and_identity_scope():
    device = next(p for p in profiles(Config()) if p.id == "device")
    assert device.parameters["signature"] == "Ed25519"
    assert device.parameters["encryption"] == "X25519 / HKDF-SHA-256 / AES-256-GCM"
    assert "expected sender ID" in device.parameters["verification_key_source"]
    assert device.reference == "https://www.rfc-editor.org/rfc/rfc8032.html#section-5.1"
    assert any("reply key" in operation for operation in device.operations)
    assert any("External identity assurance" in boundary for boundary in device.boundaries)


def test_anonymous_retrieval_publishes_single_use_and_fidelity_boundaries():
    profile = next(p for p in profiles(Config()) if p.id == "anonymous-retrieval")
    assert profile.parameters == {"mix_layers": 3, "reply_block_uses": 1}
    assert profile.reference and "nym-whitepaper" in profile.reference
    assert any("compatibility" in limit for limit in profile.boundaries)

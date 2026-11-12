from app.config import Config
from app.profiles import profiles


def test_fidelity_profiles_publish_parameters_and_boundaries():
    registry = {p.id: p for p in profiles(Config(mu_per_second=2))}
    assert registry["loopix-usenix-2017"].parameters["mu_per_second"] == 2
    assert registry["kademlia-2002"].parameters["k"] == 20
    assert "unverified" in registry["device"].boundaries[0]
    assert all(p.boundaries for p in registry.values())

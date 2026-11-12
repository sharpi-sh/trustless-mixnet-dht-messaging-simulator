import pytest
from pydantic import ValidationError

from app.config import Config


@pytest.mark.parametrize(
    "changes",
    [
        {"sender_count": 11},
        {"exchanges": 0},
        {"min_nodes": 19, "max_nodes": 10},
        {"replicas": 6, "storage_nodes": 2},
        {"jitter_min_ms": 999},
        {"pairing_strategy": "one_to_one_pairs", "sender_count": 2},
        {"always_online_probability": 1, "always_offline_probability": 1},
    ],
)
def test_invalid(changes):
    with pytest.raises(ValidationError):
        Config(**changes)


def test_default_timing_dimensions():
    config = Config()
    assert (config.step_delay_ms, config.base_transit_delay_ms, config.mu_per_second) == (500, 250, 1)

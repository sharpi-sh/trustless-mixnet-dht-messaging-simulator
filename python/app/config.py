"""Validated settings shared by creation, protocol metadata and the browser."""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

ChannelKind = Literal["tor", "shadowsocks", "direct"]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Outage(Model):
    node_id: str
    start_ms: int = Field(ge=0)
    duration_ms: int = Field(ge=0)


class Config(Model):
    sender_count: int = Field(1, ge=1, le=10)
    receiver_count: int = Field(1, ge=1, le=10)
    sender_channel: ChannelKind = "tor"
    recipient_channel: ChannelKind = "tor"
    min_nodes: int = Field(15, ge=10, le=20)
    max_nodes: int = Field(15, ge=10, le=20)
    randomise_count: bool = False
    pairing_strategy: Literal["all_to_one", "one_to_all", "one_to_one_pairs", "random_pairs"] = (
        "all_to_one"
    )
    pair_count: int = Field(1, ge=1, le=100)
    exchanges: int = Field(1, ge=1, le=10)
    random_seed: int | None = Field(None, ge=0, le=2**53 - 1)
    polling_enabled: bool = True
    polling_overrides: dict[str, bool] = Field(default_factory=dict)
    polling_interval_ms: int = Field(15000, ge=100, le=600000)
    poll_batch: int = Field(3, ge=1, le=16)
    base_transit_delay_ms: int = Field(250, ge=0, le=60000)
    jitter_min_ms: int = Field(0, ge=0, le=60000)
    jitter_max_ms: int = Field(150, ge=0, le=60000)
    mu_per_second: float = Field(1, gt=0, le=100)
    payload_rate_per_minute: float = Field(3, gt=0, le=600)
    client_loop_rate_per_minute: float = Field(1, gt=0, le=600)
    drop_cover_rate_per_minute: float = Field(1, gt=0, le=600)
    mix_loop_rate_per_minute: float = Field(1, gt=0, le=600)
    dht_nodes: int = Field(8, ge=2, le=64)
    storage_nodes: int = Field(12, ge=1, le=32)
    replicas: int = Field(2, ge=1, le=8)
    chunk_bytes: int = Field(128, ge=32, le=4096)
    pattern: Literal["always_online", "always_offline", "random", "bursty", "scheduled"] = (
        "always_online"
    )
    failure_probability: float = Field(0.1, ge=0, le=1)
    min_outage_ms: int = Field(500, ge=0, le=3600000)
    max_outage_ms: int = Field(500000, ge=0, le=3600000)
    min_online_ms: int = Field(1000, ge=1, le=3600000)
    initial_offline_probability: float = Field(0, ge=0, le=1)
    always_offline_probability: float = Field(0, ge=0, le=1)
    always_online_probability: float = Field(0, ge=0, le=1)
    scheduled_outages: list[Outage] = Field(default_factory=list)
    operator_count: int = Field(32, ge=1, le=100)
    max_retries: int = Field(2, ge=0, le=10)
    ack_timeout_ms: int = Field(1000, ge=1, le=60000)
    step_delay_ms: int = Field(500, ge=0, le=2000)

    @property
    def rpc_timeout_ms(self) -> int:
        max_leg = self.base_transit_delay_ms + self.jitter_max_ms
        return max(2000, 2 * max_leg + self.ack_timeout_ms)

    @model_validator(mode="after")
    def check_ranges(self) -> Self:
        if self.min_nodes > self.max_nodes or self.jitter_min_ms > self.jitter_max_ms:
            raise ValueError("Node and jitter ranges must be ordered")
        if self.min_outage_ms > self.max_outage_ms:
            raise ValueError("Outage range must be ordered")
        if self.always_online_probability + self.always_offline_probability > 1:
            raise ValueError("Permanent state probabilities must sum to at most one")
        if self.replicas > self.storage_nodes:
            raise ValueError("Replication exceeds the number of storage nodes")
        if self.pairing_strategy == "one_to_one_pairs" and self.sender_count != self.receiver_count:
            raise ValueError("One-to-one pairing requires equal participant counts")
        if (
            self.pairing_strategy == "random_pairs"
            and self.pair_count > self.sender_count * self.receiver_count
        ):
            raise ValueError("Random pair count exceeds distinct pairs")
        return self

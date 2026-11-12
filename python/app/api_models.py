"""Public command and state projections shared by local HTTP and WebSocket clients."""

from typing import Annotated, Literal, Self, TypeAlias

from pydantic import Field, JsonValue, StrictBool, StringConstraints, model_validator

from .config import Config, Model
from .devices import Lineage
from .events import Event
from .participants import DeviceLog, Direction, Role
from .profiles import Profile
from .topology import MixNode, Node

CommandType = Literal[
    "subscribe",
    "ping",
    "run",
    "pause",
    "resume",
    "step",
    "stop",
    "reset",
    "set_playback_delay",
    "request_state",
    "request_topology",
    "request_node_details",
    "request_protocol_state",
    "set_node_availability",
    "set_polling_enabled",
    "block_network_path",
    "restore_network_path",
    "block_stage_boundary",
    "restore_stage_boundary",
    "set_staged_messages",
    "request_device_logs",
    "request_artefact_lineage",
]
Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
SimulationStatus = Literal["ready", "running", "paused", "stopped", "completed", "failed"]
Outcome = Literal["staged", "sent", "received", "failed", "skipped"]


class MessageEdits(Model):
    messages: dict[Identifier, str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_text(self) -> Self:
        if any(not value.strip() for value in self.messages.values()):
            raise ValueError("Each staged message must contain visible text")
        return self


class Command(Model):
    type: CommandType
    command_id: Identifier
    simulation_id: Identifier | None = None
    target: str = ""
    enabled: StrictBool | None = None
    drop_in_flight: StrictBool = False
    delay_ms: int | None = Field(None, ge=0, le=2000, strict=True)
    messages: dict[Identifier, str] | None = None
    after_sequence: int = Field(0, ge=0, strict=True)
    epoch: int | None = Field(None, ge=0, strict=True)

    @model_validator(mode="after")
    def validate_arguments(self) -> Self:
        if self.type != "ping" and not self.simulation_id:
            raise ValueError("This command requires a simulation ID")
        targeted = {
            "request_node_details",
            "request_protocol_state",
            "set_node_availability",
            "block_network_path",
            "restore_network_path",
            "block_stage_boundary",
            "restore_stage_boundary",
        }
        if self.type in targeted and not self.target.strip():
            raise ValueError("This command requires a target")
        if self.type in {"set_node_availability", "set_polling_enabled"} and self.enabled is None:
            raise ValueError("An explicit enabled state is required")
        if self.type == "set_playback_delay" and self.delay_ms is None:
            raise ValueError("A playback delay is required")
        if self.type == "set_staged_messages":
            if self.messages is None:
                raise ValueError("Provide the staged messages to update")
            MessageEdits(messages=self.messages)
        elif self.messages is not None:
            raise ValueError("Only staged-message commands can contain message text")
        if self.drop_in_flight and self.type not in {"block_network_path", "block_stage_boundary"}:
            raise ValueError("Only a blocking command can drop an in-flight transit")
        return self


class MixDTO(MixNode):
    kind: Literal["mix"] = "mix"


class BasicNodeDTO(Node):
    kind: Literal["person", "tor", "provider", "dht", "storage"]


NodeDTO: TypeAlias = Annotated[MixDTO | BasicNodeDTO, Field(discriminator="kind")]


class ActiveTransit(Model):
    start_ms: int
    end_ms: int
    source: str
    target: str
    lane: Direction
    token: str


class PathDTO(Model):
    id: str
    source_id: str
    target_id: str
    boundary: str
    transport_label: str
    base_transit_delay_ms: int
    jitter_min_ms: int
    jitter_max_ms: int
    blocked: bool
    blocked_at: int | None
    blocked_by: str | None
    active: dict[str, ActiveTransit]
    attempted: int
    completed: int
    failed: int
    dropped: int


class TopologyDTO(Model):
    nodes: list[NodeDTO]
    paths: list[PathDTO]


class DeviceDTO(Model):
    id: str
    label: str
    role: Role
    tor_id: str
    fingerprint: str
    polling_enabled: bool
    logs: list[DeviceLog]


class MessageDTO(Model):
    id: str
    conversation_id: str
    sender_id: str
    target_id: str
    exchange: int
    direction: Direction
    text: str | None = None


class ObserverDTO(Model):
    id: str
    lifecycle: str


class NodeDetails(Model):
    node: NodeDTO
    profile: Profile
    state: dict[str, JsonValue]
    active_paths: list[str]


class ClockDTO(Model):
    simulation_id: str
    epoch: int = Field(0, ge=0)
    sequence: int = Field(ge=0)
    status: SimulationStatus
    simulation_time_ms: int = Field(ge=0)
    next_step_ms: int | None
    step_delay_ms: int


class Snapshot(ClockDTO):
    random_seed: int
    config: Config
    topology: TopologyDTO
    profiles: list[Profile]
    initialised: bool
    messages: list[MessageDTO]
    observer: ObserverDTO
    outcomes: dict[str, Outcome]
    devices: list[DeviceDTO]
    lineage: list[Lineage]


class Delta(ClockDTO):
    initialised: bool
    messages: list[MessageDTO] = Field(default_factory=list)
    nodes: list[NodeDTO] = Field(default_factory=list)
    paths: list[PathDTO] = Field(default_factory=list)
    devices: list[DeviceDTO] = Field(default_factory=list)
    lineage: list[Lineage] = Field(default_factory=list)
    events: list[Event] = Field(default_factory=list)
    outcomes: dict[str, Outcome] = Field(default_factory=dict)

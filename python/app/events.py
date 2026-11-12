from typing import Any

from pydantic import Field

from .config import Model


class Event(Model):
    event_id: str
    event_type: str
    simulation_id: str
    sequence: int
    simulation_time_ms: int
    step_id: str | None = None
    source_id: str | None = None
    target_id: str | None = None
    conversation_id: str | None = None
    message_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

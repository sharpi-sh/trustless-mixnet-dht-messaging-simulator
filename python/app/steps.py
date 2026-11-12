from dataclasses import dataclass, field
from typing import Any, Literal, Protocol
from .config import Model


class StepResult(Model):
    outcome: str
    detail: str | None = None


class Context(Protocol):
    id: str
    now: int
    def perform(self, action: "Action") -> StepResult: ...


@dataclass(kw_only=True)
class Action:
    source: str = ""
    target: str = ""
    token: str = ""
    lane: Literal["forward","reply"] = "forward"


@dataclass(kw_only=True)
class SimulationStep:
    step_id: str
    simulation_id: str
    scheduled_ms: int
    action: Action
    state: Literal["scheduled","executing","completed","failed"] = "scheduled"
    result: StepResult | None = field(default=None,init=False)

    def execute(self, context: Context) -> StepResult:
        self.state = "executing"
        self.result = context.perform(self.action)
        self.state = "failed" if self.result.outcome == "failed" else "completed"
        return self.result

    def dto(self) -> dict[str,Any]:
        return {"step_id":self.step_id,"simulation_id":self.simulation_id,
                "scheduled_ms":self.scheduled_ms,"step_type":type(self.action).__name__,
                "state":self.state,"involved_ids":[x for x in (self.action.source,self.action.target) if x],
                "result":self.result.model_dump() if self.result else None}

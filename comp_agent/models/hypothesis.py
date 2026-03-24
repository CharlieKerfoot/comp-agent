from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field


def _gen_id() -> str:
    return uuid.uuid4().hex[:8]


@dataclass
class Hypothesis:
    description: str
    rationale: str
    expected_improvement: float
    estimated_time_minutes: int
    risk: str = "medium"  # "low" | "medium" | "high"
    id: str = field(default_factory=_gen_id)
    dependencies: list[str] = field(default_factory=list)
    strategy_phase: str = "improve"
    code_sketch: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Hypothesis:
        return cls(**data)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, s: str) -> Hypothesis:
        return cls.from_dict(json.loads(s))

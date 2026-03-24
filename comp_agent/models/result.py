from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime


def _gen_id() -> str:
    return uuid.uuid4().hex[:8]


@dataclass
class Result:
    hypothesis_id: str
    branch: str
    score: float | None
    metric: str
    runtime_seconds: float
    memory_mb: float
    status: str  # "success" | "error" | "timeout"
    id: str = field(default_factory=_gen_id)
    error_message: str | None = None
    code_diff: str = ""
    stdout: str = ""
    stderr: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def score_improved(self, best_score: float | None, direction: str) -> bool:
        if self.status != "success" or self.score is None:
            return False
        if best_score is None:
            return True
        if direction == "maximize":
            return self.score > best_score
        return self.score < best_score

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Result:
        return cls(**data)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, s: str) -> Result:
        return cls.from_dict(json.loads(s))

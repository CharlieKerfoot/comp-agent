from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime


@dataclass
class ProblemSpec:
    # Identity
    name: str
    source: str  # "kaggle" | "hackathon" | "puzzle" | "custom"
    url: str | None = None

    # Objective
    problem_type: str = "classification"
    objective_description: str = ""
    metric: str = "accuracy"
    metric_direction: str = "maximize"  # "minimize" | "maximize"

    # Constraints
    time_limit: str | None = None  # ISO format datetime string
    submission_limit: int | None = None
    compute_constraints: str | None = None
    rules: list[str] = field(default_factory=list)

    # Data
    data_paths: list[str] = field(default_factory=list)
    data_description: str = ""
    target_column: str | None = None
    submission_format: str = ""

    # Evaluation
    eval_script: str | None = None
    public_leaderboard: bool = False

    def to_json(self, path: str) -> None:
        with open(path, "w") as f:
            json.dump(asdict(self), f, indent=2)

    @classmethod
    def from_json(cls, path: str) -> ProblemSpec:
        with open(path) as f:
            data = json.load(f)
        return cls(**data)

    def get_time_limit(self) -> datetime | None:
        if self.time_limit is None:
            return None
        return datetime.fromisoformat(self.time_limit)

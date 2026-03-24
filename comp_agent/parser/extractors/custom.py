from __future__ import annotations

from pathlib import Path

import yaml

from comp_agent.models import ProblemSpec


def extract_from_yaml(path: str) -> ProblemSpec:
    with open(path) as f:
        data = yaml.safe_load(f)

    required_fields = ["name", "source"]
    for field in required_fields:
        if field not in data:
            raise ValueError(f"Missing required field in spec YAML: {field}")

    return ProblemSpec(**data)


def extract_from_dict(data: dict) -> ProblemSpec:
    return ProblemSpec(**data)

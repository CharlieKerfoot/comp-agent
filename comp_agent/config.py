"""Layered config: built-in defaults + per-workspace overrides."""

from __future__ import annotations

from pathlib import Path

import yaml


DEFAULTS: dict = {
    "llm_provider": "api",
    "llm_model": "claude-opus-4-7",
    "time_budget_hours": 48,
    "submission_limit_per_day": 5,
    "reserved_submissions_per_day": 1,
    "execution_timeout_seconds": 1800,
    "max_consecutive_failures": 5,
    "critique_interval": 5,
    "autonomy_mode": "approval",  # "approval" | "auto"
}


WORKSPACE_CONFIG_TEMPLATE = """\
# Competition-specific config. Every key is optional — anything you don't set
# falls back to comp-agent's built-in defaults.
#
# See `comp_agent/config.py::DEFAULTS` for all available keys and defaults.

# llm_provider: "api"          # "api" (ANTHROPIC_API_KEY) | "claude-code" (subscription)
# llm_model: "claude-opus-4-7"

# time_budget_hours: 48        # total wall-clock budget for the competition
# execution_timeout_seconds: 1800   # per-hypothesis script timeout
# max_consecutive_failures: 5  # trigger "pivot" after this many fails in a row
# critique_interval: 5         # run adversarial critique every N iterations
# autonomy_mode: "approval"    # "approval" (ask before each hypothesis) | "auto"
"""


def load_config(workspace_path: str = "config.yaml") -> dict:
    """Merge built-in defaults with a workspace config.yaml if present."""
    merged = dict(DEFAULTS)
    path = Path(workspace_path)
    if path.exists():
        with path.open() as f:
            overrides = yaml.safe_load(f) or {}
        merged.update(overrides)
    return merged

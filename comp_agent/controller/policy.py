from __future__ import annotations

from comp_agent.tracker.compare import compute_improvement_rate


PHASES = ["init", "parse", "baseline", "improve", "ensemble", "polish", "submit"]
IMPROVEMENT_THRESHOLD = 0.001


def select_phase(time_remaining_hours: float, history: list[dict],
                 max_consecutive_failures: int = 5) -> str:
    if not history:
        return "baseline"

    successful = [r for r in history if r["status"] == "success" and r.get("score") is not None]

    if not successful:
        return "baseline"

    # Check for stuck condition
    consecutive_failures = 0
    for r in reversed(history):
        if r["status"] != "success":
            consecutive_failures += 1
        else:
            break
    if consecutive_failures >= max_consecutive_failures:
        return "pivot"

    improvement_rate = compute_improvement_rate(history)

    if time_remaining_hours == float("inf"):
        # No deadline: use improvement rate to decide
        if improvement_rate < IMPROVEMENT_THRESHOLD and len(successful) >= 5:
            return "pivot"
        return "improve"

    if time_remaining_hours > 24:
        if improvement_rate < IMPROVEMENT_THRESHOLD and len(successful) >= 5:
            return "pivot"
        return "improve"
    elif time_remaining_hours > 6:
        return "ensemble"
    elif time_remaining_hours > 2:
        return "polish"
    else:
        return "submit"


def should_critique(total_runs: int, critique_interval: int = 5) -> bool:
    return total_runs > 0 and total_runs % critique_interval == 0

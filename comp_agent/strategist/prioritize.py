from __future__ import annotations

from comp_agent.models import Hypothesis


RISK_PENALTY = {
    "low": 1.0,
    "medium": 0.7,
    "high": 0.4,
}


def prioritize(hypotheses: list[Hypothesis],
               time_budget_hours: float,
               rejected_descriptions: list[str] | None = None) -> list[Hypothesis]:
    rejected = set(rejected_descriptions or [])

    def score(h: Hypothesis) -> float:
        # Base: expected improvement per minute
        if h.estimated_time_minutes <= 0:
            efficiency = h.expected_improvement
        else:
            efficiency = h.expected_improvement / h.estimated_time_minutes

        # Risk penalty
        risk_factor = RISK_PENALTY.get(h.risk, 0.5)

        # Time feasibility: penalize if hypothesis takes too long for remaining budget
        time_fraction = h.estimated_time_minutes / (time_budget_hours * 60)
        time_factor = 1.0 if time_fraction < 0.5 else max(0.3, 1.0 - time_fraction)

        # Novelty: penalize hypotheses similar to rejected ones
        novelty = 0.5 if h.description in rejected else 1.0

        return efficiency * risk_factor * time_factor * novelty

    return sorted(hypotheses, key=score, reverse=True)

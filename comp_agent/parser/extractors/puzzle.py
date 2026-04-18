from __future__ import annotations

from comp_agent.llm import get_provider
from comp_agent.models import ProblemSpec


def extract_from_text(problem_text: str, source_url: str | None = None) -> ProblemSpec:
    llm = get_provider()

    prompt = f"""Analyze this mathematical/algorithmic puzzle and extract structured information.

Problem:
{problem_text[:10000]}

Extract the following as JSON:
- name: short name for the puzzle
- problem_type: one of "combinatorial", "mathematical", "optimization"
- objective_description: what needs to be solved
- metric: how the solution is evaluated (e.g., "correctness", "optimality", "score")
- metric_direction: "minimize" or "maximize"
- submission_format: what format the answer should be in
- rules: list of constraints

Output ONLY valid JSON."""

    import json
    data = json.loads(llm.ask(prompt, max_tokens=2048))

    return ProblemSpec(
        name=data.get("name", "Puzzle"),
        source="puzzle",
        url=source_url,
        problem_type=data.get("problem_type", "mathematical"),
        objective_description=data.get("objective_description", ""),
        metric=data.get("metric", "correctness"),
        metric_direction=data.get("metric_direction", "maximize"),
        submission_format=data.get("submission_format", ""),
        rules=data.get("rules", []),
    )

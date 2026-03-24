from __future__ import annotations

import anthropic

from comp_agent.models import ProblemSpec


def extract_from_url(url: str, page_content: str) -> ProblemSpec:
    client = anthropic.Anthropic()

    prompt = f"""Analyze this competition/hackathon page and extract structured information.

URL: {url}

Page content:
{page_content[:10000]}

Extract the following fields as JSON:
- name: competition name
- problem_type: one of "classification", "regression", "optimization", "combinatorial", "mathematical", "systems"
- objective_description: what participants need to build/solve
- metric: how solutions are evaluated
- metric_direction: "minimize" or "maximize"
- submission_format: expected output format
- rules: list of rules/constraints
- time_limit: deadline if mentioned (ISO format)
- submission_limit: max submissions if mentioned

Output ONLY valid JSON, no other text."""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    import json
    data = json.loads(response.content[0].text)

    return ProblemSpec(
        name=data.get("name", "Unknown Competition"),
        source="hackathon",
        url=url,
        problem_type=data.get("problem_type", "systems"),
        objective_description=data.get("objective_description", ""),
        metric=data.get("metric", "custom_score"),
        metric_direction=data.get("metric_direction", "maximize"),
        submission_format=data.get("submission_format", ""),
        rules=data.get("rules", []),
        time_limit=data.get("time_limit"),
        submission_limit=data.get("submission_limit"),
    )

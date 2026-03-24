from __future__ import annotations

import json

import anthropic

from comp_agent.models import ProblemSpec


class CritiqueEngine:
    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        self.client = anthropic.Anthropic()
        self.model = model

    def critique(self, code: str, score: float, spec: ProblemSpec) -> dict:
        prompt = f"""You are a competition grandmaster reviewing a solution.

Competition: {spec.name}
Problem type: {spec.problem_type}
Metric: {spec.metric} ({spec.metric_direction})
Current score: {score}

Solution code:
```python
{code[:8000]}
```

Act as an adversarial reviewer. Provide:
1. The 3 biggest weaknesses of this solution
2. What the winning solution would likely do differently
3. Specific, actionable suggestions for improvement

Output as JSON:
{{
    "weaknesses": ["weakness 1", "weakness 2", "weakness 3"],
    "winning_approach": "description of likely winning approach",
    "suggestions": ["specific suggestion 1", "specific suggestion 2", "specific suggestion 3"]
}}

Output ONLY valid JSON."""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]

        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            return {
                "weaknesses": ["Failed to parse critique output"],
                "winning_approach": "Unknown",
                "suggestions": [text[:500]],
            }

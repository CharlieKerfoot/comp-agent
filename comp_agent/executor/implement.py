from __future__ import annotations

import anthropic

from comp_agent.models import Hypothesis, ProblemSpec


class HypothesisImplementer:
    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        self.client = anthropic.Anthropic()
        self.model = model

    def implement(self, hypothesis: Hypothesis, spec: ProblemSpec,
                  current_code: str = "", max_retries: int = 3) -> str:
        prompt = self._build_prompt(hypothesis, spec, current_code)

        response = self.client.messages.create(
            model=self.model,
            max_tokens=8192,
            messages=[{"role": "user", "content": prompt}],
        )

        return response.content[0].text

    def _build_prompt(self, hypothesis: Hypothesis, spec: ProblemSpec,
                      current_code: str) -> str:
        parts = [
            f"You are implementing a hypothesis for the competition: {spec.name}",
            f"\nProblem type: {spec.problem_type}",
            f"Metric: {spec.metric} ({spec.metric_direction})",
            f"Target column: {spec.target_column or 'N/A'}",
            f"\nHypothesis: {hypothesis.description}",
            f"Rationale: {hypothesis.rationale}",
            f"Code sketch: {hypothesis.code_sketch}",
        ]

        if current_code:
            parts.append(f"\nCurrent solution code:\n```python\n{current_code}\n```")

        parts.append(
            "\nGenerate the complete Python code to implement this hypothesis. "
            "The code should:\n"
            "1. Read data from the data/ directory\n"
            "2. Implement the hypothesis\n"
            "3. Print the validation score as 'SCORE: <number>'\n"
            "4. Save predictions to submissions/submission.csv\n"
            "\nOutput ONLY the Python code, no explanations."
        )

        return "\n".join(parts)

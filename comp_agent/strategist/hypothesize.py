from __future__ import annotations

import json
from pathlib import Path

import anthropic

from comp_agent.models import Hypothesis, ProblemSpec
from comp_agent.strategist.classify import classify_problem, get_phase_strategies


class HypothesisGenerator:
    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        self.client = anthropic.Anthropic()
        self.model = model

    def generate(self, spec: ProblemSpec, history: list[dict],
                 phase: str, time_budget_hours: float,
                 critiques: list[dict] | None = None,
                 num_hypotheses: int = 3) -> list[Hypothesis]:
        family = classify_problem(spec)
        phase_hints = get_phase_strategies(family, phase)
        playbook = self._load_playbook(family)

        prompt = self._build_prompt(
            spec, history, phase, time_budget_hours,
            phase_hints, playbook, critiques, num_hypotheses,
        )

        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )

        return self._parse_hypotheses(response.content[0].text)

    def _build_prompt(self, spec: ProblemSpec, history: list[dict],
                      phase: str, time_budget_hours: float,
                      phase_hints: list[str], playbook: str,
                      critiques: list[dict] | None,
                      num_hypotheses: int) -> str:
        parts = [
            f"You are a competition strategy expert generating hypotheses for: {spec.name}",
            f"\nProblem type: {spec.problem_type}",
            f"Metric: {spec.metric} ({spec.metric_direction})",
            f"Objective: {spec.objective_description}",
            f"Data: {spec.data_description}",
            f"Target column: {spec.target_column or 'N/A'}",
            f"\nCurrent phase: {phase}",
            f"Time remaining: {time_budget_hours:.1f} hours",
        ]

        # Score history
        if history:
            successful = [r for r in history if r["status"] == "success" and r.get("score") is not None]
            if successful:
                best = max(successful, key=lambda r: r["score"]) if spec.metric_direction == "maximize" else min(successful, key=lambda r: r["score"])
                parts.append(f"\nBest score so far: {best['score']} (run {best['id']})")
                parts.append(f"Total runs: {len(history)}, Successful: {len(successful)}")

                parts.append("\nRecent runs:")
                for r in successful[-5:]:
                    parts.append(f"  - {r['id']}: score={r['score']}, branch={r['branch']}")

        # Recent critiques
        if critiques:
            parts.append("\nRecent critiques of current best solution:")
            for c in critiques[:2]:
                parts.append(f"  - {c['content'][:500]}")

        # Phase hints
        parts.append(f"\nSuggested strategies for {phase} phase:")
        for hint in phase_hints:
            parts.append(f"  - {hint}")

        # Playbook
        if playbook:
            parts.append(f"\nPlaybook guidance:\n{playbook[:2000]}")

        parts.append(f"""
Generate exactly {num_hypotheses} specific, actionable hypotheses. For each, output JSON:
{{
    "description": "specific action (NOT vague like 'try feature engineering')",
    "rationale": "why this should improve the score",
    "expected_improvement": 0.05,
    "estimated_time_minutes": 30,
    "risk": "low|medium|high",
    "strategy_phase": "{phase}",
    "code_sketch": "pseudocode or key implementation steps"
}}

Output a JSON array of {num_hypotheses} hypothesis objects. Output ONLY the JSON array.""")

        return "\n".join(parts)

    def _parse_hypotheses(self, text: str) -> list[Hypothesis]:
        # Strip markdown code fences if present
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()

        try:
            data = json.loads(text)
            if isinstance(data, list):
                return [Hypothesis.from_dict(h) for h in data]
            return [Hypothesis.from_dict(data)]
        except (json.JSONDecodeError, TypeError):
            # If parsing fails, create a single fallback hypothesis
            return [Hypothesis(
                description="Manual review needed - LLM output parsing failed",
                rationale="Automated hypothesis generation failed",
                expected_improvement=0.0,
                estimated_time_minutes=60,
                risk="high",
                code_sketch=text[:500],
            )]

    def _load_playbook(self, family: str) -> str:
        playbook_dir = Path(__file__).parent / "playbooks"
        playbook_path = playbook_dir / f"{family}.md"
        if playbook_path.exists():
            return playbook_path.read_text()
        return ""

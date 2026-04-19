"""Apply a hypothesis to solution/train.py by generating a modified version."""

from __future__ import annotations

from pathlib import Path

from comp_agent.llm import LLMProvider, get_provider
from comp_agent.models import Hypothesis, ProblemSpec
from comp_agent.strategist._context import (
    data_preview,
    extract_python,
    sample_submission_snippet,
)


class HypothesisImplementer:
    """Rewrites solution/train.py so a hypothesis is actually executed."""

    def __init__(self, llm: LLMProvider | None = None,
                 target_path: str = "solution/train.py"):
        self.llm = llm or get_provider()
        self.target_path = Path(target_path)

    def apply(self, hypothesis: Hypothesis, spec: ProblemSpec) -> str:
        """Generate and write a new solution/train.py for this hypothesis.

        Returns the new source.
        """
        current = self.target_path.read_text() if self.target_path.exists() else ""
        prompt = _build_prompt(
            hypothesis=hypothesis,
            spec=spec,
            current_code=current,
            submission_snippet=sample_submission_snippet(spec.data_paths),
            preview=data_preview(spec.data_paths),
        )
        text = self.llm.ask(prompt, max_tokens=8192)
        new_code = extract_python(text)
        self.target_path.parent.mkdir(parents=True, exist_ok=True)
        self.target_path.write_text(new_code)
        return new_code


def _build_prompt(hypothesis: Hypothesis, spec: ProblemSpec,
                  current_code: str, submission_snippet: str,
                  preview: str) -> str:
    sketch = f"\n\nCode sketch from strategist:\n{hypothesis.code_sketch}" if hypothesis.code_sketch else ""
    rationale = f"\n\nRationale: {hypothesis.rationale}" if hypothesis.rationale else ""
    return f"""You are modifying solution/train.py to apply exactly ONE hypothesis. Rewrite the file so the hypothesis is actually implemented — do not just tweak comments.

Competition: {spec.name}
Problem type: {spec.problem_type}
Metric: {spec.metric} ({spec.metric_direction})
Target column: {spec.target_column or "(unknown — infer from data)"}

### Hypothesis to apply ###
{hypothesis.description}{rationale}{sketch}

### SUBMISSION FORMAT — YOUR OUTPUT MUST MATCH THIS EXACTLY ###
{submission_snippet}

Your generated submissions/submission.csv MUST have the same columns, in the same order, with the same dtypes. When sample_submission.csv exists, load it with pandas, fill in predictions, and write it back.

### Data files in ./data/ ###
{preview}

### Current solution/train.py ###
```python
{current_code}
```

Produce the NEW full contents of solution/train.py. Requirements:
- Keep the PEP 723 `# /// script` header; ADD any new dependencies the hypothesis introduces (xgboost, lightgbm, catboost, torch, onnx, etc.). Every imported package MUST be listed.
- The script runs via `uv run --script solution/train.py`.
- Read data from ./data/, train, write predictions to ./submissions/submission.csv.
- Print the local validation score on its own line as exactly: `SCORE: <number>`
- No CLI args, no config files.
- The code MUST be materially different from the current file in a way that reflects the hypothesis. If the hypothesis calls for a new model or feature engineering step, it must actually be in the new code.

Respond with ONLY the new Python source, wrapped in ```python ... ``` fences."""

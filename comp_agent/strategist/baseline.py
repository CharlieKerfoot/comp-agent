"""Generate an initial baseline `solution/train.py` from a ProblemSpec."""

from __future__ import annotations

from comp_agent.llm import LLMProvider, get_provider
from comp_agent.models import ProblemSpec
from comp_agent.strategist._context import (
    data_preview,
    extract_python,
    sample_submission_snippet,
)


class BaselineGenerator:
    def __init__(self, llm: LLMProvider | None = None):
        self.llm = llm or get_provider()

    def generate(self, spec: ProblemSpec) -> str:
        """Ask the LLM to produce baseline training code. Returns a Python source string."""
        prompt = _build_prompt(
            spec=spec,
            submission_snippet=sample_submission_snippet(spec.data_paths),
            preview=data_preview(spec.data_paths),
        )
        text = self.llm.ask(prompt, max_tokens=4096)
        return extract_python(text)


def _build_prompt(spec: ProblemSpec, submission_snippet: str, preview: str) -> str:
    return f"""You are writing the SIMPLEST POSSIBLE end-to-end baseline for a competition. It must run and produce a valid submission — this is the floor, not the ceiling.

Competition: {spec.name}
Problem type: {spec.problem_type}
Objective: {spec.objective_description or "(not specified)"}
Metric: {spec.metric} ({spec.metric_direction})
Target column: {spec.target_column or "(unknown — infer from data)"}

### SUBMISSION FORMAT — YOUR OUTPUT MUST MATCH THIS EXACTLY ###
{submission_snippet}

Your generated submissions/submission.csv MUST have the same columns, in the same order, with the same dtypes, as the file above. When sample_submission.csv exists, the safest pattern is: load it with pandas, fill in your predictions, write it back. Do NOT invent column names.

### Data files in ./data/ ###
{preview}

The script will be executed with `uv run --script solution/train.py`. It MUST begin with a PEP 723 inline script metadata header listing every package it imports:

```
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pandas",
#     "numpy",
#     "scikit-learn",
# ]
# ///
```

After the header, the script must:
1. Read training and test data from ./data/ with pandas.
2. Train the simplest reasonable model (logistic regression for classification, linear regression for regression, constant/majority baseline if unsure).
3. Print the local validation score on its own line as exactly: `SCORE: <number>`
4. Write predictions to ./submissions/submission.csv matching sample_submission.csv's column schema.
5. Create ./submissions/ if needed.

Keep it under 100 lines. Prefer stdlib + pandas + scikit-learn. No CLI args, no config files. If a step is ambiguous, make a reasonable choice — do NOT ask questions.

Respond with ONLY the Python source (including the PEP 723 header), wrapped in ```python ... ``` fences."""

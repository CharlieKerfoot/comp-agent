from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from comp_agent.llm import get_provider
from comp_agent.models import ProblemSpec


def extract_from_kaggle(competition_slug: str, data_dir: str = "data") -> ProblemSpec:
    Path(data_dir).mkdir(parents=True, exist_ok=True)

    _download_data(competition_slug, data_dir)
    _unzip_all(data_dir)

    url = f"https://www.kaggle.com/competitions/{competition_slug}"
    page_text = _fetch_competition_pages(competition_slug)
    sample_submission = _peek_sample_submission(data_dir)
    data_paths = [str(p) for p in Path(data_dir).glob("*") if p.is_file()]

    llm_spec = _llm_extract_spec(
        slug=competition_slug,
        url=url,
        page_text=page_text,
        sample_submission=sample_submission,
        data_files=[Path(p).name for p in data_paths],
    )

    metric = llm_spec.get("metric") or "unknown"
    direction = llm_spec.get("metric_direction") or _infer_direction(metric)

    return ProblemSpec(
        name=llm_spec.get("name") or competition_slug,
        source="kaggle",
        url=url,
        problem_type=llm_spec.get("problem_type") or "classification",
        objective_description=llm_spec.get("objective_description", ""),
        metric=metric,
        metric_direction=direction,
        target_column=llm_spec.get("target_column"),
        data_description=llm_spec.get("data_description", ""),
        submission_limit=llm_spec.get("submission_limit"),
        data_paths=data_paths,
        submission_format=llm_spec.get("submission_format") or sample_submission or "csv",
        rules=llm_spec.get("rules", []) or [],
        public_leaderboard=True,
    )


def _download_data(slug: str, data_dir: str) -> None:
    try:
        subprocess.run(
            ["kaggle", "competitions", "download", "-c", slug, "-p", data_dir],
            check=True, capture_output=True, text=True,
        )
    except FileNotFoundError as e:
        raise RuntimeError(
            "The 'kaggle' CLI is not installed or not on PATH.\n"
            "Install it with: uv tool install kaggle\n"
            "Then configure credentials at ~/.kaggle/kaggle.json "
            "(Kaggle → Account → API → Create New Token)."
        ) from e
    except subprocess.CalledProcessError as e:
        detail = (e.stderr or "").strip() or (e.stdout or "").strip() or "(no output)"
        raise RuntimeError(
            f"kaggle download failed for '{slug}':\n{detail}\n"
            "Check that the slug is correct and that you've accepted the "
            "competition rules on kaggle.com."
        ) from e


def _unzip_all(data_dir: str) -> None:
    for zip_file in Path(data_dir).glob("*.zip"):
        subprocess.run(
            ["unzip", "-o", str(zip_file), "-d", data_dir],
            capture_output=True, text=True,
        )
        zip_file.unlink()


def _fetch_competition_pages(slug: str) -> str:
    """Fetch Overview + Data + Evaluation Kaggle pages and return concatenated text."""
    urls = [
        f"https://www.kaggle.com/competitions/{slug}/overview",
        f"https://www.kaggle.com/competitions/{slug}/overview/evaluation",
        f"https://www.kaggle.com/competitions/{slug}/data",
    ]
    chunks: list[str] = []
    for u in urls:
        try:
            result = subprocess.run(
                ["curl", "-sL", "--max-time", "15",
                 "-A", "Mozilla/5.0 (compete-agent)", u],
                capture_output=True, text=True, timeout=20,
            )
            text = _strip_html(result.stdout)
            if text.strip():
                chunks.append(f"=== {u} ===\n{text}")
        except Exception:
            continue
    return "\n\n".join(chunks)


def _strip_html(html: str) -> str:
    # Remove scripts/styles wholesale, then tags, then collapse whitespace.
    text = re.sub(r"<script.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _peek_sample_submission(data_dir: str) -> str:
    """Return the header + first couple rows of sample_submission.csv, if present."""
    for name in ("sample_submission.csv", "sampleSubmission.csv"):
        path = Path(data_dir) / name
        if path.exists():
            try:
                with path.open("r", errors="replace") as f:
                    lines = [next(f, "").rstrip("\n") for _ in range(3)]
                return f"sample_submission.csv:\n" + "\n".join(l for l in lines if l)
            except OSError:
                pass
    return ""


def _llm_extract_spec(slug: str, url: str, page_text: str,
                      sample_submission: str, data_files: list[str]) -> dict:
    """Ask the LLM to parse the Kaggle page into structured fields."""
    if not page_text.strip():
        # Nothing to parse — return empty dict and let defaults apply.
        return {}

    prompt = f"""Parse this Kaggle competition into structured JSON.

URL: {url}
Slug: {slug}

Data files present locally: {', '.join(data_files) or '(none)'}

{sample_submission or '(no sample_submission.csv found)'}

Competition page text (Overview + Evaluation + Data, HTML stripped):
{page_text[:12000]}

Extract these fields. Use null if truly unknown — do NOT guess:
- name: human-readable competition name
- problem_type: one of "classification", "regression", "optimization", "combinatorial", "mathematical", "systems"
- objective_description: 1-3 sentences describing what to predict/build
- metric: the exact evaluation metric (e.g. "RMSE", "AUC", "mean F1", "quadratic weighted kappa")
- metric_direction: "minimize" or "maximize"
- target_column: name of the target column in training data, if applicable
- data_description: 1-3 sentences on the data shape/columns/relationships
- submission_format: description of the expected submission file (columns, types)
- rules: list of notable rules/constraints (external data, team size, compute limits, etc.)
- submission_limit: max submissions per day as an integer, if stated

Respond with ONLY a JSON object. No prose, no markdown fences."""

    try:
        text = get_provider().ask(prompt, max_tokens=2048)
        return _parse_json(text)
    except Exception as e:
        print(f"Warning: LLM spec extraction failed: {e}")
        return {}


def _parse_json(text: str) -> dict:
    """Parse a JSON object out of LLM output, tolerating code fences."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    else:
        obj = re.search(r"\{.*\}", text, re.DOTALL)
        if obj:
            text = obj.group(0)
    return json.loads(text)


def _infer_direction(metric: str) -> str:
    minimize_metrics = {"rmse", "mae", "mse", "log_loss", "logloss", "error", "mape", "smape"}
    metric_lower = (metric or "").lower().replace(" ", "_")
    for m in minimize_metrics:
        if m in metric_lower:
            return "minimize"
    return "maximize"

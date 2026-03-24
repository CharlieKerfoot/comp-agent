from __future__ import annotations

import json
import subprocess
from pathlib import Path

from comp_agent.models import ProblemSpec


def extract_from_kaggle(competition_slug: str, data_dir: str = "data") -> ProblemSpec:
    Path(data_dir).mkdir(parents=True, exist_ok=True)

    # Download competition data
    subprocess.run(
        ["kaggle", "competitions", "download", "-c", competition_slug, "-p", data_dir],
        check=True, capture_output=True, text=True,
    )

    # Unzip if needed
    for zip_file in Path(data_dir).glob("*.zip"):
        subprocess.run(
            ["unzip", "-o", str(zip_file), "-d", data_dir],
            capture_output=True, text=True,
        )
        zip_file.unlink()

    # Get competition metadata via API
    metadata = _get_competition_metadata(competition_slug)

    data_paths = [str(p) for p in Path(data_dir).glob("*") if p.is_file()]

    return ProblemSpec(
        name=competition_slug,
        source="kaggle",
        url=f"https://www.kaggle.com/competitions/{competition_slug}",
        problem_type=metadata.get("problem_type", "classification"),
        objective_description=metadata.get("description", ""),
        metric=metadata.get("evaluationMetric", "unknown"),
        metric_direction=_infer_direction(metadata.get("evaluationMetric", "")),
        submission_limit=metadata.get("maxDailySubmissions"),
        data_paths=data_paths,
        submission_format=metadata.get("submissionFormat", "csv"),
        public_leaderboard=True,
    )


def _get_competition_metadata(slug: str) -> dict:
    try:
        result = subprocess.run(
            ["kaggle", "competitions", "list", "-s", slug, "--csv"],
            capture_output=True, text=True, check=True,
        )
        # Parse minimal metadata from CLI output
        lines = result.stdout.strip().split("\n")
        if len(lines) >= 2:
            headers = lines[0].split(",")
            values = lines[1].split(",")
            return dict(zip(headers, values))
    except Exception:
        pass
    return {}


def _infer_direction(metric: str) -> str:
    minimize_metrics = {"rmse", "mae", "mse", "log_loss", "logloss", "error"}
    metric_lower = metric.lower().replace(" ", "_")
    for m in minimize_metrics:
        if m in metric_lower:
            return "minimize"
    return "maximize"

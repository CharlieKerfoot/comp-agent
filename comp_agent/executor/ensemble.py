from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from comp_agent.executor.runner import CodeRunner
from comp_agent.executor.snapshot import GitSnapshot
from comp_agent.models import ProblemSpec, Result
from comp_agent.tracker.db import TrackerDB


class EnsembleBuilder:
    def __init__(self, working_dir: str = ".", timeout_seconds: int = 1800):
        self.working_dir = Path(working_dir).resolve()
        self.runner = CodeRunner(timeout_seconds=timeout_seconds, working_dir=working_dir)
        self.git = GitSnapshot(working_dir)

    def collect_predictions(self, tracker: TrackerDB,
                            direction: str = "maximize",
                            top_n: int = 3) -> list[dict]:
        """Checkout each accepted branch and run predict.py to collect predictions."""
        accepted = tracker.get_accepted_runs()
        if not accepted:
            return []

        # Sort by score
        if direction == "maximize":
            accepted.sort(key=lambda r: r["score"] or 0, reverse=True)
        else:
            accepted.sort(key=lambda r: r["score"] or float("inf"))

        top_runs = accepted[:top_n]
        predictions = []
        original_branch = self.git.current_branch()

        predictions_dir = self.working_dir / "ensemble_predictions"
        predictions_dir.mkdir(exist_ok=True)

        for run in top_runs:
            branch = run["branch"]
            run_id = run["id"]
            pred_path = predictions_dir / f"pred_{run_id}.csv"

            try:
                self.git.checkout(branch)

                # Run predict.py if it exists
                predict_script = self.working_dir / "solution" / "predict.py"
                if predict_script.exists():
                    result = subprocess.run(
                        [sys.executable, str(predict_script),
                         "--output", str(pred_path)],
                        cwd=self.working_dir,
                        capture_output=True, text=True,
                        timeout=600,
                    )
                    if result.returncode == 0 and pred_path.exists():
                        predictions.append({
                            "run_id": run_id,
                            "branch": branch,
                            "score": run["score"],
                            "prediction_path": str(pred_path),
                        })
            except Exception:
                continue

        self.git.checkout(original_branch)
        return predictions

    def generate_ensemble_script(self, predictions: list[dict],
                                  method: str = "average") -> str:
        """Generate ensemble.py that combines predictions."""
        pred_paths = [p["prediction_path"] for p in predictions]
        weights = [p["score"] for p in predictions]

        script = f'''"""Auto-generated ensemble script."""
import csv
import sys
from pathlib import Path

PREDICTION_FILES = {pred_paths}
WEIGHTS = {weights}
METHOD = "{method}"


def load_predictions(path):
    """Load predictions from CSV file."""
    with open(path) as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    return rows


def weighted_average(all_preds, weights):
    """Combine predictions using weighted average."""
    if not all_preds:
        return []

    total_weight = sum(weights)
    normalized = [w / total_weight for w in weights]
    result = []

    for i in range(len(all_preds[0])):
        row = dict(all_preds[0][i])
        # Average numeric columns
        for key in row:
            if key == "id":
                continue
            try:
                values = [float(preds[i][key]) for preds in all_preds]
                row[key] = str(sum(v * w for v, w in zip(values, normalized)))
            except (ValueError, KeyError):
                pass
        result.append(row)

    return result


def majority_vote(all_preds):
    """Combine predictions using majority voting."""
    if not all_preds:
        return []

    result = []
    for i in range(len(all_preds[0])):
        row = dict(all_preds[0][i])
        for key in row:
            if key == "id":
                continue
            votes = [preds[i][key] for preds in all_preds]
            from collections import Counter
            row[key] = Counter(votes).most_common(1)[0][0]
        result.append(row)

    return result


def main():
    all_preds = []
    for path in PREDICTION_FILES:
        if Path(path).exists():
            all_preds.append(load_predictions(path))

    if not all_preds:
        print("No prediction files found!")
        sys.exit(1)

    if METHOD == "average":
        combined = weighted_average(all_preds, WEIGHTS[:len(all_preds)])
    elif METHOD == "vote":
        combined = majority_vote(all_preds)
    else:
        combined = all_preds[0]

    # Write output
    output_path = Path("submissions/submission.csv")
    output_path.parent.mkdir(exist_ok=True)

    if combined:
        fieldnames = list(combined[0].keys())
        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(combined)
        print(f"Ensemble written to {{output_path}}")
    else:
        print("No predictions to combine!")
        sys.exit(1)


if __name__ == "__main__":
    main()
'''
        return script

    def build_ensemble(self, tracker: TrackerDB, spec: ProblemSpec,
                       top_n: int = 3, method: str = "average") -> Result | None:
        """Full ensemble workflow: collect predictions, generate script, run it."""
        predictions = self.collect_predictions(
            tracker, spec.metric_direction, top_n,
        )

        if len(predictions) < 2:
            return None

        # Generate and write ensemble script
        script = self.generate_ensemble_script(predictions, method)
        ensemble_path = self.working_dir / "solution" / "ensemble.py"
        ensemble_path.parent.mkdir(exist_ok=True)
        ensemble_path.write_text(script)

        # Run the ensemble
        result = self.runner.run(
            [sys.executable, str(ensemble_path)],
            hypothesis_id="ensemble",
            branch=self.git.current_branch(),
            metric=spec.metric,
        )

        return result

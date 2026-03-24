import csv
import tempfile
from pathlib import Path

from comp_agent.executor.ensemble import EnsembleBuilder


class TestEnsembleScript:
    def test_generate_ensemble_script(self):
        builder = EnsembleBuilder()
        predictions = [
            {"run_id": "r1", "branch": "b1", "score": 0.9, "prediction_path": "/tmp/p1.csv"},
            {"run_id": "r2", "branch": "b2", "score": 0.85, "prediction_path": "/tmp/p2.csv"},
        ]
        script = builder.generate_ensemble_script(predictions, method="average")
        assert "PREDICTION_FILES" in script
        assert "weighted_average" in script
        assert "/tmp/p1.csv" in script

    def test_generate_vote_script(self):
        builder = EnsembleBuilder()
        predictions = [
            {"run_id": "r1", "branch": "b1", "score": 0.9, "prediction_path": "/tmp/p1.csv"},
            {"run_id": "r2", "branch": "b2", "score": 0.85, "prediction_path": "/tmp/p2.csv"},
        ]
        script = builder.generate_ensemble_script(predictions, method="vote")
        assert 'METHOD = "vote"' in script

    def test_ensemble_script_runs(self):
        """Test that generated ensemble script actually runs and produces output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create prediction files
            pred1 = Path(tmpdir) / "pred1.csv"
            pred2 = Path(tmpdir) / "pred2.csv"

            with open(pred1, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["id", "target"])
                writer.writeheader()
                writer.writerow({"id": "1", "target": "0.8"})
                writer.writerow({"id": "2", "target": "0.6"})

            with open(pred2, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["id", "target"])
                writer.writeheader()
                writer.writerow({"id": "1", "target": "0.9"})
                writer.writerow({"id": "2", "target": "0.4"})

            predictions = [
                {"run_id": "r1", "branch": "b1", "score": 0.9,
                 "prediction_path": str(pred1)},
                {"run_id": "r2", "branch": "b2", "score": 0.85,
                 "prediction_path": str(pred2)},
            ]

            builder = EnsembleBuilder(working_dir=tmpdir)
            script = builder.generate_ensemble_script(predictions, method="average")

            # Write and run the script
            script_path = Path(tmpdir) / "ensemble.py"
            script_path.write_text(script)

            import subprocess
            import sys
            result = subprocess.run(
                [sys.executable, str(script_path)],
                cwd=tmpdir, capture_output=True, text=True,
            )

            assert result.returncode == 0
            assert "Ensemble written" in result.stdout

            # Check output exists
            output = Path(tmpdir) / "submissions" / "submission.csv"
            assert output.exists()

            # Verify contents
            with open(output) as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            assert len(rows) == 2
            # Weighted average of 0.8 and 0.9 with weights 0.9 and 0.85
            # = (0.8*0.9 + 0.9*0.85) / (0.9+0.85) = (0.72 + 0.765) / 1.75 = 0.8486
            target_1 = float(rows[0]["target"])
            assert 0.84 < target_1 < 0.86

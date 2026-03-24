import tempfile
from pathlib import Path

from comp_agent.models import Hypothesis, Result
from comp_agent.tracker.compare import (
    compute_improvement_rate,
    format_score,
    score_improved,
)
from comp_agent.tracker.db import TrackerDB
from comp_agent.tracker.log import generate_report


class TestTrackerDB:
    def setup_method(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db = TrackerDB(self.tmp.name)

    def teardown_method(self):
        self.db.close()
        Path(self.tmp.name).unlink(missing_ok=True)

    def _make_hypothesis(self, id: str = "h1", **kwargs) -> Hypothesis:
        defaults = dict(
            id=id,
            description="Test hypothesis",
            rationale="Testing",
            expected_improvement=0.05,
            estimated_time_minutes=30,
        )
        defaults.update(kwargs)
        return Hypothesis(**defaults)

    def _make_result(self, hypothesis_id: str = "h1", id: str = "r1",
                     score: float = 0.9, **kwargs) -> Result:
        defaults = dict(
            id=id,
            hypothesis_id=hypothesis_id,
            branch=f"hypothesis/{hypothesis_id}",
            score=score,
            metric="accuracy",
            runtime_seconds=10.0,
            memory_mb=100.0,
            status="success",
        )
        defaults.update(kwargs)
        return Result(**defaults)

    def test_log_and_get_hypothesis(self):
        h = self._make_hypothesis()
        self.db.log_hypothesis(h)
        got = self.db.get_hypothesis("h1")
        assert got is not None
        assert got["description"] == "Test hypothesis"
        assert got["status"] == "pending"

    def test_update_hypothesis_status(self):
        h = self._make_hypothesis()
        self.db.log_hypothesis(h)
        self.db.update_hypothesis_status("h1", "accepted", "r1")
        got = self.db.get_hypothesis("h1")
        assert got["status"] == "accepted"
        assert got["result_run_id"] == "r1"

    def test_log_and_get_run(self):
        h = self._make_hypothesis()
        self.db.log_hypothesis(h)
        r = self._make_result()
        self.db.log_run(r)
        got = self.db.get_run("r1")
        assert got is not None
        assert got["score"] == 0.9
        assert got["status"] == "success"

    def test_get_best_run_maximize(self):
        h1 = self._make_hypothesis(id="h1")
        h2 = self._make_hypothesis(id="h2")
        self.db.log_hypothesis(h1)
        self.db.log_hypothesis(h2)
        self.db.log_run(self._make_result("h1", "r1", 0.8))
        self.db.log_run(self._make_result("h2", "r2", 0.95))
        best = self.db.get_best_run("maximize")
        assert best["id"] == "r2"
        assert best["score"] == 0.95

    def test_get_best_run_minimize(self):
        h1 = self._make_hypothesis(id="h1")
        h2 = self._make_hypothesis(id="h2")
        self.db.log_hypothesis(h1)
        self.db.log_hypothesis(h2)
        self.db.log_run(self._make_result("h1", "r1", 0.8))
        self.db.log_run(self._make_result("h2", "r2", 0.3))
        best = self.db.get_best_run("minimize")
        assert best["id"] == "r2"
        assert best["score"] == 0.3

    def test_get_best_score_no_runs(self):
        assert self.db.get_best_score("maximize") is None

    def test_total_runs(self):
        assert self.db.total_runs() == 0
        h = self._make_hypothesis()
        self.db.log_hypothesis(h)
        self.db.log_run(self._make_result())
        assert self.db.total_runs() == 1

    def test_accepted_rejected_counts(self):
        for i in range(3):
            h = self._make_hypothesis(id=f"h{i}")
            self.db.log_hypothesis(h)
        self.db.update_hypothesis_status("h0", "accepted")
        self.db.update_hypothesis_status("h1", "rejected")
        self.db.update_hypothesis_status("h2", "rejected")
        assert self.db.accepted_count() == 1
        assert self.db.rejected_count() == 2

    def test_pending_hypotheses(self):
        h1 = self._make_hypothesis(id="h1", expected_improvement=0.1)
        h2 = self._make_hypothesis(id="h2", expected_improvement=0.5)
        self.db.log_hypothesis(h1)
        self.db.log_hypothesis(h2)
        pending = self.db.get_pending_hypotheses()
        assert len(pending) == 2
        assert pending[0]["id"] == "h2"  # Higher expected improvement first

    def test_consecutive_failures(self):
        h = self._make_hypothesis()
        self.db.log_hypothesis(h)
        self.db.log_run(self._make_result("h1", "r1", 0.9))
        self.db.log_run(self._make_result("h1", "r2", score=None, status="error"))
        self.db.log_run(self._make_result("h1", "r3", score=None, status="timeout"))
        assert self.db.get_consecutive_failures() == 2

    def test_log_submission(self):
        h = self._make_hypothesis()
        self.db.log_hypothesis(h)
        self.db.log_run(self._make_result())
        self.db.log_submission("r1", local_score=0.9, submission_path="sub.csv")
        assert self.db.submissions_today() >= 1

    def test_log_critique(self):
        self.db.log_critique(
            "Solution is overfitting",
            weaknesses=["no regularization", "too many features"],
            suggestions=["add L2 regularization"],
        )
        critiques = self.db.get_recent_critiques()
        assert len(critiques) == 1
        assert "overfitting" in critiques[0]["content"]


class TestCompare:
    def test_score_improved_maximize(self):
        assert score_improved(0.95, 0.90, "maximize") is True
        assert score_improved(0.85, 0.90, "maximize") is False

    def test_score_improved_minimize(self):
        assert score_improved(0.05, 0.10, "minimize") is True
        assert score_improved(0.15, 0.10, "minimize") is False

    def test_score_improved_no_baseline(self):
        assert score_improved(0.5, None, "maximize") is True

    def test_score_improved_none_score(self):
        assert score_improved(None, 0.5, "maximize") is False

    def test_improvement_rate(self):
        runs = [
            {"status": "success", "score": 0.80},
            {"status": "success", "score": 0.85},
            {"status": "success", "score": 0.90},
        ]
        rate = compute_improvement_rate(runs)
        assert rate > 0

    def test_improvement_rate_insufficient_data(self):
        assert compute_improvement_rate([]) == 0.0
        assert compute_improvement_rate([{"status": "success", "score": 0.8}]) == 0.0

    def test_format_score(self):
        assert format_score(0.9) == "0.900000"
        assert format_score(None) == "N/A"


class TestReport:
    def test_generate_report_empty(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        db = TrackerDB(tmp.name)
        report = generate_report(db, "Test Competition")
        assert "Test Competition" in report
        assert "No successful runs yet" in report
        db.close()
        Path(tmp.name).unlink(missing_ok=True)

    def test_generate_report_with_runs(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        db = TrackerDB(tmp.name)

        h1 = Hypothesis(
            id="h1", description="Baseline XGBoost",
            rationale="Start simple", expected_improvement=0.0,
            estimated_time_minutes=15,
        )
        h2 = Hypothesis(
            id="h2", description="Add target encoding",
            rationale="Improve features", expected_improvement=0.05,
            estimated_time_minutes=30,
        )
        db.log_hypothesis(h1)
        db.log_hypothesis(h2)

        r1 = Result(
            id="r1", hypothesis_id="h1", branch="hypothesis/h1",
            score=0.85, metric="accuracy", runtime_seconds=60.0,
            memory_mb=200.0, status="success",
        )
        r2 = Result(
            id="r2", hypothesis_id="h2", branch="hypothesis/h2",
            score=0.90, metric="accuracy", runtime_seconds=120.0,
            memory_mb=300.0, status="success",
        )
        db.log_run(r1)
        db.log_run(r2)
        db.update_hypothesis_status("h1", "accepted", "r1")
        db.update_hypothesis_status("h2", "accepted", "r2")

        report = generate_report(db, "Test Competition")
        assert "0.900000" in report
        assert "Baseline XGBoost" in report
        assert "Add target encoding" in report
        assert "What Worked" in report

        db.close()
        Path(tmp.name).unlink(missing_ok=True)

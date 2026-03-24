import json
import tempfile
from pathlib import Path

from comp_agent.models import Hypothesis, ProblemSpec, Result


class TestProblemSpec:
    def test_roundtrip_json(self):
        spec = ProblemSpec(
            name="test-comp",
            source="kaggle",
            url="https://kaggle.com/c/test",
            problem_type="classification",
            metric="accuracy",
            metric_direction="maximize",
            rules=["no external data"],
            data_paths=["data/train.csv"],
            target_column="label",
            submission_format="csv with id and label columns",
        )
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        spec.to_json(path)
        loaded = ProblemSpec.from_json(path)

        assert loaded.name == "test-comp"
        assert loaded.source == "kaggle"
        assert loaded.metric_direction == "maximize"
        assert loaded.rules == ["no external data"]
        assert loaded.target_column == "label"
        Path(path).unlink()

    def test_defaults(self):
        spec = ProblemSpec(name="test", source="custom")
        assert spec.problem_type == "classification"
        assert spec.metric == "accuracy"
        assert spec.metric_direction == "maximize"
        assert spec.url is None
        assert spec.rules == []

    def test_time_limit_parsing(self):
        spec = ProblemSpec(
            name="test", source="custom",
            time_limit="2026-04-01T12:00:00",
        )
        dt = spec.get_time_limit()
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 4

    def test_time_limit_none(self):
        spec = ProblemSpec(name="test", source="custom")
        assert spec.get_time_limit() is None


class TestHypothesis:
    def test_creation_with_defaults(self):
        h = Hypothesis(
            description="Add feature X",
            rationale="Should improve score",
            expected_improvement=0.05,
            estimated_time_minutes=30,
        )
        assert h.risk == "medium"
        assert h.strategy_phase == "improve"
        assert len(h.id) == 8

    def test_roundtrip_json(self):
        h = Hypothesis(
            id="abc12345",
            description="Test hypothesis",
            rationale="Testing",
            expected_improvement=0.1,
            estimated_time_minutes=15,
            risk="low",
            dependencies=["dep1"],
            strategy_phase="baseline",
            code_sketch="# do something",
        )
        json_str = h.to_json()
        loaded = Hypothesis.from_json(json_str)
        assert loaded.id == "abc12345"
        assert loaded.description == "Test hypothesis"
        assert loaded.dependencies == ["dep1"]

    def test_to_dict(self):
        h = Hypothesis(
            description="test",
            rationale="test",
            expected_improvement=0.1,
            estimated_time_minutes=10,
        )
        d = h.to_dict()
        assert "description" in d
        assert "id" in d


class TestResult:
    def test_score_improved_maximize(self):
        r = Result(
            hypothesis_id="h1", branch="test", score=0.95,
            metric="accuracy", runtime_seconds=10.0, memory_mb=100.0,
            status="success",
        )
        assert r.score_improved(0.90, "maximize") is True
        assert r.score_improved(0.95, "maximize") is False
        assert r.score_improved(0.99, "maximize") is False

    def test_score_improved_minimize(self):
        r = Result(
            hypothesis_id="h1", branch="test", score=0.10,
            metric="rmse", runtime_seconds=10.0, memory_mb=100.0,
            status="success",
        )
        assert r.score_improved(0.15, "minimize") is True
        assert r.score_improved(0.10, "minimize") is False
        assert r.score_improved(0.05, "minimize") is False

    def test_score_improved_no_baseline(self):
        r = Result(
            hypothesis_id="h1", branch="test", score=0.5,
            metric="accuracy", runtime_seconds=10.0, memory_mb=100.0,
            status="success",
        )
        assert r.score_improved(None, "maximize") is True

    def test_score_improved_error_status(self):
        r = Result(
            hypothesis_id="h1", branch="test", score=None,
            metric="accuracy", runtime_seconds=10.0, memory_mb=100.0,
            status="error", error_message="OOM",
        )
        assert r.score_improved(0.5, "maximize") is False

    def test_score_improved_none_score(self):
        r = Result(
            hypothesis_id="h1", branch="test", score=None,
            metric="accuracy", runtime_seconds=10.0, memory_mb=100.0,
            status="success",
        )
        assert r.score_improved(0.5, "maximize") is False

    def test_roundtrip_json(self):
        r = Result(
            id="r1", hypothesis_id="h1", branch="test", score=0.9,
            metric="accuracy", runtime_seconds=30.0, memory_mb=512.0,
            status="success", stdout="done", stderr="",
        )
        json_str = r.to_json()
        loaded = Result.from_json(json_str)
        assert loaded.id == "r1"
        assert loaded.score == 0.9
        assert loaded.status == "success"

import tempfile
from pathlib import Path

import yaml

from comp_agent.parser.extractors.custom import extract_from_yaml
from comp_agent.parser.extractors.kaggle import _infer_direction
from comp_agent.parser.parse import detect_source, _extract_kaggle_slug


class TestCustomExtractor:
    def test_extract_from_yaml(self):
        data = {
            "name": "test-competition",
            "source": "custom",
            "problem_type": "regression",
            "metric": "rmse",
            "metric_direction": "minimize",
            "target_column": "price",
            "submission_format": "csv with id and price columns",
            "rules": ["no external data"],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(data, f)
            path = f.name

        spec = extract_from_yaml(path)
        assert spec.name == "test-competition"
        assert spec.problem_type == "regression"
        assert spec.metric == "rmse"
        assert spec.metric_direction == "minimize"
        assert spec.rules == ["no external data"]
        Path(path).unlink()

    def test_extract_missing_required_field(self):
        data = {"problem_type": "classification"}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(data, f)
            path = f.name

        try:
            extract_from_yaml(path)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "name" in str(e)
        finally:
            Path(path).unlink()


class TestKaggleHelpers:
    def test_infer_direction_minimize(self):
        assert _infer_direction("RMSE") == "minimize"
        assert _infer_direction("Mean Absolute Error") == "minimize"
        assert _infer_direction("log_loss") == "minimize"

    def test_infer_direction_maximize(self):
        assert _infer_direction("AUC") == "maximize"
        assert _infer_direction("accuracy") == "maximize"
        assert _infer_direction("F1") == "maximize"


class TestDetectSource:
    def test_detect_kaggle(self):
        assert detect_source("https://www.kaggle.com/competitions/titanic") == "kaggle"

    def test_detect_devpost(self):
        assert detect_source("https://devpost.com/hackathons/something") == "hackathon"

    def test_detect_yaml_file(self):
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
            path = f.name
        assert detect_source(path) == "custom"
        Path(path).unlink()

    def test_detect_janestreet(self):
        assert detect_source("https://www.janestreet.com/puzzles/something") == "puzzle"


class TestExtractKaggleSlug:
    def test_from_url(self):
        assert _extract_kaggle_slug("https://www.kaggle.com/competitions/titanic") == "titanic"
        assert _extract_kaggle_slug("https://www.kaggle.com/competitions/titanic/") == "titanic"

    def test_from_slug(self):
        assert _extract_kaggle_slug("titanic") == "titanic"

from comp_agent.models import Hypothesis, ProblemSpec
from comp_agent.strategist.classify import (
    classify_problem,
    get_phase_strategies,
)
from comp_agent.strategist.hypothesize import HypothesisGenerator
from comp_agent.strategist.prioritize import prioritize


class TestClassify:
    def test_classification_maps_to_tabular(self):
        spec = ProblemSpec(name="test", source="kaggle", problem_type="classification")
        assert classify_problem(spec) == "tabular_ml"

    def test_regression_maps_to_tabular(self):
        spec = ProblemSpec(name="test", source="kaggle", problem_type="regression")
        assert classify_problem(spec) == "tabular_ml"

    def test_combinatorial(self):
        spec = ProblemSpec(name="test", source="puzzle", problem_type="combinatorial")
        assert classify_problem(spec) == "combinatorial"

    def test_mathematical(self):
        spec = ProblemSpec(name="test", source="puzzle", problem_type="mathematical")
        assert classify_problem(spec) == "math_puzzle"

    def test_systems(self):
        spec = ProblemSpec(name="test", source="hackathon", problem_type="systems")
        assert classify_problem(spec) == "systems"

    def test_unknown_defaults_to_tabular(self):
        spec = ProblemSpec(name="test", source="custom", problem_type="unknown_type")
        assert classify_problem(spec) == "tabular_ml"


class TestPhaseStrategies:
    def test_tabular_baseline(self):
        strategies = get_phase_strategies("tabular_ml", "baseline")
        assert len(strategies) > 0
        assert any("XGBoost" in s for s in strategies)

    def test_combinatorial_improve(self):
        strategies = get_phase_strategies("combinatorial", "improve")
        assert any("annealing" in s.lower() for s in strategies)

    def test_unknown_family_falls_back(self):
        strategies = get_phase_strategies("nonexistent", "improve")
        assert len(strategies) > 0  # Falls back to tabular_ml


class TestPrioritize:
    def test_higher_efficiency_ranked_first(self):
        h1 = Hypothesis(
            description="Low efficiency",
            rationale="test", expected_improvement=0.01,
            estimated_time_minutes=60, risk="medium",
        )
        h2 = Hypothesis(
            description="High efficiency",
            rationale="test", expected_improvement=0.10,
            estimated_time_minutes=10, risk="low",
        )
        ranked = prioritize([h1, h2], time_budget_hours=24)
        assert ranked[0].description == "High efficiency"

    def test_risk_affects_ranking(self):
        h_low = Hypothesis(
            description="Low risk",
            rationale="test", expected_improvement=0.05,
            estimated_time_minutes=30, risk="low",
        )
        h_high = Hypothesis(
            description="High risk",
            rationale="test", expected_improvement=0.05,
            estimated_time_minutes=30, risk="high",
        )
        ranked = prioritize([h_high, h_low], time_budget_hours=24)
        assert ranked[0].description == "Low risk"

    def test_rejected_descriptions_penalized(self):
        h1 = Hypothesis(
            description="Previously rejected idea",
            rationale="test", expected_improvement=0.10,
            estimated_time_minutes=10, risk="low",
        )
        h2 = Hypothesis(
            description="Fresh idea",
            rationale="test", expected_improvement=0.08,
            estimated_time_minutes=10, risk="low",
        )
        ranked = prioritize(
            [h1, h2], time_budget_hours=24,
            rejected_descriptions=["Previously rejected idea"],
        )
        assert ranked[0].description == "Fresh idea"

    def test_time_feasibility_factor(self):
        h_fast = Hypothesis(
            description="Quick win",
            rationale="test", expected_improvement=0.03,
            estimated_time_minutes=10, risk="low",
        )
        h_slow = Hypothesis(
            description="Long shot",
            rationale="test", expected_improvement=0.05,
            estimated_time_minutes=120, risk="low",
        )
        # With only 1 hour budget, 120-minute hypothesis should be penalized
        ranked = prioritize([h_slow, h_fast], time_budget_hours=1)
        assert ranked[0].description == "Quick win"


class TestPlaybookLoading:
    def test_load_tabular_playbook(self):
        gen = HypothesisGenerator()
        playbook = gen._load_playbook("tabular_ml")
        assert "XGBoost" in playbook
        assert "Baseline" in playbook

    def test_load_nonexistent_playbook(self):
        gen = HypothesisGenerator()
        playbook = gen._load_playbook("nonexistent_family")
        assert playbook == ""

    def test_parse_hypotheses_json_array(self):
        gen = HypothesisGenerator()
        text = """[
            {
                "description": "Add target encoding",
                "rationale": "Improves categorical handling",
                "expected_improvement": 0.05,
                "estimated_time_minutes": 30,
                "risk": "low",
                "strategy_phase": "improve",
                "code_sketch": "# encode targets"
            }
        ]"""
        hypotheses = gen._parse_hypotheses(text)
        assert len(hypotheses) == 1
        assert hypotheses[0].description == "Add target encoding"

    def test_parse_hypotheses_with_code_fences(self):
        gen = HypothesisGenerator()
        text = """```json
[{"description": "Test", "rationale": "test", "expected_improvement": 0.1, "estimated_time_minutes": 10, "risk": "low", "strategy_phase": "improve", "code_sketch": ""}]
```"""
        hypotheses = gen._parse_hypotheses(text)
        assert len(hypotheses) == 1

    def test_parse_hypotheses_fallback(self):
        gen = HypothesisGenerator()
        hypotheses = gen._parse_hypotheses("This is not valid JSON at all")
        assert len(hypotheses) == 1
        assert "parsing failed" in hypotheses[0].description.lower()

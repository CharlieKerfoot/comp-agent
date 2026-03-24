from datetime import datetime, timedelta, timezone

from comp_agent.controller.budget import SubmissionBudget, TimeBudget
from comp_agent.controller.policy import select_phase, should_critique


class TestSelectPhase:
    def test_no_history_returns_baseline(self):
        assert select_phase(48.0, []) == "baseline"

    def test_no_successful_runs_returns_baseline(self):
        history = [{"status": "error", "score": None}]
        assert select_phase(48.0, history) == "baseline"

    def test_plenty_of_time_returns_improve(self):
        history = [
            {"status": "success", "score": 0.8},
            {"status": "success", "score": 0.85},
        ]
        assert select_phase(30.0, history) == "improve"

    def test_medium_time_returns_ensemble(self):
        history = [{"status": "success", "score": 0.9}]
        assert select_phase(10.0, history) == "ensemble"

    def test_low_time_returns_polish(self):
        history = [{"status": "success", "score": 0.9}]
        assert select_phase(3.0, history) == "polish"

    def test_very_low_time_returns_submit(self):
        history = [{"status": "success", "score": 0.9}]
        assert select_phase(1.5, history) == "submit"

    def test_consecutive_failures_returns_pivot(self):
        history = [
            {"status": "success", "score": 0.8},
            {"status": "error", "score": None},
            {"status": "error", "score": None},
            {"status": "error", "score": None},
            {"status": "error", "score": None},
            {"status": "error", "score": None},
        ]
        assert select_phase(30.0, history, max_consecutive_failures=5) == "pivot"

    def test_infinite_time_returns_improve(self):
        history = [{"status": "success", "score": 0.8}]
        assert select_phase(float("inf"), history) == "improve"


class TestShouldCritique:
    def test_critique_at_interval(self):
        assert should_critique(5, 5) is True
        assert should_critique(10, 5) is True

    def test_no_critique_between_intervals(self):
        assert should_critique(3, 5) is False
        assert should_critique(7, 5) is False

    def test_no_critique_at_zero(self):
        assert should_critique(0, 5) is False


class TestTimeBudget:
    def test_budget_from_hours(self):
        budget = TimeBudget(budget_hours=24)
        assert budget.remaining_hours() > 23.9
        assert budget.expired() is False

    def test_budget_from_deadline(self):
        future = datetime.now(timezone.utc) + timedelta(hours=10)
        budget = TimeBudget(deadline=future)
        assert 9.9 < budget.remaining_hours() < 10.1
        assert budget.expired() is False

    def test_expired_deadline(self):
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        budget = TimeBudget(deadline=past)
        assert budget.remaining_hours() == 0.0
        assert budget.expired() is True

    def test_no_deadline(self):
        budget = TimeBudget()
        assert budget.remaining_hours() == float("inf")
        assert budget.expired() is False


class TestSubmissionBudget:
    def test_no_limit(self):
        budget = SubmissionBudget(daily_limit=None)
        # Can always submit with no limit
        # (Would need a tracker mock, just test the logic)
        assert budget.daily_limit is None

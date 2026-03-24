from __future__ import annotations

from datetime import datetime, timezone

from comp_agent.tracker.db import TrackerDB


class TimeBudget:
    def __init__(self, deadline: datetime | None = None,
                 budget_hours: float | None = None):
        self.start_time = datetime.now(timezone.utc)
        if deadline:
            self.deadline = deadline
        elif budget_hours:
            from datetime import timedelta
            self.deadline = self.start_time + timedelta(hours=budget_hours)
        else:
            self.deadline = None

    def remaining_hours(self) -> float:
        if self.deadline is None:
            return float("inf")
        delta = self.deadline - datetime.now(timezone.utc)
        return max(0.0, delta.total_seconds() / 3600)

    def expired(self) -> bool:
        if self.deadline is None:
            return False
        return datetime.now(timezone.utc) >= self.deadline

    def estimate_runs_remaining(self, tracker: TrackerDB) -> int:
        runs = tracker.get_all_runs()
        if not runs:
            return 100  # No data yet, assume plenty

        avg_runtime = sum(r["runtime_seconds"] for r in runs) / len(runs)
        if avg_runtime <= 0:
            return 100

        remaining_seconds = self.remaining_hours() * 3600
        return max(0, int(remaining_seconds / avg_runtime))


class SubmissionBudget:
    def __init__(self, daily_limit: int | None = None,
                 reserved_per_day: int = 1):
        self.daily_limit = daily_limit
        self.reserved_per_day = reserved_per_day

    def can_submit(self, tracker: TrackerDB) -> bool:
        if self.daily_limit is None:
            return True
        used = tracker.submissions_today()
        available = self.daily_limit - self.reserved_per_day
        return used < available

    def remaining_today(self, tracker: TrackerDB) -> int | None:
        if self.daily_limit is None:
            return None
        used = tracker.submissions_today()
        return max(0, self.daily_limit - self.reserved_per_day - used)

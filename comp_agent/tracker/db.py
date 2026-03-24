from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from comp_agent.models import Hypothesis, Result


class TrackerDB:
    def __init__(self, db_path: str = "tracker.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._create_tables()

    def _create_tables(self) -> None:
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS hypotheses (
                id TEXT PRIMARY KEY,
                description TEXT NOT NULL,
                rationale TEXT NOT NULL,
                expected_improvement REAL,
                estimated_time_minutes INTEGER,
                risk TEXT,
                dependencies TEXT,  -- JSON array
                strategy_phase TEXT,
                code_sketch TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                parent_run_id TEXT,
                result_run_id TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                hypothesis_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                branch TEXT NOT NULL,
                score REAL,
                metric TEXT NOT NULL,
                runtime_seconds REAL,
                memory_mb REAL,
                status TEXT NOT NULL,
                error_message TEXT,
                code_diff TEXT,
                stdout TEXT,
                stderr TEXT,
                notes TEXT,
                FOREIGN KEY (hypothesis_id) REFERENCES hypotheses(id)
            );

            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                local_score REAL,
                leaderboard_score REAL,
                submission_path TEXT,
                notes TEXT,
                FOREIGN KEY (run_id) REFERENCES runs(id)
            );

            CREATE TABLE IF NOT EXISTS critiques (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                run_id TEXT,
                content TEXT NOT NULL,
                weaknesses TEXT,  -- JSON array
                suggestions TEXT,  -- JSON array
                FOREIGN KEY (run_id) REFERENCES runs(id)
            );
        """)
        self.conn.commit()

    def log_hypothesis(self, h: Hypothesis, parent_run_id: str | None = None) -> None:
        import json
        self.conn.execute(
            """INSERT INTO hypotheses
               (id, description, rationale, expected_improvement,
                estimated_time_minutes, risk, dependencies, strategy_phase,
                code_sketch, status, parent_run_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
            (
                h.id, h.description, h.rationale, h.expected_improvement,
                h.estimated_time_minutes, h.risk, json.dumps(h.dependencies),
                h.strategy_phase, h.code_sketch, parent_run_id,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self.conn.commit()

    def update_hypothesis_status(self, hypothesis_id: str, status: str,
                                  result_run_id: str | None = None) -> None:
        if result_run_id:
            self.conn.execute(
                "UPDATE hypotheses SET status = ?, result_run_id = ? WHERE id = ?",
                (status, result_run_id, hypothesis_id),
            )
        else:
            self.conn.execute(
                "UPDATE hypotheses SET status = ? WHERE id = ?",
                (status, hypothesis_id),
            )
        self.conn.commit()

    def log_run(self, r: Result) -> None:
        self.conn.execute(
            """INSERT INTO runs
               (id, hypothesis_id, timestamp, branch, score, metric,
                runtime_seconds, memory_mb, status, error_message,
                code_diff, stdout, stderr)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                r.id, r.hypothesis_id, r.timestamp, r.branch, r.score,
                r.metric, r.runtime_seconds, r.memory_mb, r.status,
                r.error_message, r.code_diff, r.stdout, r.stderr,
            ),
        )
        self.conn.commit()

    def log_submission(self, run_id: str, local_score: float | None = None,
                       leaderboard_score: float | None = None,
                       submission_path: str | None = None,
                       notes: str | None = None) -> None:
        self.conn.execute(
            """INSERT INTO submissions
               (run_id, timestamp, local_score, leaderboard_score,
                submission_path, notes)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                run_id, datetime.now(timezone.utc).isoformat(),
                local_score, leaderboard_score, submission_path, notes,
            ),
        )
        self.conn.commit()

    def log_critique(self, content: str, run_id: str | None = None,
                     weaknesses: list[str] | None = None,
                     suggestions: list[str] | None = None) -> None:
        import json
        self.conn.execute(
            """INSERT INTO critiques
               (timestamp, run_id, content, weaknesses, suggestions)
               VALUES (?, ?, ?, ?, ?)""",
            (
                datetime.now(timezone.utc).isoformat(), run_id, content,
                json.dumps(weaknesses) if weaknesses else None,
                json.dumps(suggestions) if suggestions else None,
            ),
        )
        self.conn.commit()

    def get_best_run(self, direction: str = "maximize") -> dict | None:
        order = "DESC" if direction == "maximize" else "ASC"
        row = self.conn.execute(
            f"""SELECT * FROM runs
                WHERE status = 'success' AND score IS NOT NULL
                ORDER BY score {order} LIMIT 1"""
        ).fetchone()
        return dict(row) if row else None

    def get_best_score(self, direction: str = "maximize") -> float | None:
        run = self.get_best_run(direction)
        return run["score"] if run else None

    def get_all_runs(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM runs ORDER BY timestamp ASC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_accepted_runs(self) -> list[dict]:
        rows = self.conn.execute(
            """SELECT r.* FROM runs r
               JOIN hypotheses h ON r.hypothesis_id = h.id
               WHERE h.status = 'accepted' AND r.status = 'success'
               ORDER BY r.score DESC"""
        ).fetchall()
        return [dict(r) for r in rows]

    def get_rejected_runs(self) -> list[dict]:
        rows = self.conn.execute(
            """SELECT r.* FROM runs r
               JOIN hypotheses h ON r.hypothesis_id = h.id
               WHERE h.status = 'rejected'
               ORDER BY r.timestamp DESC"""
        ).fetchall()
        return [dict(r) for r in rows]

    def get_pending_hypotheses(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM hypotheses WHERE status = 'pending' ORDER BY expected_improvement DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_hypothesis(self, hypothesis_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM hypotheses WHERE id = ?", (hypothesis_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_run(self, run_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM runs WHERE id = ?", (run_id,)
        ).fetchone()
        return dict(row) if row else None

    def total_runs(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) as cnt FROM runs").fetchone()
        return row["cnt"]

    def accepted_count(self) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM hypotheses WHERE status = 'accepted'"
        ).fetchone()
        return row["cnt"]

    def rejected_count(self) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM hypotheses WHERE status = 'rejected'"
        ).fetchone()
        return row["cnt"]

    def submissions_today(self) -> int:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        row = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM submissions WHERE timestamp LIKE ?",
            (f"{today}%",),
        ).fetchone()
        return row["cnt"]

    def get_recent_critiques(self, limit: int = 3) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM critiques ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_consecutive_failures(self) -> int:
        rows = self.conn.execute(
            "SELECT status FROM runs ORDER BY timestamp DESC"
        ).fetchall()
        count = 0
        for row in rows:
            if row["status"] != "success":
                count += 1
            else:
                break
        return count

    def history(self) -> list[dict]:
        return self.get_all_runs()

    def cleanup_stale_hypotheses(self, timeout_seconds: int = 3600) -> int:
        cutoff = datetime.now(timezone.utc).isoformat()
        # Mark any hypothesis stuck in 'running' as 'error'
        cursor = self.conn.execute(
            """UPDATE hypotheses SET status = 'error'
               WHERE status = 'running'
               AND created_at < ?""",
            (cutoff,),
        )
        self.conn.commit()
        return cursor.rowcount

    def close(self) -> None:
        self.conn.close()

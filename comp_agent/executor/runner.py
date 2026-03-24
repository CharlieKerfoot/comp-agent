from __future__ import annotations

import resource
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path

from comp_agent.models import Result


class CodeRunner:
    def __init__(self, timeout_seconds: int = 1800, working_dir: str = "."):
        self.timeout_seconds = timeout_seconds
        self.working_dir = Path(working_dir).resolve()

    def run(self, command: list[str], hypothesis_id: str, branch: str,
            metric: str) -> Result:
        start_time = time.monotonic()
        try:
            proc = subprocess.run(
                command,
                cwd=self.working_dir,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
            elapsed = time.monotonic() - start_time
            # Try to get memory usage from the process
            memory_mb = self._get_memory_mb()

            if proc.returncode != 0:
                return Result(
                    hypothesis_id=hypothesis_id,
                    branch=branch,
                    score=None,
                    metric=metric,
                    runtime_seconds=elapsed,
                    memory_mb=memory_mb,
                    status="error",
                    error_message=proc.stderr[-2000:] if proc.stderr else "Non-zero exit code",
                    stdout=proc.stdout[-5000:] if proc.stdout else "",
                    stderr=proc.stderr[-5000:] if proc.stderr else "",
                )

            # Try to extract score from stdout
            score = self._extract_score(proc.stdout)

            return Result(
                hypothesis_id=hypothesis_id,
                branch=branch,
                score=score,
                metric=metric,
                runtime_seconds=elapsed,
                memory_mb=memory_mb,
                status="success",
                stdout=proc.stdout[-5000:] if proc.stdout else "",
                stderr=proc.stderr[-5000:] if proc.stderr else "",
            )

        except subprocess.TimeoutExpired:
            elapsed = time.monotonic() - start_time
            return Result(
                hypothesis_id=hypothesis_id,
                branch=branch,
                score=None,
                metric=metric,
                runtime_seconds=elapsed,
                memory_mb=0.0,
                status="timeout",
                error_message=f"Execution timed out after {self.timeout_seconds}s",
            )
        except Exception as e:
            elapsed = time.monotonic() - start_time
            return Result(
                hypothesis_id=hypothesis_id,
                branch=branch,
                score=None,
                metric=metric,
                runtime_seconds=elapsed,
                memory_mb=0.0,
                status="error",
                error_message=str(e),
            )

    def _extract_score(self, stdout: str) -> float | None:
        """Extract score from stdout. Looks for 'SCORE: <number>' pattern."""
        for line in reversed(stdout.strip().split("\n")):
            line = line.strip()
            if line.upper().startswith("SCORE:"):
                try:
                    return float(line.split(":", 1)[1].strip())
                except ValueError:
                    continue
        return None

    def _get_memory_mb(self) -> float:
        try:
            usage = resource.getrusage(resource.RUSAGE_CHILDREN)
            return usage.ru_maxrss / (1024 * 1024)  # macOS reports in bytes
        except Exception:
            return 0.0

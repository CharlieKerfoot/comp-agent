from __future__ import annotations

import resource
import subprocess
import sys
import threading
import time
from pathlib import Path

from comp_agent.models import Result


def solution_command(script: str = "solution/train.py") -> list[str]:
    """Command to execute a solution script.

    Uses `uv run --script` so PEP 723 inline metadata at the top of the script
    drives dependency resolution automatically — no manual venv setup required.
    Falls back to the workspace .venv python, then system python3, if uv is
    missing.
    """
    import shutil

    if shutil.which("uv"):
        return ["uv", "run", "--script", script]

    venv = Path(".venv/bin/python")
    if venv.exists():
        return [str(venv.resolve()), script]

    return [shutil.which("python3") or "python3", script]


# Backwards-compat alias for any older call sites.
def workspace_python() -> str:
    import shutil
    venv = Path(".venv/bin/python")
    if venv.exists():
        return str(venv.resolve())
    return shutil.which("python3") or "python3"


class CodeRunner:
    def __init__(self, timeout_seconds: int = 1800, working_dir: str = "."):
        self.timeout_seconds = timeout_seconds
        self.working_dir = Path(working_dir).resolve()

    def run(self, command: list[str], hypothesis_id: str, branch: str,
            metric: str) -> Result:
        """Run `command`, streaming each stdout/stderr line to the terminal.

        Lines are echoed with a `  | ` prefix so the user can tell at a glance
        whether the hypothesis is making progress or has hung. Full output is
        still captured for the Result.
        """
        start_time = time.monotonic()
        try:
            proc = subprocess.Popen(
                command,
                cwd=self.working_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # line-buffered
            )
        except Exception as e:
            elapsed = time.monotonic() - start_time
            return Result(
                hypothesis_id=hypothesis_id, branch=branch, score=None,
                metric=metric, runtime_seconds=elapsed, memory_mb=0.0,
                status="error", error_message=str(e),
            )

        stdout_buf: list[str] = []
        stderr_buf: list[str] = []
        last_output_at = [time.monotonic()]
        done = threading.Event()

        def pump(stream, buf: list[str], prefix: str):
            for line in iter(stream.readline, ""):
                buf.append(line)
                last_output_at[0] = time.monotonic()
                sys.stdout.write(f"  {prefix} {line}" if line.endswith("\n")
                                 else f"  {prefix} {line}\n")
                sys.stdout.flush()
            stream.close()

        t_out = threading.Thread(target=pump, args=(proc.stdout, stdout_buf, "|"))
        t_err = threading.Thread(target=pump, args=(proc.stderr, stderr_buf, "!"))
        t_out.start()
        t_err.start()

        # Heartbeat so the user can distinguish "still working" from "hung".
        def heartbeat():
            while not done.is_set():
                time.sleep(5)
                if done.is_set():
                    break
                idle = time.monotonic() - last_output_at[0]
                if idle >= 30:
                    elapsed = time.monotonic() - start_time
                    sys.stdout.write(
                        f"  . still running ({elapsed:.0f}s elapsed, "
                        f"{idle:.0f}s since last output)\n"
                    )
                    sys.stdout.flush()
                    last_output_at[0] = time.monotonic()

        hb = threading.Thread(target=heartbeat, daemon=True)
        hb.start()

        try:
            returncode = proc.wait(timeout=self.timeout_seconds)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            done.set()
            t_out.join(timeout=2)
            t_err.join(timeout=2)
            elapsed = time.monotonic() - start_time
            return Result(
                hypothesis_id=hypothesis_id, branch=branch, score=None,
                metric=metric, runtime_seconds=elapsed, memory_mb=0.0,
                status="timeout",
                error_message=f"Execution timed out after {self.timeout_seconds}s",
                stdout="".join(stdout_buf)[-5000:],
                stderr="".join(stderr_buf)[-5000:],
            )

        done.set()
        t_out.join()
        t_err.join()

        elapsed = time.monotonic() - start_time
        stdout = "".join(stdout_buf)
        stderr = "".join(stderr_buf)
        memory_mb = self._get_memory_mb()

        if returncode != 0:
            return Result(
                hypothesis_id=hypothesis_id, branch=branch, score=None,
                metric=metric, runtime_seconds=elapsed, memory_mb=memory_mb,
                status="error",
                error_message=stderr[-2000:] if stderr else "Non-zero exit code",
                stdout=stdout[-5000:], stderr=stderr[-5000:],
            )

        return Result(
            hypothesis_id=hypothesis_id, branch=branch,
            score=self._extract_score(stdout), metric=metric,
            runtime_seconds=elapsed, memory_mb=memory_mb,
            status="success",
            stdout=stdout[-5000:], stderr=stderr[-5000:],
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

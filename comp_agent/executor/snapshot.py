from __future__ import annotations

import subprocess
from pathlib import Path


class GitSnapshot:
    def __init__(self, repo_path: str = "."):
        self.repo_path = Path(repo_path).resolve()

    def _run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=check,
        )

    def current_branch(self) -> str:
        result = self._run("branch", "--show-current")
        return result.stdout.strip()

    def branch_exists(self, branch: str) -> bool:
        result = self._run("rev-parse", "--verify", branch, check=False)
        return result.returncode == 0

    def create_branch(self, hypothesis_id: str) -> str:
        branch_name = f"hypothesis/{hypothesis_id}"
        self._run("checkout", "-b", branch_name)
        return branch_name

    def checkout(self, branch: str) -> None:
        result = self._run("checkout", branch, check=False)
        if result.returncode != 0:
            # Stash any uncommitted work from a failed run and retry.
            self._run("stash", "push", "-u", "-m", "compete-auto-stash",
                      check=False)
            self._run("checkout", branch, check=False)

    def commit_snapshot(self, hypothesis_id: str, message: str) -> str:
        self._run("add", "-A")
        result = self._run(
            "commit", "-m", f"[{hypothesis_id}] {message}",
            check=False,
        )
        if result.returncode != 0 and "nothing to commit" in result.stdout:
            return ""
        # Return commit hash
        hash_result = self._run("rev-parse", "HEAD")
        return hash_result.stdout.strip()

    def get_diff(self, base: str = "main") -> str:
        current = self.current_branch()
        result = self._run("diff", f"{base}...{current}", check=False)
        return result.stdout

    def merge_to_main(self, branch: str) -> tuple[bool, str]:
        original = self.current_branch()
        try:
            self._run("checkout", "main")
            result = self._run("merge", branch, "--no-ff",
                               "-m", f"Merge {branch}", check=False)
            if result.returncode != 0:
                # Merge conflict - abort and return to original branch
                self._run("merge", "--abort", check=False)
                self._run("checkout", original, check=False)
                return False, result.stderr
            return True, ""
        except Exception as e:
            self._run("checkout", original, check=False)
            return False, str(e)

    def rebase_onto_main(self, branch: str) -> tuple[bool, str]:
        try:
            self._run("checkout", branch)
            result = self._run("rebase", "main", check=False)
            if result.returncode != 0:
                self._run("rebase", "--abort", check=False)
                return False, result.stderr
            return True, ""
        except Exception as e:
            return False, str(e)

    def list_hypothesis_branches(self) -> list[str]:
        result = self._run("branch", "--list", "hypothesis/*")
        branches = []
        for line in result.stdout.strip().split("\n"):
            line = line.strip().lstrip("* ")
            if line:
                branches.append(line)
        return branches

    def get_commit_log(self, branch: str, max_count: int = 5) -> str:
        result = self._run(
            "log", branch, f"--max-count={max_count}",
            "--oneline", check=False,
        )
        return result.stdout.strip()

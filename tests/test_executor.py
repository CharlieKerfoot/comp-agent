import os
import subprocess
import sys
import tempfile
from pathlib import Path

from comp_agent.executor.runner import CodeRunner
from comp_agent.executor.snapshot import GitSnapshot
from comp_agent.executor.validate import OutputValidator


class TestCodeRunner:
    def test_successful_run_with_score(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            script = Path(tmpdir) / "run.py"
            script.write_text('print("training...")\nprint("SCORE: 0.95")\n')
            runner = CodeRunner(timeout_seconds=30, working_dir=tmpdir)
            result = runner.run(
                [sys.executable, str(script)],
                hypothesis_id="h1", branch="test", metric="accuracy",
            )
            assert result.status == "success"
            assert result.score == 0.95
            assert result.runtime_seconds > 0

    def test_run_with_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            script = Path(tmpdir) / "run.py"
            script.write_text('raise ValueError("boom")\n')
            runner = CodeRunner(timeout_seconds=30, working_dir=tmpdir)
            result = runner.run(
                [sys.executable, str(script)],
                hypothesis_id="h1", branch="test", metric="accuracy",
            )
            assert result.status == "error"
            assert result.score is None
            assert "boom" in (result.error_message or "")

    def test_run_with_timeout(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            script = Path(tmpdir) / "run.py"
            script.write_text('import time; time.sleep(60)\n')
            runner = CodeRunner(timeout_seconds=1, working_dir=tmpdir)
            result = runner.run(
                [sys.executable, str(script)],
                hypothesis_id="h1", branch="test", metric="accuracy",
            )
            assert result.status == "timeout"
            assert result.score is None

    def test_run_no_score_in_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            script = Path(tmpdir) / "run.py"
            script.write_text('print("done")\n')
            runner = CodeRunner(timeout_seconds=30, working_dir=tmpdir)
            result = runner.run(
                [sys.executable, str(script)],
                hypothesis_id="h1", branch="test", metric="accuracy",
            )
            assert result.status == "success"
            assert result.score is None

    def test_extract_score_various_formats(self):
        runner = CodeRunner()
        assert runner._extract_score("SCORE: 0.95") == 0.95
        assert runner._extract_score("Score: 0.123") == 0.123
        assert runner._extract_score("some output\nSCORE: 0.5\n") == 0.5
        assert runner._extract_score("no score here") is None


class TestOutputValidator:
    def test_validate_existing_csv(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("id,label\n1,0\n2,1\n")
            path = f.name

        validator = OutputValidator()
        valid, msg = validator.validate(path, "csv with id and label columns")
        assert valid is True
        assert "2 columns" in msg
        Path(path).unlink()

    def test_validate_missing_file(self):
        validator = OutputValidator()
        valid, msg = validator.validate("/nonexistent/file.csv", "csv")
        assert valid is False
        assert "not found" in msg

    def test_validate_empty_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            path = f.name

        validator = OutputValidator()
        valid, msg = validator.validate(path, "csv")
        assert valid is False
        assert "empty" in msg
        Path(path).unlink()

    def test_validate_csv_header_only(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("id,label\n")
            path = f.name

        validator = OutputValidator()
        valid, msg = validator.validate(path, "csv")
        assert valid is False
        assert "no data rows" in msg
        Path(path).unlink()

    def test_validate_non_csv_format(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("some output\n")
            path = f.name

        validator = OutputValidator()
        valid, msg = validator.validate(path, "text file with predictions")
        assert valid is True
        Path(path).unlink()


class TestGitSnapshot:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        subprocess.run(["git", "init"], cwd=self.tmpdir, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "main"], cwd=self.tmpdir, capture_output=True)
        # Create initial commit
        Path(self.tmpdir, "README.md").write_text("# Test\n")
        subprocess.run(["git", "add", "."], cwd=self.tmpdir, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=self.tmpdir, capture_output=True,
            env={**os.environ, "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "test@test.com",
                 "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "test@test.com"},
        )
        self.git = GitSnapshot(self.tmpdir)

    def test_current_branch(self):
        assert self.git.current_branch() == "main"

    def test_create_branch(self):
        branch = self.git.create_branch("h1")
        assert branch == "hypothesis/h1"
        assert self.git.current_branch() == "hypothesis/h1"

    def test_branch_exists(self):
        assert self.git.branch_exists("main") is True
        assert self.git.branch_exists("nonexistent") is False

    def test_commit_snapshot(self):
        self.git.create_branch("h1")
        Path(self.tmpdir, "solution.py").write_text("print('hello')\n")
        sha = self.git.commit_snapshot("h1", "add solution")
        assert len(sha) > 0

    def test_merge_to_main(self):
        self.git.create_branch("h1")
        Path(self.tmpdir, "feature.py").write_text("# feature\n")
        env = {**os.environ, "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "test@test.com",
               "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "test@test.com"}
        subprocess.run(["git", "add", "."], cwd=self.tmpdir, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat"], cwd=self.tmpdir, capture_output=True, env=env)
        success, err = self.git.merge_to_main("hypothesis/h1")
        assert success is True
        assert self.git.current_branch() == "main"

    def test_list_hypothesis_branches(self):
        self.git.create_branch("h1")
        self.git.checkout("main")
        self.git.create_branch("h2")
        self.git.checkout("main")
        branches = self.git.list_hypothesis_branches()
        assert "hypothesis/h1" in branches
        assert "hypothesis/h2" in branches

    def test_get_diff(self):
        self.git.create_branch("h1")
        Path(self.tmpdir, "new_file.py").write_text("x = 1\n")
        env = {**os.environ, "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "test@test.com",
               "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "test@test.com"}
        subprocess.run(["git", "add", "."], cwd=self.tmpdir, capture_output=True)
        subprocess.run(["git", "commit", "-m", "add"], cwd=self.tmpdir, capture_output=True, env=env)
        diff = self.git.get_diff("main")
        assert "new_file.py" in diff

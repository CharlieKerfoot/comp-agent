import tempfile
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from comp_agent.cli import cli


class TestCLISmoke:
    def test_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Competition Agent" in result.output

    def test_init_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["init", "--help"])
        assert result.exit_code == 0
        assert "location" in result.output.lower() or "LOCATION" in result.output

    def test_run_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["run", "--help"])
        assert result.exit_code == 0
        assert "iterations" in result.output.lower()

    def test_status_no_spec(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(cli, ["status"])
            assert result.exit_code != 0 or "problem_spec.json" in result.output

    def test_history_no_runs(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            # Create empty tracker
            from comp_agent.tracker.db import TrackerDB
            db = TrackerDB("tracker.db")
            db.close()
            result = runner.invoke(cli, ["history"])
            assert "No runs" in result.output

    def test_submit_no_spec(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(cli, ["submit"])
            assert result.exit_code != 0 or "problem_spec.json" in result.output

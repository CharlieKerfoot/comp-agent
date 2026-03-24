from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import click
import yaml

from comp_agent.controller.loop import load_config, run_loop
from comp_agent.models import ProblemSpec
from comp_agent.parser import detect_source, parse_problem
from comp_agent.tracker.db import TrackerDB
from comp_agent.tracker.log import generate_report, write_report


@click.group()
def cli():
    """Competition Agent - iterative score optimization for competitions."""
    pass


@cli.command()
@click.argument("location")
@click.option("--source", type=click.Choice(["kaggle", "hackathon", "puzzle", "custom"]),
              default=None, help="Source type (auto-detected if not specified)")
@click.option("--time-budget", type=float, default=None,
              help="Time budget in hours")
@click.option("--data-dir", default="data", help="Directory for competition data")
def init(location: str, source: str | None, time_budget: float | None,
         data_dir: str):
    """Initialize a competition workspace from a URL or spec file."""
    # Auto-detect source if not specified
    if source is None:
        source = detect_source(location)
        click.echo(f"Detected source type: {source}")

    # Parse problem
    click.echo(f"Parsing competition from: {location}")
    spec = parse_problem(source, location, data_dir)

    # Save spec
    spec.to_json("problem_spec.json")
    click.echo(f"Problem spec saved to problem_spec.json")

    # Update config with time budget if provided
    config_path = Path("config.yaml")
    if config_path.exists():
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}
    else:
        config = {}

    if time_budget is not None:
        config["time_budget_hours"] = time_budget
        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False)

    # Initialize tracker
    tracker = TrackerDB("tracker.db")
    tracker.close()
    click.echo("Tracker database initialized")

    # Create solution directory
    Path("solution").mkdir(exist_ok=True)
    Path("submissions").mkdir(exist_ok=True)

    # Initialize git if not already
    if not Path(".git").exists():
        subprocess.run(["git", "init"], capture_output=True)
        subprocess.run(["git", "checkout", "-b", "main"], capture_output=True)

    click.echo(f"\nWorkspace initialized for: {spec.name}")
    click.echo(f"  Type: {spec.problem_type}")
    click.echo(f"  Metric: {spec.metric} ({spec.metric_direction})")
    click.echo(f"  Data: {len(spec.data_paths)} files in {data_dir}/")
    click.echo(f"\nNext: write your baseline in solution/train.py, then run 'compete run'")


@cli.command()
@click.option("--iterations", "-n", default=5, help="Max iterations to run")
@click.option("--auto", "auto_mode", is_flag=True, help="Run autonomously without approval")
@click.option("--phase", type=click.Choice(["baseline", "improve", "ensemble", "polish"]),
              default=None, help="Force a specific phase")
def run(iterations: int, auto_mode: bool, phase: str | None):
    """Run the optimization loop."""
    spec = _load_spec()
    config = load_config()
    tracker = TrackerDB("tracker.db")

    try:
        run_loop(
            spec=spec,
            tracker=tracker,
            config=config,
            max_iterations=iterations,
            auto_mode=auto_mode,
            forced_phase=phase,
        )
    finally:
        tracker.close()


@cli.command()
@click.option("--verbose", "-v", is_flag=True, help="Show detailed information")
def status(verbose: bool):
    """Show current competition status and score history."""
    spec = _load_spec()
    tracker = TrackerDB("tracker.db")

    try:
        report = generate_report(tracker, spec.name, spec.metric_direction)
        click.echo(report)

        if verbose:
            click.echo("\n--- All Runs ---")
            for r in tracker.get_all_runs():
                click.echo(
                    f"  {r['id'][:8]} | {r['status']:8} | "
                    f"score={r['score'] or 'N/A':>10} | "
                    f"{r['runtime_seconds']:.1f}s | {r['branch']}"
                )

            click.echo("\n--- Hypothesis Branches ---")
            from comp_agent.executor.snapshot import GitSnapshot
            git = GitSnapshot()
            for branch in git.list_hypothesis_branches():
                click.echo(f"  {branch}")
    finally:
        tracker.close()


@cli.command()
@click.argument("hypothesis_id")
def approve(hypothesis_id: str):
    """Approve and execute a pending hypothesis."""
    spec = _load_spec()
    config = load_config()
    tracker = TrackerDB("tracker.db")

    try:
        h = tracker.get_hypothesis(hypothesis_id)
        if h is None:
            click.echo(f"Hypothesis {hypothesis_id} not found")
            return
        if h["status"] != "pending":
            click.echo(f"Hypothesis {hypothesis_id} is {h['status']}, not pending")
            return

        click.echo(f"Executing: {h['description']}")

        # Run single iteration with this hypothesis
        from comp_agent.executor.runner import CodeRunner
        from comp_agent.executor.snapshot import GitSnapshot
        from comp_agent.models import Result

        git = GitSnapshot()
        runner = CodeRunner(
            timeout_seconds=config.get("execution_timeout_seconds", 1800),
        )

        tracker.update_hypothesis_status(hypothesis_id, "running")
        branch = git.create_branch(hypothesis_id)

        result = runner.run(
            [sys.executable, "solution/train.py"],
            hypothesis_id=hypothesis_id,
            branch=branch,
            metric=spec.metric,
        )

        result.code_diff = git.get_diff("main")
        git.commit_snapshot(hypothesis_id, h["description"])
        tracker.log_run(result)

        if result.status == "success" and result.score is not None:
            best_score = tracker.get_best_score(spec.metric_direction)
            if result.score_improved(best_score, spec.metric_direction):
                click.echo(f"ACCEPTED: {result.score}")
                tracker.update_hypothesis_status(hypothesis_id, "accepted", result.id)
                git.checkout("main")
                git.merge_to_main(branch)
            else:
                click.echo(f"REJECTED: {result.score} (best: {best_score})")
                tracker.update_hypothesis_status(hypothesis_id, "rejected", result.id)
                git.checkout("main")
        else:
            click.echo(f"FAILED: {result.status}")
            tracker.update_hypothesis_status(hypothesis_id, "error", result.id)
            git.checkout("main")

        write_report(tracker, spec.name, spec.metric_direction)
    finally:
        tracker.close()


@cli.command()
@click.option("--validate-only", is_flag=True, help="Only validate, don't create submission")
def submit(validate_only: bool):
    """Generate and validate the final submission."""
    spec = _load_spec()
    tracker = TrackerDB("tracker.db")

    try:
        best = tracker.get_best_run(spec.metric_direction)
        if best is None:
            click.echo("No successful runs found. Nothing to submit.")
            return

        click.echo(f"Best run: {best['id']} (score: {best['score']}, branch: {best['branch']})")

        submission_path = Path("submissions/submission.csv")
        if submission_path.exists():
            from comp_agent.executor.validate import OutputValidator
            validator = OutputValidator()
            valid, msg = validator.validate(str(submission_path), spec.submission_format)
            click.echo(f"Validation: {msg}")

            if not valid:
                click.echo("Submission is INVALID. Fix issues before submitting.")
                return

            if validate_only:
                click.echo("Validation passed. Use without --validate-only to submit.")
                return

            click.echo(f"\nSubmission ready at: {submission_path}")
            click.echo(f"Best score: {best['score']}")

            # Log submission
            tracker.log_submission(
                run_id=best["id"],
                local_score=best["score"],
                submission_path=str(submission_path),
            )
        else:
            click.echo("No submission file found at submissions/submission.csv")
            click.echo(f"Re-run the best approach on branch: {best['branch']}")
    finally:
        tracker.close()


@cli.command()
@click.option("--last", "-n", default=10, help="Number of recent runs to show")
def history(last: int):
    """Show run history."""
    tracker = TrackerDB("tracker.db")
    try:
        runs = tracker.get_all_runs()[-last:]
        if not runs:
            click.echo("No runs yet.")
            return

        click.echo(f"{'ID':>10} {'Status':>8} {'Score':>12} {'Runtime':>10} {'Branch'}")
        click.echo("-" * 70)
        for r in runs:
            score_str = f"{r['score']:.6f}" if r['score'] is not None else "N/A"
            click.echo(
                f"{r['id'][:10]:>10} {r['status']:>8} {score_str:>12} "
                f"{r['runtime_seconds']:>8.1f}s {r['branch']}"
            )
    finally:
        tracker.close()


def _load_spec() -> ProblemSpec:
    spec_path = Path("problem_spec.json")
    if not spec_path.exists():
        click.echo("No problem_spec.json found. Run 'compete init' first.")
        raise SystemExit(1)
    return ProblemSpec.from_json(str(spec_path))

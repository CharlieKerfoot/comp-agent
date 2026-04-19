from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import click
from dotenv import load_dotenv

load_dotenv()

from comp_agent.config import WORKSPACE_CONFIG_TEMPLATE, load_config
from comp_agent.controller.loop import run_loop
from comp_agent.llm import set_default_provider
from comp_agent.models import ProblemSpec
from comp_agent.parser import detect_source, parse_problem
from comp_agent.tracker.db import TrackerDB
from comp_agent.tracker.log import generate_report, write_report


@click.group()
@click.option("--provider", type=click.Choice(["api", "claude-code"]),
              default="api", envvar="COMPETE_PROVIDER",
              help="LLM provider: 'api' for Anthropic API, 'claude-code' for Claude Code CLI (subscription)")
@click.option("--model", default="claude-opus-4-7", envvar="COMPETE_MODEL",
              help="Model to use")
def cli(provider: str, model: str):
    """Competition Agent - iterative score optimization for competitions."""
    set_default_provider(provider=provider, model=model)


@cli.command()
@click.argument("location")
@click.option("--source", type=click.Choice(["kaggle", "hackathon", "puzzle", "custom"]),
              default=None, help="Source type (auto-detected if not specified)")
@click.option("--time-budget", type=float, default=None,
              help="Time budget in hours")
@click.option("--data-dir", default="data", help="Directory for competition data")
@click.option("--metric", default=None,
              help="Override the evaluation metric (e.g. 'AUC', 'RMSE', 'mean F1')")
@click.option("--metric-direction", type=click.Choice(["minimize", "maximize"]),
              default=None, help="Override the metric direction")
@click.option("--problem-type",
              type=click.Choice(["classification", "regression", "optimization",
                                 "combinatorial", "mathematical", "systems"]),
              default=None, help="Override the problem type")
def init(location: str, source: str | None, time_budget: float | None,
         data_dir: str, metric: str | None, metric_direction: str | None,
         problem_type: str | None):
    """Initialize a competition workspace from a URL or spec file.

    Run this from an empty directory you've created for the competition,
    e.g. `mkdir ~/competitions/titanic && cd $_ && compete init <url>`.
    """
    _guard_workspace_cwd()

    # Auto-detect source if not specified
    if source is None:
        source = detect_source(location)
        click.echo(f"Detected source type: {source}")

    # Parse problem
    click.echo(f"Parsing competition from: {location}")
    try:
        spec = parse_problem(source, location, data_dir)
    except (RuntimeError, ValueError) as e:
        raise click.ClickException(str(e)) from e

    # Apply CLI overrides, then prompt for anything still unknown.
    if problem_type:
        spec.problem_type = problem_type
    if metric:
        spec.metric = metric
    if metric_direction:
        spec.metric_direction = metric_direction

    _fill_unknowns_interactively(spec)

    # Save spec
    spec.to_json("problem_spec.json")
    click.echo(f"Problem spec saved to problem_spec.json")

    # Scaffold a per-workspace config.yaml (commented template).
    config_path = Path("config.yaml")
    if not config_path.exists():
        config_path.write_text(WORKSPACE_CONFIG_TEMPLATE)

    if time_budget is not None:
        # Append so the commented template above stays intact as docs.
        with config_path.open("a") as f:
            f.write(f"\ntime_budget_hours: {time_budget}\n")

    # Initialize tracker
    tracker = TrackerDB("tracker.db")
    tracker.close()
    click.echo("Tracker database initialized")

    # Create solution directory
    Path("solution").mkdir(exist_ok=True)
    Path("submissions").mkdir(exist_ok=True)

    _write_default_files(data_dir)
    _git_bootstrap()

    click.echo(f"\nWorkspace initialized for: {spec.name}")
    click.echo(f"  Type: {spec.problem_type}")
    click.echo(f"  Metric: {spec.metric} ({spec.metric_direction})")
    click.echo(f"  Data: {len(spec.data_paths)} files in {data_dir}/")
    click.echo(
        "\nSolution scripts run via `uv run --script` and declare their own "
        "dependencies using a PEP 723 `# /// script` header — no venv setup "
        "needed.\n"
        "\nNext: `compete baseline` to scaffold solution/train.py, "
        "then `compete run`."
    )


@cli.command()
@click.option("--force", is_flag=True,
              help="Overwrite an existing solution/train.py")
def baseline(force: bool):
    """Generate solution/train.py from problem_spec.json using the LLM."""
    spec = _load_spec()
    target = Path("solution/train.py")
    if target.exists() and not force:
        click.echo(f"{target} already exists. Use --force to overwrite.")
        raise SystemExit(1)

    from comp_agent.strategist.baseline import BaselineGenerator

    click.echo("Generating baseline with LLM...")
    code = BaselineGenerator().generate(spec)

    target.parent.mkdir(parents=True, exist_ok=True)
    Path("submissions").mkdir(exist_ok=True)
    target.write_text(code)
    click.echo(f"Wrote {target} ({len(code.splitlines())} lines)")
    _commit_baseline_to_main(target)
    click.echo("Next: `compete run` to start the optimization loop.")


def _commit_baseline_to_main(target: Path) -> None:
    """Commit the baseline on main so hypothesis branches inherit it.

    Without this step, the file stays untracked and later git checkouts back
    to main after a hypothesis run leave solution/train.py missing.
    """
    if not Path(".git").exists():
        return
    current = subprocess.run(
        ["git", "branch", "--show-current"],
        capture_output=True, text=True,
    ).stdout.strip()
    if current and current != "main":
        # Only auto-commit when we're on main — otherwise let the user sort it out.
        click.echo(
            f"(On branch '{current}', not 'main' — "
            f"commit {target} manually if you want it carried forward.)"
        )
        return
    subprocess.run(["git", "add", str(target)], check=False, capture_output=True)
    result = subprocess.run(
        ["git", "commit", "-q", "-m", "add baseline solution"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        click.echo("Committed baseline to main.")


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

    # Config can opt into auto mode too: `autonomy_mode: "auto"`.
    effective_auto = auto_mode or config.get("autonomy_mode") == "auto"

    try:
        run_loop(
            spec=spec,
            tracker=tracker,
            config=config,
            max_iterations=iterations,
            auto_mode=effective_auto,
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

        # Reconstruct a Hypothesis for the implementer from the DB row.
        from comp_agent.executor.implement import HypothesisImplementer
        from comp_agent.executor.runner import solution_command
        from comp_agent.models import Hypothesis as _Hyp
        hyp_obj = _Hyp(
            id=hypothesis_id,
            description=h["description"],
            rationale=h.get("rationale", "") or "",
            expected_improvement=0.0,
            estimated_time_minutes=0,
            code_sketch=h.get("code_sketch", "") or "",
        )
        click.echo("Implementing hypothesis (LLM is modifying solution/train.py)...")
        HypothesisImplementer().apply(hyp_obj, spec)

        result = runner.run(
            solution_command("solution/train.py"),
            hypothesis_id=hypothesis_id,
            branch=branch,
            metric=spec.metric,
        )

        result.code_diff = git.get_diff("main")
        git.commit_snapshot(hypothesis_id, h["description"])
        # Snapshot best BEFORE logging, otherwise the run compares against itself.
        best_score = tracker.get_best_score(spec.metric_direction)
        tracker.log_run(result)

        if result.status == "success" and result.score is not None:
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


_DEFAULT_GITIGNORE = """\
.venv/
__pycache__/
*.pyc
data/
submissions/
tracker.db
tracker.db-journal
.env
"""


def _write_default_files(data_dir: str) -> None:
    """Scaffold .gitignore if missing."""
    gi_path = Path(".gitignore")
    if not gi_path.exists():
        body = _DEFAULT_GITIGNORE
        if data_dir != "data":
            body = body.replace("data/\n", f"{data_dir.rstrip('/')}/\n")
        gi_path.write_text(body)


def _git_bootstrap() -> None:
    """Initialize git and make an initial commit so `main` is a real ref."""
    if not Path(".git").exists():
        subprocess.run(["git", "init", "-q"], check=False)
        subprocess.run(["git", "checkout", "-q", "-b", "main"], check=False)

    # If main has no commits yet, make the initial commit.
    head = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        capture_output=True, text=True,
    )
    if head.returncode != 0:
        subprocess.run(["git", "add", "-A"], check=False)
        subprocess.run(
            ["git", "commit", "-q", "-m", "initial workspace"],
            check=False, capture_output=True,
        )


def _llm_extract_metric(evaluation_text: str) -> str | None:
    """Ask the LLM for a short metric name given pasted evaluation prose."""
    from comp_agent.llm import get_provider
    prompt = f"""The following is the 'Evaluation' section of a competition description. Extract the name of the scoring metric as a short phrase a practitioner would recognize (e.g. 'AUC', 'RMSE', 'mean F1', 'quadratic weighted kappa', 'per-task points = max(1, 25 - log(macs + memory + bytes + params))').

Respond with ONLY the metric phrase on a single line — no quotes, no prose, no explanation. If the text describes a bespoke formula, return a compact one-line form of that formula.

Evaluation section:
{evaluation_text[:8000]}"""
    try:
        text = get_provider().ask(prompt, max_tokens=200).strip()
        # Take just the first non-empty line, strip surrounding quotes.
        for line in text.splitlines():
            line = line.strip().strip('"').strip("'")
            if line:
                return line
    except Exception as e:
        click.echo(f"(LLM extraction failed: {e})")
    return None


def _fill_unknowns_interactively(spec: ProblemSpec) -> None:
    """If key fields couldn't be auto-extracted, ask the user to fill them in.

    Kaggle's competition pages are JS-rendered, so curl-based scraping can miss
    the evaluation section. Rather than silently using 'unknown' (which poisons
    every downstream prompt), prompt for the values here.
    """
    if not spec.metric or spec.metric.lower() == "unknown":
        click.echo(
            "\nWe couldn't auto-extract the evaluation metric from the "
            "competition page (Kaggle renders most content client-side).\n"
            f"Check {spec.url or 'the competition page'} → Overview → Evaluation.\n"
            "Enter a one-line metric name, or press Enter to open $EDITOR and "
            "paste the full Evaluation section."
        )
        entered = click.prompt(
            "Evaluation metric (e.g. 'AUC', 'RMSE', 'mean F1')",
            default="", show_default=False,
        ).strip()
        if not entered:
            pasted = click.edit(
                "# Paste the competition's Evaluation section below this line, then save and quit.\n"
                "# Lines starting with # are ignored.\n"
            )
            if pasted:
                text = "\n".join(
                    ln for ln in pasted.splitlines() if not ln.lstrip().startswith("#")
                ).strip()
                if text:
                    entered = _llm_extract_metric(text) or ""
                    if entered:
                        click.echo(f"Extracted metric: {entered}")
        if entered:
            spec.metric = entered

    if spec.metric and spec.metric.lower() != "unknown":
        # Re-infer direction if we just set the metric or it looks wrong.
        from comp_agent.parser.extractors.kaggle import _infer_direction
        inferred = _infer_direction(spec.metric)
        if not spec.metric_direction or spec.metric_direction not in ("minimize", "maximize"):
            spec.metric_direction = inferred
        elif spec.metric_direction != inferred:
            confirm = click.prompt(
                f"Metric '{spec.metric}' usually implies '{inferred}', "
                f"but direction is set to '{spec.metric_direction}'. "
                f"Keep '{spec.metric_direction}'? [y/N]",
                default="n", show_default=False,
            ).strip().lower()
            if confirm != "y":
                spec.metric_direction = inferred


def _guard_workspace_cwd() -> None:
    """Prevent accidentally initializing a workspace inside the comp-agent repo.

    `compete init` scaffolds files in the current working directory. Running it
    inside the tool's own source tree (or any other Python project) pollutes it.
    """
    cwd = Path.cwd()
    pyproject = cwd / "pyproject.toml"
    if pyproject.exists():
        try:
            text = pyproject.read_text()
        except OSError:
            text = ""
        if 'name = "comp-agent"' in text:
            click.echo(
                "Refusing to init: this directory is the comp-agent source repo.\n"
                "Create a new empty directory for the competition and run init there:\n"
                "  mkdir ~/competitions/<name> && cd $_ && compete init <url>"
            )
            raise SystemExit(1)
        click.echo(
            "Warning: cwd already contains a pyproject.toml. Workspaces should "
            "live in their own empty directory. Continue? [y/N] ",
            nl=False,
        )
        if not click.confirm("", default=False, show_default=False):
            raise SystemExit(1)

    if (cwd / "problem_spec.json").exists():
        click.echo(
            "A problem_spec.json already exists in this directory. "
            "Delete it or pick a new directory before running init."
        )
        raise SystemExit(1)


def _load_spec() -> ProblemSpec:
    spec_path = Path("problem_spec.json")
    if not spec_path.exists():
        click.echo("No problem_spec.json found. Run 'compete init' first.")
        raise SystemExit(1)
    return ProblemSpec.from_json(str(spec_path))

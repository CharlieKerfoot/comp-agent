from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import click

from comp_agent.config import load_config  # noqa: F401  (re-exported for back-compat)
from comp_agent.controller.budget import SubmissionBudget, TimeBudget
from comp_agent.controller.policy import select_phase, should_critique
from comp_agent.executor.implement import HypothesisImplementer
from comp_agent.executor.runner import CodeRunner, solution_command
from comp_agent.executor.snapshot import GitSnapshot
from comp_agent.executor.validate import OutputValidator
from comp_agent.models import Hypothesis, ProblemSpec, Result
from comp_agent.strategist.classify import classify_problem
from comp_agent.strategist.critique import CritiqueEngine
from comp_agent.strategist.hypothesize import HypothesisGenerator
from comp_agent.strategist.prioritize import prioritize
from comp_agent.tracker.db import TrackerDB
from comp_agent.tracker.log import write_report


def _maybe_hint_missing_deps(error_text: str) -> None:
    if "ModuleNotFoundError" not in error_text and "No module named" not in error_text:
        return
    click.echo(
        "\nHint: the solution imports a package not listed in its PEP 723 "
        "`# /// script` header. Add it to the `dependencies = [...]` block at "
        "the top of solution/train.py and re-run."
    )


def _ensure_baseline_exists(spec: ProblemSpec) -> None:
    """Auto-generate solution/train.py on first run if it's missing."""
    train_path = Path("solution/train.py")
    if train_path.exists():
        return

    from comp_agent.strategist.baseline import BaselineGenerator

    click.echo("No solution/train.py found — generating baseline with LLM...")
    code = BaselineGenerator().generate(spec)
    train_path.parent.mkdir(parents=True, exist_ok=True)
    Path("submissions").mkdir(exist_ok=True)
    train_path.write_text(code)
    click.echo(f"Wrote {train_path} ({len(code.splitlines())} lines)")

    # Commit on main so hypothesis branches inherit the baseline.
    from comp_agent.executor.snapshot import GitSnapshot
    git = GitSnapshot()
    if git.current_branch() == "main":
        git._run("add", str(train_path), check=False)
        git._run("commit", "-q", "-m", "add baseline solution", check=False)


def run_loop(spec: ProblemSpec, tracker: TrackerDB,
             config: dict, max_iterations: int = 5,
             auto_mode: bool = False,
             forced_phase: str | None = None) -> None:
    time_budget = TimeBudget(
        deadline=spec.get_time_limit(),
        budget_hours=config.get("time_budget_hours"),
    )
    sub_budget = SubmissionBudget(
        daily_limit=spec.submission_limit or config.get("submission_limit_per_day"),
        reserved_per_day=config.get("reserved_submissions_per_day", 1),
    )

    _ensure_baseline_exists(spec)

    generator = HypothesisGenerator()
    implementer = HypothesisImplementer()
    critique_engine = CritiqueEngine()
    runner = CodeRunner(
        timeout_seconds=config.get("execution_timeout_seconds", 1800),
    )
    git = GitSnapshot()
    validator = OutputValidator()
    critique_interval = config.get("critique_interval", 5)
    max_failures = config.get("max_consecutive_failures", 5)

    for iteration in range(max_iterations):
        click.echo(f"\n{'='*60}")
        click.echo(f"Iteration {iteration + 1}/{max_iterations}")
        click.echo(f"{'='*60}")

        # Check time budget
        if time_budget.expired():
            click.echo("Time budget expired. Finalizing.")
            break

        # Select phase
        history = tracker.history()
        phase = forced_phase or select_phase(
            time_budget.remaining_hours(), history, max_failures,
        )
        click.echo(f"Phase: {phase}")
        click.echo(f"Time remaining: {time_budget.remaining_hours():.1f}h")

        if phase == "submit":
            click.echo("Entering submit phase. Run 'compete submit' to finalize.")
            break

        if phase == "pivot":
            click.echo(
                "\nStuck detected! Last several hypotheses failed.\n"
                "Consider a fundamentally different approach.\n"
                "Continuing with 'improve' phase but flagging for review."
            )
            phase = "improve"

        # Get recent critiques for the strategist
        critiques = tracker.get_recent_critiques(limit=2)

        # Generate hypotheses
        click.echo("\nGenerating hypotheses...")
        hypotheses = generator.generate(
            spec=spec,
            history=history,
            phase=phase,
            time_budget_hours=time_budget.remaining_hours(),
            critiques=critiques,
        )

        # Prioritize
        rejected_descs = [
            h["description"] for h in tracker.get_pending_hypotheses()
            if h["status"] == "rejected"
        ]
        hypotheses = prioritize(
            hypotheses, time_budget.remaining_hours(), rejected_descs,
        )

        # Display hypotheses
        click.echo(f"\nTop {len(hypotheses)} hypotheses:")
        for i, h in enumerate(hypotheses, 1):
            click.echo(
                f"  {i}. [{h.risk}] {h.description}\n"
                f"     Expected: +{h.expected_improvement:.4f}, "
                f"~{h.estimated_time_minutes}min"
            )

        # Approval gate
        if not auto_mode:
            click.echo(
                "\nApprove a hypothesis to execute, or 'skip' to regenerate."
            )
            choice = click.prompt(
                "Enter number (or 'skip')",
                default="1",
            )
            if choice.lower() == "skip":
                continue
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(hypotheses):
                    selected = hypotheses[idx]
                else:
                    click.echo("Invalid choice, using #1")
                    selected = hypotheses[0]
            except ValueError:
                click.echo("Invalid input, using #1")
                selected = hypotheses[0]
        else:
            selected = hypotheses[0]

        # Log hypothesis
        tracker.log_hypothesis(selected)
        tracker.update_hypothesis_status(selected.id, "running")

        # Execute
        click.echo(f"\nExecuting: {selected.description}")
        branch = git.create_branch(selected.id)

        try:
            # Rewrite solution/train.py to actually carry out the hypothesis.
            click.echo("Implementing hypothesis (LLM is modifying solution/train.py)...")
            implementer.apply(selected, spec)

            # Run the modified solution
            result = runner.run(
                solution_command("solution/train.py"),
                hypothesis_id=selected.id,
                branch=branch,
                metric=spec.metric,
            )

            # Get diff
            result.code_diff = git.get_diff("main")

            # Commit changes
            git.commit_snapshot(selected.id, selected.description)

            # Snapshot best BEFORE logging this run, otherwise we'd compare
            # against ourselves and every run would "not improve."
            best_score_before = tracker.get_best_score(spec.metric_direction)
            tracker.log_run(result)

            # Evaluate
            if result.status == "success":
                click.echo(f"Score: {result.score}")

                # Validate output if present
                submission_path = "submissions/submission.csv"
                if Path(submission_path).exists():
                    valid, msg = validator.validate(
                        submission_path, spec.submission_format,
                    )
                    click.echo(f"Validation: {msg}")

                if result.score_improved(best_score_before, spec.metric_direction):
                    click.echo("ACCEPTED - Score improved!")
                    tracker.update_hypothesis_status(
                        selected.id, "accepted", result.id,
                    )
                    git.checkout("main")
                    success, err = git.merge_to_main(branch)
                    if not success:
                        click.echo(f"Merge conflict: {err}")
                        click.echo("Marked as accepted-unmergeable")
                else:
                    click.echo("REJECTED - Score did not improve")
                    tracker.update_hypothesis_status(
                        selected.id, "rejected", result.id,
                    )
                    git.checkout("main")
            else:
                click.echo(f"FAILED: {result.status} - {result.error_message}")
                _maybe_hint_missing_deps(result.error_message or "")
                tracker.update_hypothesis_status(
                    selected.id, "error", result.id,
                )
                git.checkout("main")

        except Exception as e:
            click.echo(f"ERROR: {e}")
            tracker.update_hypothesis_status(selected.id, "error")
            git.checkout("main")

        # Periodic critique
        if should_critique(tracker.total_runs(), critique_interval):
            best_run = tracker.get_best_run(spec.metric_direction)
            if best_run:
                click.echo("\nRunning critique of current best solution...")
                try:
                    # Read the solution code
                    solution_path = Path("solution/train.py")
                    code = solution_path.read_text() if solution_path.exists() else ""
                    critique_result = critique_engine.critique(
                        code, best_run["score"], spec,
                    )
                    tracker.log_critique(
                        content=critique_result.get("winning_approach", ""),
                        run_id=best_run["id"],
                        weaknesses=critique_result.get("weaknesses", []),
                        suggestions=critique_result.get("suggestions", []),
                    )
                    click.echo("Critique logged.")
                except Exception as e:
                    click.echo(f"Critique failed: {e}")

        # Refresh report
        write_report(tracker, spec.name, spec.metric_direction)
        click.echo(f"\nReport updated: tracker/report.md")

    click.echo(f"\nLoop complete. Total runs: {tracker.total_runs()}")
    best = tracker.get_best_run(spec.metric_direction)
    if best:
        click.echo(f"Best score: {best['score']} (run {best['id']})")

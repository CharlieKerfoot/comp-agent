from __future__ import annotations

from pathlib import Path

from comp_agent.tracker.compare import format_score, score_delta
from comp_agent.tracker.db import TrackerDB


def generate_report(tracker: TrackerDB, competition_name: str,
                    direction: str = "maximize") -> str:
    runs = tracker.get_all_runs()
    best_run = tracker.get_best_run(direction)
    accepted = tracker.get_accepted_runs()
    rejected = tracker.get_rejected_runs()
    pending = tracker.get_pending_hypotheses()
    total = tracker.total_runs()

    lines = [
        f"# Competition: {competition_name}",
        "",
    ]

    # Best score
    if best_run:
        lines.append(
            f"## Best Score: {format_score(best_run['score'])} "
            f"(run {best_run['id']}, branch {best_run['branch']})"
        )
    else:
        lines.append("## Best Score: No successful runs yet")
    lines.append(
        f"## Runs: {total} | Accepted: {tracker.accepted_count()} "
        f"| Rejected: {tracker.rejected_count()}"
    )
    lines.append("")

    # Score progression
    lines.append("### Score Progression")
    lines.append("")
    successful_runs = [r for r in runs if r["status"] == "success" and r["score"] is not None]
    if successful_runs:
        scores = [r["score"] for r in successful_runs]
        min_s, max_s = min(scores), max(scores)
        width = 40
        for r in successful_runs:
            if max_s == min_s:
                bar_len = width
            else:
                bar_len = int((r["score"] - min_s) / (max_s - min_s) * width)
            bar = "#" * max(bar_len, 1)
            lines.append(f"  {r['id'][:8]} | {bar} {format_score(r['score'])}")
        lines.append("")
    else:
        lines.append("  No successful runs yet.")
        lines.append("")

    # What worked
    lines.append("### What Worked")
    lines.append("")
    if accepted:
        prev_score = None
        for r in accepted:
            h = tracker.get_hypothesis(r["hypothesis_id"])
            desc = h["description"] if h else r["hypothesis_id"]
            if prev_score is not None:
                delta = score_delta(r["score"], prev_score)
                sign = "+" if delta >= 0 else ""
                lines.append(
                    f"- {desc}: {format_score(prev_score)} -> "
                    f"{format_score(r['score'])} ({sign}{delta:.6f})"
                )
            else:
                lines.append(f"- {desc}: {format_score(r['score'])} (baseline)")
            prev_score = r["score"]
    else:
        lines.append("  Nothing accepted yet.")
    lines.append("")

    # What didn't work
    lines.append("### What Didn't Work")
    lines.append("")
    if rejected:
        for r in rejected[:10]:  # Show last 10
            h = tracker.get_hypothesis(r["hypothesis_id"])
            desc = h["description"] if h else r["hypothesis_id"]
            score_str = format_score(r["score"]) if r["score"] is not None else r["status"]
            lines.append(f"- {desc}: {score_str}")
    else:
        lines.append("  Nothing rejected yet.")
    lines.append("")

    # Pending hypotheses
    lines.append("### Pending Hypotheses")
    lines.append("")
    if pending:
        for i, h in enumerate(pending, 1):
            lines.append(
                f"{i}. {h['description']} "
                f"(est. +{h['expected_improvement']:.4f}, "
                f"~{h['estimated_time_minutes']}min)"
            )
    else:
        lines.append("  No pending hypotheses.")
    lines.append("")

    return "\n".join(lines)


def write_report(tracker: TrackerDB, competition_name: str,
                 direction: str = "maximize",
                 output_path: str = "tracker/report.md") -> str:
    report = generate_report(tracker, competition_name, direction)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report)
    return report

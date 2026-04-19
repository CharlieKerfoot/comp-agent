"""Shared helpers for building prompt context from a competition workspace."""

from __future__ import annotations

import re
from pathlib import Path


_PREVIEW_MAX_FILES = 6
_PREVIEW_MAX_LINES = 5
_PREVIEW_MAX_LINE_CHARS = 240
_PREVIEW_TOTAL_BUDGET = 4000

_SAMPLE_SUBMISSION_NAMES = ("sample_submission.csv", "sampleSubmission.csv")


def sample_submission_snippet(data_paths: list[str]) -> str:
    """Return a verbatim snippet of sample_submission.csv if present.

    The submission format is the single highest-leverage piece of context the
    LLM needs — read it unconditionally and early, not just as part of a
    truncated preview.
    """
    for path_str in data_paths:
        path = Path(path_str)
        if path.name in _SAMPLE_SUBMISSION_NAMES:
            return _read_head(path, max_lines=4, label="sample_submission.csv (verbatim)")
    # Fallback: scan data/ in case data_paths is stale.
    for name in _SAMPLE_SUBMISSION_NAMES:
        path = Path("data") / name
        if path.exists():
            return _read_head(path, max_lines=4, label=f"{name} (verbatim)")
    return "(no sample_submission.csv found — format from problem_spec if any)"


def data_preview(data_paths: list[str]) -> str:
    if not data_paths:
        return "(no data files)"

    out: list[str] = []
    total = 0
    for path_str in data_paths[:_PREVIEW_MAX_FILES]:
        path = Path(path_str)
        if not path.exists():
            out.append(f"- {path_str} (missing)")
            continue

        size = path.stat().st_size
        header = f"\n- {path_str} ({size} bytes)"
        out.append(header)
        total += len(header)

        if path.suffix.lower() in (".csv", ".tsv", ".txt", ".json"):
            try:
                with path.open("r", errors="replace") as f:
                    for i, line in enumerate(f):
                        if i >= _PREVIEW_MAX_LINES:
                            break
                        stripped = line.rstrip("\n")
                        if len(stripped) > _PREVIEW_MAX_LINE_CHARS:
                            stripped = stripped[:_PREVIEW_MAX_LINE_CHARS] + "…"
                        rendered = f"    {stripped}"
                        if total + len(rendered) > _PREVIEW_TOTAL_BUDGET:
                            out.append("    … (truncated)")
                            return "\n".join(out)
                        out.append(rendered)
                        total += len(rendered)
            except OSError:
                out.append("    (could not read)")

    if len(data_paths) > _PREVIEW_MAX_FILES:
        out.append(f"\n... and {len(data_paths) - _PREVIEW_MAX_FILES} more file(s)")

    return "\n".join(out)


def _read_head(path: Path, max_lines: int, label: str) -> str:
    try:
        with path.open("r", errors="replace") as f:
            lines = []
            for i, line in enumerate(f):
                if i >= max_lines:
                    break
                lines.append(line.rstrip("\n"))
        body = "\n".join(lines)
        return f"{label}:\n{body}"
    except OSError:
        return f"{label}: (could not read)"


def extract_python(text: str) -> str:
    """Pull Python source out of a fenced code block, or return text as-is."""
    match = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).rstrip() + "\n"
    return text.strip() + "\n"

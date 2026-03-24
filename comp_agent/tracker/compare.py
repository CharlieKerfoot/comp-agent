from __future__ import annotations


def score_improved(new_score: float | None, best_score: float | None,
                   direction: str) -> bool:
    if new_score is None:
        return False
    if best_score is None:
        return True
    if direction == "maximize":
        return new_score > best_score
    return new_score < best_score


def compute_improvement_rate(runs: list[dict], window: int = 5) -> float:
    successful = [r for r in runs if r["status"] == "success" and r["score"] is not None]
    if len(successful) < 2:
        return 0.0

    recent = successful[-window:]
    if len(recent) < 2:
        return 0.0

    first_score = recent[0]["score"]
    last_score = recent[-1]["score"]

    if first_score == 0:
        return 0.0

    return (last_score - first_score) / abs(first_score)


def score_delta(new_score: float, old_score: float) -> float:
    return new_score - old_score


def format_score(score: float | None) -> str:
    if score is None:
        return "N/A"
    return f"{score:.6f}"

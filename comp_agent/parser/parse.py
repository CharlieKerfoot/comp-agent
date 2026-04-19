from __future__ import annotations

from pathlib import Path

from comp_agent.models import ProblemSpec


def parse_problem(source: str, location: str, data_dir: str = "data") -> ProblemSpec:
    if source == "custom":
        from comp_agent.parser.extractors.custom import extract_from_yaml
        return extract_from_yaml(location)

    elif source == "kaggle":
        from comp_agent.parser.extractors.kaggle import extract_from_kaggle
        slug = _extract_kaggle_slug(location)
        return extract_from_kaggle(slug, data_dir)

    elif source == "hackathon":
        from comp_agent.parser.extractors.hackathon import extract_from_url
        page_content = _fetch_page(location)
        return extract_from_url(location, page_content)

    elif source == "puzzle":
        from comp_agent.parser.extractors.puzzle import extract_from_text
        if Path(location).exists():
            text = Path(location).read_text()
            return extract_from_text(text)
        else:
            page_content = _fetch_page(location)
            return extract_from_text(page_content, source_url=location)

    else:
        raise ValueError(f"Unknown source type: {source}")


def detect_source(location: str) -> str:
    if Path(location).exists():
        suffix = Path(location).suffix
        if suffix in (".yaml", ".yml"):
            return "custom"
        return "puzzle"

    location_lower = location.lower()
    if "kaggle.com" in location_lower:
        return "kaggle"
    if "devpost.com" in location_lower or "hackathon" in location_lower:
        return "hackathon"
    if "janestreet.com" in location_lower:
        return "puzzle"

    return "hackathon"  # Default: treat as generic web page


def _extract_kaggle_slug(url_or_slug: str) -> str:
    if "/" not in url_or_slug or not url_or_slug.startswith("http"):
        return url_or_slug
    # Expect https://www.kaggle.com/competitions/<slug>[/...]
    parts = url_or_slug.rstrip("/").split("/")
    if "competitions" not in parts:
        raise ValueError(
            f"Not a valid Kaggle competition URL: {url_or_slug!r}\n"
            "Expected form: https://www.kaggle.com/competitions/<slug>"
        )
    idx = parts.index("competitions")
    if idx + 1 >= len(parts) or not parts[idx + 1]:
        raise ValueError(
            f"Kaggle URL is missing a competition slug: {url_or_slug!r}"
        )
    return parts[idx + 1]


def _fetch_page(url: str) -> str:
    import subprocess
    try:
        result = subprocess.run(
            ["curl", "-sL", url],
            capture_output=True, text=True, timeout=30,
        )
        return result.stdout
    except Exception:
        return ""

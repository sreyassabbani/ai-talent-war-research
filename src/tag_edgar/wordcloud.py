"""Deterministic, dependency-free word-cloud rendering as self-contained SVG.

Layout uses fixed-frequency ordering and an archimedean spiral with deterministic
collision handling, so repeated runs on identical input are byte-identical. Clouds are
word-use summaries only; they never imply sentiment or outcomes by themselves.
"""

from __future__ import annotations

import hashlib
import html
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class CloudConfig:
    width: int = 800
    height: int = 400
    max_terms: int = 40
    min_font: float = 10.0
    max_font: float = 48.0
    seed_salt: str = "ai100-wordcloud"


def _color_for(term: str) -> str:
    digest = hashlib.sha256(f"{term}:{term}".encode()).hexdigest()
    return f"#{digest[:6]}"


def _spiral_positions(width: int, height: int):
    """Yield deterministic spiral positions from the canvas center outward."""
    center_x, center_y = width / 2, height / 2
    step = 2.5
    for t in range(20000):
        angle = 0.35 * (t**0.85)
        radius = step * t**0.72
        x = center_x + radius * math.cos(angle) * 1.15
        y = center_y + radius * math.sin(angle) * 0.62
        yield x, y


def render_svg(
    frequencies: dict[str, int], *, config: CloudConfig | None = None, title: str = ""
) -> str:
    cfg = config or CloudConfig()
    ordered = sorted(
        ((term, count) for term, count in frequencies.items() if count > 0),
        key=lambda item: (-item[1], item[0]),
    )[: cfg.max_terms]
    if not ordered:
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{cfg.width}" '
            f'height="{cfg.height}"><text x="10" y="30">no terms</text></svg>'
        )
    max_count = ordered[0][1]
    min_count = ordered[-1][1]
    span = max(max_count - min_count, 1)

    placed: list[tuple[float, float, float, float]] = []
    text_elements: list[str] = []
    positions = _spiral_positions(cfg.width, cfg.height)
    for term, count in ordered:
        scale = (count - min_count) / span
        font = round(cfg.min_font + scale * (cfg.max_font - cfg.min_font), 1)
        approx_width = font * 0.62 * len(term)
        approx_height = font * 1.25
        x = y = None
        for candidate_x, candidate_y in positions:
            left = candidate_x - approx_width / 2
            right = candidate_x + approx_width / 2
            top = candidate_y - approx_height / 2
            bottom = candidate_y + approx_height / 2
            if left < 4 or right > cfg.width - 4 or top < 4 or bottom > cfg.height - 4:
                continue
            if all(
                right < p_left or left > p_right or bottom < p_top or top > p_bottom
                for p_left, p_right, p_top, p_bottom in placed
            ):
                x, y = candidate_x, candidate_y
                break
        if x is None or y is None:
            continue
        placed.append(
            (
                x - approx_width / 2,
                x + approx_width / 2,
                y - approx_height / 2,
                y + approx_height / 2,
            )
        )
        escaped = html.escape(term)
        text_elements.append(
            f'<text x="{x:.1f}" y="{y:.1f}" font-family="Helvetica, Arial, sans-serif" '
            f'font-size="{font}" fill="{_color_for(term)}" text-anchor="middle">{escaped}</text>'
        )

    title_element = (
        f'<text x="12" y="20" font-size="16" fill="#333" '
        f'font-family="Helvetica, Arial, sans-serif">{html.escape(title)}</text>'
        if title
        else ""
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{cfg.width}" height="{cfg.height}">'
        f'<rect width="100%" height="100%" fill="#ffffff"/>{title_element}'
        f"{''.join(text_elements)}</svg>"
    )


def write_cloud_index(
    clouds: dict[str, dict[str, int]], out_html_path, *, config: CloudConfig | None = None
) -> str:
    """Render one SVG per cloud group and embed them in one standalone HTML page."""
    import pathlib

    cfg = config or CloudConfig()
    sections: list[str] = []
    for name in sorted(clouds):
        svg = render_svg(clouds[name], config=cfg, title=name)
        digest = hashlib.sha256(name.encode()).hexdigest()[:12]
        anchor = f"cloud_{digest}"
        sections.append(
            f'<h2 id="{anchor}">{html.escape(name)}</h2>'
            f"<figure><figcaption>Word-use salience for {html.escape(name)} "
            f"(frequency-scaled, deterministic layout)</figcaption>{svg}</figure>"
        )
    page = (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        "<title>AI-Deal Employee-Disclosure Word Clouds</title>"
        "<style>body{font-family:sans-serif;margin:24px}figure{margin:8px 0 24px}"
        "figcaption{font-size:13px;color:#555}</style></head><body>"
        "<h1>Word-use clouds — AI-deal employee passages</h1>"
        "<p>Clouds summarize which words appear most often in employee-related passages. "
        "They are descriptive word-frequency displays, not sentiment or outcome evidence.</p>"
        + "".join(sections)
        + "</body></html>"
    )
    path = pathlib.Path(out_html_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8")
    return str(path)


__all__ = ["CloudConfig", "render_svg", "write_cloud_index"]

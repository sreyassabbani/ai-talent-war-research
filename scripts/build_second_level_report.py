"""Write the second-level topic report: what sits inside each of the three themes.

The task Dr. Singh set on 2026-09-03: the three themes are "a broad classification, now we need
to narrow down within each class", and Theme 3 -- stock and equity -- matters most because it is
the theme that speaks to high-skilled workers.

This reads the sub-model directories produced by `scripts/run_topic_subsets.sh` and reports each
one against the same bar the parent model was held to, so a reader can see whether a second-level
split is as trustworthy as the first-level one it came from. Where a sub-model misses that bar,
the report says so in the same sentence as the result rather than in a footnote.

Usage:
    python scripts/build_second_level_report.py
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DERIVED = PROJECT_ROOT / "data" / "derived"

csv.field_size_limit(2**31 - 1)

#: The recovery-rate bar the parent model was judged against, set before that model was fitted.
STABILITY_BAR = 0.80

PARENT_THEMES = {
    "topic_1": ("Executive and officer language", "C-suite"),
    "topic_2": ("Benefit plans and retirement", "rank-and-file workers"),
    "topic_3": ("Stock and equity awards", "high-skilled workers"),
}

#: Reported first, because it is the one the advisor asked for by name.
REPORT_ORDER = ("topic_3", "topic_1", "topic_2")

#: Verified plain-English readings, keyed parent -> sub-theme. Written by reading passages, not
#: inferred from term lists, and kept out of this file so the interpretation is reviewable on its
#: own. Exemplar text is pulled from the corpus at render time and never transcribed by hand.
READINGS_PATH = PROJECT_ROOT / "docs" / "second_level_readings.json"

#: Longest exemplar quote to print. Long enough to show the provision, short enough to read.
EXEMPLAR_CHARS = 320


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def _number(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pct(value: float | None) -> str:
    return "not reported" if value is None else f"{value:.0%}"


def _fixed(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _terms(raw: str, limit: int = 8) -> str:
    return ", ".join(part for part in raw.split("|")[:limit] if part)


def _load_readings() -> dict[str, dict[str, dict[str, str]]]:
    if not READINGS_PATH.exists():
        return {}
    raw = json.loads(READINGS_PATH.read_text(encoding="utf-8"))
    return {key: value for key, value in raw.items() if not key.startswith("_")}


def _corpus_text(corpus_dir: Path) -> dict[str, tuple[str, str]]:
    """Passage id -> (document type, collapsed text) for pulling exemplar quotes."""
    path = corpus_dir / "passages.csv"
    if not path.exists():
        return {}
    return {
        row["passage_id"]: (row.get("document_type", ""), " ".join((row.get("text") or "").split()))
        for row in _read(path)
    }


def load_submodel(topics_dir: Path, corpus_dir: Path) -> dict[str, object] | None:
    summary_path = topics_dir / "topic_summary.csv"
    if not summary_path.exists():
        return None
    subset_manifest_path = corpus_dir / "subset_manifest.json"
    manifest_path = topics_dir / "analysis_manifest.json"
    return {
        "corpus_text": _corpus_text(corpus_dir),
        "topics": _read(summary_path),
        "diagnostics": _read(topics_dir / "model_diagnostics.csv")
        if (topics_dir / "model_diagnostics.csv").exists()
        else [],
        "deal_topics": _read(topics_dir / "deal_topic_matrix.csv")
        if (topics_dir / "deal_topic_matrix.csv").exists()
        else [],
        "subset": json.loads(subset_manifest_path.read_text(encoding="utf-8"))
        if subset_manifest_path.exists()
        else {},
        "manifest": json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.exists()
        else {},
    }


def _deal_spread(deal_topics: list[dict[str, str]]) -> tuple[int, int, float]:
    """Deals covered, deals with a sub-theme above half their weight, and the median top share."""
    by_deal: dict[str, list[float]] = defaultdict(list)
    for row in deal_topics:
        value = _number(row.get("normalized_weight", ""))
        if value is not None:
            by_deal[row["deal_id"]].append(value)
    tops = sorted(max(values) for values in by_deal.values() if values)
    dominant = sum(1 for value in tops if value > 0.5)
    median = tops[len(tops) // 2] if tops else 0.0
    return len(by_deal), dominant, median


def render(models: dict[str, dict[str, object] | None]) -> str:
    lines = [
        "# Inside the three themes: second-level topics",
        "",
        (
            f"Generated {datetime.now(tz=UTC).date().isoformat()} by "
            "`scripts/build_second_level_report.py`."
        ),
        "",
        "Dr. Singh, 2026-09-03:",
        "",
        (
            "> This is the broad 3 themes ... now we need to go deeper into each of those discussions "
            "and ask, how we can differentiate within those discussions. ... Especially the Theme 3, "
            "and see what we get."
        ),
        "",
        (
            "Each first-level theme was cut out of the corpus and modelled again on its own, using the "
            "same fitting pipeline and the same settings as the parent run. So every diagnostic below "
            "means what the parent model's diagnostic of the same name means."
        ),
        "",
        (
            "Each sub-theme carries a plain-English **reading**, written after reading its passages "
            "rather than inferred from its term list. A reading is our interpretation. The quote "
            "beneath it is the filing's own words, pulled from the corpus at render time."
        ),
        "",
        (
            "**Read the stability column before the terms.** A sub-theme whose recovery rate is below "
            f"{STABILITY_BAR:.0%} did not survive the leave-one-deal-out test, and its terms are a "
            "description of this particular corpus rather than a finding that would reappear."
        ),
        "",
    ]

    for parent_id in REPORT_ORDER:
        title, workers = PARENT_THEMES[parent_id]
        model = models.get(parent_id)
        lines += [f"## {title} (`{parent_id}`)", ""]
        if model is None:
            lines += [
                "Not yet fitted. Run `bash scripts/run_topic_subsets.sh`.",
                "",
            ]
            continue

        subset = model["subset"] if isinstance(model["subset"], dict) else {}
        topics = model["topics"] if isinstance(model["topics"], list) else []
        deal_topics = model["deal_topics"] if isinstance(model["deal_topics"], list) else []

        passage_count = subset.get("passage_count", "?")
        share = subset.get("share_of_parent_corpus")
        share_text = f" ({share:.1%} of the modelled corpus)" if isinstance(share, float) else ""
        lines += [
            (
                f"In the parent model this theme covers **{passage_count} passages**{share_text}, "
                f"and Dr. Singh read it as the language aimed at **{workers}**."
            ),
            "",
            f"Modelling those passages alone produced **{len(topics)} sub-themes**:",
            "",
            "| Sub-theme | Passages | Defining terms | Coherence | Stability | Survives? |",
            "| --- | ---: | --- | ---: | ---: | --- |",
        ]
        for row in topics:
            recovery = _number(row.get("stability_recovery_rate", ""))
            survives = (
                "not reported"
                if recovery is None
                else ("yes" if recovery >= STABILITY_BAR else "**no**")
            )
            lines.append(
                f"| `{row['topic_id']}` | {row.get('primary_passage_count', '?')} | "
                f"{_terms(row.get('top_terms', ''))} | "
                f"{_fixed(_number(row.get('coherence', '')))} | {_pct(recovery)} | {survives} |"
            )

        readings = _load_readings().get(parent_id, {})
        corpus_text = model["corpus_text"] if isinstance(model["corpus_text"], dict) else {}
        for row in topics:
            reading = readings.get(row["topic_id"])
            if not reading:
                continue
            lines += ["", f"**`{row['topic_id']}` — {reading['label']}.** {reading['reading']}"]
            exemplar = corpus_text.get(reading.get("exemplar_passage_id", ""))
            if exemplar:
                document_type, text = exemplar
                clipped = (
                    text[: EXEMPLAR_CHARS - 1].rstrip() + "…"
                    if len(text) > EXEMPLAR_CHARS
                    else text
                )
                lines += ["", f"> {clipped}", "", f"> — {document_type}, filed text"]

        covered, dominant, median_top = _deal_spread(deal_topics)
        if covered:
            lines += [
                "",
                (
                    f"Across the {covered} deals this theme reaches, the largest sub-theme share in a "
                    f"deal is **{median_top:.0%} at the median**, and **{dominant} of {covered} deals** "
                    "have one sub-theme above half their weight within the theme."
                ),
            ]

        weak = [
            row["topic_id"]
            for row in topics
            if (value := _number(row.get("stability_recovery_rate", ""))) is not None
            and value < STABILITY_BAR
        ]
        if weak:
            lines += [
                "",
                (
                    f"**{len(weak)} of {len(topics)} sub-themes fail the {STABILITY_BAR:.0%} "
                    f"stability bar** ({', '.join('`' + item + '`' for item in weak)}). They are "
                    "reported because suppressing them would make the split look cleaner than it is, "
                    "not because they are ready to carry an argument."
                ),
            ]
        lines.append("")

    lines += [
        "## What this does not establish",
        "",
        (
            "- A sub-theme is a pattern in disclosed language. It is not a category of deal, a "
            "category of employee, or an outcome for anybody."
        ),
        (
            "- Sub-themes inherit every selection property of the parent sample, including that a "
            "deal only appears when its buyer filed with the SEC."
        ),
        (
            "- The 150-passage relevance audit is still unread. Nothing here is a validated finding, "
            "and a filter that keeps the wrong passages would produce clean sub-themes of the wrong "
            "text."
        ),
        (
            "- Second-level topic numbers are local to their parent. `topic_1` inside Theme 3 has no "
            "relationship to `topic_1` of the parent model."
        ),
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").strip())
    parser.add_argument("--derived", type=Path, default=DERIVED)
    parser.add_argument(
        "--output", type=Path, default=PROJECT_ROOT / "docs" / "second_level_topics.md"
    )
    args = parser.parse_args(argv[1:])

    models: dict[str, dict[str, object] | None] = {}
    for parent_id in PARENT_THEMES:
        suffix = parent_id.replace("topic_", "t")
        models[parent_id] = load_submodel(
            args.derived / f"employee_topics_100_{suffix}",
            args.derived / f"employee_corpus_100_{suffix}",
        )

    fitted = [key for key, value in models.items() if value is not None]
    if not fitted:
        print("No sub-models found. Run: bash scripts/run_topic_subsets.sh", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(models), encoding="utf-8")
    print(f"Fitted sub-models: {', '.join(sorted(fitted))}")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

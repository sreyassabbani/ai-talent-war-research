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

#: Written after all three splits were in hand. Interpretation, not output: it is kept here rather
#: than generated so it is reviewable as a claim, and it is printed only when all three sub-models
#: exist, because it is a statement about the pattern across them.
#: The claim the synthesis makes. It is kept as prose because it is an interpretation and should
#: be reviewable as one; the evidence under it is generated, because an earlier version hardcoded
#: six stability figures and two sub-theme names, and a refit made all six numbers wrong and
#: dissolved both of the named components.
SYNTHESIS_THESIS = (
    "Read the nine sub-themes together and one pattern runs through all three parents: "
    "**what survives the stability test is the language that is templated across deals, and "
    "what fails is the language that varies with the particular workforce.**"
)

SYNTHESIS_CLOSING = [
    (
        "**This matters for how the numbers are read.** A high recovery rate here means a phrase "
        "recurs across deals, not that the provision is important, common, or generous. Where a "
        "sub-theme about what happens to a particular workforce scores low, that is a fact about "
        "how much such terms vary between deals, not evidence that they matter less."
    ),
    "",
    (
        "It also means leave-one-deal-out stability is the wrong instrument for finding the "
        "provisions that distinguish deals from one another. It rewards sameness by "
        "construction. A measure of *variation* across deals would be a better next step than a "
        "third level of clustering."
    ),
    "",
]


def _synthesis(
    models: dict[str, dict[str, object] | None], readings: dict[str, dict[str, dict[str, str]]]
) -> list[str]:
    """The cross-parent pattern, with the ranked evidence computed from the models themselves."""
    ranked: list[tuple[float, str]] = []
    for parent_id in PARENT_THEMES:
        model = models.get(parent_id)
        if model is None:
            continue
        for topic_id, terms, _coherence, stability in _stability_rows(model):
            if stability is None:
                continue
            label = readings.get(parent_id, {}).get(topic_id, {}).get("label")
            name = label or terms
            ranked.append((stability, f"{name} ({_pct(stability)})"))
    if len(ranked) < 6:
        return []
    ranked.sort(reverse=True)
    top = "; ".join(name for _, name in ranked[:3])
    bottom = "; ".join(name for _, name in reversed(ranked[-3:]))
    return [
        "## What the splits have in common",
        "",
        SYNTHESIS_THESIS,
        "",
        f"The three most stable sub-themes across all parents are {top}.",
        "",
        f"The three least stable are {bottom}.",
        "",
        (
            "A sub-theme without a carried reading is named by its leading terms, because naming "
            "it anything else would be inventing an interpretation to fill a table."
        ),
        "",
        *SYNTHESIS_CLOSING,
    ]


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def _number(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pct(value: float | None) -> str:
    # One decimal, because the bar sits at 80% and a recovery rate of 0.797 rendered as "80%"
    # next to a "no" verdict reads as a contradiction rather than a near miss.
    return "not reported" if value is None else f"{value:.1%}"


def _fixed(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _terms(raw: str, limit: int = 8) -> str:
    return ", ".join(part for part in raw.split("|")[:limit] if part)


def _load_readings(path: Path | None = None) -> dict[str, dict[str, dict[str, str]]]:
    target = path or READINGS_PATH
    if not target.exists():
        return {}
    raw = json.loads(target.read_text(encoding="utf-8"))
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


def _stability_rows(
    model: dict[str, object] | None,
) -> list[tuple[str, str, float | None, float | None]]:
    topics = model["topics"] if model and isinstance(model["topics"], list) else []
    return [
        (
            row["topic_id"],
            _terms(row.get("top_terms", ""), 3),
            _number(row.get("coherence", "")),
            _number(row.get("stability_recovery_rate", "")),
        )
        for row in topics
    ]


def _sensitivity_section(
    baseline: dict[str, object] | None, without_pr: dict[str, object] | None
) -> list[str]:
    """Theme 1 fitted with and without press releases, side by side.

    Reported as a pair rather than as a replacement result: the question is whether the split
    changes, and that is only answerable by showing both.
    """
    if baseline is None or without_pr is None:
        return []
    base_rows = _stability_rows(baseline)
    alt_rows = _stability_rows(without_pr)
    subset = without_pr["subset"] if isinstance(without_pr["subset"], dict) else {}
    dropped = subset.get("excluded_by_document_type", "?")

    passed_base = sum(
        1 for _, _, _, stab in base_rows if stab is not None and stab >= STABILITY_BAR
    )
    passed_alt = sum(1 for _, _, _, stab in alt_rows if stab is not None and stab >= STABILITY_BAR)

    lines = [
        "## Sensitivity: Theme 1 without press releases",
        "",
        (
            f"Theme 1 mixes merger-agreement text with {dropped} EX-99 press-release passages. "
            "Refitting it with those dropped tests whether it is one theme or two document "
            "registers sharing a bucket."
        ),
        "",
        "| | Sub-theme (top terms) | Passages | Coherence | Stability |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for label, rows, model in (
        ("with", base_rows, baseline),
        ("without", alt_rows, without_pr),
    ):
        topics = model["topics"] if isinstance(model["topics"], list) else []
        for (topic_id, terms, coherence, stability), row in zip(rows, topics, strict=False):
            lines.append(
                f"| {label} EX-99 | `{topic_id}` {terms} | "
                f"{row.get('primary_passage_count', '?')} | {_fixed(coherence)} | "
                f"{_pct(stability)} |"
            )

    # Everything below is computed. An earlier version stated the direction of this result in
    # prose -- that dropping press releases stabilised the split, and that EX-99 should therefore
    # be excluded. That was true of the cycle it was written for and false in the next one, where
    # the same comparison reverses. A conclusion that flips between corpora cannot be a constant.
    base_stats = [stab for _, _, _, stab in base_rows if stab is not None]
    alt_stats = [stab for _, _, _, stab in alt_rows if stab is not None]
    base_mean = sum(base_stats) / len(base_stats) if base_stats else 0.0
    alt_mean = sum(alt_stats) / len(alt_stats) if alt_stats else 0.0
    delta = passed_alt - passed_base
    direction = (
        "more sub-themes clear the bar without press releases"
        if delta > 0
        else "fewer sub-themes clear the bar without press releases"
        if delta < 0
        else "the same number of sub-themes clear the bar either way"
    )

    lines += [
        "",
        (
            f"**On this corpus, {direction}.** {passed_base} of {len(base_rows)} sub-themes clear "
            f"the {STABILITY_BAR:.0%} bar with press releases in; {passed_alt} of {len(alt_rows)} "
            f"clear it with them out. Mean recovery moves from {base_mean:.1%} to {alt_mean:.1%}."
        ),
        "",
        (
            "The two fits are separate models, so their sub-themes are not paired and a row here "
            "cannot be read across the table as the same group before and after. What the "
            "comparison supports is whether the split as a whole holds up, not what happened to "
            "any one sub-theme."
        ),
        "",
        (
            "**This is a corpus decision and it is still open.** Whether EX-99 announcements "
            "belong in the modelled corpus, or should be modelled separately from contract text, "
            "is a question about what the study is measuring rather than a setting to be tuned to "
            "whichever value scores better on this page."
        ),
        "",
    ]
    return lines


def render(
    models: dict[str, dict[str, object] | None], readings_path: Path | None = None
) -> str:
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

        readings = _load_readings(readings_path).get(parent_id, {})
        corpus_text = model["corpus_text"] if isinstance(model["corpus_text"], dict) else {}
        unread = [row["topic_id"] for row in topics if not readings.get(row["topic_id"])]
        if unread and readings:
            # Silence would read as "no interpretation offered" rather than "this component is
            # not the one the earlier reading described", which is the actual situation whenever
            # a refit renumbers or reorganises the sub-themes.
            lines += [
                "",
                (
                    f"No plain-English reading is carried for {', '.join(f'`{t}`' for t in unread)}: "
                    "these sub-themes do not match a component any earlier reading was written "
                    "about, so anything said about them here would be a description of a term "
                    "list rather than of passages somebody read."
                ),
            ]
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

    lines += _sensitivity_section(models.get("topic_1"), models.get("topic_1_nopr"))

    if all(models.get(key) is not None for key in PARENT_THEMES):
        lines += _synthesis(models, _load_readings(readings_path))

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
        "--topics-prefix",
        type=Path,
        default=None,
        help=(
            "Parent topic-model directory. Sub-models are read from this path with _t1, _t2, _t3 "
            "and _t1_nopr appended, matching what run_topic_subsets.sh writes. "
            "Defaults to <derived>/employee_topics_100."
        ),
    )
    parser.add_argument(
        "--corpus-prefix",
        type=Path,
        default=None,
        help="Parent corpus directory, suffixed the same way. Defaults to "
        "<derived>/employee_corpus_100.",
    )
    parser.add_argument(
        "--readings",
        type=Path,
        default=None,
        help=(
            "Plain-English sub-theme readings. Second-level topic numbers are assigned by the fit "
            "and are not stable across cycles, so a refit needs its own file. Defaults to "
            "docs/second_level_readings.json."
        ),
    )
    parser.add_argument(
        "--output", type=Path, default=PROJECT_ROOT / "docs" / "second_level_topics.md"
    )
    args = parser.parse_args(argv[1:])

    # A prefix is a directory path with a suffix appended, not a parent directory, so the sibling
    # naming from run_topic_subsets.sh is reproduced here rather than reinvented.
    topics_prefix = args.topics_prefix or (args.derived / "employee_topics_100")
    corpus_prefix = args.corpus_prefix or (args.derived / "employee_corpus_100")

    def suffixed(prefix: Path, suffix: str) -> Path:
        return prefix.with_name(f"{prefix.name}_{suffix}")

    models: dict[str, dict[str, object] | None] = {}
    for parent_id in PARENT_THEMES:
        suffix = parent_id.replace("topic_", "t")
        models[parent_id] = load_submodel(
            suffixed(topics_prefix, suffix),
            suffixed(corpus_prefix, suffix),
        )
    models["topic_1_nopr"] = load_submodel(
        suffixed(topics_prefix, "t1_nopr"),
        suffixed(corpus_prefix, "t1_nopr"),
    )

    fitted = [key for key, value in models.items() if value is not None]
    if not fitted:
        print("No sub-models found. Run: bash scripts/run_topic_subsets.sh", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(models, args.readings), encoding="utf-8")
    print(f"Fitted sub-models: {', '.join(sorted(fitted))}")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

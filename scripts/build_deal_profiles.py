"""One row per modelled deal: its theme mix, its dominant theme, its AI label, and its size.

Dr. Singh, 2026-09-03: "each deal has to be categorized ... but what you did is you categorized
the full data into three." The topic model does produce per-deal theme shares, but they were
spread across three files and never presented as a deal-level table, so the answer to his
question existed and could not be shown.

This is that table. Each of the 133 modelled deals gets its share of each theme, the theme that
dominates it, how concentrated the mix is, and the deal facts needed to read the row.

On the dominant theme: it is the largest share, and `dominant_margin` is how far it sits above
the runner-up. A deal whose margin is small is genuinely mixed, and calling it by its dominant
theme would overstate what the model found. `theme_profile` states that plainly rather than
leaving a reader to work it out from the numbers -- a deal is only labelled by one theme when
that theme leads by a real margin, and is called "mixed" otherwise.

Usage:
    python scripts/build_deal_profiles.py
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DERIVED = PROJECT_ROOT / "data" / "derived"

MODELLED_STATUS = "modelled"

#: Below this lead over the runner-up a deal is called mixed rather than named by one theme.
#: Set before looking at the distribution: a tenth of the total weight is the smallest gap that
#: still reads as a real difference when shares are thirds.
DOMINANCE_MARGIN = 0.10

TOPIC_LABELS = {
    "topic_1": "executive_and_officer",
    "topic_2": "benefit_plans_and_retirement",
    "topic_3": "stock_and_equity_awards",
}

FIELDS = (
    "deal_id",
    "acquirer_name",
    "target_name",
    "announcement_date",
    "effective_date",
    "transaction_value_mil",
    "target_public_status",
    "included_passages",
    "documents_retrieved",
    "topic_1_share",
    "topic_2_share",
    "topic_3_share",
    "dominant_topic",
    "dominant_topic_label",
    "dominant_share",
    "dominant_margin",
    "concentration_hhi",
    "theme_profile",
    "ai_label",
    "talent_join_language",
    "talent_acquihire_explicit",
    "talent_license_and_hire_explicit",
)


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _number(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _fmt(value: float) -> str:
    return f"{value:.6f}"


def build_profiles(
    frozen_sample_csv: Path, deal_topic_csv: Path, ai_labels_csv: Path
) -> list[dict[str, str]]:
    deals = {
        row["deal_id"]: row
        for row in _read(frozen_sample_csv)
        if row.get("sample_status", "").strip() == MODELLED_STATUS
    }
    ai_labels = {row["deal_id"]: row for row in _read(ai_labels_csv)}

    shares: dict[str, dict[str, float]] = defaultdict(dict)
    for row in _read(deal_topic_csv):
        shares[row["deal_id"]][row["topic_id"]] = _number(row.get("normalized_weight", ""))

    profiles: list[dict[str, str]] = []
    for deal_id in sorted(deals):
        deal = deals[deal_id]
        mix = shares.get(deal_id)
        if not mix:
            # A modelled deal with no topic row would mean the freeze and the model disagree
            # about the sample. Fail rather than emit a row with three blank shares.
            raise ValueError(
                f"Deal {deal_id} is modelled but has no rows in {deal_topic_csv.name}."
            )

        ranked = sorted(mix.items(), key=lambda item: (-item[1], item[0]))
        top_topic, top_share = ranked[0]
        runner_up = ranked[1][1] if len(ranked) > 1 else 0.0
        margin = top_share - runner_up
        concentrated = margin >= DOMINANCE_MARGIN
        ai = ai_labels.get(deal_id, {})

        profiles.append(
            {
                "deal_id": deal_id,
                "acquirer_name": deal.get("acquirer_name", ""),
                "target_name": deal.get("target_name", ""),
                "announcement_date": deal.get("announcement_date", ""),
                "effective_date": deal.get("effective_date", ""),
                "transaction_value_mil": deal.get("transaction_value_mil", ""),
                "target_public_status": deal.get("target_public_status", ""),
                "included_passages": deal.get("included_passages", ""),
                "documents_retrieved": deal.get("documents_retrieved", ""),
                "topic_1_share": _fmt(mix.get("topic_1", 0.0)),
                "topic_2_share": _fmt(mix.get("topic_2", 0.0)),
                "topic_3_share": _fmt(mix.get("topic_3", 0.0)),
                "dominant_topic": top_topic,
                "dominant_topic_label": TOPIC_LABELS.get(top_topic, top_topic),
                "dominant_share": _fmt(top_share),
                "dominant_margin": _fmt(margin),
                "concentration_hhi": _fmt(sum(value**2 for value in mix.values())),
                "theme_profile": TOPIC_LABELS.get(top_topic, top_topic)
                if concentrated
                else "mixed",
                "ai_label": ai.get("ai_label", "unknown"),
                "talent_join_language": ai.get("talent_join_language", "unknown"),
                "talent_acquihire_explicit": ai.get("talent_acquihire_explicit", "unknown"),
                "talent_license_and_hire_explicit": ai.get(
                    "talent_license_and_hire_explicit", "unknown"
                ),
            }
        )
    return profiles


def summarize(profiles: list[dict[str, str]]) -> dict[str, object]:
    dominant = defaultdict(int)
    profile_counts = defaultdict(int)
    ai_counts = defaultdict(int)
    for row in profiles:
        dominant[row["dominant_topic"]] += 1
        profile_counts[row["theme_profile"]] += 1
        ai_counts[row["ai_label"]] += 1
    margins = sorted(_number(row["dominant_margin"]) for row in profiles)
    median = margins[len(margins) // 2] if margins else 0.0
    return {
        "deals": len(profiles),
        "dominant_topic_counts": dict(sorted(dominant.items())),
        "theme_profile_counts": dict(sorted(profile_counts.items())),
        "ai_label_counts": dict(sorted(ai_counts.items())),
        "median_dominant_margin": round(median, 6),
        "dominance_margin_threshold": DOMINANCE_MARGIN,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").strip())
    parser.add_argument(
        "--frozen-sample",
        type=Path,
        default=DERIVED / "disclosure_frozen_sample" / "frozen_sample.csv",
    )
    parser.add_argument(
        "--deal-topic-matrix",
        type=Path,
        default=DERIVED / "employee_topics_100" / "deal_topic_matrix.csv",
    )
    parser.add_argument(
        "--ai-labels", type=Path, default=DERIVED / "deal_ai_labels" / "deal_ai_labels.csv"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "published" / "disclosure_sample_133",
    )
    args = parser.parse_args(argv[1:])

    inputs = (args.frozen_sample, args.deal_topic_matrix, args.ai_labels)
    missing = [str(path) for path in inputs if not path.exists()]
    if missing:
        print("Missing inputs; run the analysis first:", file=sys.stderr)
        for item in missing:
            print(f"  {item}", file=sys.stderr)
        return 1

    profiles = build_profiles(args.frozen_sample, args.deal_topic_matrix, args.ai_labels)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / "09_deal_profiles.csv"
    with output.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(FIELDS))
        writer.writeheader()
        writer.writerows(profiles)

    summary = summarize(profiles)
    summary.update(
        {
            "schema_version": 1,
            "written": datetime.now(tz=UTC).isoformat(timespec="seconds"),
            "output_sha256": _sha256(output),
            "evidence_boundary": (
                "A theme share is how much of a deal's disclosed employee language falls in a "
                "theme. It is not how much the buyer spent, promised, or delivered on that "
                "theme, and a deal that discusses equity at length has not thereby been shown "
                "to treat employees better than one that does not."
            ),
        }
    )
    (args.output_dir / "09_deal_profiles_manifest.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(f"Deals: {summary['deals']}")
    print(f"Dominant theme: {summary['dominant_topic_counts']}")
    print(f"Theme profile:  {summary['theme_profile_counts']}")
    print(f"AI label:       {summary['ai_label_counts']}")
    print(f"Median dominant margin: {summary['median_dominant_margin']:.3f}")
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

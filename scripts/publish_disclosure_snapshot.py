"""Publish the small result tables behind the 133-deal report into source control.

`data/derived/` is git-ignored, so everything the report cites lives only on the machine that
ran it. That is how the cycle-5 artifacts ended up travelling in zip files. This copies the
result tables, which are small, into `data/published/` so a reader can check any number in the
report against the file it came from.

What is deliberately left out: the passage corpus, the HTTP cache, and the raw SDC archive. The
corpus is 117 MB of SEC body text and the archive is licensed vendor data. Everything published
here is derived metadata and model output.

Usage:
    python scripts/publish_disclosure_snapshot.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DERIVED = PROJECT_ROOT / "data" / "derived"

# (source, published name). Order follows the pipeline, so the directory reads as the funnel.
ARTIFACTS: tuple[tuple[Path, str], ...] = (
    (DERIVED / "disclosure_pool" / "pool_manifest.json", "01_pool_manifest.json"),
    (DERIVED / "disclosure_probe" / "probe_results.csv", "02_probe_results.csv"),
    (DERIVED / "disclosure_probe" / "probe_manifest.json", "02_probe_manifest.json"),
    (DERIVED / "employee_corpus_100" / "corpus_manifest.json", "03_corpus_manifest.json"),
    (DERIVED / "disclosure_frozen_sample" / "frozen_sample.csv", "04_frozen_sample.csv"),
    (
        DERIVED / "disclosure_frozen_sample" / "frozen_sample_manifest.json",
        "04_frozen_sample_manifest.json",
    ),
    (DERIVED / "deal_ai_labels" / "deal_ai_labels.csv", "05_deal_ai_labels.csv"),
    (DERIVED / "employee_topics_100" / "topic_summary.csv", "06_topic_summary.csv"),
    (DERIVED / "employee_topics_100" / "deal_topic_matrix.csv", "06_deal_topic_matrix.csv"),
    (DERIVED / "employee_topics_100" / "model_diagnostics.csv", "06_model_diagnostics.csv"),
    (DERIVED / "employee_topics_100" / "analysis_manifest.json", "06_analysis_manifest.json"),
    (DERIVED / "employee_tone_100" / "deal_tone_summary.csv", "07_deal_tone_summary.csv"),
)

EXCLUDED = (
    ("employee_corpus_100/passages.csv", "117 MB of SEC body text"),
    ("disclosure_runs/", "35,296 retrieved documents"),
    ("cache/http/", "the HTTP cache, about 520 MB"),
    ("the SDC/Thomson archive", "licensed vendor data"),
)

MAX_PUBLISHED_BYTES = 5 * 1024 * 1024


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


#: Written by this script itself, so not companions.
_SELF_WRITTEN = frozenset({"README.md", "snapshot_manifest.json"})

COMPANION_SCRIPTS = (
    ("08_passage_links*", "scripts/publish_passage_links.py", "passage text with SEC deep links"),
    ("09_deal_profiles*", "scripts/build_deal_profiles.py", "one row per modelled deal"),
)


def _companions(target: Path, published: set[str]) -> list[tuple[str, int]]:
    """Files in the directory this script did not write.

    The README is regenerated on every publish. Without this, a re-publish would silently drop
    every mention of the tables the sibling scripts wrote, and a reader would conclude they
    were withdrawn rather than simply written by a different command.
    """
    if not target.exists():
        return []
    extra = [
        path
        for path in sorted(target.iterdir())
        if path.is_file() and path.name not in published and path.name not in _SELF_WRITTEN
    ]
    return [(path.name, path.stat().st_size) for path in extra]


def readme(published: list[tuple[str, int, str]], target: Path) -> str:
    lines = [
        "# Disclosure-first sample: published result tables",
        "",
        "The small tables behind `docs/disclosure_sample_report.md`, copied out of the",
        "git-ignored `data/derived/` so every number in the report can be checked against the",
        "file it came from.",
        "",
        f"Snapshot written {datetime.now(tz=UTC).date().isoformat()} by",
        "`scripts/publish_disclosure_snapshot.py`. Re-running that script refreshes it.",
        "",
        "## What is here",
        "",
        "| File | Size | SHA-256 (first 16) |",
        "| --- | ---: | --- |",
    ]
    for name, size, digest in published:
        lines.append(f"| `{name}` | {size // 1024} KB | `{digest[:16]}` |")
    companions = _companions(target, {name for name, _, _ in published})
    if companions:
        lines += [
            "",
            "Written by the sibling scripts rather than by this one:",
            "",
            "| File | Size |",
            "| --- | ---: |",
        ]
        for name, size in companions:
            lines.append(f"| `{name}` | {size // 1024} KB |")
        lines += ["", "Rebuild them with:", ""]
        for pattern, script, purpose in COMPANION_SCRIPTS:
            lines.append(f"- `python {script}` — {pattern}, {purpose}.")

    lines += [
        "",
        "The numbered prefixes follow the pipeline: pool, probe, corpus, frozen sample, AI",
        "labels, topic model, tone, passage links, deal profiles.",
        "",
        "## What is not here, and why",
        "",
    ]
    for item, reason in EXCLUDED:
        lines.append(f"- `{item}` — {reason}.")
    lines += [
        "",
        "## Evidence boundary",
        "",
        "These are disclosed contract and filing terms, not employee outcomes. The sample is",
        "selected by whether a buyer filed with the SEC, so it is not representative of",
        "acquisitions generally. The corpus relevance audit was not run for this cycle, so no",
        "table here is a validated finding. AI labels and archetype suggestions are machine-",
        "derived and pending human review.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").strip())
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "published" / "disclosure_sample_133",
    )
    args = parser.parse_args(argv[1:])

    missing = [str(source) for source, _ in ARTIFACTS if not source.exists()]
    if missing:
        print("Missing artifacts; run the analysis first:", file=sys.stderr)
        for item in missing:
            print(f"  {item}", file=sys.stderr)
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    published: list[tuple[str, int, str]] = []
    total = 0
    for source, name in ARTIFACTS:
        size = source.stat().st_size
        if size > MAX_PUBLISHED_BYTES:
            # A guard, not a formality: this directory exists because large files do not belong
            # in git, and an artifact that grows past the cap must be reconsidered, not copied.
            print(f"Refusing to publish {source} at {size // 1024} KB.", file=sys.stderr)
            return 1
        shutil.copyfile(source, args.output_dir / name)
        published.append((name, size, sha256(source)))
        total += size

    (args.output_dir / "README.md").write_text(readme(published, args.output_dir), encoding="utf-8")
    (args.output_dir / "snapshot_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "files": [
                    {"name": name, "bytes": size, "sha256": digest}
                    for name, size, digest in published
                ],
                "total_bytes": total,
                "excluded": [{"path": item, "reason": reason} for item, reason in EXCLUDED],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Published {len(published)} files ({total // 1024} KB) to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

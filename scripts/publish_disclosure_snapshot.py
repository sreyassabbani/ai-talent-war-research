"""Publish the small result tables behind the 133-deal report into source control.

`data/derived/` is git-ignored, so everything the report cites lives only on the machine that
ran it. That is how the cycle-5 artifacts ended up travelling in zip files. This copies the
result tables, which are small, into `data/published/` so a reader can check any number in the
report against the file it came from.

What is deliberately left out: the passage corpus, the HTTP cache, and the raw SDC archive. The
corpus is over 100 MB of SEC body text and the archive is licensed vendor data. Everything
published here is derived metadata and model output.

The input directories default to the cycle-5 run and are all overridable, so a later cycle
publishes a new numbered snapshot without this file being edited.

Usage:
    python scripts/publish_disclosure_snapshot.py
    python scripts/publish_disclosure_snapshot.py \\
        --corpus-dir data/derived/employee_corpus_c6 \\
        --topics-dir data/derived/employee_topics_c6 \\
        --frozen-dir data/derived/disclosure_frozen_sample_c6 \\
        --ai-labels-dir data/derived/deal_ai_labels_c6 \\
        --tone-dir data/derived/employee_tone_c6 \\
        --report docs/disclosure_sample_report_c6.md \\
        --output-dir data/published/disclosure_sample_<n>
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

#: Default input directories: the cycle-5 run. A later cycle writes to parallel directories and
#: passes them in, so this script is not rewritten once per cycle.
DEFAULT_DIRS: dict[str, Path] = {
    "pool": DERIVED / "disclosure_pool",
    "probe": DERIVED / "disclosure_probe",
    "corpus": DERIVED / "employee_corpus_100",
    "frozen": DERIVED / "disclosure_frozen_sample",
    "ai_labels": DERIVED / "deal_ai_labels",
    "topics": DERIVED / "employee_topics_100",
    "tone": DERIVED / "employee_tone_100",
}


def artifacts(dirs: dict[str, Path]) -> tuple[tuple[Path, str], ...]:
    """(source, published name). Order follows the pipeline, so the directory reads as the funnel.

    The published names carry no cycle tag. A snapshot directory is one cycle's record, and the
    tag lives in that directory's name, so two snapshots stay diffable file by file.
    """
    return (
        (dirs["pool"] / "pool_manifest.json", "01_pool_manifest.json"),
        (dirs["probe"] / "probe_results.csv", "02_probe_results.csv"),
        (dirs["probe"] / "probe_manifest.json", "02_probe_manifest.json"),
        (dirs["corpus"] / "corpus_manifest.json", "03_corpus_manifest.json"),
        (dirs["frozen"] / "frozen_sample.csv", "04_frozen_sample.csv"),
        (dirs["frozen"] / "frozen_sample_manifest.json", "04_frozen_sample_manifest.json"),
        (dirs["ai_labels"] / "deal_ai_labels.csv", "05_deal_ai_labels.csv"),
        (dirs["topics"] / "topic_summary.csv", "06_topic_summary.csv"),
        (dirs["topics"] / "deal_topic_matrix.csv", "06_deal_topic_matrix.csv"),
        (dirs["topics"] / "model_diagnostics.csv", "06_model_diagnostics.csv"),
        (dirs["topics"] / "analysis_manifest.json", "06_analysis_manifest.json"),
        (dirs["tone"] / "deal_tone_summary.csv", "07_deal_tone_summary.csv"),
    )


def excluded(dirs: dict[str, Path]) -> tuple[tuple[str, str], ...]:
    """What is deliberately not copied. The corpus size is measured, not remembered.

    The passage file grew and shrank across cycles, so a hardcoded size would be wrong for any
    cycle but the one it was written for.
    """
    passages = dirs["corpus"] / "passages.csv"
    size = (
        f"{passages.stat().st_size // (1024 * 1024)} MB of SEC body text"
        if passages.exists()
        else "SEC body text"
    )
    return (
        (f"{dirs['corpus'].name}/passages.csv", size),
        ("disclosure_runs/", "35,296 retrieved documents"),
        ("cache/http/", "the HTTP cache, about 520 MB"),
        ("the SDC/Thomson archive", "licensed vendor data"),
    )

MAX_PUBLISHED_BYTES = 5 * 1024 * 1024


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relative(path: Path) -> str:
    """Repo-relative, forward-slashed. This manifest is committed and read on GitHub, so an
    absolute path would publish one machine's directory layout and mean nothing to a reader."""
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


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


def readme(
    published: list[tuple[str, int, str]],
    target: Path,
    report: str,
    excluded_items: tuple[tuple[str, str], ...],
) -> str:
    lines = [
        "# Disclosure-first sample: published result tables",
        "",
        f"The small tables behind `{report}`, copied out of the",
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
    for item, reason in excluded_items:
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
    for key, default in DEFAULT_DIRS.items():
        parser.add_argument(
            f"--{key.replace('_', '-')}-dir", type=Path, default=default, dest=f"{key}_dir"
        )
    parser.add_argument(
        "--report",
        default="docs/disclosure_sample_report.md",
        help="Report this snapshot backs, named in the README so a reader lands on the right one.",
    )
    args = parser.parse_args(argv[1:])

    dirs = {key: getattr(args, f"{key}_dir") for key in DEFAULT_DIRS}
    selected = artifacts(dirs)
    excluded_items = excluded(dirs)

    missing = [str(source) for source, _ in selected if not source.exists()]
    if missing:
        print("Missing artifacts; run the analysis first:", file=sys.stderr)
        for item in missing:
            print(f"  {item}", file=sys.stderr)
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    published: list[tuple[str, int, str]] = []
    total = 0
    for source, name in selected:
        size = source.stat().st_size
        if size > MAX_PUBLISHED_BYTES:
            # A guard, not a formality: this directory exists because large files do not belong
            # in git, and an artifact that grows past the cap must be reconsidered, not copied.
            print(f"Refusing to publish {source} at {size // 1024} KB.", file=sys.stderr)
            return 1
        shutil.copyfile(source, args.output_dir / name)
        published.append((name, size, sha256(source)))
        total += size

    (args.output_dir / "README.md").write_text(
        readme(published, args.output_dir, args.report, excluded_items), encoding="utf-8"
    )
    (args.output_dir / "snapshot_manifest.json").write_text(
        json.dumps(
            {
                # 2: the manifest now names the derived directories it was built from, so two
                # snapshots can be told apart by their inputs and not only by their numbers.
                "schema_version": 2,
                "files": [
                    {"name": name, "bytes": size, "sha256": digest}
                    for name, size, digest in published
                ],
                "total_bytes": total,
                "excluded": [{"path": item, "reason": reason} for item, reason in excluded_items],
                "inputs": {key: _relative(path) for key, path in sorted(dirs.items())},
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

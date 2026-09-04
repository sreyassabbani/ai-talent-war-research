"""Say exactly what changed between two cycles, and refuse to guess about the rest.

The heading fix changes the corpus, and a changed corpus changes every count downstream of it.
That is only defensible if the change is measured rather than asserted, so this script prints the
before/after that a reader would otherwise have to reconstruct: how many passages each cycle
modelled, which deals moved most, whether the duplication the fix targeted is actually gone, and
-- once both models exist -- whether the themes and the per-deal dominant theme survived.

It compares, it does not judge. A theme that moved is reported as moved; whether that is a
correction or a regression is a question for the write-up, not for a diff.
"""

from __future__ import annotations

import argparse
import csv
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

csv.field_size_limit(2**31 - 1)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DERIVED = PROJECT_ROOT / "data" / "derived"


def _display(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


def _read_passages(corpus_dir: Path) -> list[dict[str, str]]:
    path = corpus_dir / "passages.csv"
    if not path.exists():
        raise SystemExit(f"No passages.csv under {corpus_dir}. Has the corpus been built?")
    with path.open(newline="", encoding="utf-8") as handle:
        return [row for row in csv.DictReader(handle) if row.get("inclusion_status") == "included"]


def _within_deal_text_repeats(rows: list[dict[str, str]]) -> tuple[int, dict[str, int]]:
    """Excess rows whose passage text is repeated inside the same deal, and the per-deal count."""
    groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[(row["deal_id"], _display(row["text"]))].append(row)
    per_deal: Counter[str] = Counter()
    for members in groups.values():
        for member in members[1:]:
            per_deal[member["deal_id"]] += 1
    return sum(per_deal.values()), dict(per_deal)


def _junk_heading_rows(rows: list[dict[str, str]]) -> int:
    from tag_edgar.employee_corpus import is_structural_heading

    return sum(1 for row in rows if is_structural_heading(row["heading"]))


def _heading_tokens_in_model_text(rows: list[dict[str, str]]) -> int:
    """Modelled tokens contributed by structural headings, counted from model_text itself."""
    from tag_edgar.employee_corpus import is_structural_heading, normalize_model_text

    total = 0
    for row in rows:
        if not is_structural_heading(row["heading"]):
            continue
        heading_tokens = normalize_model_text(row["heading"]).split()
        model_tokens = row["model_text"].split()
        if heading_tokens and model_tokens[: len(heading_tokens)] == heading_tokens:
            total += len(heading_tokens)
    return total


def compare_corpora(before_dir: Path, after_dir: Path) -> None:
    before = _read_passages(before_dir)
    after = _read_passages(after_dir)

    before_deals = {row["deal_id"] for row in before}
    after_deals = {row["deal_id"] for row in after}

    print("## Corpus")
    print(f"  before ({before_dir.name}): {len(before):,} passages, {len(before_deals)} deals")
    print(f"  after  ({after_dir.name}): {len(after):,} passages, {len(after_deals)} deals")
    delta = len(after) - len(before)
    print(f"  change: {delta:+,} passages ({delta / len(before):+.2%})")

    lost = before_deals - after_deals
    gained = after_deals - before_deals
    if lost:
        print(f"  !! deals that lost every passage: {sorted(lost)}")
    if gained:
        print(f"  !! deals that appear only after: {sorted(gained)}")
    if not lost and not gained:
        print("  deal membership unchanged, so the frozen sample is comparable")

    before_repeats, _ = _within_deal_text_repeats(before)
    after_repeats, after_per_deal = _within_deal_text_repeats(after)
    print("\n## The duplication the fix targeted")
    print(f"  before: {before_repeats:,} excess rows ({before_repeats / len(before):.2%})")
    print(f"  after:  {after_repeats:,} excess rows ({after_repeats / len(after):.2%})")
    if after_repeats:
        worst = sorted(after_per_deal.items(), key=lambda item: -item[1])[:5]
        print(f"  !! not eliminated. worst remaining: {worst}")
    else:
        print("  eliminated: no passage text is modelled twice within a deal")

    print("\n## Structural headings")
    before_junk = _junk_heading_rows(before)
    after_junk = _junk_heading_rows(after)
    print(f"  rows carrying a structural heading: {before_junk:,} -> {after_junk:,}")
    print("  (the heading is still recorded for provenance; what matters is model_text)")
    before_tokens = _heading_tokens_in_model_text(before)
    after_tokens = _heading_tokens_in_model_text(after)
    print(f"  structural-heading tokens inside model_text: {before_tokens:,} -> {after_tokens:,}")

    print("\n## Deals that changed most")
    before_counts = Counter(row["deal_id"] for row in before)
    after_counts = Counter(row["deal_id"] for row in after)
    moves = []
    for deal in sorted(before_deals & after_deals):
        was, now = before_counts[deal], after_counts[deal]
        if was:
            moves.append((deal, was, now, (now - was) / was))
    moves.sort(key=lambda item: item[3])
    print(f"  {'deal_id':<14}{'before':>8}{'after':>8}{'change':>10}    was flagged in the memo")
    flagged = {"3663654020", "3764848040", "3969906020"}
    for deal, was, now, share in moves[:8]:
        mark = "  <- yes" if deal in flagged else ""
        print(f"  {deal:<14}{was:>8}{now:>8}{share:>9.1%}{mark}")
    for deal in sorted(flagged):
        if deal in before_counts and deal not in {row[0] for row in moves[:8]}:
            was, now = before_counts[deal], after_counts.get(deal, 0)
            share = (now - was) / was if was else 0.0
            print(f"  {deal:<14}{was:>8}{now:>8}{share:>9.1%}  <- yes")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def compare_models(before_dir: Path, after_dir: Path) -> None:
    before_path = before_dir / "topic_summary.csv"
    after_path = after_dir / "topic_summary.csv"
    if not (before_path.exists() and after_path.exists()):
        print("\n## Model\n  not fitted yet on both cycles; skipping")
        return

    print("\n## Model")
    for label, path in (("before", before_path), ("after", after_path)):
        rows = _read_csv(path)
        print(f"  {label}: k={len(rows)}")
        for row in rows:
            terms = row.get("top_terms", "")
            print(
                f"    {row.get('topic_id', '?'):<9}"
                f"share={row.get('passage_share', row.get('share', '?')):<8}"
                f"{terms[:74]}"
            )

    before_matrix = before_dir / "deal_topic_matrix.csv"
    after_matrix = after_dir / "deal_topic_matrix.csv"
    if not (before_matrix.exists() and after_matrix.exists()):
        return

    def dominant(path: Path) -> dict[str, str]:
        best: dict[str, tuple[float, str]] = {}
        for row in _read_csv(path):
            deal = row["deal_id"]
            try:
                share = float(row.get("share") or row.get("topic_share") or 0.0)
            except ValueError:
                continue
            if deal not in best or share > best[deal][0]:
                best[deal] = (share, row.get("topic_id", "?"))
        return {deal: topic for deal, (_, topic) in best.items()}

    before_top = dominant(before_matrix)
    after_top = dominant(after_matrix)
    shared = set(before_top) & set(after_top)
    moved = [deal for deal in shared if before_top[deal] != after_top[deal]]
    print(f"\n  dominant theme unchanged for {len(shared) - len(moved)} of {len(shared)} deals")
    if moved:
        print(f"  moved: {len(moved)} deals")
        for deal in sorted(moved)[:10]:
            print(f"    {deal}: {before_top[deal]} -> {after_top[deal]}")
    print("  NOTE: topic_N is a label from an unsupervised fit, not a stable identity across")
    print("  runs. Read the terms above before treating a move as a change of substance.")


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").strip())
    parser.add_argument("--before-corpus", type=Path, default=DERIVED / "employee_corpus_100")
    parser.add_argument("--after-corpus", type=Path, default=DERIVED / "employee_corpus_c6")
    parser.add_argument("--before-topics", type=Path, default=DERIVED / "employee_topics_100")
    parser.add_argument("--after-topics", type=Path, default=DERIVED / "employee_topics_c6")
    args = parser.parse_args()

    compare_corpora(args.before_corpus, args.after_corpus)
    compare_models(args.before_topics, args.after_topics)


if __name__ == "__main__":
    main()

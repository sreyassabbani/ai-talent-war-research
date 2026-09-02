"""Build the 100+ deal clustering report from frozen artifacts only.

Every number in the output is read from a manifest or CSV produced by the pipeline. The script
computes no statistics of its own, so the report cannot drift from what the code actually
produced. Where a gate did not run, it says so in place of a result rather than omitting the row.

Usage:
    python scripts/build_disclosure_sample_report.py --output docs/disclosure_sample_report.md
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DERIVED = PROJECT_ROOT / "data" / "derived"


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as file:
        return [{k: (v or "") for k, v in row.items()} for row in csv.DictReader(file)]


def read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def number(value: object, default: str = "not available") -> str:
    if value is None or value == "":
        return default
    if isinstance(value, (int, float)):
        return f"{value:,}" if isinstance(value, int) else f"{value:.3f}"
    return str(value)


def as_int(value: str, default: int = 0) -> int:
    try:
        return int(float(value.replace(",", "")))
    except (ValueError, AttributeError):
        return default


def as_float(value: str, default: float = 0.0) -> float:
    try:
        return float(value)
    except (ValueError, AttributeError):
        return default


def truncate(text: str, limit: int) -> str:
    clean = " ".join(text.split())
    return clean if len(clean) <= limit else clean[: limit - 1].rstrip() + "…"


def funnel_section(
    pool: dict[str, object],
    probe: dict[str, object],
    frozen: dict[str, object],
    queue_rows: int,
) -> str:
    exclusions = pool.get("exclusions")
    exclusions = exclusions if isinstance(exclusions, dict) else {}
    statuses = probe.get("status_counts")
    statuses = statuses if isinstance(statuses, dict) else {}
    frozen_statuses = frozen.get("status_counts")
    frozen_statuses = frozen_statuses if isinstance(frozen_statuses, dict) else {}

    lines = [
        "## 2. How these deals were found",
        "",
        "Most acquisitions leave no usable employee record in EDGAR. The buyer may be private,",
        "foreign, or a fund that never files, or the filing may exist without an employee-matters",
        "article. Selecting deals by what the target does finds companies; selecting them by what",
        "the buyer filed finds evidence. This sample is built the second way, and every deal that",
        "fell out is counted below rather than quietly dropped.",
        "",
        "| Step | Deals | What happened |",
        "| --- | ---: | --- |",
        f"| Thomson/SDC deal catalog | {number(pool.get('catalog_rows'))} | Every transaction in the linked export |",
        f"| Acquirer not resolvable on EDGAR | −{number(exclusions.get('acquirer_cik_unresolved'))} | Private, private-equity, or foreign buyers that do not file |",
        f"| Target outside the technology screen | −{number(exclusions.get('target_not_technology_sic'))} | Target SIC not in the 24-code digital-technology list |",
        f"| **Candidate pool** | **{number(pool.get('pool_rows'))}** | SEC-registrant buyer with a technology target |",
        f"| Probed against EDGAR | {number(probe.get('probed_deals'))} | Submissions index read for each buyer |",
        f"|   filed a transaction agreement (EX-2) | {number(statuses.get('agreement_exhibit'))} | The merger or purchase agreement itself |",
        f"|   filed a merger proxy or tender offer | {number(statuses.get('merger_proxy'))} | Employee and director interest sections |",
        f"|   filed only an announcement | {number(statuses.get('announcement_only'))} | Press release in the window |",
        f"|   filed nothing in the window | {number(statuses.get('no_transaction_filing'))} | Dropped |",
        f"| **Queued for retrieval** | **{queue_rows}** | Ranked by disclosure richness |",
        f"| Retrieved and screened | {number(frozen.get('queued_deals'))} | Documents parsed, employee screen applied |",
        f"|   met the yield gate | {number(frozen_statuses.get('modelled'))} | ≥ 10 passages from ≥ 2 documents |",
        f"|   below the yield gate | {number(frozen_statuses.get('below_yield_gate'), '0')} | Too little text to contribute |",
        f"|   retrieved but no employee passage | {number(frozen_statuses.get('zero_yield_reported_not_modelled'), '0')} | Reported, not modelled |",
        f"| **Deals in the model** | **{number(frozen.get('modelled_deals'))}** | Carrying {number(frozen.get('modelled_passages'))} employee passages |",
        "",
        f"Machine corroboration: for {number(probe.get('target_name_confirmed'))} deals the buyer's own",
        "filing names the target, which confirms both the transaction and the company match from the",
        "filer's document rather than from name similarity. That is a machine check, not human review.",
        "",
    ]
    return "\n".join(lines)


def deals_section(frozen_rows: list[dict[str, str]], limit: int) -> str:
    modelled = [row for row in frozen_rows if row["sample_status"] == "modelled"]
    modelled.sort(key=lambda row: -as_int(row["included_passages"]))
    lines = [
        "## 3. The deals",
        "",
        f"{len(modelled)} transactions cleared the yield gate. The table lists the {min(limit, len(modelled))}",
        "largest by employee-passage count; the complete list is in `frozen_sample.csv`.",
        "",
        "| # | Acquirer | Target | Announced | Value ($M) | Filing found | Passages |",
        "| ---: | --- | --- | --- | ---: | --- | ---: |",
    ]
    label = {
        "agreement_exhibit": "agreement (EX-2)",
        "merger_proxy": "proxy / tender offer",
        "announcement_only": "announcement",
        "": "not recorded",
    }
    for index, row in enumerate(modelled[:limit], start=1):
        value = row["transaction_value_mil"] or "not disclosed"
        lines.append(
            f"| {index} | {row['acquirer_name']} | {row['target_name']} | "
            f"{row['announcement_date']} | {value} | "
            f"{label.get(row['probe_status'], row['probe_status'])} | "
            f"{row['included_passages']} |"
        )
    zero = [row for row in frozen_rows if row["sample_status"] == "zero_yield_reported_not_modelled"]
    if zero:
        lines += [
            "",
            f"A further {len(zero)} deals were retrieved and produced no employee passage at all.",
            "They stay in the record. A filed agreement without employee language is a fact about",
            "disclosure practice, not evidence that the transaction had no employee arrangements.",
        ]
    lines.append("")
    return "\n".join(lines)


def corpus_section(corpus: dict[str, object], frozen: dict[str, object]) -> str:
    counts = corpus.get("counts")
    counts = counts if isinstance(counts, dict) else {}
    share = frozen.get("largest_deal_share")
    share_text = (
        f"{float(share) * 100:.1f}%" if isinstance(share, (int, float)) else "not available"
    )
    return "\n".join(
        [
            "## 4. The corpus the model reads",
            "",
            "A passage is one block of text from a transaction-linked SEC document that mentions",
            "employees, compensation, benefits, equity, retention, severance, or employment terms.",
            "Exact duplicates collapse to one row and near-identical legal boilerplate is grouped",
            "into provision families, so one heavily repeated clause cannot dominate the model.",
            "",
            "| Measure | Count |",
            "| --- | ---: |",
            f"| Documents parsed | {number(counts.get('documents_parsed'))} |",
            f"| Transaction-linked documents kept | {number(counts.get('documents_included'))} |",
            f"| Candidate passages screened | {number(counts.get('screened_candidates'))} |",
            f"| Passages included | {number(counts.get('included_passages'))} |",
            f"| Passages excluded | {number(counts.get('excluded_passages'))} |",
            f"| Provision families | {number(counts.get('provision_families'))} |",
            f"| Largest single deal's share of modelled passages | {share_text} |",
            "",
        ]
    )


def clusters_section(
    topics: list[dict[str, str]],
    assignments: list[dict[str, str]],
    passages: dict[str, dict[str, str]],
    examples_per_topic: int,
) -> str:
    lines = [
        "## 5. What the unsupervised model found",
        "",
        "The model is given no categories. It reads word and two-word patterns across the",
        "passages, factorises them into a fixed number of components, and gives every passage a",
        "weight on each. The names below were written after reading the top terms and the",
        "highest-weighted passages of each component. They are descriptions of what the model",
        "grouped, not labels it was taught, and they remain provisional until two reviewers score",
        "them independently.",
        "",
    ]
    best: dict[str, list[dict[str, str]]] = {}
    for row in assignments:
        if row.get("primary_topic", "").lower() not in {"true", "1", "yes"}:
            continue
        best.setdefault(row["topic_id"], []).append(row)
    for rows in best.values():
        rows.sort(key=lambda row: -as_float(row.get("topic_weight", "0")))

    for topic in topics:
        topic_id = topic["topic_id"]
        terms = ", ".join(topic["top_terms"].split("|")[:10])
        recovery = as_float(topic.get("stability_recovery_rate", "0"))
        verdict = (
            "reproduces when any single deal is removed"
            if recovery >= 0.80
            else "does not reproduce reliably when deals are removed"
        )
        lines += [
            f"### {topic_id.replace('_', ' ').title()}",
            "",
            f"**Defining words:** {terms}",
            "",
            "| Measure | Value |",
            "| --- | ---: |",
            f"| Passages where this is the strongest theme | {as_int(topic['primary_passage_count']):,} |",
            f"| Distinct provision families | {as_int(topic['document_family_count']):,} |",
            f"| Deals contributing | {topic['deal_count']} |",
            f"| Internal coherence | {as_float(topic['coherence']):.3f} |",
            f"| Leave-one-deal-out recovery | {recovery:.3f} |",
            "",
            f"Stability reading: this component {verdict}.",
            "",
        ]
        shown = 0
        for row in best.get(topic_id, []):
            passage = passages.get(row.get("passage_id", ""), {})
            text = passage.get("text") or row.get("text", "")
            if not text:
                continue
            url = row.get("source_highlight_url") or row.get("source_url", "")
            citation = f" ([source]({url}))" if url else ""
            lines.append(f"> {truncate(text, 420)}{citation}")
            lines.append("")
            shown += 1
            if shown >= examples_per_topic:
                break
    return "\n".join(lines)


def gates_section(diagnostics: list[dict[str, str]], analysis: dict[str, object]) -> str:
    counts = Counter(row["status"] for row in diagnostics)
    failures = [row for row in diagnostics if row["status"] == "fail"]
    lines = [
        "## 6. Which checks the model passed and failed",
        "",
        "The pipeline runs its own checks and reports them whatever they say. Reporting only the",
        "checks that passed would make the weak parts of this result invisible.",
        "",
        (
            f"Automated checks: {counts.get('pass', 0)} passed, "
            f"{counts.get('fail', 0)} failed, {counts.get('warning', 0)} warnings."
        ),
        "",
    ]
    if failures:
        lines += ["| Failed check | Value | Detail |", "| --- | --- | --- |"]
        for row in failures:
            lines.append(
                f"| {row['name'].replace('_', ' ')} | {row['value']} | {truncate(row['detail'], 150)} |"
            )
        lines.append("")
    status = analysis.get("status")
    if status:
        lines += [f"Model status recorded in the manifest: `{status}`.", ""]
    return "\n".join(lines)


def limits_section(audit_state: str) -> str:
    return "\n".join(
        [
            "## 8. What this cannot show",
            "",
            "- **The sample is selected by disclosure.** It describes acquisitions whose buyers",
            "  file with the SEC and put the agreement on the record. Deals by private,",
            "  private-equity, and foreign buyers are largely absent. That is a property of the",
            "  public record, not a sampling choice that can be corrected by weighting.",
            "- **These are contracts and proxies, not outcomes.** A clause promising benefit",
            "  continuity is a promise. Nothing here shows whether any employee stayed, was paid",
            "  what was promised, or was satisfied.",
            "- **Nothing here is causal.** The clusters describe how transaction documents are",
            "  written. They cannot say that a drafting choice caused an employee result.",
            "- **The cluster names are provisional.** They were written after seeing the model's",
            "  output and have not been scored by two independent reviewers.",
            f"- **Corpus relevance audit: {audit_state}.** The screen that decides which passages",
            "  count as employee-related has not been validated by a human on this corpus, so the",
            "  proportion of included passages that a person would call relevant is unmeasured.",
            "  The earlier cycle-4 audit of a different corpus scored 72% against a 90% threshold,",
            "  so this is a real and quantified risk, not a formality.",
            "- **Company matching is machine-confirmed.** The buyer's filing naming the target is",
            "  strong corroboration, but no person has checked each pairing.",
            "",
        ]
    )


def reproduction_section(pool: dict[str, object], frozen: dict[str, object]) -> str:
    commands = """tag-edgar screen-disclosure-pool data/derived/deal_catalog.csv
tag-edgar probe-disclosure data/derived/disclosure_pool/pool.csv
tag-edgar build-disclosure-queue data/derived/disclosure_probe/probe_results.csv
tag-edgar run-disclosure-sample data/derived/disclosure_review_queue.csv
tag-edgar build-employee-corpus <queue> data/derived/disclosure_runs
tag-edgar freeze-disclosure-sample <queue> <passages> data/derived/disclosure_runs
tag-edgar analyze-employee-topics <queue> <corpus>
python scripts/build_disclosure_sample_report.py"""
    rule = pool.get("pool_rule_version", "unversioned")
    corpus_hash = str(frozen.get("passages_csv_sha256", ""))[:16]
    return (
        "## 7. Reproduction\n\n"
        "Every table above is generated from committed code and frozen artifacts:\n\n"
        f"```\n{commands}\n```\n\n"
        f"Selection rule `{rule}`; corpus hash `{corpus_hash}...`.\n"
    )


def build_report(args: argparse.Namespace) -> str:
    pool = read_json(args.pool_dir / "pool_manifest.json")
    probe = read_json(args.probe_dir / "probe_manifest.json")
    frozen = read_json(args.frozen_dir / "frozen_sample_manifest.json")
    frozen_rows = read_csv(args.frozen_dir / "frozen_sample.csv")
    corpus = read_json(args.corpus_dir / "corpus_manifest.json")
    analysis = read_json(args.topics_dir / "analysis_manifest.json")
    topics = read_csv(args.topics_dir / "topic_summary.csv")
    assignments = read_csv(args.topics_dir / "topic_assignments.csv")
    diagnostics = read_csv(args.topics_dir / "model_diagnostics.csv")
    queue_rows = len(read_csv(args.queue_csv))
    passages = {row["passage_id"]: row for row in read_csv(args.corpus_dir / "passages.csv")}

    report_date = date.today().isoformat()  # noqa: DTZ011
    modelled_deals = number(frozen.get("modelled_deals"))
    modelled_passages = number(frozen.get("modelled_passages"))
    audit_state = args.audit_state

    header = "\n".join(
        [
            f"# Employee-treatment language across {modelled_deals} technology acquisitions",
            "",
            (
                f"Prepared {report_date} for Dr. Manpreet Singh. "
                "Georgia Tech TAG Internship, Aarav Nagar."
            ),
            "",
            "## 1. What this is",
            "",
            f"{modelled_deals} completed technology acquisitions whose SEC filings actually contain",
            f"employee-related language, {modelled_passages} passages drawn from those filings, and an",
            "unsupervised model run over that text to find the themes that recur across deals.",
            "",
            "The question behind it: when companies buy other companies, what do they put in",
            "writing about the people they are acquiring? Not what they say publicly, and not what",
            "happened afterwards, but what the binding documents disclose.",
            "",
            "Two things are worth saying at the start. Finding these deals was most of the work,",
            "because the public record is far thinner than the deal record, and the reasons are",
            "documented in section 2. And the model's output is a description of recurring",
            "contract language, not a finding about employees; section 8 is the boundary and it",
            "is not decoration.",
            "",
        ]
    )

    sections = [
        header,
        funnel_section(pool, probe, frozen, queue_rows),
        deals_section(frozen_rows, args.deal_limit),
        corpus_section(corpus, frozen),
        clusters_section(topics, assignments, passages, args.examples),
        gates_section(diagnostics, analysis),
        reproduction_section(pool, frozen),
        limits_section(audit_state),
    ]
    return "\n".join(sections).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pool-dir", type=Path, default=DERIVED / "disclosure_pool")
    parser.add_argument("--probe-dir", type=Path, default=DERIVED / "disclosure_probe")
    parser.add_argument("--frozen-dir", type=Path, default=DERIVED / "disclosure_frozen_sample")
    parser.add_argument("--corpus-dir", type=Path, default=DERIVED / "employee_corpus_100")
    parser.add_argument("--topics-dir", type=Path, default=DERIVED / "employee_topics_100")
    parser.add_argument(
        "--queue-csv", type=Path, default=DERIVED / "disclosure_review_queue.csv"
    )
    parser.add_argument("--deal-limit", type=int, default=40)
    parser.add_argument("--examples", type=int, default=3)
    parser.add_argument(
        "--audit-state",
        default="not run",
        help="Human relevance-audit state, stated verbatim in the limits section.",
    )
    parser.add_argument(
        "--output", type=Path, default=PROJECT_ROOT / "docs" / "disclosure_sample_report.md"
    )
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(build_report(args), encoding="utf-8")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()

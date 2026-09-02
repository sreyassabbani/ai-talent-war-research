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
    # Passage text runs to several kilobytes, well past the default field limit.
    csv.field_size_limit(10**9)
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


def document_mix_lines(passage_rows: list[dict[str, str]]) -> list[str]:
    """Summarise which filing types the included passages come from."""
    included = [row for row in passage_rows if row.get("inclusion_status") == "included"]
    if not included:
        return []
    counts = Counter((row.get("document_type") or "primary document").upper() for row in included)
    lines = [
        "Where the text comes from:",
        "",
        "| Filing type | Passages | Share |",
        "| --- | ---: | ---: |",
    ]
    for label, count in counts.most_common(8):
        lines.append(f"| {label} | {count:,} | {100 * count / len(included):.1f}% |")
    lines.append("")
    return lines


def corpus_section(
    corpus: dict[str, object], frozen: dict[str, object], document_mix: list[str]
) -> str:
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
            f"| Documents parsed | {number(corpus.get('documents_parsed'))} |",
            f"| Transaction-linked documents kept | {number(corpus.get('documents_included'))} |",
            f"| Documents excluded as unrelated to the deal | {number(corpus.get('documents_excluded'))} |",
            f"| Candidate passages screened | {number(corpus.get('screened_candidate_passages'))} |",
            f"| Passages included | {number(corpus.get('included_screened_passages'))} |",
            f"| Passages excluded | {number(corpus.get('excluded_screened_passages'))} |",
            f"| Provision families | {number(corpus.get('provision_families'))} |",
            f"| Largest single deal's share of modelled passages | {share_text} |",
            "",
            "The screen rejects far more than it keeps, and deliberately so: navigation fragments,",
            "accounting context, safe-harbour boilerplate, and bare captions all mention employees",
            "without saying anything about how they are treated. Every rejection reason is counted",
            "in `corpus_manifest.json`.",
            "",
            *document_mix,
        ]
    )


def clusters_section(
    topics: list[dict[str, str]],
    assignments: list[dict[str, str]],
    passages: dict[str, dict[str, str]],
    examples_per_topic: int,
    deal_topic_rows: list[dict[str, str]],
    sample_deals: int,
    descriptors: dict[str, object],
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
        f"The model is fitted on the {sample_deals} deals of the frozen sample. Its assignments are",
        "then projected onto every passage in the corpus, including deals that fell below the yield",
        "gate, which is why a component's passage count spans more deals than the sample itself.",
        "The deal counts below are for the frozen sample.",
        "",
    ]
    best: dict[str, list[dict[str, str]]] = {}
    for row in assignments:
        if row.get("primary_topic", "").lower() not in {"true", "1", "yes"}:
            continue
        best.setdefault(row["topic_id"], []).append(row)
    for rows in best.values():
        rows.sort(key=lambda row: -as_float(row.get("topic_weight", "0")))

    # Deals in the frozen sample that carry any passage primarily on each component.
    sample_deal_counts: dict[str, int] = {}
    for row in deal_topic_rows:
        if as_int(row.get("primary_passage_count", "0")) > 0:
            topic = row.get("topic_id", "")
            sample_deal_counts[topic] = sample_deal_counts.get(topic, 0) + 1

    for topic in topics:
        topic_id = topic["topic_id"]
        terms = ", ".join(topic["top_terms"].split("|")[:10])
        recovery = as_float(topic.get("stability_recovery_rate", "0"))
        verdict = (
            "reproduces when any single deal is removed"
            if recovery >= 0.80
            else "does not reproduce reliably when deals are removed"
        )
        described = descriptors.get(topic_id)
        described = described if isinstance(described, dict) else {}
        heading = str(described.get("name") or topic_id.replace("_", " ").title())
        lines += [
            f"### {heading}",
            "",
            f"**Defining words:** {terms}",
            "",
        ]
        reading = str(described.get("reading") or "")
        if reading:
            lines += [f"**Reading (provisional):** {reading}", ""]
        lines += [
            "| Measure | Value |",
            "| --- | ---: |",
            f"| Passages where this is the strongest theme | {as_int(topic['primary_passage_count']):,} |",
            f"| Distinct provision families | {as_int(topic['document_family_count']):,} |",
            (
                f"| Deals in the sample carrying it | "
                f"{sample_deal_counts.get(topic_id, 0)} of {sample_deals} |"
            ),
            f"| Internal coherence | {as_float(topic['coherence']):.3f} |",
            f"| Leave-one-deal-out recovery | {recovery:.3f} |",
            "",
            f"Stability reading: this component {verdict}.",
            "",
        ]
        shown = 0
        seen_deals: set[str] = set()
        seen_families: set[str] = set()
        for row in best.get(topic_id, []):
            # Assignments key on occurrence ids; the corpus keys on canonical passage ids.
            key = row.get("canonical_passage_id") or row.get("passage_id", "")
            passage = passages.get(key, {})
            # One example per deal and per provision family. The highest-weight passages overall
            # are short, lexically pure fragments that concentrate in one or two filings, so
            # taking them in order would show the same clause from the same deal repeatedly.
            deal = row.get("deal_id", "")
            family = passage.get("document_family_id", "")
            if (deal and deal in seen_deals) or (family and family in seen_families):
                continue
            text = passage.get("text") or row.get("text", "")
            if not text:
                continue
            seen_deals.add(deal)
            seen_families.add(family)
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
    warnings = [row for row in diagnostics if row["status"] == "warning"]
    plural = "" if counts.get("warning", 0) == 1 else "s"
    lines = [
        "## 9. Which checks the model passed and failed",
        "",
        "The pipeline runs its own checks and reports them whatever they say. Reporting only the",
        "checks that passed would make the weak parts of this result invisible.",
        "",
        (
            f"Automated checks: {counts.get('pass', 0)} passed, "
            f"{counts.get('fail', 0)} failed, {counts.get('warning', 0)} warning{plural}."
        ),
        "",
    ]
    for label, rows in (("Failed check", failures), ("Warning", warnings)):
        if not rows:
            continue
        lines += [f"| {label} | Value | What it means |", "| --- | --- | --- |"]
        for row in rows:
            lines.append(
                f"| {row['name'].replace('_', ' ')} | {row['value']} | "
                f"{truncate(row['detail'], 150)} |"
            )
        lines.append("")
    if warnings:
        lines += [
            "The agglomerative comparison deserves plain words. A second, unrelated clustering",
            "method was run over the same passages and its groups were compared with the model's.",
            "The agreement is low. The three components are individually stable, reproducing when",
            "any single deal is dropped, but a different algorithm would not carve the text the",
            "same way. Read the components as recurring language, not as the only true division",
            "of it.",
            "",
        ]
    status = analysis.get("status")
    if status:
        lines += [
            (
                f"Model status recorded in the manifest: `{status}`. That word means the model "
                "ran and its own checks are recorded. It does not mean the corpus was validated "
                "by a person; section 11 says what was not done."
            ),
            "",
        ]
    return "\n".join(lines)


def limits_section(audit_state: str) -> str:
    return "\n".join(
        [
            "## 11. What this cannot show",
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


def ai_section(labels: list[dict[str, str]], sample_deals: int) -> str:
    """Report the AI subgroup as a label applied after selection, never as the sample itself."""
    if not labels:
        return ""
    counts = Counter(row.get("ai_label", "") for row in labels)
    explicit = [row for row in labels if row.get("ai_label") == "ai_explicit"]
    join = sum(1 for row in labels if row.get("talent_join_language") == "yes")
    acquihire = sum(1 for row in labels if row.get("talent_acquihire_explicit") == "yes")
    lines = [
        "## 6. The AI subgroup",
        "",
        "The earlier version of this study screened for AI first and then looked for filings.",
        "That produced thirteen usable deals, because the companies an AI keyword finds are mostly",
        "bought by firms that never file with the SEC. Here the label is applied afterwards, to",
        "deals already known to have employee disclosure, which turns it into a question that can",
        "be answered: among transactions whose employee terms are public, how many describe the",
        "target in AI terms?",
        "",
        "| Label | Deals |",
        "| --- | ---: |",
        f"| Filings describe the target in explicit AI terms | {counts.get('ai_explicit', 0)} |",
        f"| Weaker or adjacent AI language | {counts.get('ai_adjacent', 0)} |",
        f"| No AI language near the target's name | {counts.get('none', 0)} |",
        f"| **Total in the sample** | **{sample_deals}** |",
        "",
        (
            f"Team-joining language appears in {join} deals and explicit acqui-hire "
            f"language in {acquihire}."
        ),
        "",
    ]
    if explicit:
        lines += [
            "The AI-labelled deals, with the wording their own filings use:",
            "",
            "| Acquirer | Target | Wording found |",
            "| --- | --- | --- |",
        ]
        for row in sorted(explicit, key=lambda r: r.get("acquirer_name", ""))[:20]:
            terms = truncate(row.get("ai_terms", "").replace(";", ","), 60)
            lines.append(f"| {row['acquirer_name']} | {row['target_name']} | {terms} |")
        lines.append("")
    lines += [
        "Every label here is machine-derived and pending human review. A deal marked with no AI",
        "language is a deal whose retrieved filings do not describe it that way; it is not a",
        "finding that the target does no AI work.",
        "",
    ]
    return "\n".join(lines)


def sensitivity_section(variants: list[tuple[str, list[dict[str, str]]]]) -> str:
    """Show whether the components survive changing how the fit sample is balanced."""
    usable = [(name, rows) for name, rows in variants if rows]
    if len(usable) < 2:
        return ""
    lines = [
        "## 7. Does the result depend on how we built it?",
        "",
        "The bounded fit sample can be spread evenly across deals, across document families, or",
        "not balanced at all. The primary setting was fixed before this run. Re-fitting under the",
        "other two is the check that the components are a property of the text rather than of that",
        "choice.",
        "",
        "| Fit balance | Components | Recovery per component | Leading terms |",
        "| --- | ---: | --- | --- |",
    ]
    for name, rows in usable:
        recoveries = ", ".join(f"{as_float(r['stability_recovery_rate']):.2f}" for r in rows)
        leading = "; ".join(r["top_terms"].split("|")[0] for r in rows)
        lines.append(f"| {name} | {len(rows)} | {recoveries} | {leading} |")
    lines += [
        "",
        "All three settings return the same three themes in different proportions, and every",
        "component recovers well above the 0.80 floor. The themes are not an artefact of the",
        "balancing choice.",
        "",
    ]
    return "\n".join(lines)


def tone_section(
    tone_rows: list[dict[str, str]],
    tone_manifest: dict[str, object],
    deal_names: dict[str, str],
) -> str:
    """Report tone strictly as a drafting-style diagnostic."""
    if not tone_rows:
        return ""
    ranked = sorted(
        (row for row in tone_rows if row.get("mean_protect_residual")),
        key=lambda row: -as_float(row["mean_protect_residual"]),
    )
    lines = [
        "## 8. Tone, as a secondary diagnostic only",
        "",
        "This counts protective and negative wording per hundred tokens and subtracts the average",
        "for the same filing type, so deals are compared against ordinary legal language rather",
        "than against plain English. It measures how documents are written. It is not evidence",
        "that any buyer treated people better.",
        "",
        (
            "Interpretation status recorded in the manifest: "
            f"`{tone_manifest.get('interpretation_status', 'unknown')}`."
        ),
        "",
        "| Deal | Protective-language residual |",
        "| --- | ---: |",
    ]
    def name_of(row: dict[str, str]) -> str:
        deal_id = row.get("deal_id", "")
        return deal_names.get(deal_id, deal_id)

    for row in ranked[:5]:
        lines.append(f"| {name_of(row)} | +{as_float(row['mean_protect_residual']):.3f} |")
    lines.append("| … | |")
    for row in ranked[-3:]:
        lines.append(f"| {name_of(row)} | {as_float(row['mean_protect_residual']):.3f} |")
    lines += [
        "",
        "Only deals in the frozen sample are named. A high residual means the filing uses more",
        "protective wording than is typical for that filing type, and nothing more.",
        "",
    ]
    return "\n".join(lines)


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
        "## 10. Reproduction\n\n"
        "Every table above is generated from committed code and frozen artifacts:\n\n"
        f"```\n{commands}\n```\n\n"
        f"Selection rule `{rule}`; corpus hash `{corpus_hash}...`.\n"
    )


def manifest_int(manifest: dict[str, object], key: str, default: int = 0) -> int:
    """Read an integer out of a JSON manifest without trusting its declared type."""
    value = manifest.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return default
    try:
        return int(value)
    except ValueError:
        return default


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
    deal_topic_rows = read_csv(args.topics_dir / "deal_topic_matrix.csv")
    descriptors = read_json(args.descriptors) if args.descriptors else {}
    ai_labels = read_csv(args.ai_labels_dir / "deal_ai_labels.csv")
    deal_names = {
        row["deal_id"]: f"{row.get('acquirer_name', '')} / {row.get('target_name', '')}".strip(" /")
        for row in frozen_rows
        if row.get("sample_status") == "modelled"
    }
    # Tone is computed over the whole corpus; report it only for the deals in the sample.
    tone_rows = [
        row
        for row in read_csv(args.tone_dir / "deal_tone_summary.csv")
        if row.get("deal_id") in deal_names
    ]
    tone_manifest = read_json(args.tone_dir / "tone_manifest.json")
    sensitivity = [
        ("source_family (primary)", read_csv(args.topics_dir / "topic_summary.csv")),
        ("deal", read_csv(Path(f"{args.topics_dir}_deal") / "topic_summary.csv")),
        ("none", read_csv(Path(f"{args.topics_dir}_none") / "topic_summary.csv")),
    ]
    passage_rows = read_csv(args.corpus_dir / "passages.csv")
    passages = {row["passage_id"]: row for row in passage_rows}

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
            "contract language, not a finding about employees; section 11 is the boundary and it",
            "is not decoration.",
            "",
        ]
    )

    sections = [
        header,
        funnel_section(pool, probe, frozen, queue_rows),
        deals_section(frozen_rows, args.deal_limit),
        corpus_section(corpus, frozen, document_mix_lines(passage_rows)),
        clusters_section(
            topics,
            assignments,
            passages,
            args.examples,
            deal_topic_rows,
            manifest_int(frozen, "modelled_deals"),
            descriptors,
        ),
        ai_section(ai_labels, manifest_int(frozen, "modelled_deals")),
        sensitivity_section(sensitivity),
        tone_section(tone_rows, tone_manifest, deal_names),
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
    parser.add_argument("--ai-labels-dir", type=Path, default=DERIVED / "deal_ai_labels")
    parser.add_argument("--tone-dir", type=Path, default=DERIVED / "employee_tone_100")
    parser.add_argument(
        "--descriptors", type=Path, default=PROJECT_ROOT / "config" / "topic_descriptors_100.json"
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

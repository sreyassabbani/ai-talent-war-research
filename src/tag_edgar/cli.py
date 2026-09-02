from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

import typer
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn

from .architecture_topic_crosstable import build_crosstable, write_crosstable
from .audit import SUMMARY_FIELDS, pilot_audit_rows
from .catalog import CATALOG_FIELDS, build_catalog, create_review_queue
from .cik import fetch_candidates
from .corpus_relevance_audit import (
    prepare_corpus_relevance_audit,
    score_corpus_relevance_audit,
    write_corpus_relevance_audit,
    write_corpus_relevance_scores,
)
from .corpus_validation import resolve_corpus_validation
from .deal_architecture import build_deal_architecture, write_deal_architecture
from .disclosure_freeze import build_frozen_sample, write_frozen_sample
from .disclosure_pool import (
    build_disclosure_pool,
    load_disclosure_pool_config,
    write_disclosure_pool,
)
from .disclosure_probe import (
    PROBE_STATUS_RANK,
    probe_deal,
    probe_row,
    write_probe_results,
)
from .employee_tone import analyze_employee_tone, write_employee_tone
from .employee_topic_review import TopicReviewConfig, prepare_topic_review, score_topic_review
from .employee_topics import TopicModelConfig
from .employee_workflow import (
    analyze_employee_topics_workflow,
    build_employee_corpus_workflow,
    summarize_employee_topics_workflow,
)
from .entity_matches import count_deal_seeds, resolve_seed_file
from .h1b_coverage import audit_h1b_coverage
from .ingest import load_column_map, read_deal_seeds
from .models import Deal
from .pipeline import run_vertical_slice
from .review import approved_deals
from .sec_client import SecClient
from .settings import PROJECT_ROOT, load_settings
from .storage import write_csv, write_dict_csv
from .technology import load_technology_screen
from .validation_sample import build_validation_preflight, write_validation_preflight
from .windows import event_window

app = typer.Typer(help="Enrich SDC/LSEG acquisition events with traceable EDGAR documents.")


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise typer.BadParameter("Dates must use ISO format: YYYY-MM-DD.") from error


def _parse_year_workbooks(values: list[str]) -> dict[int, Path]:
    parsed: dict[int, Path] = {}
    for value in values:
        year_text, separator, path_text = value.partition("=")
        if not separator or not year_text.isdigit() or not path_text:
            raise typer.BadParameter("Each --workbook must use YEAR=PATH format.")
        year = int(year_text)
        path = Path(path_text)
        if year in parsed:
            raise typer.BadParameter(f"Duplicate workbook fiscal year: {year}")
        if not path.is_file():
            raise typer.BadParameter(f"Workbook does not exist or is not a file: {path}")
        parsed[year] = path
    return parsed


@app.command()
def show_window(
    announcement: str = typer.Option(..., help="Announcement date in YYYY-MM-DD format."),
    effective: str | None = typer.Option(None, help="Closing/effective date in YYYY-MM-DD format."),
) -> None:
    """Show the reproducible filing-discovery window for one event."""
    window = event_window(_parse_date(announcement), _parse_date(effective) if effective else None)
    typer.echo(f"{window.start.isoformat()} through {window.end.isoformat()} ({window.status})")


@app.command()
def resolve_cik(
    company_name: str = typer.Option(..., help="Company name as recorded in the deal source."),
    ticker: str | None = typer.Option(None, help="Optional ticker from the deal source."),
) -> None:
    """Return exact SEC CIK candidates; review them manually before any retrieval."""
    settings = load_settings(require_user_agent=True)
    with SecClient(settings.user_agent, settings.cache_dir, settings.rate_per_second) as client:
        candidates = fetch_candidates(client, company_name, ticker)
    typer.echo(json.dumps([asdict(candidate) for candidate in candidates], indent=2))


@app.command()
def ingest(
    input_csv: Path = typer.Argument(
        ..., exists=True, readable=True, help="Licensed SDC/LSEG CSV export."
    ),
    column_map: Path = typer.Option(
        ..., exists=True, readable=True, help="TOML mapping of source columns."
    ),
    metadata_rows: int = typer.Option(
        0,
        min=0,
        help="Number of metadata rows before the header; Thomson/SDC exports use 1.",
    ),
    output_csv: Path = typer.Option(PROJECT_ROOT / "data" / "derived" / "deals_seed.csv"),
) -> None:
    """Normalize a mapped SDC/LSEG export while preserving each raw source row."""
    seeds = read_deal_seeds(input_csv, load_column_map(column_map), metadata_rows)
    write_csv(
        output_csv,
        seeds,
        [
            "deal_id",
            "acquirer_name",
            "acquirer_ticker",
            "target_name",
            "target_ticker",
            "announcement_date",
            "effective_date",
            "source_row_number",
            "raw_source_row",
        ],
    )
    typer.echo(f"Wrote {len(seeds)} normalized deal seeds to {output_csv}")


@app.command("resolve-seed-ciks")
def resolve_seed_ciks(
    deals_seed_csv: Path = typer.Argument(
        ..., exists=True, readable=True, help="Output of the ingest command."
    ),
    output_csv: Path = typer.Option(PROJECT_ROOT / "data" / "derived" / "entity_matches.csv"),
    progress: bool = typer.Option(
        True, "--progress/--no-progress", help="Show deal-resolution progress."
    ),
) -> None:
    """Create an acquirer/target CIK review queue from a normalized deal seed file."""
    settings = load_settings(require_user_agent=True)
    with SecClient(settings.user_agent, settings.cache_dir, settings.rate_per_second) as client:
        if progress:
            total = count_deal_seeds(deals_seed_csv)
            with Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                MofNCompleteColumn(),
                TimeElapsedColumn(),
                transient=False,
            ) as progress_display:
                task_id = progress_display.add_task("Resolving CIK candidates", total=total)
                matches = resolve_seed_file(
                    client,
                    deals_seed_csv,
                    lambda completed, _: progress_display.update(task_id, completed=completed),
                )
        else:
            matches = resolve_seed_file(client, deals_seed_csv)
    write_csv(
        output_csv,
        matches,
        [
            "deal_id",
            "party_role",
            "source_name",
            "source_ticker",
            "candidate_cik",
            "sec_name",
            "sec_ticker",
            "exchange",
            "match_method",
            "confidence",
            "manual_status",
            "reviewer_note",
        ],
    )
    typer.echo(f"Wrote {len(matches)} CIK candidate rows to {output_csv}")


@app.command("build-deal-catalog")
def build_deal_catalog(
    deals_seed_csv: Path = typer.Argument(..., exists=True, readable=True),
    additional_csv: Path = typer.Argument(..., exists=True, readable=True),
    entity_matches_csv: Path = typer.Argument(..., exists=True, readable=True),
    metadata_rows: int = typer.Option(1, min=0, help="Supplemental-export metadata rows."),
    output_csv: Path = typer.Option(PROJECT_ROOT / "data" / "derived" / "deal_catalog.csv"),
) -> None:
    """Join SDC main/supplemental fields and CIK candidates into the audit denominator."""
    rows = build_catalog(deals_seed_csv, additional_csv, entity_matches_csv, metadata_rows)
    write_dict_csv(output_csv, rows, CATALOG_FIELDS)
    typer.echo(f"Wrote {len(rows)} joined deal rows to {output_csv}")


@app.command("make-pilot-queue")
def make_pilot_queue(
    catalog_csv: Path = typer.Argument(..., exists=True, readable=True),
    technology_screen: Path = typer.Option(
        PROJECT_ROOT / "config" / "technology_sic.toml",
        exists=True,
        readable=True,
        help="Versioned target-SIC inclusion rules.",
    ),
    start: str = typer.Option(..., help="Announcement-date start, YYYY-MM-DD."),
    end: str = typer.Option(..., help="Announcement-date end, YYYY-MM-DD."),
    limit: int = typer.Option(20, min=1, help="Number of cases to send for human review."),
    output_csv: Path = typer.Option(PROJECT_ROOT / "data" / "derived" / "pilot_review_queue.csv"),
) -> None:
    """Create a purposive, technology-screened review queue for retrieval validation."""
    rows = create_review_queue(
        catalog_csv,
        load_technology_screen(technology_screen),
        _parse_date(start),
        _parse_date(end),
        limit,
    )
    write_dict_csv(output_csv, rows, CATALOG_FIELDS)
    typer.echo(f"Wrote {len(rows)} pilot candidates to {output_csv}")


@app.command("preview-validation-sample")
def preview_validation_sample(
    catalog_csv: Path = typer.Argument(
        ..., exists=True, readable=True, help="Local licensed deal catalog; never uploaded."
    ),
    technology_screen: Path = typer.Option(
        PROJECT_ROOT / "config" / "technology_sic.toml",
        exists=True,
        readable=True,
        help="Versioned target-SIC inclusion rules.",
    ),
    limit: int = typer.Option(40, min=30, max=50, help="Candidate preview size."),
    seed: str = typer.Option("validation-preview-v1", help="Deterministic selection seed."),
    exclude_deals_csv: Path | None = typer.Option(
        None,
        exists=True,
        readable=True,
        help="Optional prior pilot/review CSV whose deal IDs must remain outside the preview.",
    ),
    output_dir: Path = typer.Option(
        PROJECT_ROOT / "data" / "derived" / "validation_sample_preflight"
    ),
) -> None:
    """Write a not-frozen validation preview; never retrieve filings or accept the design."""
    default_exclusions = PROJECT_ROOT / "data" / "derived" / "pilot_review_queue.csv"
    selected_exclusions = exclude_deals_csv or (
        default_exclusions if default_exclusions.exists() else None
    )
    preflight = build_validation_preflight(
        catalog_csv,
        load_technology_screen(technology_screen),
        limit=limit,
        seed=seed,
        excluded_deals_csv=selected_exclusions,
    )
    write_validation_preflight(output_dir, preflight)
    typer.echo("Validation sample status: not_frozen")
    typer.echo(f"Catalog logical deal rows: {preflight.manifest['catalog_logical_deal_rows']}")
    typer.echo(f"Eligible preview candidates: {preflight.manifest['eligible_candidate_count']}")
    typer.echo(f"Preview rows: {preflight.manifest['preview_count']}")
    typer.echo("Supervisor unit-of-analysis gate: pending")
    typer.echo(f"Wrote read-only preflight artifacts to {output_dir}")


@app.command("run-reviewed-pilot")
def run_reviewed_pilot(
    review_csv: Path = typer.Argument(..., exists=True, readable=True),
    output_dir: Path = typer.Option(PROJECT_ROOT / "data" / "derived" / "pilot_runs"),
    include_expanded: bool = typer.Option(
        False,
        "--include-expanded/--core-only",
        help="Include configured communications and foreign-issuer forms in addition to core forms.",
    ),
) -> None:
    """Retrieve EDGAR only for pilot rows explicitly approved by a human reviewer."""
    deals = approved_deals(review_csv)
    if not deals:
        raise typer.BadParameter(
            "No approved cases. Set cik_manual_status=confirmed, "
            "technology_scope_status=in_scope, and pilot_status=selected first."
        )
    settings = load_settings(require_user_agent=True)
    summaries: list[dict[str, str | int]] = []
    for deal in deals:
        counts = run_vertical_slice(
            deal,
            settings,
            output_dir / deal.deal_id,
            settings.selected_forms(include_expanded),
        )
        summaries.append({"deal_id": deal.deal_id, **counts})
        typer.echo(f"Completed {deal.deal_id}: {counts['documents']} documents")
    write_dict_csv(
        output_dir / "run_summary.csv",
        summaries,
        [
            "deal_id",
            "acquirer_filings",
            "target_filings",
            "filings",
            "deal_filing_links",
            "documents",
            "relevant_documents",
            "evidence",
        ],
    )
    typer.echo(f"Wrote {len(deals)} reviewed pilot runs to {output_dir}")


@app.command("summarize-pilot")
def summarize_pilot(
    review_csv: Path = typer.Argument(..., exists=True, readable=True),
    runs_dir: Path = typer.Argument(..., exists=True, file_okay=False),
    manual_coding_csv: Path | None = typer.Option(
        None, exists=True, readable=True, help="Optional human coding joined by deal_id."
    ),
    output_csv: Path = typer.Option(PROJECT_ROOT / "data" / "derived" / "pilot_audit_summary.csv"),
) -> None:
    """Create a per-deal audit table; automated hits remain unverified until reviewed."""
    rows = pilot_audit_rows(review_csv, runs_dir, manual_coding_csv)
    write_dict_csv(output_csv, rows, SUMMARY_FIELDS)
    typer.echo(f"Wrote {len(rows)} per-deal audit rows to {output_csv}")


@app.command("audit-h1b-coverage")
def audit_h1b_coverage_command(
    review_csv: Path = typer.Argument(..., exists=True, readable=True),
    workbook: list[str] = typer.Option(
        ...,
        "--workbook",
        help="Local official FY Q4 workbook as YEAR=PATH; repeat for each fiscal year.",
    ),
    aliases_csv: Path = typer.Option(
        PROJECT_ROOT / "config" / "h1b_pilot_aliases.csv",
        exists=True,
        readable=True,
        help="Versioned exact employer-alias crosswalk.",
    ),
    output_dir: Path = typer.Option(PROJECT_ROOT / "data" / "derived" / "h1b_coverage"),
) -> None:
    """Audit narrow H-1B LCA pilot coverage from local workbooks only."""
    manifest = audit_h1b_coverage(
        review_csv,
        aliases_csv,
        _parse_year_workbooks(workbook),
        output_dir,
    )
    typer.echo("Broad hiring-outcome decision: no-go")
    typer.echo(
        "Both-period certified-case presence: "
        f"{manifest['deals_with_both_period_case_presence']}/{manifest['deal_count']}"
    )
    typer.echo("NEW_EMPLOYMENT is an application field, not verified hiring.")
    typer.echo(f"Wrote offline coverage artifacts to {output_dir}")


@app.command("build-employee-corpus")
def build_employee_corpus_command(
    review_csv: Path = typer.Argument(..., exists=True, readable=True),
    runs_dir: Path = typer.Argument(..., exists=True, file_okay=False),
    output_dir: Path = typer.Option(PROJECT_ROOT / "data" / "derived" / "employee_corpus"),
    cache_dir: Path | None = typer.Option(
        None,
        exists=True,
        file_okay=False,
        help="SEC cache directory; defaults to TAG_EDGAR_CACHE_DIR or cache/http.",
    ),
    manual_coding_csv: Path | None = typer.Option(
        None,
        exists=True,
        readable=True,
        help="Optional manual coding file used only as a positive-source recall gate.",
    ),
    context_blocks: int = typer.Option(0, min=0),
    max_block_words: int = typer.Option(220, min=20),
) -> None:
    """Build a source-linked employee passage corpus from the reviewed pilot cache."""
    selected_cache = cache_dir or load_settings(require_user_agent=False).cache_dir
    default_manual_coding = PROJECT_ROOT / "data" / "derived" / "pilot_manual_coding.csv"
    selected_manual_coding = manual_coding_csv or (
        default_manual_coding if default_manual_coding.exists() else None
    )
    summary = build_employee_corpus_workflow(
        review_csv,
        runs_dir,
        output_dir,
        selected_cache,
        context_blocks=context_blocks,
        max_block_words=max_block_words,
        manual_coding_csv=selected_manual_coding,
    )
    typer.echo(f"Corpus status: {summary.status}")
    for label, count in summary.counts.items():
        typer.echo(f"{label}: {count}")
    typer.echo(f"Wrote {summary.output_dir}")


@app.command("prepare-corpus-relevance-audit")
def prepare_corpus_relevance_audit_command(
    candidates_csv: Path = typer.Argument(
        ...,
        exists=True,
        readable=True,
        help="Complete passages.csv with included and excluded screened candidates.",
    ),
    output_dir: Path = typer.Option(
        PROJECT_ROOT / "data" / "derived" / "corpus_relevance_audit"
    ),
    included_limit: int = typer.Option(75, min=1),
    excluded_limit: int = typer.Option(75, min=1),
    seed: str = typer.Option(
        "employee-corpus-relevance-v1", help="Deterministic, prespecified selection seed."
    ),
) -> None:
    """Create an assessor-blinded packet and separate private sampling key."""
    audit = prepare_corpus_relevance_audit(
        candidates_csv,
        included_limit=included_limit,
        excluded_limit=excluded_limit,
        seed=seed,
    )
    write_corpus_relevance_audit(output_dir, audit)
    typer.echo("Corpus relevance/recall gate: pending_human_labels")
    included_count = sum(row["inclusion_decision"] == "included" for row in audit.key_rows)
    excluded_count = sum(row["inclusion_decision"] == "excluded" for row in audit.key_rows)
    typer.echo(f"Included audit items: {included_count}")
    typer.echo(f"Excluded audit items: {excluded_count}")
    typer.echo(f"Wrote blinded packet and separate private key to {output_dir}")


@app.command("score-corpus-relevance-audit")
def score_corpus_relevance_audit_command(
    private_key_csv: Path = typer.Argument(..., exists=True, readable=True),
    completed_packet_csv: Path = typer.Argument(..., exists=True, readable=True),
    audit_manifest_json: Path = typer.Argument(..., exists=True, readable=True),
    output_dir: Path = typer.Option(
        PROJECT_ROOT / "data" / "derived" / "corpus_relevance_scores"
    ),
) -> None:
    """Validate complete human labels and score the prespecified 90%/5% gate."""
    score = score_corpus_relevance_audit(
        private_key_csv,
        completed_packet_csv,
        audit_manifest_json,
    )
    write_corpus_relevance_scores(output_dir, score)
    typer.echo(f"Corpus relevance/recall gate: {score.status}")
    typer.echo(f"Wrote audit scores to {output_dir}")


@app.command("build-deal-architecture")
def build_deal_architecture_command(
    evidence_register_csv: Path = typer.Argument(
        PROJECT_ROOT / "config" / "pilot_deal_architecture_evidence.csv",
        exists=True,
        readable=True,
        help="Version-controlled evidence register: one row per deal, attribute, and source.",
    ),
    output_dir: Path = typer.Option(PROJECT_ROOT / "data" / "derived" / "deal_architecture_pilot"),
) -> None:
    """Derive the 10-deal architecture review table from source-backed attributes.

    Archetypes are machine suggestions pending human review; the human fields stay blank.
    """
    result = build_deal_architecture(evidence_register_csv)
    write_deal_architecture(output_dir, result)
    typer.echo(f"Deals coded: {result.manifest['deal_count']}")
    typer.echo(f"Evidence rows: {result.manifest['evidence_row_count']}")
    typer.echo(f"Suggested archetypes: {result.manifest['machine_suggested_archetype_counts']}")
    typer.echo(f"Review status: {result.manifest['review_status']}")
    typer.echo(f"Wrote {output_dir}")


@app.command("build-architecture-topic-crosstable")
def build_architecture_topic_crosstable_command(
    architecture_csv: Path = typer.Argument(..., exists=True, readable=True),
    deal_topic_matrix_csv: Path = typer.Argument(..., exists=True, readable=True),
    corpus_passages_csv: Path = typer.Argument(
        ..., exists=True, readable=True, help="passages.csv the topic model was fitted on."
    ),
    topic_assignments_csv: Path | None = typer.Option(None, exists=True, readable=True),
    corpus_audit_dir: Path | None = typer.Option(None, exists=True, file_okay=False),
    corpus_scores_dir: Path | None = typer.Option(None, exists=True, file_okay=False),
    output_dir: Path = typer.Option(
        PROJECT_ROOT / "data" / "derived" / "architecture_topic_crosstable"
    ),
) -> None:
    """Join deal-architecture attributes to deal-level topic weights, descriptively.

    Every row carries the corpus-validation and architecture-review labels of its inputs.
    """
    corpus_validation = resolve_corpus_validation(
        corpus_audit_dir,
        corpus_scores_dir,
        expected_candidate_sha256=hashlib.sha256(corpus_passages_csv.read_bytes()).hexdigest(),
    )
    table = build_crosstable(
        architecture_csv, deal_topic_matrix_csv, topic_assignments_csv, corpus_validation
    )
    write_crosstable(output_dir, table)
    typer.echo(f"Cross-table rows: {table.manifest['row_count']}")
    typer.echo(f"Corpus validation: {corpus_validation.status}")
    typer.echo(f"Wrote {output_dir}")


@app.command("analyze-employee-tone")
def analyze_employee_tone_command(
    passages_csv: Path = typer.Argument(..., exists=True, readable=True),
    output_dir: Path = typer.Option(PROJECT_ROOT / "data" / "derived" / "employee_tone"),
    corpus_audit_dir: Path | None = typer.Option(None, exists=True, file_okay=False),
    corpus_scores_dir: Path | None = typer.Option(None, exists=True, file_okay=False),
) -> None:
    """Analyze tone, hedging, and word usage in included employee passages.

    Tone is a secondary drafting-style diagnostic. The manifest records the corpus hash and
    its human relevance-audit state so the tables cannot outrun the corpus gate.
    """
    corpus_validation = resolve_corpus_validation(
        corpus_audit_dir,
        corpus_scores_dir,
        expected_candidate_sha256=hashlib.sha256(passages_csv.read_bytes()).hexdigest(),
    )
    analysis = analyze_employee_tone(passages_csv, corpus_validation=corpus_validation)
    write_employee_tone(output_dir, analysis)
    typer.echo(
        f"Analyzed tone for {analysis.passage_count} passages across {analysis.deal_count} deals"
    )
    typer.echo(f"Wrote tone analysis to {output_dir}")


@app.command("analyze-employee-topics")
def analyze_employee_topics_command(
    review_csv: Path = typer.Argument(..., exists=True, readable=True),
    corpus_dir: Path = typer.Argument(..., exists=True, file_okay=False),
    output_dir: Path = typer.Option(PROJECT_ROOT / "data" / "derived" / "employee_topics"),
    seed: int = typer.Option(1729),
    min_passages: int = typer.Option(75, min=1),
    min_deals: int = typer.Option(3, min=1),
    k_min: int = typer.Option(3, min=2),
    k_max: int = typer.Option(7, min=2),
    bootstrap_replicates: int = typer.Option(100, min=1),
    embedding_svd_components: int = typer.Option(50, min=1),
    embedding_hdbscan_min_cluster_size: int = typer.Option(5, min=2),
    fit_balance: str = typer.Option(
        "deal", help="Fit-universe balancing: deal, source_family, or none."
    ),
    max_fit_passages: int = typer.Option(
        240,
        min=10,
        help="Bounded fit-universe size. Raise it with the deal count so each deal keeps "
        "several representative rows.",
    ),
) -> None:
    """Fit deterministic topics and propagate assignments through every passage source."""
    config = TopicModelConfig(
        seed=seed,
        max_fit_passages=max_fit_passages,
        min_passages=min_passages,
        min_deals=min_deals,
        k_min=k_min,
        k_max=k_max,
        bootstrap_replicates=bootstrap_replicates,
        embedding_svd_components=embedding_svd_components,
        embedding_hdbscan_min_cluster_size=embedding_hdbscan_min_cluster_size,
        fit_balance=fit_balance,
    )
    summary = analyze_employee_topics_workflow(
        review_csv,
        corpus_dir,
        output_dir,
        config=config,
    )
    typer.echo(f"Analysis status: {summary.status}")
    for label, count in summary.counts.items():
        typer.echo(f"{label}: {count}")
    typer.echo(f"Wrote {summary.output_dir}")


@app.command("summarize-employee-topics")
def summarize_employee_topics_command(
    review_csv: Path = typer.Argument(..., exists=True, readable=True),
    corpus_dir: Path = typer.Argument(..., exists=True, file_okay=False),
    analysis_dir: Path = typer.Argument(..., exists=True, file_okay=False),
    output_dir: Path = typer.Option(PROJECT_ROOT / "data" / "derived" / "employee_report"),
    representative_limit: int = typer.Option(3, min=1),
    corpus_audit_dir: Path | None = typer.Option(
        None, exists=True, file_okay=False, help="Prepared relevance-audit packet directory."
    ),
    corpus_scores_dir: Path | None = typer.Option(
        None, exists=True, file_okay=False, help="Scored relevance-audit directory."
    ),
) -> None:
    """Validate model artifacts and write the descriptive report and review queue.

    Without a scored, passing corpus audit the report verdict is withheld rather than passed.
    """
    summary = summarize_employee_topics_workflow(
        review_csv,
        corpus_dir,
        analysis_dir,
        output_dir,
        representative_limit=representative_limit,
        corpus_audit_dir=corpus_audit_dir,
        corpus_scores_dir=corpus_scores_dir,
    )
    typer.echo(f"Report gate: {summary.status}")
    for label, count in summary.counts.items():
        typer.echo(f"{label}: {count}")
    typer.echo(f"Wrote {summary.output_dir}")


@app.command("prepare-employee-topic-review")
def prepare_employee_topic_review_command(
    assignments_csv: Path = typer.Argument(
        ...,
        exists=True,
        readable=True,
        help="Canonical topic assignments from analyze-employee-topics.",
    ),
    passages_csv: Path = typer.Argument(
        ...,
        exists=True,
        readable=True,
        help="Canonical passages used for the topic analysis.",
    ),
    output_dir: Path = typer.Option(
        PROJECT_ROOT / "data" / "derived" / "employee_topic_review"
    ),
    top_n: int = typer.Option(10, min=1, help="Highest-weight primary passages per topic."),
    seed: int = typer.Option(20260823, help="Seed for topic aliases and packet order."),
) -> None:
    """Create blinded, randomized coding files and a private topic-review key."""
    result = prepare_topic_review(
        assignments_csv,
        passages_csv,
        output_dir,
        config=TopicReviewConfig(top_n=top_n, seed=seed),
    )
    typer.echo(f"Topics: {result.topic_count}")
    typer.echo(f"Review items: {result.review_item_count}")
    typer.echo(f"Packet SHA-256: {result.packet_sha256}")
    typer.echo(f"Wrote {result.output_dir}")


@app.command("score-employee-topic-review")
def score_employee_topic_review_command(
    key_csv: Path = typer.Argument(..., exists=True, readable=True),
    reviewer_one_csv: Path = typer.Argument(..., exists=True, readable=True),
    reviewer_two_csv: Path = typer.Argument(..., exists=True, readable=True),
    output_dir: Path = typer.Option(
        PROJECT_ROOT / "data" / "derived" / "employee_topic_review_scores"
    ),
    top_n: int = typer.Option(10, min=1, help="Required completed passages per topic."),
    min_fit_rate: float = typer.Option(
        0.80, min=0.0, max=1.0, help="Minimum reviewer-level 'fit' rate for every topic."
    ),
    min_exact_agreement: float = typer.Option(
        0.80, min=0.0, max=1.0, help="Minimum exact code agreement."
    ),
    min_agreement_coefficient: float = typer.Option(
        0.70, min=0.0, max=1.0, help="Minimum kappa, or AC1 when kappa is undefined."
    ),
) -> None:
    """Validate two independent coding files and emit human-review release gates."""
    result = score_topic_review(
        key_csv,
        reviewer_one_csv,
        reviewer_two_csv,
        output_dir,
        config=TopicReviewConfig(
            top_n=top_n,
            min_fit_rate=min_fit_rate,
            min_exact_agreement=min_exact_agreement,
            min_agreement_coefficient=min_agreement_coefficient,
        ),
    )
    typer.echo(f"Human review release gate: {result.status}")
    typer.echo(f"Topics scored: {len(result.topic_scores)}")
    typer.echo(f"Wrote {result.output_dir}")


@app.command()
def vertical_slice(
    deal_id: str = typer.Option(..., help="Stable local deal identifier."),
    acquirer_cik: str = typer.Option(..., help="Manually confirmed public-acquirer CIK."),
    target_cik: str | None = typer.Option(
        None, help="Optional manually confirmed public-target CIK."
    ),
    announcement: str = typer.Option(..., help="Announcement date in YYYY-MM-DD format."),
    effective: str | None = typer.Option(None, help="Closing/effective date in YYYY-MM-DD format."),
    target_name: str | None = typer.Option(
        None, help="Optional target name, used only as a ranking feature."
    ),
    output_dir: Path = typer.Option(PROJECT_ROOT / "data" / "derived" / "vertical_slice"),
    include_expanded: bool = typer.Option(
        False,
        "--include-expanded/--core-only",
        help="Include configured communications and foreign-issuer forms in addition to core forms.",
    ),
) -> None:
    """Run EDGAR retrieval for the confirmed acquirer and, when supplied, target."""
    settings = load_settings(require_user_agent=True)
    deal = Deal(
        deal_id=deal_id,
        acquirer_cik=acquirer_cik,
        announcement_date=_parse_date(announcement),
        effective_date=_parse_date(effective) if effective else None,
        target_name=target_name,
        target_cik=target_cik,
    )
    counts = run_vertical_slice(
        deal,
        settings,
        output_dir,
        settings.selected_forms(include_expanded),
    )
    typer.echo(f"Wrote {output_dir}")
    for label, count in counts.items():
        typer.echo(f"{label}: {count}")


def _value_or(raw: str, default: float) -> float:
    try:
        return float(raw.replace(",", ""))
    except ValueError:
        return default


@app.command("screen-disclosure-pool")
def screen_disclosure_pool_command(
    catalog_csv: Path = typer.Argument(..., exists=True, readable=True),
    output_dir: Path = typer.Option(PROJECT_ROOT / "data" / "derived" / "disclosure_pool"),
    config_path: Path = typer.Option(
        PROJECT_ROOT / "config" / "disclosure_pool.toml", exists=True, readable=True
    ),
    technology_config: Path = typer.Option(
        PROJECT_ROOT / "config" / "technology_sic.toml", exists=True, readable=True
    ),
    start: str = typer.Option("", help="Optional ISO start date for announcement filtering."),
    end: str = typer.Option("", help="Optional ISO end date for announcement filtering."),
) -> None:
    """Select the disclosure-first candidate pool from the deal catalog (offline)."""
    config = load_disclosure_pool_config(config_path)
    screen = load_technology_screen(technology_config)
    result = build_disclosure_pool(
        catalog_csv,
        screen,
        config,
        start=_parse_date(start) if start else None,
        end=_parse_date(end) if end else None,
    )
    write_disclosure_pool(output_dir, result)
    typer.echo(f"Pool rows: {len(result.rows)}")
    for reason, count in sorted(result.exclusions.items()):
        if count:
            typer.echo(f"excluded {reason}: {count}")
    typer.echo(f"Wrote {output_dir}")


@app.command("probe-disclosure")
def probe_disclosure_command(
    pool_csv: Path = typer.Argument(..., exists=True, readable=True),
    output_dir: Path = typer.Option(PROJECT_ROOT / "data" / "derived" / "disclosure_probe"),
    config_path: Path = typer.Option(
        PROJECT_ROOT / "config" / "disclosure_pool.toml", exists=True, readable=True
    ),
    limit: int = typer.Option(0, min=0, help="Probe at most this many deals; 0 probes all."),
    confirm_target_name: bool = typer.Option(
        True,
        "--confirm-target-name/--skip-target-name",
        help="Check that the acquirer filing names the target (corroborates the CIK match).",
    ),
) -> None:
    """Ask EDGAR which pooled deals actually have a transaction filing (live)."""
    config = load_disclosure_pool_config(config_path)
    settings = load_settings(require_user_agent=True)
    with pool_csv.open(newline="", encoding="utf-8") as file:
        pool = [{k: (v or "") for k, v in row.items()} for row in csv.DictReader(file)]
    if limit:
        pool = pool[:limit]

    rows: list[dict[str, str]] = []
    counts: dict[str, int] = {}
    with (
        SecClient(settings.user_agent, settings.cache_dir, settings.rate_per_second) as client,
        Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
        ) as progress,
    ):
        task = progress.add_task("probing", total=len(pool))
        for row in pool:
            outcome = probe_deal(
                client,
                row,
                config,
                settings.selected_forms(False),
                confirm_target_name=confirm_target_name,
            )
            rows.append(probe_row(row, outcome))
            counts[outcome.status] = counts.get(outcome.status, 0) + 1
            progress.advance(task)

    rows.sort(
        key=lambda item: (
            PROBE_STATUS_RANK.get(item["probe_status"], 9),
            item["target_name_hit"] != "yes",
            -_value_or(item.get("windowed_filings", ""), 0.0),
            -_value_or(item.get("transaction_value_mil", ""), -1.0),
            item["deal_id"],
        )
    )
    positive = sum(counts.get(status, 0) for status in ("agreement_exhibit", "merger_proxy"))
    manifest: dict[str, object] = {
        "schema_version": 1,
        "pool_rule_version": config.version,
        "pool_csv_sha256": hashlib.sha256(pool_csv.read_bytes()).hexdigest(),
        "probed_deals": len(rows),
        "status_counts": counts,
        "probe_positive_deals": positive,
        "target_name_confirmed": sum(1 for row in rows if row["target_name_hit"] == "yes"),
        "probe_window": (
            "tag_edgar.windows.event_window: announcement-30d to effective+30d, or "
            "announcement+365d when no closing date is recorded"
        ),
        "confirm_target_name": confirm_target_name,
        "evidence_boundary": (
            "probe_status records which forms exist, not what they disclose; target_name_hit is a "
            "machine corroboration and is not human review"
        ),
    }
    write_probe_results(output_dir, rows, manifest)
    for status, count in sorted(counts.items()):
        typer.echo(f"{status}: {count}")
    typer.echo(f"probe-positive: {positive}")
    typer.echo(f"Wrote {output_dir}")


@app.command("build-disclosure-queue")
def build_disclosure_queue_command(
    probe_csv: Path = typer.Argument(..., exists=True, readable=True),
    output_csv: Path = typer.Option(
        PROJECT_ROOT / "data" / "derived" / "disclosure_review_queue.csv"
    ),
    limit: int = typer.Option(300, min=1, help="Cap the number of deals queued for retrieval."),
    include_announcement_only: bool = typer.Option(
        False,
        "--include-announcement-only/--positive-only",
        help="Also queue deals whose window holds only a press release.",
    ),
) -> None:
    """Turn probe-positive deals into a retrieval queue the existing pipeline can run."""
    accepted = {"agreement_exhibit", "merger_proxy"}
    if include_announcement_only:
        accepted.add("announcement_only")
    with probe_csv.open(newline="", encoding="utf-8") as file:
        rows = [
            {k: (v or "") for k, v in row.items()}
            for row in csv.DictReader(file)
            if (row.get("probe_status") or "") in accepted
        ]
    queued: list[dict[str, str]] = []
    for row in rows[:limit]:
        confirmed = row.get("target_name_hit") == "yes"
        queued.append(
            {
                "deal_id": row["deal_id"],
                "announcement_date": row["announcement_date"],
                "effective_date": row["effective_date"],
                "acquirer_name": row["acquirer_name"],
                "target_name": row["target_name"],
                "target_public_status": row.get("target_public_status", ""),
                "transaction_value_mil": row.get("transaction_value_mil", ""),
                "candidate_cik": row["candidate_cik"],
                "cik_match_method": row.get("cik_confirmation_basis", ""),
                "cik_match_confidence": "machine_probe_confirmed",
                "cik_manual_status": "confirmed",
                "cik_reviewer_note": (
                    "Machine confirmation: an acquirer filing in the announcement window names "
                    "the target. This is not human review."
                    if confirmed
                    else "Machine confirmation: transaction form present in window; target name "
                    "not corroborated in the primary document."
                ),
                "pilot_status": "selected",
                "technology_scope_status": "in_scope",
                "technology_screen_version": "digital-tech-v1",
                "technology_screen_reason": "target SIC in config/technology_sic.toml",
                "pilot_reviewer_note": f"probe_status={row['probe_status']}",
                "target_candidate_cik": row.get("target_candidate_cik", ""),
                "target_cik_manual_status": "",
                "target_cik_reviewer_note": "",
            }
        )
    if not queued:
        raise typer.BadParameter("No probe-positive deals to queue.")
    write_dict_csv(output_csv, queued, list(queued[0]))
    typer.echo(f"Queued {len(queued)} deals -> {output_csv}")


@app.command("run-disclosure-sample")
def run_disclosure_sample_command(
    queue_csv: Path = typer.Argument(..., exists=True, readable=True),
    output_dir: Path = typer.Option(PROJECT_ROOT / "data" / "derived" / "disclosure_runs"),
    include_expanded: bool = typer.Option(False, "--include-expanded/--core-only"),
    resume: bool = typer.Option(
        True, "--resume/--no-resume", help="Skip deals whose run directory already has documents."
    ),
) -> None:
    """Retrieve EDGAR documents for every queued deal, resumably (live, long-running)."""
    deals = approved_deals(queue_csv)
    if not deals:
        raise typer.BadParameter("Queue holds no approved rows.")
    settings = load_settings(require_user_agent=True)
    forms = settings.selected_forms(include_expanded)
    summaries: list[dict[str, str | int]] = []
    completed = 0
    for index, deal in enumerate(deals, start=1):
        deal_dir = output_dir / deal.deal_id
        if resume and (deal_dir / "documents.csv").exists():
            typer.echo(f"[{index}/{len(deals)}] {deal.deal_id}: already retrieved")
            continue
        try:
            counts = run_vertical_slice(deal, settings, deal_dir, forms)
        except (RuntimeError, ValueError, TypeError) as error:
            typer.echo(f"[{index}/{len(deals)}] {deal.deal_id}: FAILED {error}")
            summaries.append({"deal_id": deal.deal_id, "error": str(error)[:200]})
            continue
        completed += 1
        summaries.append({"deal_id": deal.deal_id, **counts})
        typer.echo(
            f"[{index}/{len(deals)}] {deal.deal_id}: {counts['documents']} documents, "
            f"{counts['evidence']} evidence"
        )
    if summaries:
        fields = sorted({key for row in summaries for key in row} - {"deal_id"})
        write_dict_csv(output_dir / "run_summary.csv", summaries, ["deal_id", *fields])
    typer.echo(f"Retrieved {completed} deals -> {output_dir}")


@app.command("freeze-disclosure-sample")
def freeze_disclosure_sample_command(
    queue_csv: Path = typer.Argument(..., exists=True, readable=True),
    passages_csv: Path = typer.Argument(..., exists=True, readable=True),
    runs_dir: Path = typer.Argument(..., exists=True, file_okay=False),
    output_dir: Path = typer.Option(
        PROJECT_ROOT / "data" / "derived" / "disclosure_frozen_sample"
    ),
    probe_csv: Path | None = typer.Option(
        None, exists=True, readable=True, help="Probe results, to carry probe evidence forward."
    ),
    config_path: Path = typer.Option(
        PROJECT_ROOT / "config" / "disclosure_pool.toml", exists=True, readable=True
    ),
) -> None:
    """Apply the yield gate and freeze the deal list the report is built from (offline)."""
    config = load_disclosure_pool_config(config_path)
    sample = build_frozen_sample(
        queue_csv, passages_csv, runs_dir, config, probe_csv=probe_csv
    )
    write_frozen_sample(output_dir, sample)
    status_counts = sample.manifest["status_counts"]
    if isinstance(status_counts, dict):
        for status, count in sorted(status_counts.items()):
            typer.echo(f"{status}: {count}")
    typer.echo(f"modelled passages: {sample.manifest['modelled_passages']}")
    typer.echo(f"largest deal share: {sample.manifest['largest_deal_share']}")
    typer.echo(f"Wrote {output_dir}")


if __name__ == "__main__":
    app()

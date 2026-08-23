from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

import typer
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn

from .audit import SUMMARY_FIELDS, pilot_audit_rows
from .catalog import CATALOG_FIELDS, build_catalog, create_review_queue
from .cik import fetch_candidates
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
) -> None:
    """Fit deterministic topics and propagate assignments through every passage source."""
    config = TopicModelConfig(
        seed=seed,
        min_passages=min_passages,
        min_deals=min_deals,
        k_min=k_min,
        k_max=k_max,
        bootstrap_replicates=bootstrap_replicates,
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
) -> None:
    """Validate model artifacts and write the descriptive report and review queue."""
    summary = summarize_employee_topics_workflow(
        review_csv,
        corpus_dir,
        analysis_dir,
        output_dir,
        representative_limit=representative_limit,
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


if __name__ == "__main__":
    app()

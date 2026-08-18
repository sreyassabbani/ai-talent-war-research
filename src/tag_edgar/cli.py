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
from .entity_matches import count_deal_seeds, resolve_seed_file
from .ingest import load_column_map, read_deal_seeds
from .models import Deal
from .pipeline import run_vertical_slice
from .review import approved_deals
from .sec_client import SecClient
from .settings import PROJECT_ROOT, load_settings
from .storage import write_csv, write_dict_csv
from .technology import load_technology_screen
from .windows import event_window

app = typer.Typer(help="Enrich SDC/LSEG acquisition events with traceable EDGAR documents.")


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise typer.BadParameter("Dates must use ISO format: YYYY-MM-DD.") from error


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


@app.command("run-reviewed-pilot")
def run_reviewed_pilot(
    review_csv: Path = typer.Argument(..., exists=True, readable=True),
    output_dir: Path = typer.Option(PROJECT_ROOT / "data" / "derived" / "pilot_runs"),
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
        counts = run_vertical_slice(deal, settings, output_dir / deal.deal_id)
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
    counts = run_vertical_slice(deal, settings, output_dir)
    typer.echo(f"Wrote {output_dir}")
    for label, count in counts.items():
        typer.echo(f"{label}: {count}")


if __name__ == "__main__":
    app()

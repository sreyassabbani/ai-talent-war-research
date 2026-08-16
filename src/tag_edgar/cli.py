from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

import typer

from .cik import fetch_candidates
from .ingest import load_column_map, read_deal_seeds
from .models import Deal
from .pipeline import run_vertical_slice
from .sec_client import SecClient
from .settings import PROJECT_ROOT, load_settings
from .storage import write_csv
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
    output_csv: Path = typer.Option(PROJECT_ROOT / "data" / "derived" / "deals_seed.csv"),
) -> None:
    """Normalize a mapped SDC/LSEG export while preserving each raw source row."""
    seeds = read_deal_seeds(input_csv, load_column_map(column_map))
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


@app.command()
def vertical_slice(
    deal_id: str = typer.Option(..., help="Stable local deal identifier."),
    acquirer_cik: str = typer.Option(..., help="Manually confirmed public-acquirer CIK."),
    announcement: str = typer.Option(..., help="Announcement date in YYYY-MM-DD format."),
    effective: str | None = typer.Option(None, help="Closing/effective date in YYYY-MM-DD format."),
    target_name: str | None = typer.Option(
        None, help="Optional target name, used only as a ranking feature."
    ),
    output_dir: Path = typer.Option(PROJECT_ROOT / "data" / "derived" / "vertical_slice"),
) -> None:
    """Run the first end-to-end EDGAR retrieval pilot for one verified CIK."""
    settings = load_settings(require_user_agent=True)
    deal = Deal(
        deal_id=deal_id,
        acquirer_cik=acquirer_cik,
        announcement_date=_parse_date(announcement),
        effective_date=_parse_date(effective) if effective else None,
        target_name=target_name,
    )
    counts = run_vertical_slice(deal, settings, output_dir)
    typer.echo(f"Wrote {output_dir}")
    for label, count in counts.items():
        typer.echo(f"{label}: {count}")


if __name__ == "__main__":
    app()

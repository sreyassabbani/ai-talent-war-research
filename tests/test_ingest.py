from pathlib import Path

from tag_edgar.ingest import load_column_map, read_deal_seeds


def test_ingest_normalizes_dates_and_preserves_source_row(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    source.write_text(
        "Deal No,Buyer,Buyer Ticker,Target,Target Ticker,Announced,Closed\n"
        "42,Example Buyer,BUY,Example Target,TGT,01/10/2024,20240410\n",
        encoding="utf-8",
    )
    mapping = tmp_path / "columns.toml"
    mapping.write_text(
        "[columns]\n"
        'deal_id = "Deal No"\n'
        'acquirer_name = "Buyer"\n'
        'acquirer_ticker = "Buyer Ticker"\n'
        'target_name = "Target"\n'
        'target_ticker = "Target Ticker"\n'
        'announcement_date = "Announced"\n'
        'effective_date = "Closed"\n',
        encoding="utf-8",
    )

    seeds = read_deal_seeds(source, load_column_map(mapping))

    assert len(seeds) == 1
    assert seeds[0].deal_id == "42"
    assert seeds[0].announcement_date.isoformat() == "2024-01-10"
    assert seeds[0].effective_date is not None
    assert seeds[0].effective_date.isoformat() == "2024-04-10"
    assert '"Buyer": "Example Buyer"' in seeds[0].raw_source_row

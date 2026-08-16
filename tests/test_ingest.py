from pathlib import Path

from tag_edgar.ingest import _unique_headers, load_column_map, read_deal_seeds


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


def test_ingest_handles_thomson_metadata_and_wrapped_headers(tmp_path: Path) -> None:
    source = tmp_path / "sdc.csv"
    source.write_text(
        "Source: Thomson Reuters,,,,,,\n"
        '" Deal\nNumber"," Date\nAnnounced"," Date\nEffective","Acquiror Ultimate\nParent","Acquiror Ultimate Parent\nTicker Symbol","Target Name","Target\nTicker Symbol"\n'
        '"42","01/10/24","04/10/24","Example Public Corp","EX","Example Target","TGT"\n',
        encoding="utf-8",
    )
    mapping = tmp_path / "columns.toml"
    mapping.write_text(
        "[columns]\n"
        'deal_id = "Deal Number"\n'
        'acquirer_name = "Acquiror Ultimate Parent"\n'
        'acquirer_ticker = "Acquiror Ultimate Parent Ticker Symbol"\n'
        'target_name = "Target Name"\n'
        'target_ticker = "Target Ticker Symbol"\n'
        'announcement_date = "Date Announced"\n'
        'effective_date = "Date Effective"\n',
        encoding="utf-8",
    )

    seeds = read_deal_seeds(source, load_column_map(mapping), metadata_rows=1)

    assert seeds[0].deal_id == "42"
    assert seeds[0].announcement_date.isoformat() == "2024-01-10"
    assert seeds[0].acquirer_ticker == "EX"


def test_duplicate_sdc_headers_are_retained_with_a_stable_suffix() -> None:
    assert _unique_headers(["Value\nof Transaction", "Value of Transaction"]) == [
        "Value of Transaction",
        "Value of Transaction__2",
    ]


def test_ingest_skips_an_all_empty_export_trailer(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    source.write_text("Deal,Buyer,Date\n1,Example,2024-01-10\n,,\n", encoding="utf-8")
    mapping = tmp_path / "columns.toml"
    mapping.write_text(
        '[columns]\ndeal_id = "Deal"\nacquirer_name = "Buyer"\nannouncement_date = "Date"\n',
        encoding="utf-8",
    )

    seeds = read_deal_seeds(source, load_column_map(mapping))

    assert [seed.deal_id for seed in seeds] == ["1"]

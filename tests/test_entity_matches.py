import csv
from pathlib import Path

from tag_edgar.entity_matches import resolve_seed_file


class FakeSecClient:
    def get_json(self, url: str) -> dict[str, object]:
        assert url.endswith("company_tickers_exchange.json")
        return {
            "fields": ["cik", "name", "ticker", "exchange"],
            "data": [[789019, "MICROSOFT CORP", "MSFT", "Nasdaq"]],
        }


def test_seed_resolution_outputs_both_party_roles_when_target_exists(tmp_path: Path) -> None:
    source = tmp_path / "deals_seed.csv"
    with source.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "deal_id",
                "acquirer_name",
                "acquirer_ticker",
                "target_name",
                "target_ticker",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "deal_id": "one",
                "acquirer_name": "Microsoft Corporation",
                "acquirer_ticker": "MSFT",
                "target_name": "Private Target LLC",
                "target_ticker": "",
            }
        )

    matches = resolve_seed_file(FakeSecClient(), source)  # type: ignore[arg-type]

    assert [(match.party_role, match.confidence) for match in matches] == [
        ("acquirer", "high"),
        ("target", "unresolved"),
    ]

from tag_edgar.cik import entity_match_rows, normalize_company_name, resolve_candidates

REGISTRY: dict[str, object] = {
    "fields": ["cik", "name", "ticker", "exchange"],
    "data": [
        [789019, "MICROSOFT CORP", "MSFT", "Nasdaq"],
        [1652044, "ALPHABET INC.", "GOOGL", "Nasdaq"],
    ],
}


def test_normalize_company_name_removes_common_legal_suffixes() -> None:
    assert normalize_company_name("Alphabet, Inc.") == "alphabet"


def test_exact_ticker_match_is_a_transparent_candidate() -> None:
    candidates = resolve_candidates(REGISTRY, "Microsoft Corporation", "MSFT")

    assert len(candidates) == 1
    assert candidates[0].cik == "0000789019"
    assert candidates[0].match_method == "exact_ticker"
    assert candidates[0].confidence == "high"


def test_exact_name_match_is_medium_confidence_without_ticker() -> None:
    candidates = resolve_candidates(REGISTRY, "Alphabet Inc.")

    assert len(candidates) == 1
    assert candidates[0].match_method == "exact_normalized_name"
    assert candidates[0].confidence == "medium"


def test_no_candidate_is_recorded_as_unresolved_instead_of_being_dropped() -> None:
    matches = entity_match_rows("deal-1", "acquirer", "Private Buyer LLC", None, REGISTRY)

    assert len(matches) == 1
    assert matches[0].candidate_cik is None
    assert matches[0].confidence == "unresolved"
    assert matches[0].manual_status == "pending"

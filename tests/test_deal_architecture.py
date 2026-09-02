import csv
import json
from pathlib import Path

import pytest

from tag_edgar.deal_architecture import (
    ATTRIBUTES,
    EVIDENCE_FIELDS,
    OUTPUT_FIELDS,
    REVIEW_STATUS,
    build_deal_architecture,
    load_evidence_register,
    suggest_archetypes,
    write_deal_architecture,
)

REGISTER = Path(__file__).resolve().parents[1] / "config" / "pilot_deal_architecture_evidence.csv"
URL = "https://www.sec.gov/Archives/edgar/data/1/000000000100000001/ex21.htm"
EXPECTED_SELECTED_DEAL_IDS = {
    "2647141020",
    "3700303020",
    "3705005020",
    "3741094020",
    "3783818020",
    "3847595020",
    "3859429020",
    "3923067020",
    "3948517040",
    "3968186020",
}


def _row(deal_id: str, attribute: str, value: str, **overrides: str) -> dict[str, str]:
    base = {
        "deal_id": deal_id,
        "deal_name": "Buyer–Target",
        "acquirer": "Buyer",
        "target": "Target",
        "agreement_date": "2021-01-01",
        "attribute": attribute,
        "machine_value": value,
        "evidence_basis": "direct_passage",
        "evidence_status": "direct",
        "document_id": "doc-1",
        "document_type": "SEC Exhibit 2.1",
        "source_url": URL,
        "source_locator": "Section 1",
        "excerpt_kind": "verbatim",
        "evidence_excerpt": "Continuing Employees shall receive base salary for twelve months.",
        "limitation": "Contract design only.",
        "salvage_reference": "test",
    }
    if value == "unknown":
        base.update(evidence_basis="unknown", evidence_status="unknown")
    base.update(overrides)
    return base


def _write(path: Path, rows: list[dict[str, str]]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=EVIDENCE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _full_deal(deal_id: str = "deal-1", **values: str) -> list[dict[str, str]]:
    defaults = {
        "legal_transaction_form": "statutory_merger",
        "scope_and_control": "entity_equity|control_transferred",
        "ip_treatment": "acquired_with_entity",
        "business_product_continuity": "unknown",
        "workforce_movement": "group_continuing_employees",
        "talent_motive_explicit": "unknown",
        "talent_salience_signal": "unknown",
    }
    defaults.update(values)
    return [_row(deal_id, attribute, defaults[attribute]) for attribute in ATTRIBUTES]


def test_committed_register_builds_ten_reviewed_deals_with_blank_human_fields() -> None:
    result = build_deal_architecture(REGISTER)

    assert result.manifest["deal_count"] == 10
    assert result.manifest["evidence_row_count"] == 70
    assert [row["deal_id"] for row in result.deal_rows] == sorted(
        row["deal_id"] for row in result.deal_rows
    )
    for row in result.deal_rows:
        assert row["review_status"] == REVIEW_STATUS
        assert row["human_final_archetype"] == ""
        assert row["human_reviewer_id"] == ""
        assert row["human_review_note"] == ""
        assert row["machine_suggested_archetypes"]
        assert list(row) == OUTPUT_FIELDS
    # Every non-unknown attribute is pinned to a document and canonical URL.
    for row in result.evidence_rows:
        if row["machine_value"] != "unknown":
            assert row["document_id"] and row["source_url"].startswith("https://www.sec.gov/")
    # The salvage excerpts are paraphrases, so no highlight URL is fabricated for them.
    statuses = result.manifest["highlight_status_counts"]
    assert isinstance(statuses, dict)
    assert statuses.get("unsupported_paraphrase_not_quotable", 0) > 0
    assert all(row["source_highlight_url"] == "" for row in result.evidence_rows)


def test_committed_register_exactly_matches_selected_pilot_ids() -> None:
    queue_path = REGISTER.parents[1] / "data" / "derived" / "pilot_review_queue.csv"
    manifest_path = (
        REGISTER.parents[1] / "data" / "derived" / "employee_corpus_cycle5" / "corpus_manifest.json"
    )
    register_ids = {row["deal_id"] for row in load_evidence_register(REGISTER)}

    assert register_ids == EXPECTED_SELECTED_DEAL_IDS
    # These generated inputs are git-ignored, but when present they must agree with the committed
    # pilot contract as well as with one another.
    if queue_path.exists() and manifest_path.exists():
        with queue_path.open(newline="", encoding="utf-8") as file:
            selected_queue_ids = {
                row["deal_id"] for row in csv.DictReader(file) if row["pilot_status"] == "selected"
            }
        manifest_ids = set(
            json.loads(manifest_path.read_text(encoding="utf-8"))["selected_deal_ids"]
        )
        assert selected_queue_ids == manifest_ids == EXPECTED_SELECTED_DEAL_IDS
    assert "3923067020" in register_ids  # Fastly–Glitch is the intentional zero/unknown case.


def test_pilot_does_not_invent_license_or_acquihire_structures() -> None:
    """The pilot contains no evidenced license-and-hire or traditional acquihire structure."""
    result = build_deal_architecture(REGISTER)
    suggested = {
        archetype
        for row in result.deal_rows
        for archetype in row["machine_suggested_archetypes"].split("|")
    }
    assert "hire_and_license" not in suggested
    assert "reverse_acquihire" not in suggested
    assert "traditional_acquihire" not in suggested
    assert {"full_acquisition", "asset_acquisition"} & suggested
    skyworks = next(row for row in result.deal_rows if row["deal_id"] == "3700303020")
    assert skyworks["machine_suggested_archetypes"].startswith("asset_acquisition")
    fastly = next(row for row in result.deal_rows if row["deal_id"] == "3923067020")
    assert fastly["machine_suggested_archetypes"] == "unknown"
    assert fastly["unknown_attribute_count"] == str(len(ATTRIBUTES))


def test_verbatim_excerpts_produce_highlight_urls(tmp_path: Path) -> None:
    result = build_deal_architecture(_write(tmp_path / "r.csv", _full_deal()))
    verbatim = [row for row in result.evidence_rows if row["excerpt_kind"] == "verbatim"]
    assert verbatim
    for row in verbatim:
        if row["machine_value"] == "unknown":
            continue
        assert row["highlight_status"] == "ok"
        assert row["source_highlight_url"].startswith(URL + "#:~:text=")


def test_archetype_rules_cover_the_structures_the_study_distinguishes() -> None:
    conventional = suggest_archetypes(
        {
            "scope_and_control": "entity_equity|control_transferred",
            "ip_treatment": "acquired_with_entity",
            "business_product_continuity": "unknown",
            "workforce_movement": "group_continuing_employees",
            "talent_motive_explicit": "no",
            "talent_salience_signal": "unknown",
        }
    )
    assert conventional[0] == ["full_acquisition"]
    assert conventional[1] == "low"

    emphasis = suggest_archetypes(
        {
            "scope_and_control": "entity_equity|control_transferred",
            "ip_treatment": "acquired_with_entity",
            "business_product_continuity": "unknown",
            "workforce_movement": "named_founders_and_key_employees",
            "talent_motive_explicit": "unknown",
            "talent_salience_signal": "yes",
        }
    )
    assert emphasis[0] == ["full_acquisition", "acquisition_with_talent_salience"]
    assert emphasis[1] == "medium"

    acquihire = suggest_archetypes(
        {
            "scope_and_control": "entity_equity|control_transferred",
            "ip_treatment": "acquired_with_entity",
            "business_product_continuity": "discontinued",
            "workforce_movement": "named_founders_and_key_employees",
            "talent_motive_explicit": "yes",
            "talent_salience_signal": "yes",
        }
    )
    assert acquihire[0] == ["traditional_acquihire"]

    licence = suggest_archetypes(
        {
            "scope_and_control": "no_control_transfer",
            "ip_treatment": "licensed",
            "business_product_continuity": "continues_independently",
            "workforce_movement": "named_founders_and_key_employees",
            "talent_motive_explicit": "yes",
            "talent_salience_signal": "yes",
        }
    )
    assert licence[0] == ["hire_and_license", "reverse_acquihire"]

    unknown = suggest_archetypes(
        {
            "scope_and_control": "unknown",
            "ip_treatment": "unknown",
            "business_product_continuity": "unknown",
            "workforce_movement": "unknown",
            "talent_motive_explicit": "unknown",
            "talent_salience_signal": "unknown",
        }
    )
    assert unknown[0] == ["unknown"]
    assert unknown[1] == "high"


def test_register_refuses_unpinned_claims_and_incomplete_deals(tmp_path: Path) -> None:
    rows = _full_deal()
    rows[0]["source_url"] = ""
    with pytest.raises(ValueError, match="source_url is required"):
        load_evidence_register(_write(tmp_path / "a.csv", rows))

    rows = _full_deal()
    rows[0]["excerpt_kind"] = "summary"
    with pytest.raises(ValueError, match="excerpt_kind"):
        load_evidence_register(_write(tmp_path / "b.csv", rows))

    rows = _full_deal()[:-1]
    with pytest.raises(ValueError, match="missing attribute rows"):
        load_evidence_register(_write(tmp_path / "c.csv", rows))

    rows = _full_deal() + [_row("deal-1", "ip_treatment", "licensed")]
    with pytest.raises(ValueError, match="duplicate attribute"):
        load_evidence_register(_write(tmp_path / "d.csv", rows))

    rows = _full_deal()
    rows[-1]["machine_value"] = "unknown"
    rows[-1]["evidence_status"] = "direct"
    with pytest.raises(ValueError, match="unknown value must carry"):
        load_evidence_register(_write(tmp_path / "e.csv", rows))

    rows = _full_deal(talent_motive_explicit="partial")
    with pytest.raises(ValueError, match="talent_motive_explicit must be yes, no, or unknown"):
        load_evidence_register(_write(tmp_path / "f.csv", rows))


def test_written_artifacts_are_hash_linked_and_deterministic(tmp_path: Path) -> None:
    register = _write(tmp_path / "r.csv", _full_deal())
    first_dir, second_dir = tmp_path / "one", tmp_path / "two"
    write_deal_architecture(first_dir, build_deal_architecture(register))
    write_deal_architecture(second_dir, build_deal_architecture(register))

    for name in ("deal_architecture.csv", "deal_architecture_evidence.csv"):
        assert (first_dir / name).read_bytes() == (second_dir / name).read_bytes()
    manifest = json.loads((first_dir / "architecture_manifest.json").read_text(encoding="utf-8"))
    assert manifest["review_status"] == REVIEW_STATUS
    assert manifest["evidence_register_sha256"]
    assert manifest["deal_architecture_sha256"]
    assert manifest["human_fields_left_blank"] == [
        "human_final_archetype",
        "human_reviewer_id",
        "human_review_note",
    ]

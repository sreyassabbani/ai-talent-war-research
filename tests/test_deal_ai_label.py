from __future__ import annotations

import csv
import json
from pathlib import Path

from tag_edgar.deal_ai_label import AI_LABEL_FIELDS, label_deal, label_row, write_deal_ai_labels

AI_PRESS_RELEASE = (
    "Acme Corp today announced the acquisition of WidgetMind Inc. WidgetMind's artificial "
    "intelligence platform applies machine learning and deep learning models to logistics "
    "planning. WidgetMind's neural network research team will join Acme."
)

PLAIN_AGREEMENT = (
    "Section 6.7 Employee Matters. For a period of twelve months following the Effective Time, "
    "Parent shall provide each Continuing Employee with a base salary no less favorable than "
    "that provided immediately prior to the Effective Time."
)

WEAK_MENTION = (
    "WidgetMind Inc manufactures robotics components for warehouse automation and conveyor "
    "systems used across distribution centers."
)

URL = "https://www.sec.gov/Archives/edgar/data/1/000121000001/ex991.htm"


def test_explicit_ai_language_is_labelled_and_evidenced() -> None:
    label = label_deal("deal_1", "WidgetMind Inc", [(URL, AI_PRESS_RELEASE)])
    assert label.label == "ai_explicit"
    assert label.weight >= 5
    assert "artificial intelligence" in label.terms
    assert label.source_url == URL
    assert label.excerpt


def test_deal_without_ai_language_is_none_not_missing() -> None:
    label = label_deal("deal_2", "WidgetMind Inc", [(URL, PLAIN_AGREEMENT)])
    assert label.label == "none"
    assert label.weight == 0
    assert label.terms == ()


def test_weak_mention_alone_does_not_qualify_as_explicit() -> None:
    """Robotics is not artificial intelligence; the earlier screen's false positives came here."""
    label = label_deal("deal_3", "WidgetMind Inc", [(URL, WEAK_MENTION)])
    assert label.label != "ai_explicit"


def test_strongest_document_across_the_deal_wins() -> None:
    label = label_deal(
        "deal_4",
        "WidgetMind Inc",
        [(URL, PLAIN_AGREEMENT), ("https://example.invalid/pr.htm", AI_PRESS_RELEASE)],
    )
    assert label.label == "ai_explicit"
    assert label.source_url == "https://example.invalid/pr.htm"
    assert label.documents_screened == 2


def test_ai_evidence_must_sit_near_the_target_name() -> None:
    """A buyer describing its own AI strategy must not qualify an unrelated target."""
    unrelated = (
        "Acme Corp continues to invest in artificial intelligence and machine learning across "
        "its own product lines. " + "Filler sentence about unrelated matters. " * 40
        + "Separately, Acme acquired Bolt Fasteners Inc, a supplier of industrial hardware."
    )
    label = label_deal("deal_5", "Bolt Fasteners Inc", [(URL, unrelated)])
    assert label.label == "none"


def test_empty_documents_yield_none_without_error() -> None:
    label = label_deal("deal_6", "WidgetMind Inc", [])
    assert label.label == "none"
    assert label.documents_screened == 0


def test_row_carries_review_status_and_highlight_link() -> None:
    label = label_deal("deal_7", "WidgetMind Inc", [(URL, AI_PRESS_RELEASE)])
    row = label_row(label, "Acme Corp", "WidgetMind Inc")
    assert set(row) == set(AI_LABEL_FIELDS)
    assert row["review_status"] == "machine_suggested_pending_human_review"
    assert row["ai_source_highlight_url"].startswith(URL)
    assert "#:~:text=" in row["ai_source_highlight_url"]


def test_write_emits_schema_and_boundary(tmp_path: Path) -> None:
    label = label_deal("deal_8", "WidgetMind Inc", [(URL, AI_PRESS_RELEASE)])
    row = label_row(label, "Acme Corp", "WidgetMind Inc")
    write_deal_ai_labels(
        tmp_path,
        [row],
        {"labelled_deals": 1, "evidence_boundary": "labels are machine-derived"},
    )
    with (tmp_path / "deal_ai_labels.csv").open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        assert reader.fieldnames == AI_LABEL_FIELDS
        assert next(reader)["ai_label"] == "ai_explicit"
    manifest = json.loads((tmp_path / "ai_label_manifest.json").read_text(encoding="utf-8"))
    assert manifest["labelled_deals"] == 1

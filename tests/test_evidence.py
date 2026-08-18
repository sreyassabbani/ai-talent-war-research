from tag_edgar.evidence import find_evidence
from tag_edgar.models import Document


def _document() -> Document:
    return Document(
        document_id="doc_1",
        accession_number="0000000000-00-000001",
        cik="0000000001",
        sequence="1",
        description="8-K",
        document_name="form8k.htm",
        document_type="8-K",
        url="https://example.test/form8k.htm",
        is_primary=True,
    )


def test_evidence_stores_excerpt_category_and_location() -> None:
    document = _document()
    found = find_evidence(
        "deal_1",
        document,
        "The company offered a retention bonus conditional on continued employment.",
        {"retention_compensation": ("retention bonus",)},
    )
    assert len(found) == 1
    assert found[0].category == "retention_compensation"
    assert "retention bonus" in found[0].excerpt.lower()
    assert found[0].match_start == 22
    assert found[0].match_end == 37


def test_evidence_patterns_do_not_match_inside_other_words() -> None:
    found = find_evidence(
        "deal_1",
        _document(),
        "Cash flows from investing activities required a determination by the board.",
        {
            "retention_compensation": ("vesting",),
            "exit_protections": ("termination",),
        },
    )

    assert found == []


def test_evidence_keeps_later_distinct_occurrences() -> None:
    found = find_evidence(
        "deal_1",
        _document(),
        "Retention appears in the contents. The employee retention term appears later.",
        {"retention_compensation": ("retention",)},
    )

    assert len(found) == 2
    assert found[0].match_start < found[1].match_start
    assert found[0].evidence_id != found[1].evidence_id


def test_evidence_prefers_the_longest_pattern_at_the_same_location() -> None:
    found = find_evidence(
        "deal_1",
        _document(),
        "A retention bonus was offered.",
        {"retention_compensation": ("retention", "retention bonus")},
    )

    assert [item.pattern for item in found] == ["retention bonus"]

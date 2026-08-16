from tag_edgar.evidence import find_evidence
from tag_edgar.models import Document


def test_evidence_stores_excerpt_and_category() -> None:
    document = Document(
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
    found = find_evidence(
        "deal_1",
        document,
        "The company offered a retention bonus conditional on continued employment.",
        {"retention_compensation": ("retention bonus",)},
    )
    assert len(found) == 1
    assert found[0].category == "retention_compensation"
    assert "retention bonus" in found[0].excerpt.lower()

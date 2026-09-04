from tag_edgar.employee_corpus import (
    CorpusDocument,
    build_employee_corpus,
    is_structural_heading,
    normalize_model_text,
    parse_document,
    screen_employee_terms,
)


def _document(
    document_id: str,
    content: str,
    *,
    deal_id: str = "deal-1",
    source_url: str | None = None,
) -> CorpusDocument:
    return CorpusDocument(
        deal_id=deal_id,
        document_id=document_id,
        accession_number=f"accession-{document_id}",
        document_type="EX-2.1",
        source_url=source_url or f"https://www.sec.gov/Archives/{document_id}.htm",
        content=content,
        content_type="text/html",
    )


def test_parse_document_preserves_headings_offsets_and_hashes() -> None:
    html = """
    <html><script>Retention script noise</script><body>
      <h2>Employee Matters</h2>
      <p>Continuing employees will receive their existing salaries.</p>
      <p><b>Benefits</b></p>
      <div>Each employee benefit plan remains in effect.</div>
    </body></html>
    """

    parsed = parse_document(html.encode(), "text/html")

    assert [block.heading for block in parsed.blocks] == ["Employee Matters", "Benefits"]
    assert "script noise" not in parsed.text
    assert parsed.text[parsed.blocks[0].char_start : parsed.blocks[0].char_end] == (
        parsed.blocks[0].text
    )
    assert parsed.source_sha256 != parsed.text_sha256
    assert len(parsed.source_sha256) == 64


def test_parse_document_splits_a_long_block_at_stable_word_boundaries() -> None:
    text = " ".join(f"word{index}" for index in range(45))

    parsed = parse_document(text, max_block_words=20)

    assert [len(block.text.split()) for block in parsed.blocks] == [20, 20, 5]
    assert parsed.blocks[0].char_start == 0
    assert parsed.blocks[-1].char_end == len(text)


def test_employee_screen_uses_boundaries_and_covers_multiple_people_topics() -> None:
    text = "Employee benefit plans, restricted-stock units, and collective bargaining continue."

    assert screen_employee_terms(text) == (
        "employee",
        "collective bargaining",
        "restricted stock",
        "restricted stock unit",
        "benefit plan",
        "employee benefit",
    )
    assert screen_employee_terms("Investing activities require a determination.") == ()


def test_overlapping_context_windows_merge_within_a_heading() -> None:
    html = """
    <h2>Employee Matters</h2>
    <p>Opening context.</p>
    <p>Employees keep their salaries.</p>
    <p>Existing benefit plans continue.</p>
    <p>Closing context.</p>
    """

    corpus = build_employee_corpus([_document("doc-1", html)], context_blocks=1)

    assert len(corpus.passages) == 1
    assert corpus.passages[0].heading == "Employee Matters"
    assert corpus.passages[0].block_start == 0
    assert corpus.passages[0].block_end == 3
    assert corpus.blocks_matched == 2
    assert corpus.passages[0].screen_terms == ("employee", "employees", "benefit plan")


def test_default_passages_do_not_inherit_neighboring_blocks_or_match_heading_only() -> None:
    html = """
    <h2>Workforce Strategy</h2>
    <p>Opening context about product strategy.</p>
    <p>Key employees receive a retention bonus.</p>
    <p>Closing context about office locations.</p>
    """

    corpus = build_employee_corpus([_document("doc-1", html)])

    assert corpus.blocks_matched == 1
    assert len(corpus.passages) == 1
    assert corpus.passages[0].block_start == 1
    assert corpus.passages[0].block_end == 1
    assert corpus.passages[0].text == "Key employees receive a retention bonus."


def test_exact_duplicates_model_once_and_keep_every_source_occurrence() -> None:
    passage = "<h2>People</h2><p>Key employees receive a retention bonus.</p>"
    documents = [
        _document("doc-b", passage, deal_id="deal-b"),
        _document("doc-a", passage, deal_id="deal-a"),
    ]

    corpus = build_employee_corpus(reversed(documents), context_blocks=0)
    repeated = build_employee_corpus(documents, context_blocks=0)

    assert corpus == repeated
    assert len(corpus.passages) == 1
    assert len(corpus.occurrences) == 2
    assert corpus.passages[0].deal_id == "deal-a"
    assert corpus.passages[0].occurrence_count == 2
    assert {row.deal_id for row in corpus.occurrences} == {"deal-a", "deal-b"}
    assert {row.passage_id for row in corpus.occurrences} == {corpus.passages[0].passage_id}
    assert corpus.passages[0].passage_id.endswith(corpus.passages[0].content_sha256[:16])


def test_model_normalization_masks_numbers_urls_and_normalizes_case() -> None:
    normalized = normalize_model_text("RSUs worth $1,250 vest at HTTPS://EXAMPLE.COM/x.")

    assert normalized == "rsus worth numbertoken vest at urltoken"


def test_same_clause_under_different_headings_is_modelled_once() -> None:
    """The defect this fixes: an exhibit and the S-4 reprinting it disagreed about the heading.

    The clause is identical, so it is one provision and must contribute one modelled row. Before
    the key dropped the heading, the running-header artefact in the wrapper produced a second
    hash and the deal's own language was counted twice against it.
    """
    clause = "<p>Continuing employees keep their base salary for twelve months.</p>"
    documents = [
        _document("ex-2-1", f"<h2>Article VII COVENANTS AND AGREEMENTS</h2>{clause}"),
        _document("s-4", f"<h2>Table of Contents</h2>{clause}"),
    ]

    corpus = build_employee_corpus(documents, context_blocks=0)

    assert len(corpus.passages) == 1
    assert corpus.passages[0].occurrence_count == 2
    assert {row.document_id for row in corpus.occurrences} == {"ex-2-1", "s-4"}


def test_the_surviving_row_keeps_the_real_section_heading() -> None:
    clause = "<p>Continuing employees keep their base salary for twelve months.</p>"
    # "aaa" sorts before "zzz", so the deterministic tie-break alone would pick the artefact.
    documents = [
        _document("aaa-wrapper", f"<h2>Table of Contents</h2>{clause}"),
        _document("zzz-exhibit", f"<h2>Article VII COVENANTS AND AGREEMENTS</h2>{clause}"),
    ]

    corpus = build_employee_corpus(documents, context_blocks=0)

    assert len(corpus.passages) == 1
    assert corpus.passages[0].heading == "Article VII COVENANTS AND AGREEMENTS"
    assert corpus.passages[0].document_id == "zzz-exhibit"


def test_structural_headings_are_kept_out_of_the_modelled_text() -> None:
    clause = "<p>Continuing employees keep their base salary for twelve months.</p>"
    wrapper = build_employee_corpus(
        [_document("s-4", f"<h2>Table of Contents</h2>{clause}")], context_blocks=0
    )
    exhibit = build_employee_corpus(
        [_document("ex", f"<h2>Employee Matters</h2>{clause}")], context_blocks=0
    )

    assert "table" not in wrapper.passages[0].model_text
    assert "contents" not in wrapper.passages[0].model_text
    # A real section heading is a genuine feature and stays.
    assert exhibit.passages[0].model_text.startswith("employee matters")
    # Provenance is not rewritten: the row still records the heading the filing carried.
    assert wrapper.passages[0].heading == "Table of Contents"


def test_structural_heading_detection_keeps_titles_and_drops_furniture() -> None:
    for furniture in (
        "Table of Contents",
        "TABLE OF CONTENTS \u200b",
        "Contents",
        "I- 1",
        "A:",
        "Page 14",
        "Annex B",
        "Article VII",
        "Exhibit 10.1",
        "iv",
        "2.14",
    ):
        assert is_structural_heading(furniture), furniture

    for title in (
        "Article VII COVENANTS AND AGREEMENTS",
        "EMPLOYMENT AGREEMENT",
        "6.12. ERISA Compliance .",
        "Employee Matters",
        "2022 STOCK INCENTIVE PLAN",
        "Section 5.4 Employee Benefits",
        "",
    ):
        assert not is_structural_heading(title), title

    assert not is_structural_heading(None)


def test_clauses_differing_only_in_an_amount_stay_separate_rows() -> None:
    """Deduplication must not normalise numbers away: the amount is the provision."""
    documents = [
        _document("a", "<h2>People</h2><p>A retention bonus of $5,000,000 is payable.</p>"),
        _document("b", "<h2>People</h2><p>A retention bonus of $2,000,000 is payable.</p>"),
    ]

    corpus = build_employee_corpus(documents, context_blocks=0)

    assert len(corpus.passages) == 2

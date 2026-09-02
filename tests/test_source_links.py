from urllib.parse import unquote, urlsplit

from tag_edgar.source_links import (
    MAX_FRAGMENT_CHARS,
    highlight_link,
    text_fragment_url,
)

DOC = "https://www.sec.gov/Archives/edgar/data/896878/000119312521271682/d226456dex21.htm"


def _directive(url: str) -> str:
    fragment = urlsplit(url).fragment
    marker, _, directive = fragment.partition(":~:")
    assert directive.startswith("text=")
    del marker
    return directive[len("text=") :]


def test_exact_quote_round_trips_through_percent_encoding() -> None:
    quote = "Continuing Employees shall receive base salary"
    url = text_fragment_url(DOC, quote)
    assert url.startswith(DOC + "#:~:text=")
    assert unquote(_directive(url)) == quote


def test_whitespace_and_invisible_characters_are_normalized() -> None:
    messy = "Continuing Employees   shall\n\treceive\u200b base salary"
    assert unquote(_directive(text_fragment_url(DOC, messy))) == (
        "Continuing Employees shall receive base salary"
    )


def test_directive_delimiters_are_percent_encoded() -> None:
    # A literal "-", "," or "&" would otherwise be parsed as directive grammar.
    quote = "severance, retention & change-in-control payments are preserved"
    directive = _directive(text_fragment_url(DOC, quote))
    for delimiter in ("-", ",", "&"):
        assert delimiter not in directive
    assert unquote(directive) == quote


def test_unicode_quote_is_encoded_as_utf8() -> None:
    quote = "employees receive €1,000 and a café stipend each month"
    url = text_fragment_url(DOC, quote)
    assert unquote(_directive(url)) == quote
    assert url.isascii()


def test_long_passage_becomes_a_bounded_start_end_range() -> None:
    quote = " ".join(f"clause{index} provides continuing benefits" for index in range(80))
    link = highlight_link(DOC, quote)
    assert link.fragment_kind == "range"
    start, _, end = _directive(link.url).partition(",")
    assert end
    assert len(unquote(start)) <= MAX_FRAGMENT_CHARS
    assert len(unquote(end)) <= MAX_FRAGMENT_CHARS
    assert quote.startswith(unquote(start))
    assert quote.endswith(unquote(end))


def test_existing_query_string_is_preserved() -> None:
    url = text_fragment_url(f"{DOC}?doc=1&v=2", "Continuing Employees shall receive base salary")
    parts = urlsplit(url)
    assert parts.query == "doc=1&v=2"
    assert parts.fragment.startswith(":~:text=")


def test_existing_fragment_is_kept_ahead_of_the_directive() -> None:
    url = text_fragment_url(f"{DOC}#section7", "Continuing Employees shall receive base salary")
    assert urlsplit(url).fragment.startswith("section7:~:text=")


def test_existing_text_directive_is_replaced_not_stacked() -> None:
    url = text_fragment_url(f"{DOC}#:~:text=old%20quote", "Continuing Employees receive salary")
    assert urlsplit(url).fragment.count(":~:") == 1
    assert "old%20quote" not in url


def test_missing_or_relative_urls_return_an_explicit_unsupported_status() -> None:
    quote = "Continuing Employees shall receive base salary"
    assert highlight_link(None, quote).status == "unsupported_missing_url"
    assert highlight_link("", quote).status == "unsupported_missing_url"
    assert highlight_link("   ", quote).status == "unsupported_missing_url"
    assert highlight_link("/Archives/edgar/data/1/x.htm", quote).status == (
        "unsupported_non_absolute_url"
    )
    assert highlight_link("ftp://example.com/x.htm", quote).status == (
        "unsupported_non_absolute_url"
    )


def test_formats_that_cannot_honour_a_text_fragment_are_refused() -> None:
    quote = "Continuing Employees shall receive base salary"
    for path in ("filing.pdf", "report.XML", "data.xsd"):
        link = highlight_link(f"https://www.sec.gov/Archives/{path}", quote)
        assert link.status == "unsupported_document_format"
        assert link.url == ""


def test_empty_or_tiny_quotes_never_produce_a_link() -> None:
    assert highlight_link(DOC, None).status == "unsupported_empty_quote"
    assert highlight_link(DOC, "   \n ").status == "unsupported_empty_quote"
    assert highlight_link(DOC, "employees").status == "unsupported_quote_too_short"
    assert text_fragment_url(DOC, "employees") == ""


def test_unsupported_results_are_empty_strings_not_partial_urls() -> None:
    for url, quote in ((None, "a" * 40), (DOC, ""), ("notaurl", "a" * 40)):
        link = highlight_link(url, quote)
        assert not link.supported
        assert link.url == ""


def test_highlight_urls_propagate_from_corpus_into_topic_artifacts(monkeypatch, tmp_path) -> None:
    """A highlight URL built at corpus time must survive into every evidence-bearing table."""
    from urllib.parse import unquote, urlsplit

    from test_employee_workflow import (
        _cached_document,
        _review,
        _rows,
        _topic_result_for,
    )

    from tag_edgar.employee_workflow import (
        analyze_employee_topics_workflow,
        build_employee_corpus_workflow,
    )

    review = tmp_path / "review.csv"
    runs, cache = tmp_path / "runs", tmp_path / "cache"
    corpus_dir, analysis_dir = tmp_path / "corpus", tmp_path / "analysis"
    _review(review)
    body = b"<h2>Employee Matters</h2><p>Key employees receive a retention bonus.</p>"
    _cached_document(runs, cache, "deal-1", "doc-1", body)
    _cached_document(runs, cache, "deal-2", "doc-2", body)

    build_employee_corpus_workflow(review, runs, corpus_dir, cache)

    passages = _rows(corpus_dir / "passages.csv")
    passage = passages[0]
    highlight = passage["source_highlight_url"]
    assert highlight.startswith(passage["source_url"] + "#:~:text=")
    # The directive must decode back to the passage text the corpus actually stored.
    assert unquote(urlsplit(highlight).fragment.split(":~:text=", 1)[1]) == passage["text"]

    # Each occurrence points at its own document, so each carries its own highlight URL.
    sources = _rows(corpus_dir / "passage_sources.csv")
    assert len(sources) == 2
    for row in sources:
        assert row["source_highlight_url"].startswith(row["source_url"] + "#:~:text=")
    assert len({row["source_highlight_url"] for row in sources}) == 2

    monkeypatch.setattr(
        "tag_edgar.employee_workflow.analyze_employee_topics_csv",
        lambda _path, _config: _topic_result_for(passage),
    )
    analyze_employee_topics_workflow(review, corpus_dir, analysis_dir)

    for name in ("topic_assignments.csv", "canonical_topic_assignments.csv", "source_passages.csv"):
        rows = _rows(analysis_dir / name)
        assert rows, name
        for row in rows:
            assert row["source_highlight_url"].startswith(row["source_url"] + "#:~:text="), name

from datetime import date

from tag_edgar.accessions import accession_directory_url, enumerate_documents, filing_index_url
from tag_edgar.models import Filing
from tag_edgar.sec_client import CachedResponse


class FakeSecClient:
    def __init__(self, html: str) -> None:
        self.html = html

    def get(self, url: str) -> CachedResponse:
        return CachedResponse(
            url=url, content=self.html.encode(), content_type="text/html", from_cache=False
        )


def test_accession_urls_use_undashed_accession_directory() -> None:
    accession = "0001193125-24-123456"
    directory = accession_directory_url("789019", accession)
    assert directory == "https://www.sec.gov/Archives/edgar/data/789019/000119312524123456/"
    assert filing_index_url("789019", accession).endswith("0001193125-24-123456-index.html")


def test_filing_index_enumerates_primary_document_and_exhibits() -> None:
    html = """
    <table>
      <tr><th>Seq</th><th>Description</th><th>Document</th><th>Type</th><th>Size</th></tr>
      <tr><td>1</td><td>8-K</td><td><a href="form8k.htm">form8k.htm</a></td><td>8-K</td><td>1</td></tr>
      <tr><td>2</td><td>Merger agreement</td><td><a href="ex2-1.htm">ex2-1.htm</a></td><td>EX-2.1</td><td>2</td></tr>
      <tr><td>3</td><td>Press release</td><td><a href="ex99-1.htm">ex99-1.htm</a></td><td>EX-99.1</td><td>3</td></tr>
    </table>
    """
    filing = Filing(
        accession_number="0001193125-24-123456",
        cik="0000789019",
        form="8-K",
        filing_date=date(2024, 1, 10),
        report_date=None,
        primary_document="form8k.htm",
    )

    documents = enumerate_documents(FakeSecClient(html), filing)  # type: ignore[arg-type]

    assert [document.document_type for document in documents] == ["8-K", "EX-2.1", "EX-99.1"]
    assert documents[0].is_primary is True
    assert documents[1].url.endswith("/ex2-1.htm")

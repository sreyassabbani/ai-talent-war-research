from tag_edgar.accessions import accession_directory_url, filing_index_url


def test_accession_urls_use_undashed_accession_directory() -> None:
    accession = "0001193125-24-123456"
    directory = accession_directory_url("789019", accession)
    assert directory == "https://www.sec.gov/Archives/edgar/data/789019/000119312524123456/"
    assert filing_index_url("789019", accession).endswith("0001193125-24-123456-index.html")

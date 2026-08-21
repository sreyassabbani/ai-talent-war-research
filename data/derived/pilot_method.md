# Technical method for the 10-deal pilot

## In short

- Built a small **Python command-line pipeline** rather than reviewing EDGAR by hand.
- Used **HTTPX** to download and cache SEC materials, **Beautiful Soup** to read SEC filing-index pages and HTML documents, and **Typer** for the command-line workflow.
- Used **Ruff**, **basedpyright**, and **pytest** to check the code; the pipeline has 35 passing tests.

## How it worked

1. **Choose deals**
   - Started with SDC/LSEG acquisition records.
   - Selected 10 manually approved, 2021–22 digital-technology deals with confirmed acquirer CIKs.

2. **Find filings**
   - Pulled each acquirer’s EDGAR history from 30 days before announcement through 30 days after closing.
   - Searched transaction forms: 8-Ks, S-4s, 424B3s, proxy filings, and tender-offer filings.
   - Opened each filing’s index page and saved its primary document and exhibits, especially EX-2.* agreements, EX-10.* employment/compensation documents, and EX-99.* announcements.

3. **Find possible employee terms**
   - Extracted document text and searched for phrases such as “key employee,” “continued employment,” “retention bonus,” “vesting,” and “change in control.”
   - Saved the matching excerpt, its location, document type, and SEC URL. These were leads, not final findings.

4. **Check the source manually**
   - Reviewed the agreement or announcement for each deal and wrote one source-linked finding.
   - The final audit combines the deal record, retrieved filings/documents, automated leads, and the manual finding.

## Files produced

- One folder per deal: `deals.csv`, `filings.csv`, `documents.csv`, `deal_filings.csv`, and `evidence.csv`.
- One combined audit: `pilot_audit_summary.csv`.
- One human coding file: `pilot_manual_coding.csv`.

## Boundary

- This finds what was **publicly disclosed** in the reviewed filings. It cannot recover private side agreements, omitted schedules, person-level compensation, or whether a retention term worked.

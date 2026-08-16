# SDC-EDGAR Technology Acquisition Enrichment Pilot

## 1. Immediate objective

Build a reproducible pipeline that starts with an SDC/LSEG technology-acquisition event and
identifies potentially relevant SEC filings and exhibits. The pipeline should show what EDGAR
adds to the existing deal record, preserve the source of every extracted observation, and route
ambiguous evidence to human review.

The first research question is deliberately about data feasibility:

> Among SDC-recorded technology acquisitions involving public acquirers, which transaction and
> human-capital fields can be recovered from transaction-related SEC filings, and which kinds of
> deals or disclosures remain unobservable?

This pilot is a prerequisite for later research on employee movement, retention, team formation,
or buy-versus-retain decisions. It does not attempt to answer those later questions yet.

## 2. Success criteria

The pilot succeeds when:

1. A single command can process a small SDC extract without silently dropping a deal.
2. Acquirer and, when applicable, target CIK candidates are recorded with the match method,
   confidence category, and manual-confirmation state.
3. The pipeline searches from shortly before announcement through approximately 30 days after
   closing, rather than relying on a fixed post-announcement window.
4. It retrieves filing histories, opens each candidate accession, enumerates the primary document
   and exhibits, and saves stable SEC URLs.
5. It records keyword hits and short excerpts as review leads, not as verified factual claims.
6. A reviewer can confirm or reject each proposed deal-document link.
7. A derived deal summary distinguishes no filing, no relevant filing, nondisclosure, redaction,
   retrieval failure, and unresolved matching.
8. The code uses an identifiable User-Agent, caches responses, retries safely, and remains
   comfortably below the SEC limit of 10 requests per second.

## 3. Explicit non-goals for the pilot

- Classifying a transaction as an acquihire from generic SDC fields.
- Estimating whether a company should buy talent or spend on retention.
- Treating keyword hits as evidence that an employee received a retention offer.
- Extracting a single "price of talent" from headline transaction value.
- Scraping LinkedIn or constructing employee embeddings.
- Training an ML model before document coverage and labels are known.
- Downloading all of EDGAR.

## 4. Source hierarchy

### 4.1 Event seed: SDC/LSEG

SDC supplies the candidate event universe and baseline metadata. Preserve the original row and
source identifiers. Expected inputs include, when available:

- SDC deal number;
- acquirer and target names;
- announcement and effective dates;
- public/private status;
- ticker, CUSIP, GVKEY, and ultimate-parent identifiers;
- transaction form, status, value, and consideration fields.

SDC metadata is a starting point, not evidence of a talent motive.

### 4.2 Entity resolution: SEC identifiers

Use the SEC's company/ticker files and filing histories to generate CIK candidates. Current ticker
files alone are insufficient for historical firms, renamed firms, acquisition subsidiaries, and
non-registrants, so every resolution must preserve how it was obtained.

CIK resolution states:

- `confirmed`: manually confirmed against SEC identity and deal evidence;
- `high`: exact ticker plus compatible normalized company name;
- `medium`: exact or historical name with supporting metadata;
- `low`: fuzzy-name-only candidate;
- `ambiguous`: multiple plausible candidates;
- `unresolved`: no defensible candidate;
- `not_registrant`: evidence indicates that the party does not file with the SEC.

Do not automatically convert `high` into `confirmed`. The direct acquirer, ultimate parent, merger
subsidiary, bidder, subject company, and filing entity can have different CIKs.

### 4.3 Filing discovery: SEC Submissions API

For each confirmed or reviewable CIK:

1. Retrieve `https://data.sec.gov/submissions/CIK##########.json`.
2. Read the recent filing arrays.
3. Follow the additional historical submission files listed under `filings.files` when the event
   window predates the recent array.
4. Filter by form and event window.
5. Preserve accession number, filing date, report date, primary document, filing entity, form,
   and 8-K items where available.

### 4.4 Accession-level document discovery

The Submissions API identifies filings, not all documents contained in each filing. For every
candidate accession:

1. Construct the accession directory using the filer CIK and accession number without dashes.
2. Open the accession filing-detail page and/or directory index.
3. Enumerate the primary document and every submitted document.
4. Preserve sequence, description, SEC document type, filename, size when available, and URL.
5. Select relevant primary documents and exhibits for text retrieval.
6. Fall back to the complete submission text only when document-level retrieval is unavailable.

Never infer exhibit type from the filename alone when the filing index provides the SEC type.

## 5. Forms and exhibits

### 5.1 Core forms for the first pilot

- `8-K` and `8-K/A`
  - Item 1.01: entry into a material definitive agreement;
  - Item 2.01: completion of an acquisition or disposition;
  - Item 5.02: named executive departures, appointments, employment, or compensation;
  - Item 8.01: voluntary disclosure of other events;
  - Item 9.01: financial statements and exhibit list.
- `S-4`, `S-4/A`, `424B3`.
- `PREM14A`, `PREM14A/A`, `DEFM14A`, `DEFM14A/A`.
- `SC 14D9`, `SC 14D9/A`.
- `SC TO-T`, `SC TO-T/A`, `SC TO-I`, `SC TO-I/A`.

### 5.2 Core document types inside an accession

- the primary filing document;
- `EX-2.*`: acquisition, merger, or asset-purchase agreements;
- `EX-10.*`: material employment, compensation, retention, incentive, or related agreements;
- `EX-99.*`: press releases and supplemental announcements.

### 5.3 Expansion forms after the vertical slice

- `425` and `DEFA14A` communications;
- `PREM14C`, `DEFM14C`, and relevant amendments;
- `SC TO-C` and `SC14D9C` communications;
- `F-4`, `F-4/A`, `6-K`, and `CB` for foreign or cross-border transactions;
- termination, amendment, and later closing filings discovered from the initial filing sequence.

The form list must live in configuration so it can be revised without changing retrieval code.

## 6. Event-window rules

Use dates from the source record as anchors and retain the rule used for every deal.

Default rules:

- `window_start = announcement_date - 30 days`;
- when a valid effective/closing date exists,
  `window_end = effective_date + 30 days`;
- when the effective date is missing, use a configurable provisional endpoint, initially
  `announcement_date + 365 days`, and label the window `closing_missing`;
- when a deal is withdrawn or cancelled and a termination date is available, end 30 days after
  termination;
- flag impossible or suspicious date orderings for review rather than repairing them silently.

The one-year fallback is a discovery rule, not a claim about a standard deal duration. The pilot
should report how many records depend on it so the value can be revised empirically.

## 7. Data model

At minimum, deliver `deals` and `documents`. Internally, use normalized tables so one filing can
contain many documents and one document can contain many pieces of evidence.

### 7.1 `deals`

One row per SDC deal.

Key fields:

- `deal_id`;
- `source_dataset`, `source_row_id`;
- original and normalized acquirer/target names;
- announcement, effective, termination, and derived window dates;
- original SDC identifiers and deal fields;
- acquirer and target CIK candidates;
- CIK match method, confidence, reviewer, and review timestamp;
- retrieval status and structured missingness reason.

### 7.2 `entity_matches`

One row per deal-party-CIK candidate. This prevents discarding alternative matches.

Key fields:

- `deal_id`, `party_role`, `candidate_cik`;
- SEC conformed name and ticker;
- match features and method;
- confidence category;
- `manual_status`, `reviewer_note`.

### 7.3 `filings`

One row per SEC accession encountered.

Key fields:

- `accession_number`;
- filer CIK and filer role;
- form, filing date, report date, acceptance timestamp;
- 8-K item list when available;
- primary-document name;
- filing-detail and complete-submission URLs;
- retrieval and parsing status.

### 7.4 `deal_filings`

Many-to-many link between deals and filings.

Key fields:

- `deal_id`, `accession_number`;
- discovery route: acquirer, target, bidder, subject, or manual;
- date distance from announcement and closing;
- automated relevance score;
- manual verification state and note.

### 7.5 `documents`

One row per document or exhibit inside an accession.

Key fields:

- stable `document_id`;
- accession number, sequence, description, SEC document type;
- filename, canonical URL, media type, and size;
- primary-document indicator;
- cached-content checksum;
- retrieval and text-extraction status.

### 7.6 `evidence`

One row per candidate passage, not one row per keyword.

Key fields:

- `evidence_id`, `document_id`, `deal_id`;
- category and matched pattern;
- short excerpt plus character or paragraph location;
- target-name proximity and other ranking features;
- automated relevance score;
- human label: `pending`, `relevant`, `irrelevant`, `duplicate`, or `unclear`;
- reviewer note.

### 7.7 Derived `deal_summary`

Generate this table from the normalized evidence; do not use it as the source of truth.

Suggested fields:

- any filing found;
- transaction agreement found;
- employee-related language proposed and manually confirmed;
- named person found;
- compensation/retention mechanism found;
- redaction observed;
- best source URL;
- unresolved reason;
- count of documents awaiting review.

## 8. Missingness and status vocabulary

Blank values are not allowed to carry methodological meaning. Use explicit states such as:

- `not_searched`;
- `cik_unresolved`;
- `party_not_sec_registrant`;
- `no_filings_in_window`;
- `filings_found_no_relevant_form`;
- `relevant_filing_no_agreement`;
- `agreement_found_topic_not_disclosed`;
- `redacted_or_omitted_schedule`;
- `retrieval_failed`;
- `parse_failed`;
- `human_review_pending`;
- `confirmed_absent_from_reviewed_documents`.

`confirmed_absent_from_reviewed_documents` must never be shortened to "no retention arrangement."
It describes the reviewed disclosure, not the unobserved transaction.

## 9. Retrieval client requirements

- Require `SEC_USER_AGENT` in the environment and fail with a clear message if it is absent.
- Use one reusable HTTP client with timeouts and compression enabled.
- Default to a conservative process-wide rate below the SEC maximum; start at 5 requests/second.
- Retry `429`, transient `403`, and `5xx` responses with exponential backoff and jitter.
- Respect `Retry-After` when present.
- Cache successful immutable archive responses and SEC identifier files.
- Store the request URL, retrieval time, status, content type, checksum, and cache state.
- Support `--offline` to rerun parsing and ranking entirely from cached fixtures.
- Support resumable stages so a failure does not restart completed downloads.
- Never place the contact email or downloaded licensed SDC data in Git.

## 10. Text extraction and ranking

### 10.1 Text handling

- Parse HTML while preserving headings, table cells, and paragraph boundaries.
- Treat plain-text filings as a fallback source.
- Record unsupported PDFs or binary exhibits for manual handling instead of silently skipping them.
- Store raw response bytes in cache and derived normalized text separately.

### 10.2 Pattern families

Keep versioned patterns in configuration. Initial categories:

- transaction identity: target name, merger, acquisition, purchase agreement, tender offer;
- consideration: purchase price, merger consideration, cash, stock, contingent consideration;
- continued service: continued employment, remain employed, service condition;
- employee specificity: employee matters, key employee, named executive, founder;
- retention/compensation: retention, bonus, award, vesting, rollover, incentive, earnout;
- exit protections: severance, termination, good reason, change in control;
- disclosure limitations: omitted schedule, confidential treatment, redacted.

Ranking can combine form priority, exhibit type, date proximity, target-name proximity, item number,
and pattern-family hits. Keep every component visible. Do not call the score a probability.

## 11. Proposed Python architecture

```text
scripts/
  src/tag_edgar/
    __init__.py
    cli.py                 # command-line entry points
    settings.py            # environment and TOML configuration
    schemas.py             # typed row/status definitions
    sdc.py                 # input mapping and normalization
    cik.py                 # candidate generation and review states
    sec_client.py          # User-Agent, rate limit, retries, cache
    submissions.py         # filing-history retrieval and window filtering
    accessions.py          # filing-detail and exhibit enumeration
    text.py                # deterministic text extraction
    evidence.py            # pattern matching, excerpts, ranking
    storage.py             # table reads/writes and run manifests
    summary.py             # derived coverage outputs
  config/
    forms.toml
    patterns.toml
    sdc_columns.example.toml
  tests/
    fixtures/              # small cached SEC responses, never live network tests
    test_cik.py
    test_windows.py
    test_submissions.py
    test_accessions.py
    test_evidence.py
  data/
    sample/                # synthetic or redistributable tiny example
    raw/                   # licensed inputs; Git-ignored
    derived/               # generated outputs; normally Git-ignored
  cache/                   # HTTP cache; Git-ignored
  docs/
    filing-map.md
    data-dictionary.md
    validation-log.md
  .env.example
  PLAN.md
  README.md
  flake.nix
  pyproject.toml
  uv.lock
```

Suggested runtime libraries:

- `httpx` for HTTP;
- `beautifulsoup4` and `lxml` for filing-detail and HTML parsing;
- `polars` for SDC and output tables;
- `rapidfuzz` for candidate generation only;
- `typer` for a small CLI;
- `pydantic-settings` or a small typed settings layer;
- `pytest` and `respx` for deterministic tests.

Prefer explicit SEC parsing code over a large third-party EDGAR package in the pilot so the method
is inspectable and the exact source URLs remain visible.

## 12. Nix, direnv, and uv division of responsibility

- Nix supplies the Python interpreter, `uv`, and non-Python system tools.
- `uv` supplies and locks Python runtime and development dependencies.
- Avoid independently pinning Ruff and basedpyright in both Nix and `uv`; select one owner so local
  and non-Nix contributors run the same versions. Prefer `uv` for Python developer tools.
- Commit `flake.lock` and `uv.lock`.
- Keep `.env` ignored. Let `.envrc` load it only if present.
- Rename the generic project metadata from `app` once the package structure is introduced.

Example environment contract:

```text
SEC_USER_AGENT="TAG acquisition research your-real-contact@example.com"
TAG_EDGAR_CACHE_DIR="./cache/http"
TAG_EDGAR_RATE_PER_SECOND="5"
```

## 13. CLI workflow

Design each stage to be runnable and resumable:

```text
tag-edgar ingest INPUT.csv --column-map config/sdc_columns.toml
tag-edgar resolve-ciks --run RUN_ID
tag-edgar discover-filings --run RUN_ID
tag-edgar enumerate-documents --run RUN_ID
tag-edgar extract-evidence --run RUN_ID
tag-edgar summarize --run RUN_ID
```

Add a convenience command only after the stages work:

```text
tag-edgar run INPUT.csv --limit 10
```

Useful debugging options:

- `--deal-id` for one vertical slice;
- `--limit` for a pilot sample;
- `--offline` for cached-only execution;
- `--refresh` for intentional cache replacement;
- `--through-stage` to stop before later processing.

## 14. Implementation phases

### Phase 0: freeze the input contract

Deliverables:

- inspect the actual SDC/LSEG files and map their real column names;
- create a redistributable sample with the same schema;
- write a data dictionary for raw and normalized fields;
- decide which SDC party represents the public parent versus direct acquirer.

Exit condition: ten rows ingest without losing original identifiers or dates.

### Phase 1: one-deal vertical slice

Deliverables:

- SEC client with User-Agent, cache, conservative limiter, and retry policy;
- one manually supplied, confirmed acquirer CIK;
- Submissions API retrieval;
- event-window form filtering;
- accession-detail parsing;
- document and exhibit rows written to disk.

Exit condition: one known transaction produces traceable `deals`, `filings`, and `documents` rows
whose URLs agree with manual EDGAR inspection.

### Phase 2: CIK resolution and ten-deal pilot

Choose ten events that vary on:

- target public/private status;
- acquisition form;
- disclosed/undisclosed value;
- short/long time to closing;
- large/small acquirer;
- apparent high/low disclosure richness.

Deliverables:

- candidate CIK generation;
- manual resolution queue;
- filing discovery for acquirer and public target;
- structured no-match and no-filing outcomes.

Exit condition: every deal has a terminal retrieval status and no unresolved case is silently
excluded.

### Phase 3: evidence ranking and human verification

Deliverables:

- versioned pattern configuration;
- short candidate excerpts with source locations;
- reviewer statuses and notes;
- derived per-deal summary.

Exit condition: a person can review the ranked documents without reopening the entire SDC row or
searching EDGAR from scratch.

### Phase 4: validation and supervisor-ready report

Report:

- CIK resolution rate by method and confidence;
- proportion of deals with any filing in window;
- proportion with a relevant transaction filing;
- proportion with an acquisition agreement or material exhibit;
- proportion with proposed and confirmed employee-related passages;
- median documents requiring review per deal;
- precision among the top-ranked documents;
- missingness reasons and examples;
- fields EDGAR adds beyond SDC and fields it still cannot supply.

Do not report recall until a defensible manually constructed reference set exists.

### Phase 5: scale only after review

Before expanding beyond the pilot:

- get Dr. Singh's feedback on the form list, date window, and evidence categories;
- freeze a versioned schema;
- estimate request volume and storage;
- use SEC bulk indexes when they reduce traffic;
- decide whether the research contribution is disclosure coverage, automated enrichment, or a
  later people-outcome analysis.

## 15. The first focused hour

The first hour should produce a working vertical slice, not the whole crawler:

1. **0-10 minutes:** add the package skeleton, environment contract, and one synthetic deal row.
2. **10-25 minutes:** implement the SEC client with required User-Agent, cache, and rate limiter.
3. **25-40 minutes:** retrieve one known CIK's submissions and filter by the configured date window
   and core forms.
4. **40-55 minutes:** open one accession detail page and enumerate its primary document and
   exhibits.
5. **55-60 minutes:** write normalized rows and record what failed or still requires manual work.

Do not begin fuzzy CIK resolution during this hour. Supply one verified CIK so the first test
isolates filing retrieval from entity-resolution errors.

## 16. Testing strategy

- Unit-test date windows, accession URL construction, form matching, normalization, and status
  transitions.
- Use cached, reduced SEC fixtures for parser tests; automated tests should not hit live EDGAR.
- Include fixtures for:
  - 8-K with Items 1.01, 2.01, 5.02, 8.01, and 9.01;
  - 424B3;
  - SC 14D9 and SC TO-T amendment chains;
  - accession containing multiple `EX-2.*`, `EX-10.*`, and `EX-99.*` documents;
  - missing or malformed filing index;
  - renamed filer and ambiguous CIK match;
  - no filing in the event window.
- Add one opt-in live smoke test, disabled by default.
- Record a checksum of every cached fixture so parser changes are distinguishable from source
  changes.

## 17. Research safeguards

- Preserve raw source fields and never overwrite them with normalized values.
- Keep automated suggestions separate from verified annotations.
- Version the form list, keyword patterns, normalization rules, and output schema.
- Record run time, code version, input checksum, configuration checksum, and cache state.
- Do not equate public disclosure with the complete economic arrangement.
- Do not equate absence from reviewed filings with absence of a retention mechanism.
- Do not distribute licensed SDC/LSEG records in the repository.
- Use only short excerpts necessary for verification and retain direct source URLs.

## 18. Decisions to bring to Dr. Singh after the pilot

1. Is the primary contribution a reusable enrichment method, an audit of selective disclosure, or
   preparation for a people-outcome study?
2. Which SDC definition and SIC/industry filter should define a technology acquisition?
3. Should the sample require a public acquirer, or include deals where only the target files?
4. Which employee fields are sufficiently important to justify manual verification?
5. How should cancelled, competing-bid, and cross-border transactions enter the sample?
6. What evidence threshold permits saying a field was "disclosed" versus merely mentioned?
7. After the pilot, is the coverage sufficient to link deals to the people dataset?

## 19. Official SEC references

- EDGAR APIs: <https://www.sec.gov/search-filings/edgar-application-programming-interfaces>
- Accessing EDGAR data and archive paths:
  <https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data>
- EDGAR submission types:
  <https://www.sec.gov/submit-filings/filer-support-resources/how-do-i-guides/understand-edgarlink-online-submission-types>
- SEC developer resources and fair-access guidance:
  <https://www.sec.gov/about/developer-resources>


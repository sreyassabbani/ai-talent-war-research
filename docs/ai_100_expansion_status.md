# 100-deal AI expansion status

## Current result

The supplied Thomson Reuters SDC archive was screened locally with the deterministic
candidate generator.

- Archive coverage used by the preflight: 2016–2022
- Unique SDC deals in that window: 63,309
- Name-screened candidates: 119
- Selected candidates: 100
- Reserve candidates: 19
- Candidates screened in the completed combined run: 119
- Retrieved documents: 1,390
- Failed individual document retrievals: 9
- Candidate-level run failures: 0
- Machine-qualified rows pending human review: 23
- Unique employee passages: 74 across 15 deals
- Qualifying deals with zero employee passages: 8
- Topic status: `exploratory_rejected_deal_concentration`
- Human-verified qualifying AI transactions: 0
- Remaining shortfall against the requested 100 verified deals: 77

The honest frozen result is therefore a 23-row provisional source-backed set, not a verified
100-deal database. The 119-row manifest preserves every rejected or unresolved candidate and its
missingness reason. No generic merger was added to reach a round number.

## Implemented pipeline

The command "python -m tag_edgar.overnight" now provides a resumable, no-LLM workflow that:

1. reads the 100 selected candidates and, when requested, all 19 reserves;
2. resolves public acquirers to SEC CIKs and retrieves cached transaction-window filings;
3. retrieves only pre-approved official company, regulator, distributor, and SEC URLs from the
   curated supplemental source register;
4. requires explicit AI evidence and a distinctive target-name anchor in the same source paragraph;
5. writes an explicit manifest row and document status for every attempted candidate;
6. prefers focused official transaction announcements for the employee corpus and otherwise uses
   the selected evidence document;
7. builds a heading-aware, exact-deduplicated employee-passage corpus;
8. records source occurrences and zero-passage deals;
9. runs fixed-seed word/bigram TF-IDF plus NMF;
10. produces sensitivity, stability, document-family baseline, tone, word-use, and
   deterministic word-cloud outputs;
11. writes source registers, manifests, a blank human-review queue, structured logs, missingness
    reports, a final research report, and a morning verification summary; and
12. resumes completed stages or reapplies stricter screening rules from the local document cache;
    cached rescreens also ingest newly approved supplemental sources without repeating the SEC
    sweep.

Machine-qualified rows are always labelled
"qualifying_machine_verified_pending_human_review". They must not be described as
human-verified.

## Live smoke audit and repair

The first one-deal smoke run retrieved 23 Microsoft documents for Microsoft–Lobe and
incorrectly qualified the candidate from a generic Microsoft sentence about artificial
intelligence that did not mention Lobe. It then created 577 employee passages, and the
topic terms exposed HTML/table artifacts such as td, valign, and font.

The screen and parser were repaired and then audited again after scaling:

- AI evidence must now occur near a distinctive target-name anchor.
- Complete-submission text with late HTML tags is parsed as HTML.
- Only target-linked retrieved documents enter the employee corpus.
- AI and target evidence must occur in the same source paragraph.
- Generic target descriptors such as `robotics`, `mapping`, and `data science` cannot act as the
  target identity by themselves.
- The corpus prefers focused official deal announcements instead of every filing that happens to
  mention the target.
- Common English and HTML-layout tokens are excluded from the topic vocabulary.
- Regression tests cover the generic-corporate-AI false positive and late-HTML case.

The second audit removed four provisional inclusions. Examples included an unrelated Box filing
that mentioned Microsoft machine-learning capabilities in one bullet and the Butter.ai team in
another, and a
Velodyne filing whose general autonomous-driving discussion was not evidence about Mapper.ai. These
remain explicit nonqualifying rows rather than being silently discarded.

A later official Box announcement separately established that the Butter.ai team joined Box and
that Butter.ai used machine learning, so that transaction re-entered the provisional set on direct,
target-linked evidence rather than the unrelated filing.

The repaired smoke run again retrieved all 23 documents with no retrieval failures, but
correctly left Microsoft–Lobe unresolved because none of those SEC documents mentioned
the target. It exited with partial status, 0 qualifying deals, 0 passages, and an explicit
one-deal shortfall. The before/after ignored artifacts are under:

- data/derived/ai_100_smoke/
- data/derived/ai_100_smoke_v2/

## Remaining evidence gate

The live source adapter now accepts a curated register containing 34 approved source URLs for 32
candidates. It does not crawl arbitrary reporting or promote unreviewed URLs. Of the 96 unresolved
rows, 69 have no EDGAR-resolved acquirer, 18 mention the target without paragraph-local AI evidence,
7 have no target mention in retrieved documents, and 2 have no retrieved deal documents.

For each included deal, a reviewer still needs to confirm:

- AI relevance and the exact supporting excerpt;
- transaction form, completion status, and closing date;
- separate talent/acqui-hire motive status;
- source URL, accession, and document identity;
- entity/CIK resolution where EDGAR applies; and
- whether employee-document retrieval is complete enough for the stated analysis.

The current topic model is not release-ready. One deal supplies 43.24% of all passages, above the
35% concentration threshold, so the three topics are retained only as exploratory diagnostics and
are labelled `exploratory_rejected_deal_concentration`. The topic-review queue remains blank for a
real reviewer.

If fewer than 100 pass, report the largest valid set and the exact shortfall. Never replace
failed candidates with generic mergers merely to reach 100.

## Commands

Run the full offline test and quality gates:

~~~powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check src\tag_edgar tests
.venv\Scripts\python.exe -m basedpyright src\tag_edgar\ai_screening.py src\tag_edgar\baseline.py src\tag_edgar\deal_retrieval.py src\tag_edgar\overnight.py src\tag_edgar\tone.py src\tag_edgar\topics100.py src\tag_edgar\universe.py src\tag_edgar\wordcloud.py
~~~

Run or resume the real batch after setting a truthful SEC contact identity:

~~~powershell
$env:SEC_USER_AGENT = "Aarav TAG Internship your-real-email@example.com"
.venv\Scripts\python.exe -m tag_edgar.overnight `
  --candidates data\derived\ai_100_candidate_preflight.csv `
  --raw-dir data\raw\ma_events `
  --out-dir data\derived\ai_100_overnight `
  --supplemental-sources config\ai_100_supplemental_sources.csv `
  --include-reserves
~~~

Reapply changed deterministic rules to the cached target-linked documents:

~~~powershell
.venv\Scripts\python.exe -m tag_edgar.overnight `
  --refresh --rescreen-cached --include-reserves `
  --supplemental-sources config\ai_100_supplemental_sources.csv
~~~

Exit code 0 means the requested target was reached without run failures, 2 means a
resumable partial/shortfall package was produced, and 1 means configuration or pipeline
failure.

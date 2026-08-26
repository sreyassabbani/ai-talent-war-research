# 100-deal AI expansion status

## Current result

The supplied Thomson Reuters SDC archive was screened locally with the deterministic
candidate generator.

- Archive coverage used by the preflight: 2016–2022
- Unique SDC deals in that window: 63,309
- Name-screened candidates: 119
- Selected candidates: 100
- Reserve candidates: 19
- Human-verified qualifying AI transactions: 0
- Candidate rows with a source URL before retrieval: 0

The 100 selected rows remain a discovery queue, not a verified AI-deal database.

## Implemented pipeline

The command "python -m tag_edgar.overnight" now provides a resumable, no-LLM workflow that:

1. reads selected candidates and resolves public acquirers to SEC CIKs;
2. retrieves and caches transaction-window filings and exhibits;
3. requires AI evidence to be locally linked to a distinctive target-name anchor;
4. writes an explicit manifest row and document status for every attempted candidate;
5. builds a heading-aware, exact-deduplicated employee-passage corpus;
6. records source occurrences and zero-passage deals;
7. runs fixed-seed word/bigram TF-IDF plus NMF;
8. produces sensitivity, stability, document-family baseline, tone, word-use, and
   deterministic word-cloud outputs;
9. writes source registers, manifests, structured logs, missingness reports, a final
   research report, and a morning verification summary; and
10. resumes completed stages from state.json.

Machine-qualified rows are always labelled
"qualifying_machine_verified_pending_human_review". They must not be described as
human-verified.

## Live smoke audit and repair

The first one-deal smoke run retrieved 23 Microsoft documents for Microsoft–Lobe and
incorrectly qualified the candidate from a generic Microsoft sentence about artificial
intelligence that did not mention Lobe. It then created 577 employee passages, and the
topic terms exposed HTML/table artifacts such as td, valign, and font.

The screen and parser were repaired before scaling:

- AI evidence must now occur near a distinctive target-name anchor.
- Complete-submission text with late HTML tags is parsed as HTML.
- Only target-linked retrieved documents enter the employee corpus.
- Common English and HTML-layout tokens are excluded from the topic vocabulary.
- Regression tests cover the generic-corporate-AI false positive and late-HTML case.

The repaired smoke run again retrieved all 23 documents with no retrieval failures, but
correctly left Microsoft–Lobe unresolved because none of those SEC documents mentioned
the target. It exited with partial status, 0 qualifying deals, 0 passages, and an explicit
one-deal shortfall. The before/after ignored artifacts are under:

- data/derived/ai_100_smoke/
- data/derived/ai_100_smoke_v2/

## Remaining evidence gate

The current live source adapter is SEC-only. Many private acquisitions, acqui-hires, and
license-and-hire transactions require official company announcements, regulator decisions,
or carefully labelled reputable reporting. Those source URLs must be assembled and reviewed
before exactly 100 deals can be called source-backed.

For each included deal, a reviewer still needs to confirm:

- AI relevance and the exact supporting excerpt;
- transaction form, completion status, and closing date;
- separate talent/acqui-hire motive status;
- source URL, accession, and document identity;
- entity/CIK resolution where EDGAR applies; and
- whether employee-document retrieval is complete enough for the stated analysis.

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
  --out-dir data\derived\ai_100_overnight
~~~

Exit code 0 means the requested target was reached without run failures, 2 means a
resumable partial/shortfall package was produced, and 1 means configuration or pipeline
failure.

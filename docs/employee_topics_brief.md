# Employee-related M&A disclosure pilot: supervisor brief

## Bottom line

The 10-deal pilot now supports a reproducible exploratory analysis. The current three-component
output is **rejected for taxonomy release** under the prespecified stability and human-review gate;
it must not be presented as a validated disclosure taxonomy. The final corpus contains 2,708
included, exact-text-deduplicated passages from 358 transaction-linked SEC documents. All 469
candidate documents parsed successfully, all eight manually positive source documents produced
qualifying passages, and Fastly–Glitch is retained as an explicit zero-passage case.

The fixed-seed word/bigram TF-IDF + NMF analysis selected three candidate components:

1. Continuing-employee benefits and plan transitions.
2. Executive compensation, tax, and merger-related arrangements.
3. Equity-award conversion and vesting treatment.

These are candidate components, not confirmed substantive labels. Human representative-to-theme review is still blank, and the second component recovered in only 6 of 9 leave-one-deal-out folds (0.667 versus the prespecified 0.80 threshold). The overall taxonomy gate therefore fails by design.

## What the documents show

The benefits component is represented by provisions addressing continuing employees' transition into buyer welfare and benefit plans; for example, the [Clarivate–ProQuest agreement describes buyer-plan eligibility and efforts to waive coverage restrictions](https://www.sec.gov/Archives/edgar/data/1764046/000110465921067259/tm2116608d1_ex2-1.htm), and the [Take-Two–Zynga proxy discusses service credit under new employee benefit plans](https://www.sec.gov/Archives/edgar/data/1439404/000119312522098903/d420326ddefm14a.htm).

The equity component is represented by transaction-specific treatment of outstanding awards: the [Microsoft–Nuance proxy describes rollover RSU conversion](https://www.sec.gov/Archives/edgar/data/1002517/000114036121017650/nt10023637x2_defm14a.htm), while the [Take-Two–Zynga filing describes conversion of options and restricted-stock-unit awards](https://www.sec.gov/Archives/edgar/data/946581/000119312522096532/d420326ds4a.htm).

The executive/compensation/tax component is less stable and mixes genuinely employee-facing passages with broader transaction material. Examples of the intended signal include [ironSource executives' expected post-signing employment discussions with Unity](https://www.sec.gov/Archives/edgar/data/1837430/000110465922098557/tm2225429d2_ex99-1.htm) and [Zynga's employee-facing tax guidance for equity awards](https://www.sec.gov/Archives/edgar/data/1439404/000119312522146664/d316507d425.htm). Because the component is not stable across held-out deals, no deal-level interpretation should be based on its weights.

These filings disclose contractual language and communications. They do not establish actual retention, headcount changes, employee behavior, or causal workforce effects.

## Validation result

- Corpus completeness: pass for 10/10 deals, including one explicit zero-passage state.
- Source provenance: pass; every report excerpt resolves to an exact HTTPS SEC document.
- Manual positive-source recall: pass for 8/8 reviewed-positive documents.
- NMF/agglomerative sensitivity: pass; adjusted Rand index 0.306 versus the prespecified 0.20 floor.
- Leave-one-deal-out stability: two components pass; the executive/compensation/tax component fails at 0.667.
- Human representative fit: pending; the review queue intentionally contains blank reviewer fields.
- Overall taxonomy release: fail/provisional.

## Reproduction

```bash
tag-edgar build-employee-corpus data/derived/pilot_review_queue.csv data/derived/pilot_runs \
  --output-dir data/derived/employee_corpus \
  --manual-coding-csv data/derived/pilot_manual_coding.csv

tag-edgar analyze-employee-topics data/derived/pilot_review_queue.csv \
  data/derived/employee_corpus \
  --output-dir data/derived/employee_topics \
  --seed 20260823

tag-edgar summarize-employee-topics data/derived/pilot_review_queue.csv \
  data/derived/employee_corpus data/derived/employee_topics \
  --output-dir data/derived/employee_report \
  --representative-limit 10

tag-edgar prepare-employee-topic-review \
  data/derived/employee_topics/canonical_topic_assignments.csv \
  data/derived/employee_corpus/passages.csv \
  --output-dir data/derived/employee_topic_review
```

The final command has generated a fixed-seed, 30-item assessor-blinded packet plus two blank
reviewer copies and a private re-identification key. The next evidence gate is completion by two
actual reviewers; automated or agent-generated labels must not substitute for that review. If at
least 80% of the ten highest-weight passages fit each candidate theme and the prespecified
agreement gates pass, the stable benefits and equity components can advance as provisional
taxonomy entries. This would not retroactively validate the rejected three-component output. The
unstable second component must remain rejected or be decomposed in a new, prespecified repair
cycle.

## Scale and outcome branches

The local catalog contains 26,369 logical deal records—not the misleading 28,364 physical data
lines produced by embedded newlines. A deterministic 40-row, multi-stratum validation preview is
ready from 1,040 technology-screened candidates, but it is explicitly `not_frozen`: supervisor
acceptance of the deal-level unit of analysis is still required before retrieval. See
[`validation_sample_preflight.md`](validation_sample_preflight.md).

The free-source historical outcome audit is a no-go for a broad hiring study. Official H-1B LCA
files provide two-period employer-case presence for 9/10 pilot deals, but only 6/10 have a positive
employer-reported `NEW_EMPLOYMENT` field in both periods; neither statistic establishes realized
hires. Current ATS endpoints are not historical snapshots, while WARN covers only qualifying mass
layoff/plant-closing notices. The preferred next branch is a licensed historical postings panel,
with a prospective cohort or explicitly narrow H-1B/WARN study as fallbacks. See
[`hiring_outcome_feasibility.md`](hiring_outcome_feasibility.md).

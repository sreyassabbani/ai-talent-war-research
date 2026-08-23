# Recursive research goal completion audit

Audit date: 2026-08-23. This audit treats the durable goal as two nested outcomes: (1) the
immediate, supervisor-ready 10-deal EDGAR employee-disclosure pilot and (2) a credible, gated path
to later hiring/retention-outcome research. The governing scope and safeguards are in
[`PLAN.md`](../PLAN.md).

## Current decision

The 10-deal retrieval, corpus, modeling, provenance, and descriptive reporting pipeline is proved
as a reproducible pilot. The goal is **not complete as a validated taxonomy**: human
representative-to-theme review is blank, and topic 2 recovers in only 6 of 9 leave-one-deal-out
folds (0.667, below the prespecified 0.80 threshold). Hiring/retention-outcome research remains a
later phase and is not supported by these filings alone.

Status meanings:

- **proved** — the current repository contains executable or source-linked evidence satisfying the
  requirement.
- **incomplete** — required work or documentation is absent, but no research gate forbids it.
- **blocked-by-gate** — proceeding would violate a prespecified evidence or review threshold.

## Requirement audit

| Requirement | Status | Current evidence | Exact next evidence needed |
| --- | --- | --- | --- |
| Freeze a traceable SDC/LSEG input denominator without silently dropping deals. | **proved** | [`pilot_review_queue.csv`](../data/derived/pilot_review_queue.csv) retains 20 candidates and 10 explicitly selected rows; [`pilot_audit_summary.csv`](../data/derived/pilot_audit_summary.csv) has one row for each selected deal. | None for the pilot. A scaled run needs a versioned, frozen sample definition and input checksum. |
| Confirm public-party identities and preserve target registrant/nonregistrant states. | **proved** | All 10 selected rows in [`pilot_review_queue.csv`](../data/derived/pilot_review_queue.csv) have confirmed acquirer CIKs; target states are explicitly `confirmed` or `not_registrant`. | None for these 10 deals. New deals require the same manual confirmation evidence. |
| Search the event window, enumerate accessions/documents, and preserve stable SEC URLs. | **proved** | Ten deal directories under [`pilot_runs`](../data/derived/pilot_runs/) contain `deals.csv`, `filings.csv`, `deal_filings.csv`, `documents.csv`, and `evidence.csv`; retrieval behavior is exercised by [`test_pipeline.py`](../tests/test_pipeline.py), [`test_submissions.py`](../tests/test_submissions.py), and [`test_accessions.py`](../tests/test_accessions.py). | None for the cached pilot. A live rerun needs a valid `SEC_USER_AGENT` and matching run/cache manifests. |
| Give every deal a reviewable terminal result and distinguish disclosure from absence. | **proved** | [`pilot_manual_coding.csv`](../data/derived/pilot_manual_coding.csv) has 10 triaged rows with completed document/evidence review and source URLs; [`pilot_findings.md`](../data/derived/pilot_findings.md) states that “not found” is limited to reviewed documents. | Convert `triaged` to `complete` only if the supervisor requires a second review or adjudication protocol. |
| Produce an offline, provenance-preserving employee-passage corpus. | **proved** | [`corpus_manifest.json`](../data/derived/employee_corpus/corpus_manifest.json) records 469/469 parsed documents, 358 included documents, 2,708 included passages, 10,933 occurrences, checksums, and all 10 deal IDs; exact locations and URLs are in [`passage_sources.csv`](../data/derived/employee_corpus/passage_sources.csv). | None for reproducibility. Before schema freeze, reconcile the manifest label `canonical_passages=5550` with `included_passages=2708` and the model diagnostic’s use of “canonical” for 2,708 rows. |
| Validate known positive sources and retain true zero states. | **proved** | [`manual_source_validation.csv`](../data/derived/employee_corpus/manual_source_validation.csv) passes all 10 checks, including 8/8 expected-positive documents; Fastly–Glitch remains a zero-passage row in [`deal_topic_matrix.csv`](../data/derived/employee_topics/deal_topic_matrix.csv) and the final report. | None for this reference set. A recall claim beyond the eight positives needs a larger independently reviewed reference set. |
| Fit a deterministic descriptive model with visible parameters and outputs. | **proved** | [`analysis_manifest.json`](../data/derived/employee_topics/analysis_manifest.json) records seed `20260823`, configuration, hashes, three components, and assignment counts; [`topic_summary.csv`](../data/derived/employee_topics/topic_summary.csv), assignments, matrix, and heatmap are emitted together. | None for rerunning this candidate solution. A versioned taxonomy still requires the gates below. |
| Compare the model with an independent sensitivity method on the same fit universe. | **proved** | [`model_diagnostics.csv`](../data/derived/employee_topics/model_diagnostics.csv) reports agglomerative ARI 0.306 against the 0.20 floor and 240 shared nonzero fit rows; [`sensitivity_assignments.csv`](../data/derived/employee_topics/sensitivity_assignments.csv) preserves assignments. | None for the specified sensitivity check. Additional methods are optional, not substitutes for human review or stability. |
| Pass leave-one-deal-out component stability. | **blocked-by-gate** | [`stability.csv`](../data/derived/employee_topics/stability.csv) shows topic 1 at 9/9, topic 2 at 6/9, and topic 3 at 8/9; [`model_diagnostics.csv`](../data/derived/employee_topics/model_diagnostics.csv) records topic 2 and overall stability warnings. | Topic 2 must reach at least 0.80 recovery under a prespecified repair/refit, or be explicitly removed/decomposed and the entire selection/stability procedure rerun without post-hoc relabeling. |
| Cover all 10 deals in the descriptive report, including zeros. | **proved** | [`employee_topics_report.md`](../data/derived/employee_report/employee_topics_report.md) contains all 10 deals and an explicit Fastly–Glitch pipeline zero state; [`report_manifest.json`](../data/derived/employee_report/report_manifest.json) records the 10 selected IDs and `representative_limit=10`. | None for deal coverage. |
| Keep every deal-specific document claim inline-linked to the exact SEC source and prohibit causal/predictive retention claims. | **proved** | The final report links each non-zero deal claim and representative inline, states the descriptive-only boundary, and is guarded by [`employee_report.py`](../src/tag_edgar/employee_report.py) plus [`test_employee_report.py`](../tests/test_employee_report.py). | None for the current generated report. Any hand-edited supervisor copy must preserve the same links and limitations. |
| Establish that top representatives fit a coherent human-interpretable theme. | **blocked-by-gate** | Automated substantiveness lint passes, but all `representative_fit_status` and `review_status` fields remain `pending` and reviewer scores are blank in [`topic_review.csv`](../data/derived/employee_report/topic_review.csv). The report correctly withholds taxonomy release. | A named reviewer must inspect the 10 source-linked representatives per topic, record fit decisions/notes, and show at least 80% fit for each component proposed for release; topic 2 also must pass stability. |
| Deliver a concise supervisor brief with reproducible commands and limitations. | **proved** | [`employee_topics_brief.md`](employee_topics_brief.md) reports corpus coverage, candidate components, validation results, three reproduction commands, and the causal/observability boundary. | After human review, update candidate labels and gate results; until then, present them only as provisional components. |
| Complete every originally proposed phase-4 summary statistic. | **incomplete** | [`pilot_findings.md`](../data/derived/pilot_findings.md) reports filing/agreement/employee-disclosure counts and missingness examples, but the repository does not show a finalized CIK-resolution-by-method table, median review burden, or top-ranked-document precision estimate. | Generate those summaries from the frozen pilot tables. Precision requires an explicit ranked-document reference label and denominator; do not infer it from keyword hits. |
| Freeze a scale-ready taxonomy/schema and expand beyond 10 deals. | **blocked-by-gate** | [`PLAN.md`](../PLAN.md) makes supervisor feedback and schema freeze prerequisites; the current report gate is false and human fit is pending. | Obtain Dr. Singh’s decisions on contribution, technology scope, evidence threshold, and sample rules; pass/adjudicate human fit; resolve topic 2 stability; then tag the schema/config version before scaling. |
| Test hiring, retention, employee movement, or causal workforce outcomes. | **incomplete** | The filing pipeline observes disclosed contractual language only. [`employee_topics_brief.md`](employee_topics_brief.md) explicitly states it cannot establish actual retention, headcount changes, employee behavior, or causal effects. No person-level outcome table or linkage protocol exists. | After the disclosure gate passes, specify a lawful people/outcome source, person/company/deal linkage validation set, pre/post observation windows, attrition/mobility outcomes, missingness analysis, comparison strategy, and a prespecified estimand. Only then run descriptive outcome linkage; causal claims require a separate identification design. |

## Verified implementation state

At audit time, the repository passes 106 tests, Ruff on `src` and `tests`, and basedpyright on
`src`. These checks prove implementation consistency, not research validity. The next recursive
cycle is therefore evidence work: complete the human review queue and resolve the topic-2 stability
gate before taxonomy release or sample expansion.

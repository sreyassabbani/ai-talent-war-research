# Pilot validation metrics

Audit date: 2026-08-23. Denominator: the 10 rows marked `pilot_status=selected` in the local
`pilot_review_queue.csv`. Counts below come from `pilot_audit_summary.csv`, the selected queue,
`pilot_manual_coding.csv`, and the final employee-corpus manifest. These are workflow-validation
statistics, not population estimates.

## Required phase-4 summary

| Metric | Result | Exact rule |
| --- | ---: | --- |
| Acquirer CIK resolution | 10/10 confirmed | Selected row has nonblank `candidate_cik` and `cik_manual_status=confirmed`. |
| CIK resolution by method/confidence | 9 exact-ticker/high; 1 exact-normalized-name/medium | Counted on the 10 confirmed acquirer rows; the medium match was manually confirmed. |
| Target identity status | 4/10 confirmed registrants; 6/10 explicitly `not_registrant` | Blank target CIK is not treated as unresolved when the review status is `not_registrant`. |
| Any filing in event window | 10/10 | `filings_found > 0`. |
| Any transaction-relevant document | 10/10 | `relevant_documents_found > 0`. This is an automated review universe, not a relevance judgment for every document. |
| Agreement/material exhibit candidate | 9/10 | `agreement_exhibit_found=candidate`; the remaining case explicitly records no agreement in retrieval. |
| Automated employee-evidence candidates | 10/10 | `automated_evidence_hits > 0`; keyword candidates are not confirmed employee provisions. |
| Positive first-pass manual employee code | 8/10 | Manual code does not begin with `no_`; the two nonpositive rows remain in the denominator. |
| Final included employee-passage state | 9/10 nonzero; 1/10 explicit zero | At least one `included` passage after document eligibility, employee-context screening, and exact-text deduplication. |
| Median transaction-relevant documents requiring review | 39.5 per deal | Median of `relevant_documents_found`: 6, 9, 13, 14, 20, 59, 62, 83, 99, 104. |
| Top-ranked-document precision | **Not estimable from the current labels** | No frozen document-level reference table marks every member of a defined top-*k* denominator relevant/not relevant. Keyword hits and deal-level manual codes cannot substitute. |

The precision result is deliberately unavailable, not zero. To estimate it, freeze the ranking
configuration and *k*, draw the resulting top-*k* documents per deal, have reviewers independently
label transaction relevance and employee relevance, adjudicate disagreements, and retain every
ranked false positive in the denominator.

## Missingness and observability

The pipeline found at least one filing and transaction-relevant candidate document for every deal,
so there is no deal-level filing absence in this selected pilot. Document-family availability still
varies. For example, the [Fastly acquisition announcement was available but did not supply an
agreement or an employee term in the reviewed retrieval](https://www.sec.gov/Archives/edgar/data/1517413/000151741322000075/fastly-pressreleasenoterep.htm).
That row remains an explicit zero in the final topic matrix.

EDGAR adds stable source URLs, issuer/accession/form/date metadata, transaction exhibits, agreement
provisions, proxy communications, and disclosed award/benefit/employment language. It does not by
itself supply realized retention, total hires, headcount paths, employee identities, undisclosed
side arrangements, or causal workforce effects.

## Interpretation boundary

The selected cases validate retrieval and review mechanics. Purposive selection, a 10-deal
denominator, uneven document counts, and pending two-reviewer topic-fit coding prevent a prevalence
claim or validated taxonomy claim. The separate validation preview must remain unfrozen until the
supervisor accepts the unit of analysis.

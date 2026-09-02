# Cycle-5 run results (10-deal pilot)

Executed 2026-09-02 on the recovered cycle-5 corpus. Every number below comes from a command in
§4 of [`cycle5_freeze_and_assessor_instructions.md`](cycle5_freeze_and_assessor_instructions.md);
nothing here is estimated.

## 1. Corpus, recovered and verified

The cycle-5 artifacts were recovered from `data (1).zip` and `cache.zip` (Downloads, 2026-09-02)
and match the documented state exactly:

| Check | Value |
| --- | ---: |
| Documents parsed / transaction-linked / excluded | 469 / 358 / 111 |
| Screened candidate passages | 5,550 |
| Included / excluded by the cycle-5 screen | 2,331 / 3,219 |
| Preserved source occurrences | 10,933 |
| Provision families | 3,982 |
| Manually positive sources validated | 8 / 8 |
| Deals (incl. one zero-passage control) | 10 |

`corpus_relevance_audit_cycle5/audit_manifest.json` records
`candidate_csv_sha256 = 5c7bb949…c6ba`, which **equals** the SHA-256 of the recovered
`employee_corpus_cycle5/passages.csv`. The audit packet therefore hash-links to this exact corpus,
and the gate machinery resolves it without borrowing another corpus's verdict.

## 2. Corpus gate: still pending, and it propagates

The 150-row packet is present and **entirely unlabelled** (150/150 blank `relevance_label`,
blank `human_attestation`). Consequently every downstream artifact reports the pending state:

- report verdict: **WITHHELD** — 55 of 62 automated gates passed, but the corpus gate is not one of them;
- `report_manifest.json` → `release_status: pending_human_corpus_validation`;
- `tone_manifest.json` → `interpretation_status: secondary_diagnostic_corpus_not_validated`;
- every cross-table row → `corpus_validation_status: pending_human_corpus_validation`.

Nothing in this run may be presented as an accepted result.

## 3. Topic model, K = 3 (deal-balanced, seed 20260823)

2,331 included passages → 240 fit rows (one per deal/provision family), 2,091 projected.
Fit sample spans 45 source-document families; largest single family holds 10.8%.

| Topic | Primary passages | Families | Deals | Coherence | Leave-one-deal-out recovery | Top terms |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| topic_1 | 795 | 549 | 9 | 0.213 | **1.000** | plan, employee, benefit, benefits, erisa, service, acquired, continuing |
| topic_2 | 1,300 | 962 | 9 | 0.296 | **0.889** | stock, shares, equity, effective time, outstanding, award, merger |
| topic_3 | 236 | 200 | 9 | 0.462 | **0.000** | tax, taxes, property, income, social security, payroll, excise |

Bootstrap (100 fixed-seed replicates): topic_1 0.87, topic_2 0.79, topic_3 0.16.

**Gate outcome — fails, honestly.** Overall leave-one-deal-out recovery is 0.630 against a 0.80
floor, and NMF/agglomerative adjusted Rand is 0.020 against a 0.20 floor. Two components (benefit
plans; equity-award treatment) are stable and reproduce the cycle-4 reading. The third — a
tax/payroll component — is not stable and must stay rejected.

## 4. Balance variants (the same corpus, three fit universes)

| Fit balance | Overall recovery | Agglomerative ARI | Source families in fit | Max family share |
| --- | ---: | ---: | ---: | ---: |
| `deal` (default) | 0.630 | 0.020 | 45 | 10.8% |
| `source_family` | **0.815** | −0.086 | 76 | 2.1% |
| `none` | 0.778 | 0.060 | 50 | 11.7% |

Spreading the bounded fit universe across source-document families rather than deals raises
leave-one-deal-out recovery above the 0.80 threshold and cuts the largest family's share from
10.8% to 2.1%, and it yields three components that all recover at ≥0.667 (employment/severance/
executive 0.889; restricted stock and units 0.889; RSU/performance/incentive 0.667).

This is a **diagnostic observation, not a released taxonomy.** The prespecified primary model is
the deal-balanced one; switching the headline model to the variant that scores best after seeing
the scores would be exactly the post-hoc selection the plan forbids. The honest use is to record
that document-type imbalance is a plausible driver of the instability, and to prespecify the
balance mode *before* the next cycle rather than choosing it now.

## 5. Tone (secondary diagnostic, corpus not validated)

2,331 passages, 9 deals. Residuals are per-100-token rates minus the mean for the same document
type (corpus fallback for rare types).

| Deal | Passages | Protection Δ | Net tone Δ | Negative-outcome rate |
| --- | ---: | ---: | ---: | ---: |
| Clarivate–ProQuest | 111 | **+0.606** | +0.465 | 0.045 |
| Intuit–Mailchimp | 84 | +0.261 | **+0.551** | 0.022 |
| Microsoft–Nuance | 231 | +0.152 | +0.199 | 0.058 |
| Oracle–Cerner | 541 | −0.009 | +0.002 | **0.162** |
| Take-Two–Zynga | 607 | −0.023 | −0.072 | 0.061 |
| Unity–ironSource | 575 | −0.111 | −0.004 | 0.020 |
| Roper–Frontline | 38 | −0.157 | −0.348 | 0.076 |
| Okta–Auth0 | 76 | −0.265 | −0.684 | 0.072 |
| Skyworks–Silicon Labs | 68 | −0.318 | −0.477 | 0.125 |

The ordering reproduces the cycle-4 tone result on the repaired corpus: the two deals whose
agreements were independently hand-coded as carrying the richest continuing-employee protections
(Clarivate–ProQuest) and a quantified retention pool (Intuit–Mailchimp) sit at the top. Oracle–Cerner's
high negative-outcome rate matches its many severance and separation documents.

These are drafting-style measures. They are not evidence that any buyer cared more about employees,
retained more of them, or produced better outcomes.

## 6. Architecture × topic cross-table

28 rows. Nine deals join on `sdc_deal_id`; two rows are unmatched, and both are informative:

- **Salesforce–Tableau** appears in the architecture layer only. The `audit_salvage_2026-08-30`
  package substituted it for Fastly–Glitch after finding Fastly's stored SEC URL pointed at a
  convertible-note release. It is not one of the ten deals the corpus was built from.
- **Fastly–Glitch (`3923067020`)** appears in the topic layer only, as the explicit
  `no_employee_passages` zero state. It has no architecture row because the salvage package
  supplies no verified source evidence for it.

With nine joined deals, all coded as conventional control-transferring acquisitions and none with
a stated talent motive, the cross-table has almost no structural variation to describe. It is
retained as a wiring check and a template, not as a finding.

## 7. What changed in the register

Five workforce-movement rows were upgraded from salvage paraphrase to **verbatim** contract text
recovered from the cycle-4 audit packet (Clarivate–ProQuest, Oracle–Cerner, Roper–Frontline,
Unity–ironSource, Skyworks–Silicon Labs), so they now carry working `#:~:text=` highlight links.
The remaining 55 evidence rows stay paraphrase with `unsupported_paraphrase_not_quotable`, which
is why the manifest reports `{ok: 5, unsupported_paraphrase_not_quotable: 55}`.

## 8. What still requires a human

1. Label the 150-row cycle-5 packet and score it (§4c–4d of the freeze doc). Until then every
   number above stays provisional.
2. Complete the blinded two-reviewer topic packet (30 items, `employee_topic_review_cycle5/`).
3. Review the ten architecture rows and fill the three human columns.
4. Decide, *before* the next cycle, which fit-balance mode is the prespecified primary.

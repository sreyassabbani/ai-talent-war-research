# Plan: the 100+ deal unsupervised deliverable (disclosure-first method)

Written 2026-09-02. Branch `aarav/aug21-pilot-completion`. Status: **plan, not yet executed.**

## 0. What Dr. Singh will receive

One report that says, in this order:

1. We needed transactions whose SEC record actually contains employee-treatment language. Most
   deals in the Thomson/SDC data do not have that, so we searched for the ones that do and here
   is exactly how we searched (rules, counts, drop-offs).
2. Here are the 100+ deals that met the rule, each with its filing links.
3. Here is the unsupervised model run on their employee-related passages, the clusters it found,
   the words and example paragraphs that define each cluster, how stable each cluster is, and
   which deals load on which cluster.
4. Here is what we think the clusters mean, and here is what they do **not** show (no retention
   outcomes, no causation).

Everything in the report is produced by a command in this repository from a frozen deal list and
a frozen corpus, so any number can be regenerated.

## 1. The plan we have now, and where it stalls

The current pipeline is sound but its **selection step is backwards**. It picks deals first and
hopes they have filings:

```
SDC catalog (26,369 deals, 2020-2022)
  -> AI keyword screen on company names/descriptions      -> 119 candidates
  -> resolve acquirer on EDGAR                            -> 57 of 119 cannot be resolved
                                                            (private, PE, or foreign acquirers)
  -> machine-qualified, pending human review              -> 35
  -> retrieve filings, screen for employee passages       -> 13 deals with any passages
  -> unique employee passages                             -> 72 (44% from one deal)
```

72 passages cannot support a topic model, and the half-sample stability was 0.246. Meanwhile the
10-deal pilot, which picked large deals with SEC-registrant acquirers, produced **2,331 included
passages from 358 documents** - about 230 passages per deal.

The lesson is simple: **employee language shows up when the acquirer is an SEC registrant that
files the transaction agreement (EX-2.1) or the target files a merger proxy / tender-offer
statement.** "Is the target an AI company?" does not predict disclosure at all. Intuit-Mailchimp
(private target) gave 84 passages; Fastly-Glitch (small private target) gave 0.

Two other things in the current plan slow it down and should be kept, but scaled correctly:

- The corpus-relevance gate (150 human-labelled rows) is right and cheap. It has simply never been
  labelled for cycle 5. At 100 deals it is still 150 rows.
- The one-deal-at-a-time human CIK confirmation does not scale to 100 deals. It is replaced below by
  a stronger machine check (the acquirer's own filings must name the target in the announcement
  window) plus a small human spot check.

## 2. The new method in one sentence

**Start from disclosure, not from the deal list:** take every technology-target deal in the
catalog whose acquirer resolves on EDGAR, *probe* EDGAR to see whether a transaction agreement or
merger proxy was actually filed in the announcement window, retrieve only the probe-positive deals,
keep every deal that yields employee passages, and label "AI" as a subgroup afterwards instead of
using it as the entry filter.

## 3. Pool sizes (computed 2026-09-02 from `data/derived/deal_catalog.csv`)

| Step | Deals |
| --- | ---: |
| Catalog rows (SDC, 2020-2022) | 26,369 |
| Acquirer resolved to an EDGAR CIK (high or medium confidence) | 4,718 |
| ... and target in the 24 digital-technology SIC codes (`config/technology_sic.toml`) | **1,060** |
| ... with a transaction value recorded | 318 |
| ... value >= $50M | 219 (162 high / 57 medium CIK confidence; 116 private, 32 subsidiary, 22 public targets) |
| ... value >= $100M | 186 |

The 10 pilot deals came from this same pool and 9 of 10 produced passages. If even 40% of the
1,060 are probe-positive and 60% of those yield >= 10 passages, that is ~250 deals - comfortably
above 100. The probe (step 4.2) settles the real number in about 15 minutes of live requests,
before any expensive retrieval.

Fallback if the pool is short: rebuild the catalog for 2016-2019 with the existing
`build-deal-catalog` command (the SDC export covers 1980-2022) and probe again. No rule changes.

## 4. Pipeline, stage by stage

Everything reuses the existing `tag_edgar` package (Python 3.12, typer CLI, pytest, ruff,
basedpyright). Two new modules and four new CLI commands; everything downstream is unchanged.

### 4.1 `screen-disclosure-pool` (new, offline, deterministic)

Module `tag_edgar/disclosure_pool.py`. Reads the catalog, applies the written rule, writes
`data/derived/disclosure_pool/pool.csv` + `pool_manifest.json` (rule version, counts at every
step, catalog SHA-256).

Rule (frozen in `config/disclosure_pool.toml`):

- `cik_match_confidence` in {high, medium}
- `target_primary_sic` in `technology_sic.toml`
- announcement date present
- **no value floor** (value is missing for 70% of the pool; the probe is the real filter)

### 4.2 `probe-disclosure` (new, live, ~1,000 cache-friendly requests)

Module `tag_edgar/disclosure_probe.py`. For each pool deal, fetch the acquirer's EDGAR
submissions index (one JSON per CIK, already cached for most) and look in the window
[announcement - 5 days, announcement + 60 days] for any of:

| Signal | Filing | Why it matters |
| --- | --- | --- |
| `agreement_exhibit` | 8-K with EX-2.1 / EX-2.x, or S-4 | the merger/purchase agreement itself - where the employee-matters article lives |
| `merger_proxy` | DEFM14A, PREM14A, SC 14D9, SC TO-T (target side, when target CIK is known) | interests-of-directors-and-officers and employee sections |
| `announcement_only` | 8-K with EX-99.1 only | press release; usually thin on employees |
| `nothing` | no transaction filing in window | deal drops out, with the reason recorded |

Then, for `agreement_exhibit` and `merger_proxy` hits, fetch the filing index and check that the
**target's name appears** in the primary document. That single check does two jobs: it confirms
the filing is about *this* deal, and it confirms the CIK match far more strongly than name
matching did. Output: `probe_results.csv` with `probe_status`, `probe_filings`, `target_name_hit`,
`cik_confirmation_basis = machine_target_name_in_acquirer_filing`.

Cost: 1,060 submissions lookups + ~2 index fetches per positive deal, at the configured 5 req/s,
about 10-20 minutes. Needs a real `SEC_USER_AGENT` in `.env` (never fabricated; Aarav supplies it).

### 4.3 `run-disclosure-sample` (new wrapper, live, overnight)

Thin wrapper around the existing `run_vertical_slice` so the retrieval code path is the same one
validated by the pilot. It accepts probe-positive rows whose `cik_confirmation_basis` is the
machine check, records that basis in `run_summary.csv`, and retrieves in a fixed order
(`probe_status` rank, then transaction value descending, then `deal_id`) with a cap of 300 deals
per run. Expected: ~250 deals x ~47 documents = ~12,000 documents, 1-2 hours, run in the background.

Human spot check, 15 minutes: a fixed-seed random 10 of the retrieved deals, confirm that the
EX-2.1 is the agreement for that deal. Recorded in the manifest as `spot_check_rows`,
`spot_check_reviewer`, `spot_check_result`, and the program never fills those columns.

### 4.4 `build-employee-corpus` (existing, unchanged, cycle-5 screen)

Same command as the pilot. Writes `employee_corpus_100/` with passages, sources, families,
exclusions, and the corpus manifest.

### 4.5 `freeze-disclosure-sample` (new, offline)

Applies the **yield gate** and writes the frozen deal list the report is built from:

- **kept for modelling:** >= 10 included passages from >= 2 transaction-linked documents;
- **zero-state, reported not modelled:** probe-positive but < 10 passages (kept as rows, like
  Fastly-Glitch in the pilot, because "no employee language" is itself information);
- **dropped at probe:** with reason.

Output `frozen_sample.csv` + `frozen_sample_manifest.json` with the SHA-256 of the corpus it was
computed from. Nothing downstream may run on a deal list other than this file.

### 4.6 AI subgroup labelling (existing `ai_screening.py`, applied afterwards)

Run the existing AI screen over each kept deal's press release (EX-99.1) and agreement recitals
to produce `ai_label` in {ai_explicit, ai_adjacent, none} with the matched phrase and its
`#:~:text=` link. This is a **machine label pending human review**; the report states the count
plainly (it may be small - that is a finding about disclosure, not a failure).

### 4.7 Corpus relevance audit (existing, the one required human step)

`prepare-corpus-relevance-audit` on `employee_corpus_100/passages.csv` -> 75 + 75 rows, hash-linked
to this corpus. Aarav and Sreyas label 75 rows each (~45 minutes each), then
`score-corpus-relevance-audit`. Gate: >= 90% relevance among included, < 5% missed among excluded.

If the gate fails, we do not rerun the screen and re-audit until it passes; we report the failure
rate and treat every topic result as provisional. If nobody labels, every downstream artifact
stays `pending_human_corpus_validation` and the report verdict is **WITHHELD**, and the brief to
Dr. Singh says so on page 1.

### 4.8 `analyze-employee-topics` (existing; three settings changed, all prespecified here)

| Setting | Pilot | 100-deal run | Reason |
| --- | --- | --- | --- |
| `--fit-balance` | `deal` | **`source_family`** | Prespecified *now*, before the run, from the cycle-5 diagnostic (deal-balanced recovery 0.630 vs source-family 0.815). Deal-balanced and `none` are run as sensitivity checks only. |
| `max_fit_passages` | 240 | **1,500** | ~10-15 representative rows per deal at 100-150 deals; the pilot's 240 would leave 2 per deal. |
| K | 3-5 | **3-7** | More deals can support more components; the stability gates decide, not us. |

Unchanged gates: leave-one-deal-out recovery >= 0.80 overall (switch to 10-fold deal-grouped if
more than 150 deals, stated in the manifest), bootstrap 100 replicates, NMF-vs-agglomerative
ARI >= 0.20, per-topic coherence reported. The model is given no topic names. Descriptors are
written after fitting from top terms and representative passages.

### 4.9 `summarize-employee-topics`, `analyze-employee-tone`, `prepare-employee-topic-review` (existing)

Report with per-topic top terms, representative passages with paragraph-level links, deal x topic
matrix, gates table, verdict. Tone stays a secondary diagnostic. The two-reviewer 30-item topic
packet is prepared; if reviewed (~20 minutes each), the agreement statistic goes in the report.

### 4.10 Deal architecture at scale (existing code, lighter evidence)

The 10-deal register is hand-curated; that does not scale. For the 100-deal table, a machine-only
`legal_transaction_form` from `sdc_form` plus the probe's document types, labelled
`machine_suggested_pending_human_review`, joined by `sdc_deal_id` through the existing cross-table.
The report says explicitly that only the 10 pilot deals have reviewed architecture evidence.

## 5. What is frozen before the first live request

- Pool rule, probe window and signals, yield gate thresholds (`config/disclosure_pool.toml`).
- Primary model: `source_family` balance, seed 20260823, K 3-7, `max_fit_passages` 1,500.
- Gates and thresholds exactly as in the pilot.
- Human steps: 150-row audit (two people), 10-deal CIK spot check, optional 30-item topic review.
- What counts as a "result": only artifacts whose manifest says the corpus gate passed.

Changing any of these after seeing results is recorded as a new cycle, never edited in place.

## 6. Timeline

| When | What | Who / how long |
| --- | --- | --- |
| Day 1 (code) | `disclosure_pool.py`, `disclosure_probe.py`, freeze command, wrapper, config, tests, docs | Claude, one session; CI green before any live run |
| Day 1 (live, 20 min) | `screen-disclosure-pool` -> `probe-disclosure`; report the real probe-positive count | needs `SEC_USER_AGENT` |
| Day 1 night | `run-disclosure-sample` in the background (1-2 h) | unattended |
| Day 2 morning | corpus build, freeze, AI labels, audit packet prepared | 30 min compute |
| Day 2 | label 75 + 75 audit rows; 10-row CIK spot check | Aarav + Sreyas, ~1 h each |
| Day 2 | score audit; topics (3 balance modes x K 3-7); tone; report; topic review packet | ~1 h compute |
| Day 3 | write the Dr. Singh report from generated tables; a11y/structure check; push | half day |

If the probe returns fewer than ~120 positives, Day 1 also rebuilds the catalog for 2016-2019
and probes again (adds ~30 minutes).

## 7. Final report outline (what the "results and reasoning" will look like)

1. **Question and boundary** - what disclosed employee-treatment language looks like across
   technology acquisitions; not outcomes, not causation.
2. **How we found deals with enough filings** - the funnel with real counts at every step
   (catalog -> resolved -> tech -> probe-positive -> retrieved -> yielded >= 10 passages), and the
   reasons deals dropped. Honest sentence: the sample is *disclosure-selected*; it describes
   acquisitions by SEC-registrant buyers that filed their agreements, not all acquisitions.
3. **The 100+ deals** - table with buyer, target, date, value, legal form, probe documents,
   passage count, AI label, links.
4. **Corpus** - documents, passages, provision families; the human relevance-audit result.
5. **Clusters** - for each topic: top terms, 3-5 representative paragraphs with highlight links,
   number of passages/deals, recovery and bootstrap stability, coherence, a plain-English
   descriptor written after the fact and marked provisional.
6. **Deals x clusters** - heat-map-style table; which deals lean on which cluster; AI-labelled
   subgroup shown as a descriptive comparison only.
7. **Sensitivity** - the three balance modes, K choices, agglomerative check; what moved and
   what did not.
8. **Tone** - secondary diagnostic, one table.
9. **What it means and what it cannot mean** - interpretation, then the limits list.
10. **Reproduction** - commands, hashes, branch, commit.

## 8. Limits we will state up front, not bury

- The sample is chosen by disclosure availability. Deals by private, PE, and foreign acquirers
  are largely absent, and that is a property of the public record, not of our search.
- "AI" is a post-hoc machine label pending review; the sample is technology M&A with an AI
  subgroup, not an AI-deal sample.
- Clusters are recurring language in contracts and proxies. They are not retention outcomes,
  employee sentiment, or evidence that anyone stayed.
- Only the ten pilot deals have reviewed deal-architecture evidence.
- Dr. Singh's August 13 direction was 2-3 deeply verified deals before scaling. This plan scales
  first; the ten pilot deals and their salvage record remain the deep-verification layer, and the
  report says which layer each claim comes from.

## 9. What I need from Aarav to start

1. A real `SEC_USER_AGENT` value in `.env` (name and contact email, per SEC fair-access policy).
2. Go-ahead to write the four new commands on this branch and run the probe.
3. About one hour each from Aarav and Sreyas on Day 2 for the audit packet.

---

# Execution record (2026-09-02)

This section records what was actually run and where the plan above changed. It is appended
rather than edited into the plan so the difference between what was planned and what happened
stays visible.

## Change of plan: the human relevance audit was skipped

Aarav directed that the 150-row corpus relevance audit be skipped for time. That decision is
recorded here rather than worked around. The consequence is stated, not hidden:

- No downstream artifact may report a passing corpus gate, and none does. The report's limits
  section states that the audit was **not run** and gives the reason it matters.
- The comparable cycle-4 audit of a different corpus scored 72% included-passage relevance
  against a 90% threshold. The risk that a meaningful share of "employee" passages are not
  about employees is therefore real and quantified, not hypothetical.
- No human-review field is filled by the program, and nothing claims human assessment.

The blinded packet can still be built and labelled later; doing so upgrades the report without
re-running any model.

## What the probe actually found

The 60-day probe window in section 4.2 was **wrong** and was corrected before the full run. It
classified Take-Two/Zynga and Intuit/Mailchimp as announcement-only although both yielded
hundreds of passages in the pilot, because merger proxies and tender-offer statements are filed
months after announcement. The probe now uses `tag_edgar.windows.event_window`, the same window
the retrieval pipeline uses. A second bug: exhibit types were read from the accession
`index.json`, whose `type` field holds icon filenames, not SEC exhibit types. They now come from
the filing-detail page through the pipeline's own parser.

Full probe of the 1,060-deal pool:

| Probe outcome | Deals |
| --- | ---: |
| Filed a transaction agreement (EX-2) | 89 |
| Filed a merger proxy or tender offer | 81 |
| Filed only an announcement in the window | 724 |
| Filed nothing in the window | 166 |
| **Probe-positive** | **170** |
| Target name corroborated in the buyer's own filing | 112 |

## Queue and retrieval

170 probe-positive deals is a thin margin over 100 once the yield gate applies, and the pilot
showed that announcement-only deals can still be rich: Microsoft-Nuance is announcement-only by
this test and produced 231 passages. So the queue takes all 170 positives plus the 230
announcement-only deals with the most filings in their window, 400 in total, ranked so the
richest disclosure is retrieved first. Retrieval is resumable and averages about 150 documents
per deal, far above the pilot's 47.

## Settings frozen before the run

| Setting | Value | Why |
| --- | --- | --- |
| Fit balance | `source_family` | Prespecified from the cycle-5 diagnostic, before seeing any 100-deal result |
| `max_fit_passages` | 1,500 | The 240 default would leave about one row per deal |
| K range | 3-7 | The stability gates decide, not the author |
| Seed | 20260823 | Same as the pilot |
| Yield gate | 10 passages from 2 documents | `config/disclosure_pool.toml` |

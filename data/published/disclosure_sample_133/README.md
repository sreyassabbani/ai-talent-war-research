# Disclosure-first sample: published result tables

> ## Superseded on 2026-09-04 by [`../disclosure_sample_134/`](../disclosure_sample_134/)
>
> **Do not quote numbers from this directory.** It is kept as the record of what was
> published on 2026-09-03, not as a second opinion alongside the newer tables. Where the
> two disagree, cycle 6 is the corrected one.
>
> These tables were built on a corpus with three defects, all found after publication and
> all now fixed. Each is written up in
> [`docs/retrieval_window_memo.md`](../../../docs/retrieval_window_memo.md):
>
> | Defect | Effect on these tables | Written up in |
> | --- | --- | --- |
> | The page's running header counted as passage text, so the relevance screen threw away real provisions whose page happened to print "table of contents" | 1,266 passage texts wrongly discarded — indemnification survival, RSU award schedules, vesting terms, double-trigger benefit continuation | § 5c |
> | Section headings were fed to the model as features | "table", "contents" and "table contents" were top-ten distinguishing terms of Theme 1 — a running header was a defining feature of a theme | § 5b |
> | A clause filed as an exhibit and reprinted inside the S-4 or proxy carrying it was modelled once per rendition | 968 rows counted twice, 7.0% of the sample; Bally's / Bet.Works, System1 / Protected.Net and Ginkgo / Baktus worst affected | §§ 5a–5b |
>
> **What changed when they were fixed** (§ 5d). The sample moved from 133 deals / 13,817
> passages to **134 deals / 13,954 passages** — one deal crossed the yield gate. Within-deal
> duplicate rows went 1,017 → 0 and structural-heading tokens 9,717 → 9. The three themes
> **survived**: k=3 in both cycles, the same identities by their terms, all still clearing the
> 0.80 stability bar, and the dominant theme unchanged for all 133 deals present in both. So
> the headline result of these tables stands. What moved is inside it — 1,955 passages
> migrated from Theme 1 to Theme 2 once the header stopped misfiling benefit-plan text into
> the executive theme, and Theme 1's coherence rose 0.258 → 0.309 while Theme 2's fell 0.351
> → 0.198.
>
> **One conclusion here is now reversed.** The cycle-5 report recommended excluding EX-99
> press releases, because dropping them took Theme 1 from 1 of 3 sub-themes passing to 3 of 3.
> In cycle 6 Theme 1 passes 3 of 3 *with* press releases and 2 of 3 without. The header fix
> had been doing what the EX-99 exclusion appeared to do. Treat that recommendation as
> withdrawn; the question is open again.
>
> Regenerating this directory with `scripts/publish_disclosure_snapshot.py` would erase this
> notice, since that script rewrites the README from the files it finds. Do not re-run it here.

The small tables behind `docs/disclosure_sample_report.md`, copied out of the
git-ignored `data/derived/` so every number in the report can be checked against the
file it came from.

Snapshot written 2026-09-03 by
`scripts/publish_disclosure_snapshot.py`. Re-running that script refreshes it.

## What is here

| File | Size | SHA-256 (first 16) |
| --- | ---: | --- |
| `01_pool_manifest.json` | 0 KB | `81300f16a31e592e` |
| `02_probe_results.csv` | 192 KB | `59aae90384398ee5` |
| `02_probe_manifest.json` | 0 KB | `a2bbc866b5c7265d` |
| `03_corpus_manifest.json` | 9 KB | `2960f53758400d1f` |
| `04_frozen_sample.csv` | 88 KB | `ca4bfff892d6bdc0` |
| `04_frozen_sample_manifest.json` | 0 KB | `dcf079287ef8a677` |
| `05_deal_ai_labels.csv` | 44 KB | `028d072d41fc161b` |
| `06_topic_summary.csv` | 1 KB | `908c61e43407b5b8` |
| `06_deal_topic_matrix.csv` | 33 KB | `4123789faf326f45` |
| `06_model_diagnostics.csv` | 8 KB | `b8a1c42146f9f1f4` |
| `06_analysis_manifest.json` | 5 KB | `f04217ca7e88df40` |
| `07_deal_tone_summary.csv` | 23 KB | `2477b82654128a39` |

Written by the sibling scripts rather than by this one:

| File | Size |
| --- | ---: |
| `08_passage_links.csv.gz` | 3021 KB |
| `08_passage_links_manifest.json` | 0 KB |
| `08_passage_links_sample.csv` | 1105 KB |
| `09_deal_profiles.csv` | 28 KB |
| `09_deal_profiles_manifest.json` | 0 KB |

Rebuild them with:

- `python scripts/publish_passage_links.py` — 08_passage_links*, passage text with SEC deep links.
- `python scripts/build_deal_profiles.py` — 09_deal_profiles*, one row per modelled deal.

The numbered prefixes follow the pipeline: pool, probe, corpus, frozen sample, AI
labels, topic model, tone, passage links, deal profiles.

## What is not here, and why

- `employee_corpus_100/passages.csv` — 117 MB of SEC body text.
- `disclosure_runs/` — 35,296 retrieved documents.
- `cache/http/` — the HTTP cache, about 520 MB.
- `the SDC/Thomson archive` — licensed vendor data.

## Evidence boundary

These are disclosed contract and filing terms, not employee outcomes. The sample is
selected by whether a buyer filed with the SEC, so it is not representative of
acquisitions generally. The corpus relevance audit was not run for this cycle, so no
table here is a validated finding. AI labels and archetype suggestions are machine-
derived and pending human review.

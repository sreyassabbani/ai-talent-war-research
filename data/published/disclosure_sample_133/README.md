# Disclosure-first sample: published result tables

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

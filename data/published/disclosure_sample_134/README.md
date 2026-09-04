# Disclosure-first sample: published result tables

The small tables behind `docs/disclosure_sample_report_c6.md`, copied out of the
git-ignored `data/derived/` so every number in the report can be checked against the
file it came from.

Snapshot written 2026-09-04 by
`scripts/publish_disclosure_snapshot.py`. Re-running that script refreshes it.

## What is here

| File | Size | SHA-256 (first 16) |
| --- | ---: | --- |
| `01_pool_manifest.json` | 0 KB | `81300f16a31e592e` |
| `02_probe_results.csv` | 192 KB | `59aae90384398ee5` |
| `02_probe_manifest.json` | 0 KB | `a2bbc866b5c7265d` |
| `03_corpus_manifest.json` | 9 KB | `bdd92e03ac236127` |
| `04_frozen_sample.csv` | 88 KB | `33382f5a8b3cccbe` |
| `04_frozen_sample_manifest.json` | 0 KB | `d9a8096a7d296285` |
| `05_deal_ai_labels.csv` | 45 KB | `19a7724253352a3e` |
| `06_topic_summary.csv` | 1 KB | `413a7bc6628bd3fb` |
| `06_deal_topic_matrix.csv` | 33 KB | `c076398f170559f4` |
| `06_model_diagnostics.csv` | 8 KB | `8103a856c293c129` |
| `06_analysis_manifest.json` | 6 KB | `12fbf2d0333d0fa7` |
| `07_deal_tone_summary.csv` | 24 KB | `465549879b45c530` |

Written by the sibling scripts rather than by this one:

| File | Size |
| --- | ---: |
| `08_passage_links.csv.gz` | 3137 KB |
| `08_passage_links_manifest.json` | 0 KB |
| `08_passage_links_sample.csv` | 1080 KB |
| `09_deal_profiles.csv` | 28 KB |
| `09_deal_profiles_manifest.json` | 0 KB |

Rebuild them with:

- `python scripts/publish_passage_links.py` — 08_passage_links*, passage text with SEC deep links.
- `python scripts/build_deal_profiles.py` — 09_deal_profiles*, one row per modelled deal.

The numbered prefixes follow the pipeline: pool, probe, corpus, frozen sample, AI
labels, topic model, tone, passage links, deal profiles.

## What is not here, and why

- `employee_corpus_c6/passages.csv` — 103 MB of SEC body text.
- `disclosure_runs/` — 35,296 retrieved documents.
- `cache/http/` — the HTTP cache, about 520 MB.
- `the SDC/Thomson archive` — licensed vendor data.

## Evidence boundary

These are disclosed contract and filing terms, not employee outcomes. The sample is
selected by whether a buyer filed with the SEC, so it is not representative of
acquisitions generally. The corpus relevance audit was not run for this cycle, so no
table here is a validated finding. AI labels and archetype suggestions are machine-
derived and pending human review.

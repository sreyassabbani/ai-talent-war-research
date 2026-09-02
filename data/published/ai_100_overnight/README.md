# AI 100 expansion: generated metadata and unsupervised-model outputs

This directory is a source-controlled snapshot of the completed `ai_100_overnight` run. It contains the 100 selected candidate slots plus 19 reserves, the resulting evidence-screening outputs, and the exploratory unsupervised-model outputs.

## Exact status

- Candidate manifest rows: 119.
- Selected candidates: 100.
- Reserve candidates: 19.
- Retrieved documents: 1,402.
- Failed individual document retrievals: 9.
- Unique employee passages: 72 across 13 deals.
- Qualifying deals with zero employee passages: 22.
- Machine-qualified rows pending human review: 35.
- Human-verified qualifying AI transactions: 0.
- Shortfall from the requested 100 verified transactions: 65.
- Topic status: `exploratory_rejected_deal_concentration`.

The 100 rows are not 100 verified AI transactions. The candidate manifest preserves unresolved, rejected, and machine-qualified rows with their missingness reasons. Machine qualification is not human verification.

## Included outputs

- `frozen_ai_manifest.csv` — all 119 candidate/reserve rows and status fields.
- `deal_human_review_queue.csv` — candidate-level human verification queue.
- `deal_source_register.csv` — source and evidence register.
- `document_inventory.csv` and `retrieved_document_index.csv` — retrieved-document metadata and status.
- `employee_screen_results.csv`, `passages.csv`, `passage_sources.csv`, and `zero_passage_deals.csv` — employee-passage screening and provenance.
- `topic_summary.csv`, `topic_assignments.csv`, `deal_by_topic.csv`, `topic_model_diagnostics.csv`, and `topic_stability.csv` — TF-IDF/NMF topic outputs and diagnostics.
- `topic_review_queue.csv` — blank human topic-review queue.
- `tone_summary.csv`, `passage_tone.csv`, `word_use_comparison.csv`, and `document_type_baselines.csv` — descriptive lexical diagnostics.
- `wordclouds.html` and `wordclouds/` — deterministic frequency-scaled visualizations.
- `analysis_manifest.json`, `corpus_manifest.json`, `state.json`, `frozen_ai_manifest.meta.json`, and verification summaries — reproducibility and run-status metadata.
- `overnight_log.jsonl` and `deduplication.csv` — run and deduplication records.

## Unsupervised model

The expansion uses word/bigram TF-IDF followed by fixed-seed NMF over K = 3 through 7. It also compares the NMF assignments with cosine/average agglomerative clustering and performs deterministic leave-one-deal-out top-term comparisons. Topic labels are derived from top terms and remain exploratory.

The current analysis selected K = 3 with half-sample stability `0.2464`. The NMF/agglomerative ARI is `0.3775`. One deal supplies `44.44%` of all passages, above the prespecified `35%` concentration threshold, so the topic result is retained only as an exploratory diagnostic. The topic-review queue is intentionally blank until real reviewers code it.

The broader 10-deal pilot contains the richer bootstrap and local LSA/HDBSCAN robustness branch. See [`docs/unsupervised_models_progress.md`](../../../docs/unsupervised_models_progress.md) for the complete history, pilot diagnostics, human-review gates, proposed methods, and limitations.

## Evidence and licensing boundary

This snapshot contains generated metadata/results and links or excerpts from retrieved official sources. It does not include the raw Thomson/SDC archive or the large scraped document corpus. The raw corpus was prepared separately for controlled handoff and should not be redistributed casually. SDC/LSEG source records remain subject to their applicable license and access restrictions.

Public-source evidence does not establish actual employee retention, a talent motive, employee behavior, or causation. Missing documents and zero-passage states remain unknown/not disclosed states, not proof that no arrangement existed.

## Reproduction

The generating code remains in [`src/tag_edgar/overnight.py`](../../../src/tag_edgar/overnight.py), [`src/tag_edgar/topics100.py`](../../../src/tag_edgar/topics100.py), and the surrounding pipeline modules. This directory is a generated snapshot, not a replacement for the code, configuration, or source-cache requirements.

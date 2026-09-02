# Unsupervised Models and Research Progress

Status date: 2026-08-31

This document records all unsupervised-model and closely related exploratory work completed in the TAG Internship project. It separates implemented code, diagnostics, proposed methods, human-review gates, and research limitations.

## Bottom line

The project now contains a real, reproducible unsupervised text-analysis pipeline. It groups employee-related transaction passages using interpretable text features and tests whether the resulting components are stable across deals and resamples.

The current output is not a validated taxonomy or finished classification system. The 10-deal pilot model runs successfully, but the corpus relevance gate failed, one topic was unstable, and human representative-passage review is still pending. The larger 100-deal branch is also partial: it contains machine-screened candidates, not 100 human-verified AI transactions.

The strongest current findings concern what public documents disclose: pay and benefit continuity, equity conversion or continued-service vesting, key-person employment or availability, severance, and occasional quantified retention instruments. The work does not prove that an employee stayed, that a provision caused retention, or that one company cared more than another.

## 1. Original research design

The project began with a question about whether employee-retention and integration language could be grouped without imposing a finished category system first.

The planned workflow was:

```text
SEC/official documents
  -> employee-related passages
  -> boilerplate removal and deduplication
  -> numeric text representation
  -> unsupervised grouping/topic exploration
  -> human inspection and theme naming
  -> possible human-approved codebook
  -> possible supervised classifier later
```

The following methods were discussed as possible future approaches:

- sentence or transformer embeddings;
- UMAP;
- HDBSCAN;
- BERTopic;
- other text-clustering methods; and
- a supervised classifier only after human labels and a codebook existed.

These were design options, not completed implementations. UMAP, BERTopic, transformer embeddings, and a supervised classifier were not used in the final project state.

## 2. Completed 10-deal topic-model pilot

The main pilot implementation is in [`src/tag_edgar/employee_topics.py`](../src/tag_edgar/employee_topics.py). The workflow is exposed through [`src/tag_edgar/employee_workflow.py`](../src/tag_edgar/employee_workflow.py) and the command-line interface.

### Input preparation

Before modeling, the workflow:

1. keeps only passages marked `included`;
2. requires non-empty model text;
3. reduces exact duplicate groups to one deterministic canonical passage for model fitting;
4. preserves every source occurrence and propagates assignments back to duplicate source rows;
5. tracks document-family and deal support;
6. balances the fit universe across deals and provision families; and
7. records explicit zero-passage and missingness states.

This prevents repeated boilerplate or one heavily documented transaction from silently becoming the entire model.

### Representation and primary model

The primary model uses:

- word and bigram TF-IDF features;
- document-frequency filtering;
- fixed seeds;
- a candidate range of 3 through 7 topics;
- a custom nonnegative matrix factorization implementation;
- a maximum fit universe of 240 passages;
- fixed-component projection for passages outside the fit universe; and
- normalized topic weights for passage- and deal-level comparison.

The model produces top terms, topic assignments, topic weights, document-family support, deal support, coherence diagnostics, assignment-specificity margins, positive residual terms, a complete deal-topic matrix, and source-linked representative passages.

No approved label such as `cash`, `equity`, `benefits`, or `exit protection` is supplied to the model as the correct answer.

### Pilot corpus

The final 10-deal corpus contained:

- 469/469 retrieved documents parsed successfully;
- 358 transaction-linked SEC documents;
- 2,708 included exact-text-deduplicated passages;
- 10,933 preserved source occurrences;
- 9 deals with included passages; and
- one explicit zero-passage case: Fastly–Glitch.

### Candidate components

The selected three-component output suggested:

1. continuing-employee benefits and plan transitions;
2. executive compensation, tax, and merger-related arrangements; and
3. equity-award conversion and vesting treatment.

These are candidate components, not confirmed legal categories or approved taxonomy labels.

## 3. Pilot robustness and stability checks

### NMF versus agglomerative clustering

The project compares the primary NMF assignments with cosine-distance, average-linkage agglomerative clustering on the same fit universe.

- Adjusted Rand index: `0.306`.
- Prespecified floor: `0.20`.
- Result: this diagnostic passed.

This indicates method agreement on the shared fit rows, but it does not prove that the components have the correct substantive interpretation.

### Leave-one-deal-out stability

The model was refit while leaving out each deal. Components were aligned by cosine similarity.

- Component 1 recovered in `9/9` folds.
- Component 2 recovered in `6/9` folds, or `0.667`.
- Component 3 recovered in `8/9` folds.
- Required recovery rate: `0.80`.

Component 2 therefore fails the stability gate.

### Fixed-seed within-deal bootstrap

The project added 100 bootstrap replicates. Each deal retained its original number of fit rows, and sampling occurred within deal/provision-family representatives with replacement.

- Component 1: `80/100` recoveries.
- Component 2: `21/100` recoveries.
- Component 3: `81/100` recoveries.

The bootstrap is a complementary robustness diagnostic. It is not a post-hoc topic-selection or relabeling rule.

### Local LSA embedding diagnostic

The project also added a local embedding-style check using normalized TruncatedSVD over the same word/bigram TF-IDF matrix. These are LSA embeddings, not transformer semantic embeddings.

- Fit rows embedded: `240/240`.
- HDBSCAN clusters discovered: `5`.
- HDBSCAN noise rows: `142`.
- LSA agglomerative ARI: `0.325`.

This branch cannot change the selected NMF solution, topic count, topic labels, or human-review status.

## 4. Corpus-quality validation

The passage screen received a separate blinded human audit. The workflow created:

- 75 sampled included candidates;
- 75 sampled excluded candidates;
- an assessor-blinded packet;
- a separate private key;
- immutable hashes; and
- a scoring command that refuses incomplete or fabricated labels.

The completed audit found:

- included-passage relevance: `72.0%`;
- required included-passage threshold: at least `90%`;
- relevant content among excluded candidates: `5.33%`;
- required excluded-content threshold: below `5%`.

The corpus-quality gate therefore failed. Problems concentrated in caption/boilerplate fragments, deal-mechanics passages retained by the screen, and relevant equity-award or retention-risk provisions removed by over-broad exclusions.

This failure means the model output cannot be treated as a clean discovery of substantive employee-protection categories until the screen is repaired and re-audited.

## 5. Human topic-review system

The blinded review implementation is in [`src/tag_edgar/employee_topic_review.py`](../src/tag_edgar/employee_topic_review.py).

It creates:

- a randomized 30-item packet;
- 10 representative passages per candidate topic;
- two independent reviewer copies;
- a private re-identification key;
- `fit`, `partial`, and `not_fit` coding options; and
- input hashes and diagnostic manifests.

The release gate requires:

- at least 80% strict `fit` for every reviewer/topic;
- at least 80% exact agreement;
- an agreement coefficient of at least 0.70; and
- successful stability checks for the topic being released.

The packet and reviewer copies exist, but the reviewer fields remain blank. No human-approved taxonomy has been released.

## 6. 100-deal expansion

The larger branch is implemented through [`src/tag_edgar/topics100.py`](../src/tag_edgar/topics100.py) and [`src/tag_edgar/overnight.py`](../src/tag_edgar/overnight.py). Its status is documented in [`docs/ai_100_expansion_status.md`](ai_100_expansion_status.md).

It is a resumable, no-LLM operational pipeline that:

1. reads selected candidates and reserves;
2. resolves public-company identities and retrieves cached SEC documents;
3. retrieves only approved supplemental official sources;
4. requires AI evidence and a distinctive target-name anchor in the same source paragraph;
5. preserves a status row for every candidate;
6. builds a heading-aware, deduplicated employee-passage corpus;
7. preserves source occurrences and zero-passage deals;
8. runs fixed-seed TF-IDF plus NMF topics;
9. produces sensitivity and stability outputs;
10. produces tone, word-use, baseline, and word-cloud outputs; and
11. writes manifests, logs, review queues, missingness reports, and a final descriptive report.

### Current expansion result

- 119 candidate rows.
- 100 selected candidates and 19 reserves.
- 1,402 retrieved documents.
- 9 failed individual document retrievals.
- 72 unique employee passages.
- Passages across 13 deals.
- 22 qualifying deals with zero employee passages.
- 35 machine-qualified rows pending human review.
- 0 human-verified qualifying AI transactions.
- 65-deal shortfall from the requested 100 verified transactions.

The topic status is `exploratory_rejected_deal_concentration` because one deal supplies 44.44% of the passages, above the 35% concentration threshold. The expansion is therefore not a completed 100-deal unsupervised study.

The expansion topic output selected three topics from K=3 through K=7 using deterministic half-sample stability. The output is retained for diagnostics, but its low stability and corpus concentration make it unsuitable for substantive interpretation.

## 7. Repairs made after false positives

The first Microsoft–Lobe smoke run incorrectly qualified a generic corporate sentence about artificial intelligence and produced 577 passages. The pipeline was repaired so that:

- AI evidence must occur near a distinctive target-name anchor;
- AI and target evidence must occur in the same source paragraph;
- late HTML is parsed correctly;
- only target-linked documents enter the employee corpus;
- generic descriptors such as `robotics`, `mapping`, and `data science` cannot identify a target by themselves;
- focused official deal announcements are preferred; and
- common HTML-layout tokens are excluded from the topic vocabulary.

After repair, Microsoft–Lobe remained unresolved with zero qualifying deals and zero passages rather than being counted as a false positive. Four other provisional inclusions were removed when their retrieved text did not establish target-linked AI evidence. A later official Box announcement independently supported re-entry for the Butter.ai team.

These repairs improved provenance and prevented unsupported rows from entering the model, but they did not replace human verification.

## 8. Tone, word-use, and word-cloud work

These are supporting exploratory analyses, not unsupervised models.

### Tone and lexical rates

[`employee_tone.py`](../src/tag_edgar/employee_tone.py), [`tone.py`](../src/tag_edgar/tone.py), and [`baseline.py`](../src/tag_edgar/baseline.py) calculate transparent lexical rates for:

- positive and negative language;
- hedging and modality;
- protection-program terms;
- retention;
- pay and wages;
- benefits;
- equity and vesting;
- termination and severance; and
- employee/workforce language.

They report raw counts, per-100-token rates, deal summaries, document-family baselines, and adjusted values.

The latest expansion has only one document family in its baseline, so the adjusted values are not a credible legal-register control for substantive ranking. The current interpretation is drafting style only.

### Word-use comparison

The later audit created a normalized term-comparison table reporting exact counts and mentions per 1,000 tokens for retention, benefits, wages, equity/vesting, severance, and continued-service language. This is more auditable than a frequency bubble map, but it remains exploratory because the passage relevance gate failed.

### Word clouds

[`wordcloud.py`](../src/tag_edgar/wordcloud.py) produces deterministic SVG/HTML frequency-scaled word clouds. They are useful for visual exploration but do not measure importance, concern, company seriousness, retention success, or strategy quality.

## 9. Current audit/salvage conclusion

The latest local audit package corrected two source-link problems and assembled a corrected official-source 10-deal pilot. Its proposed cluster families are for organization only and remain pending human review; they are not a released unsupervised taxonomy.

The most defensible current pilot families are descriptive disclosure mechanisms:

- pay and benefit continuity;
- equity conversion and continued-service treatment;
- key-person continuity or availability;
- severance and retention liabilities; and
- occasional named or quantified retention instruments.

The linked data design keeps the grains separate:

```text
deals -> documents -> evidence_passages -> exploratory clusters
  \
   -> key_people
```

Clusters should be formed from cleaned passages first. Only supported memberships or features should then be aggregated back to verified deals for comparison.

## 10. What has and has not been completed

### Completed

- An interpretable deterministic TF-IDF/NMF topic pipeline.
- Deal-balanced fitting and provision-family duplicate control.
- Passage-to-deal topic aggregation.
- Agglomerative sensitivity comparison.
- Leave-one-deal-out stability.
- 100-replicate bootstrap stability.
- Local LSA/HDBSCAN robustness diagnostics.
- Blinded human topic-review preparation and scoring infrastructure.
- Blinded corpus relevance auditing and scoring infrastructure.
- A resumable 100-candidate AI expansion workflow.
- Deterministic tone and normalized word-use diagnostics.
- Deterministic SVG/HTML word clouds.
- Source-linked reports, manifests, review queues, logs, and missingness records.
- Offline regression coverage; the current repository test run passes `197` tests.

### Not completed

- A validated unsupervised taxonomy.
- Human-approved cluster labels.
- Completed two-reviewer topic-fit scores.
- UMAP, BERTopic, or transformer embeddings.
- A supervised classifier.
- A verified 100-deal AI transaction dataset.
- Proof of actual employee retention.
- A causal workforce-outcome model.

## 11. Required language boundaries

Do not write:

- “The model found the company’s retention strategy.”
- “The company cared more about employees.”
- “The employee stayed because of the bonus or equity.”
- “The 100-deal database is complete.”
- “No document means no retention arrangement.”

Use instead:

- “The model suggested recurring language patterns in the screened passages.”
- “The screened passages had a higher rate of selected protection-program terms, subject to corpus and baseline limitations.”
- “The filing disclosed a bonus, equity award, or service condition; later employment outcome is separate.”
- “The run produced 119 candidates and 35 machine-qualified rows pending human review, with 0 human-verified transactions and a 65-deal shortfall.”
- “The arrangement was not observed in the reviewed documents, or the record remains unknown/not disclosed.”

Unsupervised grouping organizes public text. It does not know the legal meaning of a clause, whether a person stayed, whether a topic is genuine discovery or boilerplate, or whether the corpus represents all deals or employees.

## 12. Reproduction commands

For the 10-deal pilot:

```powershell
uv run tag-edgar build-employee-corpus data/derived/pilot_review_queue.csv data/derived/pilot_runs

uv run tag-edgar analyze-employee-topics `
  data/derived/pilot_review_queue.csv data/derived/employee_corpus

uv run tag-edgar summarize-employee-topics `
  data/derived/pilot_review_queue.csv `
  data/derived/employee_corpus data/derived/employee_topics

uv run tag-edgar prepare-employee-topic-review `
  data/derived/employee_topics/canonical_topic_assignments.csv `
  data/derived/employee_corpus/passages.csv
```

For the resumable expansion:

```powershell
.venv\Scripts\python.exe -m tag_edgar.overnight `
  --candidates data\derived\ai_100_candidate_preflight.csv `
  --raw-dir data\raw\ma_events `
  --out-dir data\derived\ai_100_overnight `
  --supplemental-sources config\ai_100_supplemental_sources.csv `
  --include-reserves
```

For the current offline quality check:

```powershell
.venv\Scripts\python.exe -m pytest -q
```

## References in this repository

- [`docs/employee_topics_brief.md`](employee_topics_brief.md) — 10-deal pilot results and topic-gate status.
- [`docs/pilot_validation_metrics.md`](pilot_validation_metrics.md) — pilot denominators and evidence limits.
- [`docs/ai_100_expansion_status.md`](ai_100_expansion_status.md) — exact expansion status and false-positive repairs.
- [`docs/corpus_relevance_audit.md`](corpus_relevance_audit.md) — blinded passage-screen audit contract.
- [`docs/research_goal_audit.md`](research_goal_audit.md) — proved, incomplete, and blocked-by-gate requirements.
- [`src/tag_edgar/employee_topics.py`](../src/tag_edgar/employee_topics.py) — 10-deal topic model, stability, bootstrap, and LSA diagnostics.
- [`src/tag_edgar/topics100.py`](../src/tag_edgar/topics100.py) — expansion topic model and sensitivity functions.
- [`src/tag_edgar/employee_topic_review.py`](../src/tag_edgar/employee_topic_review.py) — blinded topic-fit review.
- [`src/tag_edgar/employee_tone.py`](../src/tag_edgar/employee_tone.py) — pilot tone and word-use analysis.
- [`src/tag_edgar/overnight.py`](../src/tag_edgar/overnight.py) — resumable expansion pipeline and output generation.


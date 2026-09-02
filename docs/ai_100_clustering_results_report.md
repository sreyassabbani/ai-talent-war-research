# AI-100 Candidate Expansion and Clustering Results Report

Status date: 2026-08-31

## Executive summary

This report explains what the 100-candidate expansion actually produced, which deals reached the unsupervised analysis, how the passages were grouped, and why the current groups cannot yet be treated as substantive employee-retention categories.

The run contains **119 candidate rows**: 100 selected candidates and 19 reserves. Of those, **35 are machine-qualified and pending human review**, while **84 have no primary-source qualification**. Only **13 deals produced included passages**, yielding **72 passages** for exploratory clustering. There are currently **0 human-verified qualifying AI transactions** in this expansion. The topic result is rejected for release because one deal contributes 44.44% of passages, above the 35% concentration threshold.

**Actual funnel:** 100 selected candidate slots → 35 machine-qualified pending human review → 13 deals with included passages → 72 passages → 3 exploratory topics. This is not a completed dataset of 100 verified deals.

> The model grouped similar language. It did not determine that the deals used the same retention strategy, that the provisions worked, or that employees stayed.

## 1. What the 100-candidate expansion actually produced

| Run level | Count | Meaning |
| --- | ---: | --- |
| Selected candidate slots | 100 | Screening target; not 100 completed or verified deals. |
| Reserve candidates | 19 | Backup rows included in the combined run. |
| Total candidate manifest rows | 119 | Includes qualifying, rejected, and unresolved rows. |
| Machine-qualified rows | 35 | Pending human review. |
| No-primary-source rows | 84 | Not counted as qualifying transactions. |
| Retrieved documents | 1402 | Includes 9 failed individual document retrievals. |
| Employee passages | 72 | Screened passages, not validated provisions. |
| Deals represented in topic assignments | 13 | Only deals with passages entered the model output. |

The complete 119-row manifest is preserved in [`data/published/ai_100_overnight/frozen_ai_manifest.csv`](../data/published/ai_100_overnight/frozen_ai_manifest.csv). The 100 selected rows and 19 reserves are candidate records, not 119 verified deals. The 35 machine-qualified rows still require human review, and only 13 deals produced passages for the current model output.

### Deals that produced passages

These are the 13 deals represented in the current topic assignments. They are a processed subset of the candidate expansion, not a complete 100-deal results set. The remaining machine-qualified rows did not produce included passages in this run.

| Deal | Passages | Dominant topic | Dominant share |
| --- | ---: | --- | ---: |
| Zebra Technologies Corp - Fetch Robotics Inc | 32 | Topic 1: worker/productivity language | 57.0% |
| Glia Technologies Inc - Finn AI | 6 | Topic 3: generic AI/company language | 94.2% |
| Velodyne Lidar Inc - Bluecity.ai | 6 | Topic 3: generic AI/company language | 89.4% |
| Alphabet Inc - Kaggle Inc | 4 | Topic 3: generic AI/company language | 70.2% |
| Leanplum Inc - Connecto.ai | 4 | Topic 3: generic AI/company language | 63.6% |
| Algolia Inc - MorphL AI Inc | 4 | Topic 3: generic AI/company language | 96.8% |
| HubSpot Inc - Motion Ai Inc | 3 | Topic 3: generic AI/company language | 74.6% |
| Smartsheet Inc - Converse.AI Inc | 3 | Topic 3: generic AI/company language | 91.1% |
| AppHarvest Inc - Root AI Inc | 3 | Topic 3: generic AI/company language | 98.2% |
| 365 Retail Markets LLC - Stockwell AI Inc | 2 | Topic 3: generic AI/company language | 78.3% |
| Fortinet Inc - Sken Ai | 2 | Topic 3: generic AI/company language | 100.0% |
| IBM Corp - Databand.ai Ltd | 2 | Topic 3: generic AI/company language | 100.0% |
| Sensory Inc - Vocalize AI Inc | 1 | Topic 3: generic AI/company language | 100.0% |

### Why most candidates did not reach the model

The unresolved/rejected rows were preserved rather than silently dropped. These rows did not reach the current passage/model stage. The main missingness reasons were:

- 57 acquirers could not be resolved on EDGAR.
- 18 rows mentioned the target but lacked paragraph-local AI evidence.
- 7 rows had no target mention in retrieved documents.
- 2 rows had no documents retrieved for the deal.

These are evidence-screening outcomes, not proof that the underlying transaction was not AI-related.

## 2. How the unsupervised model worked

The expansion used the following sequence:

1. Retrieve target-linked SEC or approved official-source documents.
2. Extract and screen employee-related or transaction-linked passages.
3. Remove exact duplicate text and exclude common English or HTML-layout tokens.
4. Convert passages into word and bigram TF-IDF vectors.
5. Fit NMF models for K = 3, 4, 5, 6, and 7 using a fixed seed.
6. Select the candidate K with the best deterministic half-sample stability.
7. Assign each passage a dominant topic and a normalized weight across all topics.
8. Aggregate passage weights back to deals for descriptive comparison.
9. Compare NMF assignments with cosine/average agglomerative clustering and leave-one-deal-out term stability.

The current selected configuration was K = 3, with half-sample stability `0.2464`. The model used scikit-learn-compatible TF-IDF/NMF logic in [`src/tag_edgar/topics100.py`](../src/tag_edgar/topics100.py). This was lexical topic exploration, not semantic understanding.

## 3. What the three clusters contain

| Topic | Passage count | Deal coverage | Top terms | Why passages were grouped |
| --- | ---: | ---: | --- | --- |
| Topic 1: worker/productivity language | 20 | 1 | zebra technologies, technologies, zebra, workers, front, front line, line, productivity, worker, worker productivity, line workers, productivity zebra | Repeated Zebra/frontline-worker/productivity wording. All 20 passages come from the Zebra–Fetch source, so this is primarily document-specific vocabulary. |
| Topic 2: workforce-management language | 10 | 4 | workforce, management, workforce management, nucleus, research, nucleus research, research workforce, value matrix, matrix, technology value, management technology, leader nucleus | Repeated workforce-management, Nucleus Research, and management-heading language. This looks like mixed product/marketing text rather than one employee-protection mechanism. |
| Topic 3: generic AI/company language | 42 | 13 | ai, founder, ceo, founder ceo, data, said, glia, platform, co, co founder, customers, technology | Common acquisition-announcement language such as AI, founder, CEO, data, platform, team, and said. It is the broadest and most generic grouping. |

### Representative language behind the groupings

**Topic 1: worker/productivity language**
- Zebra Technologies and Its Channel Partners Continue to Support Front-Line Workers
- Sogegross Group Increases Front-Line Worker Productivity With Zebra Technologies
- Zebra Technologies Empowers Front-Line Workers with Next-Generation Mobile Computing Solution

**Topic 2: workforce-management language**
- Workforce Optimization
- Zebra Recognized as a Leader in Nucleus Research 2025 Workforce Management Technology Value Matrix
- Zebra Named Leader In 2023 Nucleus Research Workforce Management Technology Value Matrix

**Topic 3: generic AI/company language**
- been able to achieve widespread adoption on their own,” said Dan Michaeli, co-founder and CEO of Glia. “Glia’s large and rapidly growing customer base , combined with solid financial backing to accelerate the pace of in…
- Deposit Growth & Retention Win deposits and keep customers happy with fast service.
- Personnel Announcements

The word patterns explain the assignments mechanically: passages containing similar words receive more weight in the same NMF component. They do not establish that the passages have the same legal meaning. For example, `worker`, `productivity`, and `frontline` can describe a buyer's product marketing rather than employee retention.

## 4. Deal-level clustering view

The table below shows the normalized average topic weights used for deal-level comparison. These are descriptive model weights, not probabilities that a deal used a particular retention strategy.

| Deal | Passages | Topic 1 | Topic 2 | Topic 3 | Dominant topic |
| --- | ---: | ---: | ---: | ---: | --- |
| Zebra Technologies Corp - Fetch Robotics Inc | 32 | 57.0% | 26.7% | 16.3% | Topic 1: worker/productivity language |
| Glia Technologies Inc - Finn AI | 6 | 1.8% | 4.0% | 94.2% | Topic 3: generic AI/company language |
| Velodyne Lidar Inc - Bluecity.ai | 6 | 2.5% | 8.1% | 89.4% | Topic 3: generic AI/company language |
| Alphabet Inc - Kaggle Inc | 4 | 13.4% | 16.4% | 70.2% | Topic 3: generic AI/company language |
| Leanplum Inc - Connecto.ai | 4 | 11.1% | 25.2% | 63.6% | Topic 3: generic AI/company language |
| Algolia Inc - MorphL AI Inc | 4 | 1.9% | 1.4% | 96.8% | Topic 3: generic AI/company language |
| HubSpot Inc - Motion Ai Inc | 3 | 0.0% | 25.4% | 74.6% | Topic 3: generic AI/company language |
| Smartsheet Inc - Converse.AI Inc | 3 | 6.2% | 2.7% | 91.1% | Topic 3: generic AI/company language |
| AppHarvest Inc - Root AI Inc | 3 | 0.0% | 1.8% | 98.2% | Topic 3: generic AI/company language |
| 365 Retail Markets LLC - Stockwell AI Inc | 2 | 0.3% | 21.4% | 78.3% | Topic 3: generic AI/company language |
| Fortinet Inc - Sken Ai | 2 | 0.0% | 0.0% | 100.0% | Topic 3: generic AI/company language |
| IBM Corp - Databand.ai Ltd | 2 | 0.0% | 0.0% | 100.0% | Topic 3: generic AI/company language |
| Sensory Inc - Vocalize AI Inc | 1 | 0.0% | 0.0% | 100.0% | Topic 3: generic AI/company language |

The most important pattern is concentration: Zebra–Fetch contributes 32 of the 72 passages. It therefore dominates Topic 1 and contributes substantially to Topic 2. Most other deals are assigned primarily to Topic 3 because their shorter official announcements share generic AI/company language.

## 5. Diagnostics and why the result is not release-ready

| Diagnostic | Result | Interpretation |
| --- | ---: | --- |
| Selected topic count | K = 3 | Best candidate in the configured K range. |
| Half-sample stability | 20260826 seed; 0.2464 | Low exploratory stability; not a validated taxonomy. |
| NMF/agglomerative ARI | 0.3775 | Some assignment agreement, but not semantic validation. |
| Maximum deal passage share | 44.44% | Exceeds the 35% concentration threshold. |
| Human topic review | Blank | No human-approved labels. |

The separate 10-deal pilot found an additional corpus-quality problem: included-passage relevance was 72.0% against a 90% gate, and missed relevant content among excluded candidates was 5.33% against a below-5% gate. That audit was performed on the pilot corpus, not the 100-deal output, but it is a warning that the passage screen must be repaired before interpreting topic differences substantively.

## 6. What we can responsibly say

- The model found recurring lexical patterns in a screened set of transaction-linked passages.
- Topic 1 is heavily associated with one Zebra–Fetch source and worker/productivity wording.
- Topic 2 mixes workforce-management and company-content language and has limited interpretive clarity.
- Topic 3 is a broad generic AI/company-announcement cluster spanning the 13 deals with passages.
- The output is useful for identifying passages that need human review and for designing a better corpus.

## 7. What we cannot claim

- The clusters are not validated employee-retention categories.
- A dominant topic does not mean a company used that retention strategy.
- A disclosed bonus, equity award, benefit, or service condition does not prove retention.
- Zero passages do not prove that no employee arrangement existed.
- The 100 selected candidate slots are not 100 completed or verified AI transactions.
- The model does not measure company concern, employee motivation, or causal workforce outcomes.

## 8. Recommended next step

1. Repair the passage screen using the 150-row human relevance audit.
2. Separate official deal announcements from product-marketing and unrelated company pages.
3. Rebuild the passage corpus with one stable deal/document/passage provenance chain.
4. Rerun the topic model and concentration/stability diagnostics.
5. Have two real reviewers code representative passages before naming or releasing any cluster.
6. Only after human validation, decide whether to create a codebook and later supervised classifier.

## Source artifacts

- [`frozen_ai_manifest.csv`](../data/published/ai_100_overnight/frozen_ai_manifest.csv) — all 119 candidate/reserve rows.
- [`deal_source_register.csv`](../data/published/ai_100_overnight/deal_source_register.csv) — source and evidence register.
- [`topic_assignments.csv`](../data/published/ai_100_overnight/topic_assignments.csv) — passage-level assignments and supporting excerpts.
- [`deal_by_topic.csv`](../data/published/ai_100_overnight/deal_by_topic.csv) — deal-level normalized topic weights.
- [`topic_summary.csv`](../data/published/ai_100_overnight/topic_summary.csv) — top terms and stability fields.
- [`analysis_manifest.json`](../data/published/ai_100_overnight/analysis_manifest.json) — configuration, hashes, and status.
- [`docs/unsupervised_models_progress.md`](unsupervised_models_progress.md) — complete history of the unsupervised-model work.

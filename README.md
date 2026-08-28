# TAG EDGAR enrichment pilot

This project retrieves and audits transaction-related SEC documents for a small, known set of
SDC/LSEG acquisition events. It does not infer that a transaction is an acquihire or that a
keyword hit proves a retention arrangement.

## Setup

Run `uv sync`. `uv` can install a compatible Python version when needed.

## with Nix / `direnv` (optional)

- With Nix and `direnv`: run `direnv allow` (or use `nix develop` instead if you do not want the automatic directory hook)

## First live run

1. Copy `.env.example` to `.env` and replace the example contact address.
2. Run `uv sync`.
3. Verify the date window:

   ```sh
   uv run tag-edgar show-window --announcement 2024-01-10 --effective 2024-04-10
   ```

4. Run one vertical slice using manually confirmed public-party CIKs. The target CIK is optional
   because many targets are private or are not SEC registrants:

   ```sh
   uv run tag-edgar vertical-slice \
     --deal-id example-001 \
     --acquirer-cik 789019 \
     --target-cik 1002517 \
     --announcement 2024-01-10 \
     --effective 2024-04-10 \
     --target-name "Example Target"
   ```

The command writes normalized `deals.csv`, `filings.csv`, `deal_filings.csv`, `documents.csv`,
and `evidence.csv` under `data/derived/vertical_slice/`. `deal_filings.csv` and `evidence.csv`
are review queues, not verified datasets.

Read [PLAN.md](PLAN.md) for the full research and implementation plan.

## Offline H-1B pilot coverage audit

The H-1B coverage check reads already-downloaded official FY Q4 LCA workbooks and never downloads
data. Supply every workbook explicitly; the command records their SHA-256 values and the fixed
matching/counting rules in a manifest:

```sh
uv run tag-edgar audit-h1b-coverage data/derived/pilot_review_queue.csv \
  --workbook 2020=/path/to/LCA_Disclosure_Data_FY2020_Q4.xlsx \
  --workbook 2021=/path/to/LCA_Disclosure_Data_FY2021_Q4.xlsx \
  --workbook 2022=/path/to/LCA_Disclosure_Data_FY2022_Q4.xlsx \
  --workbook 2023=/path/to/LCA_Disclosure_Data_FY2023_Q4.xlsx
```

The resulting certified-case counts and summed `NEW_EMPLOYMENT` application fields are narrow
sponsorship-demand observables. They are not hires, retention, total hiring, worker outcomes, or a
causal acquisition effect, and the broad historical hiring-outcome branch remains no-go.

## Ingesting the SDC/LSEG export

Do not edit the licensed export. The current repository includes a mapping for the supplied Thomson
Reuters main files in `/Users/sreysus/Downloads/ma_events/`:

```sh
uv run tag-edgar ingest /Users/sreysus/Downloads/ma_events/ma_2022.csv \
  --column-map config/sdc_columns.toml \
  --metadata-rows 1
```

The normalized `deals_seed.csv` retains the original source row in a JSON column. CIK resolution
and filing retrieval are intentionally separate stages.

After adding your real SEC User-Agent to `.env`, create the review queue with:

```sh
uv run tag-edgar resolve-seed-ciks data/derived/deals_seed.csv
```

An exact ticker or name match is only a candidate. Review `entity_matches.csv` for both party
roles and change only manually confirmed rows to `confirmed` before using a CIK for retrieval.

## Creating the pilot review queue

First join the main SDC export, its supplemental export, and the CIK candidate rows. This preserves
the full source denominator and keeps `Form`, SIC codes, target public status, consideration
structure, values, and CIK confidence in separate columns:

```sh
uv run tag-edgar build-deal-catalog \
  data/derived/deals_seed.csv \
  /Users/sreysus/Downloads/ma_events/maadditional2022.csv \
  data/derived/entity_matches.csv
```

Then make a small, deterministic validation queue. `config/technology_sic.toml` applies a narrow,
versioned digital-technology target-SIC screen. The queue records the matching SIC and label on
every row, then balances public/non-public targets, merger/non-merger forms, and reported/missing
values. Within each group it prioritizes larger reported deals because this pilot tests retrieval;
it is not the final statistical sample.

```sh
uv run tag-edgar make-pilot-queue data/derived/deal_catalog.csv \
  --start 2021-01-01 --end 2022-12-31 --limit 20
```

After the pilot, inspect validation-sample readiness without freezing a sample or contacting SEC:

```sh
uv run tag-edgar preview-validation-sample data/derived/deal_catalog.csv \
  --limit 40 --exclude-deals-csv data/derived/pilot_review_queue.csv
```

This writes local, ignored eligibility and stratum diagnostics plus a deterministic candidate
preview. Every preview row remains `not_frozen`; sample freeze and retrieval are gated on supervisor
acceptance of the proposed deal-level unit of analysis. See
[`docs/validation_sample_preflight.md`](docs/validation_sample_preflight.md) for the prespecified
checks and interpretation limits.

For each chosen row, verify the acquirer CIK and, when the target is a public SEC registrant, the
target CIK. Decide whether the deal belongs in the supervisor-approved technology scope and set
the review columns deliberately:

| Column | Value to approve retrieval |
| --- | --- |
| `cik_manual_status` | `confirmed` |
| `target_cik_manual_status` | `confirmed` only after verifying `target_candidate_cik`; otherwise leave `pending` |
| `technology_scope_status` | `in_scope` |
| `pilot_status` | `selected` |

The batch command refuses every other row and writes each accepted deal to its own directory:

```sh
uv run tag-edgar run-reviewed-pilot data/derived/pilot_review_queue.csv
```

For approved public targets, the batch retrieves both filing histories and records
`acquirer_confirmed_cik` or `target_confirmed_cik` on each `deal_filings.csv` link. Unique SEC
accessions and documents are stored once, while the discovery route remains traceable. The run
summary reports acquirer-side, target-side, and deduplicated filing counts separately.

Create the audit table after retrieval:

```sh
uv run tag-edgar summarize-pilot \
  data/derived/pilot_review_queue.csv data/derived/pilot_runs
```

After human triage, include the manual coding table to produce one combined SDC-versus-SEC audit:

```sh
uv run tag-edgar summarize-pilot \
  data/derived/pilot_review_queue.csv data/derived/pilot_runs \
  --manual-coding-csv data/derived/pilot_manual_coding.csv
```

The manual coding CSV must contain one unique row per reviewed deal and these columns:

| Column | Required values |
| --- | --- |
| `deal_id` | A selected pilot deal ID |
| `manual_document_review_status` | `pending`, `in_progress`, `reviewed`, or `not_applicable` |
| `manual_evidence_review_status` | `pending`, `in_progress`, `reviewed`, or `not_applicable` |
| `manual_employee_term_code` | A documented coding label; non-empty for completed rows |
| `amount_or_named_package_publicly_disclosed` | `yes`, `no`, `unknown`, or `not_applicable` |
| `source_url` | The exact SEC document URL from that deal's `documents.csv` |
| `manual_review_status` | `pending`, `in_progress`, `triaged`, or `complete` |
| `manual_finding` | A concise, source-supported finding |

Rows marked `triaged` or `complete` must have completed document/evidence stages and a source URL
that resolves to a document retrieved for the same deal. Duplicate deal IDs, arbitrary URLs, and
manual rows for unselected deals are rejected.

`agreement_exhibit_found` and the `automated_*_hits` fields are discovery signals only. A keyword
hit does not establish a retention payment, an employee-specific term, or a legal protection; the
two `manual_*_review_status` columns exist to prevent that inference.

Evidence matching uses token boundaries, records every distinct occurrence with character offsets,
and prefers the longest configured phrase when patterns overlap at the same position.

## Employee-text topic pilot

Build the employee-related passage corpus from the same reviewed deals and cache. This command is
offline: a missing cached body is recorded in `document_texts.csv` instead of being downloaded.

```sh
uv run tag-edgar build-employee-corpus \
  data/derived/pilot_review_queue.csv data/derived/pilot_runs
```

The corpus output preserves canonical passages in `passages.csv` and every deal/document source
location in `passage_sources.csv`. It also assigns deterministic near-duplicate provision families
so repeated legal language does not count as independent document-family support. The build screens
out unrelated event-window communications and financial/safe-harbor contexts, records every
document decision in `document_eligibility.csv`, and validates manually positive sources in
`manual_source_validation.csv` when the pilot coding table is present. A positive source must
contribute at least one included passage or the build fails after writing the diagnostic. Passage
extraction is block-level by default (`--context-blocks 0`) so unrelated neighboring provisions do
not inherit an employee screen hit.

Prepare the prespecified offline relevance/recall audit before treating the screen as validated:

```sh
uv run tag-edgar prepare-corpus-relevance-audit \
  data/derived/employee_corpus/passages.csv
```

This writes a deterministic assessor-blinded packet and a separate private key, stratified across
inclusion decisions, deals, and document families. Its quality gate stays pending until every item
has a valid, explicitly human-attested label; the workflow never generates labels. After real
coding, run `score-corpus-relevance-audit` to report point rates and 95% Wilson intervals for the
included-passage relevance threshold (at least 90%) and excluded-candidate missed-content threshold
(strictly below 5%). See [`docs/corpus_relevance_audit.md`](docs/corpus_relevance_audit.md) for the
coding contract and full scoring command.

Run the deterministic topic model and diagnostics, then build the descriptive report:

```sh
uv run tag-edgar analyze-employee-topics \
  data/derived/pilot_review_queue.csv data/derived/employee_corpus

uv run tag-edgar summarize-employee-topics \
  data/derived/pilot_review_queue.csv \
  data/derived/employee_corpus data/derived/employee_topics
```

The analysis writes canonical and source-propagated assignments, a complete deal-topic matrix,
diagnostics, sensitivity/stability tables, a JSON manifest, and an SVG heatmap. The stability
artifacts include leave-one-deal-out results plus a prespecified 100-replicate fixed-seed bootstrap:
the existing deal-balanced fit universe is resampled by provision-family representative within
each deal, with replacement and each deal's fit-row count held constant. Components are aligned
one-to-one by cosine similarity; `bootstrap_stability.csv` records every replicate and
`bootstrap_summary.csv` reports per-topic recurrence, recovery share at cosine >= 0.70, and median
cosine. The bootstrap is a complementary robustness diagnostic, not a model-selection or
post-hoc relabeling rule. Deals without a stable assignment remain in the matrix with an explicit
zero state. The final Markdown report and `topic_review.csv` are interpretation aids; topic labels
still require human review.

For fit universes of this size, `embedding_robustness_assignments.csv` also records a local
passage-embedding check on exactly the same family-level fit rows. It uses fixed-seed normalized
TruncatedSVD (50-component maximum) over the fitted word/bigram TF-IDF matrix—LSA embeddings, not
transformer semantics—followed by prespecified sklearn HDBSCAN and cosine/average agglomerative
clustering. Coverage, noise, cluster counts, parameters, and ARI comparisons where defined appear
in `model_diagnostics.csv` and `analysis_manifest.json`; this check cannot alter the selected NMF
solution.

Prepare that review offline from the canonical analysis rows (not the source-propagated copies):

```sh
uv run tag-edgar prepare-employee-topic-review \
  data/derived/employee_topics/canonical_topic_assignments.csv \
  data/derived/employee_corpus/passages.csv
```

This writes a seeded manifest, a randomized `topic_review_packet.csv`, separate `reviewer_1.csv`
and `reviewer_2.csv` copies, and a private `topic_review_key.csv`. Give each reviewer only their
copy; keep the key from both reviewers until coding is complete. Actual topic IDs, model weights,
deal IDs, and source URLs are omitted from the coding packet. For every row, the reviewer supplies
one consistent `reviewer_id` and exactly one `fit_code`:

- `fit`: the passage substantively exemplifies the displayed theme terms;
- `partial`: related language is present, but the displayed theme is not the passage's main
  substance;
- `not_fit`: the passage does not substantively exemplify the displayed theme.

Only `fit` counts toward the prespecified 80% theme-fit gate. Do not edit `review_item_id` or
`blind_topic_id`. When the two reviewers have worked independently, score their files offline:

```sh
uv run tag-edgar score-employee-topic-review \
  data/derived/employee_topic_review/topic_review_key.csv \
  path/to/completed_reviewer_1.csv path/to/completed_reviewer_2.csv
```

The scorer rejects missing, duplicate, extra, blank, invalid, altered-key, or same-reviewer rows;
it never fills human codes. `topic_review_scores.csv` reports reviewer-specific and pooled fit and
partial rates, raw exact agreement, Cohen's kappa, and Gwet's AC1. Kappa is the agreement gate
unless its denominator is mathematically zero; only then is the disclosed AC1 fallback used.
`topic_review_diagnostics.csv` passes only with ten completed rows per topic, at least 80% `fit`
from each reviewer for every topic, at least 80% exact agreement, and an agreement coefficient of
at least 0.70 at both the topic and overall levels. The score manifest records the three input-file
hashes and all gate thresholds so the result can be reproduced without network access.

## Resumable 100-deal AI expansion

The expansion runner connects candidate screening, cached SEC retrieval, a target-linked document
gate, employee-corpus construction, fixed-seed NMF topics, sensitivity and stability checks,
document-family lexical baselines, tone and word-use tables, deterministic word clouds, and
source-linked Markdown reports:

~~~powershell
$env:SEC_USER_AGENT = "Researcher project-name real-contact@example.com"
.venv\Scripts\python.exe -m tag_edgar.overnight `
  --candidates data\derived\ai_100_candidate_preflight.csv `
  --raw-dir data\raw\ma_events `
  --out-dir data\derived\ai_100_overnight `
  --supplemental-sources config\ai_100_supplemental_sources.csv `
  --include-reserves
~~~

The run checkpoints to state.json and returns exit code 2 when it produces a valid partial package
but cannot reach the requested deal count. Candidate names and generic acquirer AI language never
establish inclusion by themselves. A qualifying machine row remains pending human review, and a
disclosed employee arrangement never establishes actual retention. After changing only deterministic
screening rules, add `--refresh --rescreen-cached` to reapply them to the existing target-linked
document cache. That mode also ingests newly approved supplemental-source rows without repeating
the SEC sweep.

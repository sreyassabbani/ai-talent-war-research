# Cycle-5 freeze state and human-assessor instructions

Status date: 2026-09-01. Branch `aarav/aug21-pilot-completion`.

## 1. What "cycle 5" is

Cycle 5 is the repaired passage-eligibility screen committed in `51281a4`
(`docs/corpus_screen_repair_cycle5.md`). Applied to the unchanged 5,550-passage screening universe
of the 10-deal pilot it produced, in the checkout where it was built:

| Artifact | Count |
| --- | ---: |
| Documents parsed / transaction-linked / excluded | 469 / 358 / 111 |
| Screened candidates included / excluded | 2,331 / 3,219 |
| Fresh blinded audit packet (included + excluded rows) | 75 + 75 |
| Packet status | `pending_human_labels` |

The historical cycle-4 audit remains a **failed** gate (72.0% included-passage relevance against a
90% threshold; 5.33% missed content against a <5% threshold; assessor `sreyas-sabbani`, 150/150
rows, 2026-08-26). Nothing in cycle 5 rescored or altered it.

## 2. What exists in this checkout, and what does not

`data/derived/` is git-ignored, so the corpus artifacts were never committed. In this checkout:

| Path | Present | Notes |
| --- | --- | --- |
| `data/derived/employee_corpus_cycle5/` | **no** | built only in the originating checkout |
| `data/derived/corpus_relevance_audit_cycle5/` | **no** | same |
| `data/derived/pilot_review_queue.csv`, `data/derived/pilot_runs/` | **no** | pilot inputs; human-confirmed CIK/scope columns |
| `cache/http/` for the 10 pilot deals | **no** | the local 409 MB cache holds the ai_100 expansion filers, not the pilot CIKs |
| Cycle-5 screen code + tests | yes | `51281a4` |
| Human-curated 10-deal source record | yes | `audit_salvage_2026-08-30/` (untracked) |

Consequently the cycle-5 corpus, its audit packet, the topic rerun, tone rerun, and the
architecture/topic cross-table **cannot be executed here** without first rebuilding the corpus.
Rebuilding needs (a) the pilot queue with its human-confirmed CIK and scope columns, and (b)
either the original `pilot_runs/` cache or a live SEC retrieval of the 469 documents under a real
`SEC_USER_AGENT` contact. Neither is something this workflow may reconstruct or fabricate.

The code paths for every downstream step were completed and tested against fixtures; the exact
commands are in §4 so the run is a single sequence once the corpus is present.

## 3. Freeze and hash-linking contract

When the cycle-5 corpus exists, its freeze is defined by these hashes, all of which the workflow
records automatically:

- `employee_corpus_cycle5/corpus_manifest.json` — document and passage counts and the screen
  version;
- `corpus_relevance_audit_cycle5/audit_manifest.json` — `candidate_csv_sha256` of the exact
  `passages.csv` sampled, packet and key hashes, `gate_status: pending`;
- every topic, tone, report, and cross-table manifest — `corpus_passages_sha256` /
  `passages_csv_sha256` plus a `corpus_validation` block.

`tag_edgar.corpus_validation` resolves the audit state against the hash of the corpus a downstream
artifact actually used. It also requires the score manifest to attest human labels for every
sampled row, and verifies the score-to-audit-manifest hash link whenever both are supplied. A
scored audit from a different `passages.csv` reports
`pending_human_corpus_validation` for this corpus rather than lending it a verdict. Until a scored,
passing audit is hash-linked:

- the report verdict is **WITHHELD** (never PASS);
- `report_manifest.json` and the workflow status say `pending_human_corpus_validation`
  (or `no_corpus_validation_evidence` if no packet was supplied);
- the tone manifest says `secondary_diagnostic_corpus_not_validated`;
- every cross-table row carries `corpus_validation_status`.

## 4. Exact commands

Run from the repository root with the project virtual environment. Every command is offline
except the one marked live.

### 4a. Rebuild the cycle-5 corpus (once the pilot inputs are present)

```powershell
# Requires data/derived/pilot_review_queue.csv and data/derived/pilot_runs/ from the original
# pilot, or a live rerun of `run-reviewed-pilot` with a real SEC_USER_AGENT (live; ~469 documents).
uv run tag-edgar build-employee-corpus `
  data/derived/pilot_review_queue.csv data/derived/pilot_runs `
  --output-dir data/derived/employee_corpus_cycle5 `
  --manual-coding-csv data/derived/pilot_manual_coding.csv
```

Expected: 469 parsed, 358 included, 111 excluded documents; 2,331 included and 3,219 excluded
candidates. A different count means the screen or inputs differ from cycle 5 and must be reported,
not reconciled silently.

### 4b. Prepare the blinded packet (deterministic)

```powershell
uv run tag-edgar prepare-corpus-relevance-audit `
  data/derived/employee_corpus_cycle5/passages.csv `
  --included-limit 75 --excluded-limit 75 `
  --output-dir data/derived/corpus_relevance_audit_cycle5
```

Give the assessor **only** `assessor_packet.csv`. Keep `private_key.csv` and
`audit_manifest.json` away from them until coding is locked.

### 4c. Human labelling (the only step a person performs)

For each of the 150 rows in `assessor_packet.csv`, fill exactly:

| Column | Enter |
| --- | --- |
| `relevance_label` | `relevant` if the passage substantively concerns how employees are treated in the transaction (pay, benefits, equity, retention, severance, employment terms, key-person continuity); otherwise `not_relevant` |
| `assessor_id` | your identifier, the same on every row |
| `assessor_note` | optional |
| `human_attestation` | `human_assessed` |

Do not reorder, add, remove, or edit any other cell. The scorer rejects altered packets and never
fills a label.

### 4d. Score (offline; refuses incomplete or non-attested labels)

```powershell
uv run tag-edgar score-corpus-relevance-audit `
  data/derived/corpus_relevance_audit_cycle5/private_key.csv `
  path/to/completed_assessor_packet.csv `
  data/derived/corpus_relevance_audit_cycle5/audit_manifest.json `
  --output-dir data/derived/corpus_relevance_scores_cycle5
```

Gate: included-passage relevance ≥ 0.90 **and** excluded-candidate missed content < 0.05 (point
rates; 95% Wilson intervals reported alongside). `score_manifest.json` records `gate_status`.

### 4e. Downstream reruns, each labelled by the audit state

```powershell
# Ordinary (deal-balanced) model, K in {3,4,5}
uv run tag-edgar analyze-employee-topics data/derived/pilot_review_queue.csv `
  data/derived/employee_corpus_cycle5 --output-dir data/derived/employee_topics_cycle5 `
  --seed 20260823 --k-min 3 --k-max 5 --fit-balance deal

# Source-family-balanced comparison
uv run tag-edgar analyze-employee-topics data/derived/pilot_review_queue.csv `
  data/derived/employee_corpus_cycle5 --output-dir data/derived/employee_topics_cycle5_sourcebal `
  --seed 20260823 --k-min 3 --k-max 5 --fit-balance source_family

# Unbalanced comparison
uv run tag-edgar analyze-employee-topics data/derived/pilot_review_queue.csv `
  data/derived/employee_corpus_cycle5 --output-dir data/derived/employee_topics_cycle5_nobal `
  --seed 20260823 --k-min 3 --k-max 5 --fit-balance none

# Report — verdict WITHHELD until 4d passes and is hash-linked
uv run tag-edgar summarize-employee-topics data/derived/pilot_review_queue.csv `
  data/derived/employee_corpus_cycle5 data/derived/employee_topics_cycle5 `
  --output-dir data/derived/employee_report_cycle5 --representative-limit 10 `
  --corpus-audit-dir data/derived/corpus_relevance_audit_cycle5 `
  --corpus-scores-dir data/derived/corpus_relevance_scores_cycle5

# Blinded two-reviewer topic packet (human fields blank)
uv run tag-edgar prepare-employee-topic-review `
  data/derived/employee_topics_cycle5/canonical_topic_assignments.csv `
  data/derived/employee_corpus_cycle5/passages.csv `
  --output-dir data/derived/employee_topic_review_cycle5

# Tone (secondary diagnostic)
uv run tag-edgar analyze-employee-tone data/derived/employee_corpus_cycle5/passages.csv `
  --output-dir data/derived/employee_tone_cycle5 `
  --corpus-audit-dir data/derived/corpus_relevance_audit_cycle5 `
  --corpus-scores-dir data/derived/corpus_relevance_scores_cycle5

# Deal architecture (offline, from the committed register) and the provisional cross-table
uv run tag-edgar build-deal-architecture
uv run tag-edgar build-architecture-topic-crosstable `
  data/derived/deal_architecture_pilot/deal_architecture.csv `
  data/derived/employee_topics_cycle5/deal_topic_matrix.csv `
  data/derived/employee_corpus_cycle5/passages.csv `
  --topic-assignments-csv data/derived/employee_topics_cycle5/topic_assignments.csv `
  --corpus-audit-dir data/derived/corpus_relevance_audit_cycle5 `
  --corpus-scores-dir data/derived/corpus_relevance_scores_cycle5 `
  --output-dir data/derived/architecture_topic_crosstable_cycle5
```

The agglomerative sensitivity check, leave-one-deal-out stability, and the fixed-seed bootstrap run
inside `analyze-employee-topics` and need no separate command.

### Historical topic-review provenance warning

The older `data/derived/employee_topic_review/reviewer_2.csv` and
`reviewer_2_muse-spark.csv` files contain AI-simulated coding. Despite legacy rows containing the
literal text `human_assessed`, they are **not human evidence**, must not be supplied to the scorer,
and cannot satisfy the two-independent-human-review gate. Cycle-5 review must start from the newly
generated blank reviewer files and be completed by two actual human reviewers.

## 5. What no one should do

- Do not copy the historical failed audit's labels onto the cycle-5 packet.
- Do not edit `gate_status`, `audit_status`, or any manifest hash by hand.
- Do not describe a WITHHELD report, a pending cross-table, or a tone table computed under
  `secondary_diagnostic_corpus_not_validated` as a result.

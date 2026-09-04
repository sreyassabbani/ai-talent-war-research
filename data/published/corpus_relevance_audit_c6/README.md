# Corpus relevance audit — cycle 6 packet

The blinded 150-row packet for the cycle-6 corpus, published here because the cycle-5 packet was
built only in the checkout that ran it and never reached a second reader. Nothing in this study is
a validated finding until this audit is scored.

Built 2026-09-04 from `data/derived/employee_corpus_c6/passages.csv`
(`sha256 e526dc02…`, recorded as `candidate_csv_sha256` in `audit_manifest.json`). That is the
corpus cycle 6 will publish, so what you score here is what gets reported.

## Why this packet is not the previous one

Cycle 5 scored a corpus with a defect in it. The relevance screen was reading the running header
as if it were the passage, so every real provision printed on a page headed "Table of Contents"
was discarded as an index entry — 6,855 of them. The screen now reads the passage body, and the
excluded pile fell from 6,855 navigation fragments to 331. A prior cycle-4 audit scored 72%
against a 90% bar; that result stands as a historical record of a different corpus and is not
carried forward.

## What to do

Each reviewer works on **their own copy** of `assessor_packet.csv`. Two independent complete
copies let us measure agreement between reviewers, which is the open question about whether the
coding scheme is reliable at all; splitting the 150 rows between you would answer the gate but
tell us nothing about that.

For every one of the 150 rows, fill in:

| Field | Required value |
| --- | --- |
| `relevance_label` | exactly `relevant` or `not_relevant` |
| `assessor_id` | a nonblank reviewer identifier, the same one on every row |
| `assessor_note` | optional free text |
| `human_attestation` | exactly `human_assessed` |

The question for each row is only: **is this passage relevant employee content?** Judge the text
in front of you. Do not try to infer whether the pipeline included or excluded it — the packet
deliberately omits the automated decision, the exclusion reason, the deal, the document family,
the passage id, and the source URL, and it is shuffled, so a guess about provenance is more likely
to bias you than to help.

Do not edit, reorder, add, or remove anything else. Scoring rejects an altered schema, missing or
duplicate ids, changed passage text, incomplete or invalid labels, blank assessor ids, or missing
attestations.

## What happens to the labels

```sh
tag-edgar score-corpus-relevance-audit \
  data/derived/corpus_relevance_audit_c6/private_key.csv \
  <your completed packet>.csv \
  data/derived/corpus_relevance_audit_c6/audit_manifest.json \
  --output-dir data/derived/corpus_relevance_scores_c6
```

Two prespecified gates, both set before the corpus was built:

- at least **90%** of sampled *included* passages are relevant employee content;
- fewer than **5%** of sampled *excluded* candidates contain missed relevant content.

The packet mixes 75 included and 75 excluded rows so both gates can be estimated at once. Which
row is which is exactly what is hidden from you.

## What is deliberately not here

`private_key.csv` holds the passage identities and the hidden automated decision. It stays out of
git while coding is open, because both reviewers can read this repository and the packet only
works while the decision is unknown to you. It is not at risk of being lost: selection is
deterministic for a fixed input checksum, seed, and limits, so the key regenerates exactly from
the same `passages.csv` with `--seed employee-corpus-relevance-v1 --included-limit 75
--excluded-limit 75`.

## Evidence boundary

A passing gate would mean the screen keeps the right passages. It would not make any topic,
theme, or count a statement about what happened to any employee — these are disclosed filing
terms, and the sample is selected by whether a buyer filed with the SEC.

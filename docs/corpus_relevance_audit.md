# Employee-corpus relevance and recall audit

This offline workflow audits the employee-passage screen against two prespecified point-estimate
gates:

- at least 90% of sampled included passages are relevant employee content;
- fewer than 5% of sampled excluded candidates contain missed relevant employee content.

The 95% Wilson intervals are uncertainty summaries. The prespecified gate itself uses the point
rates (`included >= 0.90` and `excluded < 0.05`). A prepared packet always reports the gate as
`pending`; only a completely labeled, human-attested packet can be scored. The program never
supplies, imputes, or guesses a human label.

## Prepare a blinded packet

Use the complete `passages.csv` produced by `build-employee-corpus`, which includes both included
and excluded screened candidates:

```sh
uv run tag-edgar prepare-corpus-relevance-audit \
  data/derived/employee_corpus/passages.csv \
  --included-limit 75 --excluded-limit 75 \
  --output-dir data/derived/corpus_relevance_audit
```

Selection is deterministic for a fixed input checksum, seed, and limits. Included and excluded
rows are sampled separately. Within each decision, round-robin selection across deal and document
family strata spreads the audit over independent source contexts; SHA-256 determines bucket,
within-bucket, and packet order without depending on input row order.

The output directory contains:

- `assessor_packet.csv`, containing only an opaque audit ID, randomized order, heading, passage
  text, and blank human-entry fields;
- `private_key.csv`, containing the passage/deal/document-family identities and the hidden automated
  inclusion decision;
- `audit_manifest.json`, recording the input checksum, method, sample counts, thresholds, packet
  checksum, and `gate_status: pending`.

Keep `private_key.csv` away from the assessor until coding is locked. The packet deliberately omits
the automated inclusion decision, exclusion reason, deal ID, document family, passage ID, and URL.

For every packet row, a human assessor must enter:

| Field | Required value |
| --- | --- |
| `relevance_label` | exactly `relevant` or `not_relevant` |
| `assessor_id` | a nonblank reviewer identifier |
| `assessor_note` | optional free text |
| `human_attestation` | exactly `human_assessed` |

Do not edit, reorder, add, or remove any other value or row. Scoring rejects an altered schema,
missing or duplicate IDs, changed passage content, incomplete labels, invalid labels, blank assessor
IDs, absent attestations, or a private key whose checksum no longer matches the preparation
manifest.

## Score completed human coding

```sh
uv run tag-edgar score-corpus-relevance-audit \
  data/derived/corpus_relevance_audit/private_key.csv \
  data/derived/corpus_relevance_audit/assessor_packet.csv \
  data/derived/corpus_relevance_audit/audit_manifest.json \
  --output-dir data/derived/corpus_relevance_scores
```

`audit_scores.csv` reports counts, point rates, and two-sided 95% Wilson intervals overall and by
deal and document family. For included rows, `relevant` is a relevance success. For excluded rows,
`relevant` is missed content and therefore an error. `score_manifest.json` records input checksums,
assessor IDs, thresholds, both component decisions, and the combined `pass` or `fail` gate.

Sample-size adequacy and interval width must be interpreted separately from the point-estimate gate.
If the available universe contains fewer candidates than requested, the manifest records both
requested and achieved counts rather than inventing candidates.

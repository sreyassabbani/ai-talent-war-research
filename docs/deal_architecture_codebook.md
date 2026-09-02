# Deal-architecture codebook (10-deal pilot)

This layer codes *what kind of transaction* each pilot deal was. It is separate from, and must
not be confused with, the unsupervised employee-language model:

| Layer | Question | Method | Unit |
| --- | --- | --- | --- |
| Deal architecture (this codebook) | What structure did the transaction take, and was talent an explicit motive? | Rule-based coding of source-backed attributes, then human review | one deal |
| Employee-treatment language | What recurring themes appear in employee-related passages? | Unsupervised TF-IDF/NMF over passages, aggregated to deals | one passage |

Assigning a deal to an archetype such as "acquihire" is manual or rule-based coding. It is not
unsupervised learning and is never described as such.

## Source of truth

`config/pilot_deal_architecture_evidence.csv` is the version-controlled evidence register: one row
per deal, attribute, and supporting source. `tag-edgar build-deal-architecture` validates it and
derives every output. Edit the register, rerun the command, and commit both; do not edit the
generated tables by hand.

Register columns:

| Column | Meaning |
| --- | --- |
| `attribute` | one of the six attributes below |
| `machine_value` | coded value; `\|` separates multiple values; `unknown` when the sources are silent |
| `evidence_basis` | `direct_passage` (a reviewed passage states it), `inferred_from_legal_form` (follows from the agreement type, no passage), or `unknown` |
| `evidence_status` | `direct`, `partial`, `indirect`, or `unknown` — the project's standard incentive-evidence scale |
| `document_id`, `source_url`, `source_locator` | the document and section the claim rests on; required for every non-unknown value |
| `excerpt_kind` | `verbatim` (quoted from the document) or `paraphrase` (a curated summary) |
| `evidence_excerpt` | the supporting text |
| `limitation` | what the excerpt cannot establish |
| `salvage_reference` | provenance back to `audit_salvage_2026-08-30/` |

A highlight URL (`#:~:text=`) is generated only for `verbatim` excerpts. Paraphrases receive
`highlight_status = unsupported_paraphrase_not_quotable` and keep the canonical URL. The current
register is transcribed from the human-curated salvage package, whose excerpts are paraphrases;
replacing them with verbatim quotes once the pilot documents are retrieved will populate the
highlight URLs without any other change.

## Attributes

### `legal_transaction_form`

The agreement type as filed: `statutory_merger`, `equity_purchase`, `asset_purchase`,
`tender_offer_then_back_end_merger`, `equity_purchase_and_merger`, or
`transaction_agreement_form_not_asserted` where the record deliberately does not assert one.

### `scope_and_control`

What moved and whether control moved. Values combine with `|`:
`entity_equity`, `business_unit_assets`, `control_transferred`,
`control_of_purchased_assets_only`, `no_control_transfer`, `unknown`.

### `ip_treatment`

`acquired_with_entity`, `acquired_with_assets_scope_not_verified`, `licensed`,
`retained_by_seller`, `unknown`. For the pilot every value is inferred from legal form; no
reviewed passage addresses IP directly.

### `business_product_continuity`

`continues_as_unit_within_buyer_segment`, `continues_independently`, `integrated`,
`discontinued`, `unknown`. Only Microsoft–Nuance has a direct passage (an announcement of intended
structure, which is not an observation of later reality).

### `workforce_movement`

Who is addressed by the reviewed passages: `group_continuing_employees`,
`defined_transferred_employee_group`, `group_severance_and_retention_liabilities`,
`named_founders`, `named_founders_and_key_employees`, `named_executive_continuity`,
`officers_and_key_employees_pre_closing`, `none_disclosed`, `unknown`. A named person in a
contract is a contract role, not an observed post-deal role.

### `talent_motive_explicit`

Whether a reviewed passage states that acquiring people or a team was a transaction motive:
`yes`, `partial` (people-specific deal terms such as founder offer letters as closing
conditions, but no stated motive), `no`, `unknown`. Absence of a statement is not evidence of
absence.

## Archetype suggestions (`deal-architecture-rules-v1`)

| Condition | Suggested archetype(s) | Ambiguity |
| --- | --- | --- |
| scope unknown | `unknown` | high |
| no control transfer, IP licensed, people moved | `hire_and_license`, `reverse_acquihire` | medium |
| no control transfer otherwise | `mixed` | high |
| control moved, talent motive `yes`, product discontinued | `traditional_acquihire` | low |
| control moved, talent motive `yes` or `partial` | base + `acquisition_with_talent_emphasis` | medium |
| control moved, named people, no motive | base | medium |
| control moved, motive unknown | base | medium |
| control moved, motive `no` | base | low |

`base` is `asset_acquisition` when `business_unit_assets` is in scope and `full_acquisition`
otherwise. Every suggestion is written with `review_status =
machine_suggested_pending_human_review` and a `competing_interpretations` sentence. The three
human columns (`human_final_archetype`, `human_reviewer_id`, `human_review_note`) are always
blank in generated output.

## What the pilot shows about itself

All ten pilot deals are control-transferring acquisitions (nine entity acquisitions and one
business-unit asset purchase). None is a license-and-hire or reverse-acquihire structure, and no
reviewed passage states a talent motive. The architecture layer therefore has little variation to
cross against employee-language topics; that is a property of the pilot sample, not a result.

## Outputs

`data/derived/deal_architecture_pilot/`:

- `deal_architecture.csv` — one row per deal with attributes, evidence bases, suggestions,
  ambiguity, competing interpretations, evidence counts, and blank human fields;
- `deal_architecture_evidence.csv` — one row per attribute with the excerpt, canonical URL,
  highlight URL or its unsupported status, and limitation;
- `architecture_manifest.json` — register hash, output hashes, rule version, counts, and the
  interpretation boundary.

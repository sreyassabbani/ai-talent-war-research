# Validation-sample preflight (not frozen)

## Status and decision gate

This workflow produces a **candidate preview only**. It does not freeze a sample, initiate SEC
retrieval, or imply supervisor acceptance. Its proposed unit of analysis is:

> one SDC/LSEG deal event keyed by `deal_id`

The sample must remain `not_frozen` and external retrieval must remain blocked until the supervisor
accepts or revises that unit. Before a freeze, the supervisor should explicitly decide whether the
unit is instead an acquirer-target pair, filing event, document, or passage and whether multiple
SDC records for related transactions should be consolidated.

## Read-only eligibility preview

The preflight reads the local, ignored licensed catalog and applies these reproducible checks in
order:

1. nonblank, unique `deal_id`;
2. exclusion of every deal already placed in the pilot review queue;
3. valid ISO announcement date;
4. target SIC included by the versioned technology screen;
5. nonblank acquirer CIK candidate with `high` or `medium` automated match confidence.

The CIK condition is a retrieval-readiness screen, not manual identity confirmation. A later frozen
sample would still require deliberate entity review before retrieval. The preflight does not use
pilot outcomes, employee-passage results, or topic assignments to choose candidates.

## Deterministic preview and strata

The requested preview must contain 30–50 candidates (default 40). Eligible cases are grouped by:

- announcement year;
- public, non-public, or unknown target status;
- merger versus non-merger transaction form;
- reported, missing, or invalid transaction value.

Within each cross-stratum, candidates are ordered by `SHA-256(seed:deal_id)`. A lexicographic
round-robin across available strata creates the preview. This is a balanced design diagnostic, not
a probability sample and not evidence that the strata are supervisor-approved.

## Local artifacts

`preview-validation-sample` writes four ignored, derived artifacts:

- `sample_preview.csv`: candidate rows, each marked `not_frozen` with the supervisor gate pending;
- `eligibility_diagnostics.csv`: aggregate included/excluded counts and reasons;
- `stratum_diagnostics.csv`: eligible-universe and preview counts/shares by marginal and joint
  strata;
- `preflight_manifest.json`: input checksum, logical row counts, selection seed and method, screen
  version, and machine-readable freeze/retrieval gates.

No raw catalog is copied into the repository. Physical CSV line counts are reported separately from
logical CSV deal rows because quoted source fields may contain embedded newlines; a physical line
count must not be described as the number of deals.

## Acceptance checks before any later freeze

- Supervisor accepts the unit of analysis in writing.
- The logical catalog denominator and any physical-line discrepancy are reconciled.
- Technology-scope rules and validation estimands are fixed.
- Prior-pilot exclusion policy is accepted.
- Strata and target counts are accepted, including sparse public-target strata.
- Acquirer/target entity-review requirements are fixed.
- A future freeze artifact uses a new command and immutable manifest; this preview command cannot
  declare acceptance or start retrieval.

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

4. Run one vertical slice using a *manually confirmed* public-acquirer CIK:

   ```sh
   uv run tag-edgar vertical-slice \
     --deal-id example-001 \
     --acquirer-cik 789019 \
     --announcement 2024-01-10 \
     --effective 2024-04-10 \
     --target-name "Example Target"
   ```

The command writes normalized `deals.csv`, `filings.csv`, `deal_filings.csv`, `documents.csv`,
and `evidence.csv` under `data/derived/vertical_slice/`. `deal_filings.csv` and `evidence.csv`
are review queues, not verified datasets.

Read [PLAN.md](PLAN.md) for the full research and implementation plan.

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

An exact ticker or name match is only a candidate. Review `entity_matches.csv` and change only
manually confirmed rows to `confirmed` before passing a CIK to `vertical-slice`.

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

For each chosen row, verify the acquirer CIK, decide whether it belongs in the supervisor-approved
technology scope, and set these three columns deliberately:

| Column | Value to approve retrieval |
| --- | --- |
| `cik_manual_status` | `confirmed` |
| `technology_scope_status` | `in_scope` |
| `pilot_status` | `selected` |

The batch command refuses every other row and writes each accepted deal to its own directory:

```sh
uv run tag-edgar run-reviewed-pilot data/derived/pilot_review_queue.csv
```

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

`agreement_exhibit_found` and the `automated_*_hits` fields are discovery signals only. A keyword
hit does not establish a retention payment, an employee-specific term, or a legal protection; the
two `manual_*_review_status` columns exist to prevent that inference.

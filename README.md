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

The command writes normalized `deals.csv`, `filings.csv`, `documents.csv`, and `evidence.csv`
under `data/derived/vertical_slice/`. `evidence.csv` is a review queue, not a verified dataset.

Read [PLAN.md](PLAN.md) for the full research and implementation plan.

## Ingesting the SDC/LSEG export

Do not edit the licensed export. Copy [config/sdc_columns.example.toml](config/sdc_columns.example.toml),
replace its values with the real column names, then run:

```sh
uv run tag-edgar ingest data/raw/your-export.csv --column-map config/sdc_columns.toml
```

The normalized `deals_seed.csv` retains the original source row in a JSON column. CIK resolution
and filing retrieval are intentionally separate stages.

# Initial Jobless Claims Pipeline

This pipeline builds a standardized dataset for US initial jobless claims.

## What it does

- Pulls latest weekly `ICSA` from FRED into `data/raw/fred/fred_icsa_latest.csv`
- Stores timestamped raw snapshots from FRED in `data/raw/fred/`
- Ingests any manual MacroMicro CSV exports placed in `data/raw/macromicro/`
- Builds a unified processed dataset:
  - CSV: `data/processed/initial_jobless_claims.csv`
  - SQLite: `data/processed/initial_jobless_claims.sqlite`

## Folder layout

- `scripts/fetch_fred_initial_claims.py`
- `scripts/build_initial_claims_dataset.py`
- `scripts/run_weekly_refresh.sh`
- `data/raw/macromicro/` (put MacroMicro downloaded CSV here)
- `data/raw/fred/`
- `data/processed/`

## Quick start

```bash
cd /Users/freedom33/Documents/New\ project
bash data_pipeline/initial_jobless_claims/scripts/run_weekly_refresh.sh
```

## Manual MacroMicro import

1. Open the page and download CSV from MacroMicro.
2. Save CSV into:
   - `data_pipeline/initial_jobless_claims/data/raw/macromicro/`
3. Re-run weekly script:

```bash
bash data_pipeline/initial_jobless_claims/scripts/run_weekly_refresh.sh
```

## Standardized schema

- `date` (ISO date)
- `value` (float)
- `series_code`
- `series_name`
- `unit`
- `frequency`
- `seasonal_adjustment`
- `source` (`fred` or `macromicro`)
- `ingested_at` (UTC timestamp)
- `version_hash`

## Notes

- MacroMicro CSV column names may vary; the ingester auto-detects common date/value headers.
- If a MacroMicro CSV has unfamiliar headers, update candidate fields in `build_initial_claims_dataset.py`.

## Local dashboard

A local interactive chart page is available at:

- `dashboard/index.html`

Run:

```bash
cd /Users/freedom33/Documents/New\ project
bash data_pipeline/initial_jobless_claims/dashboard/run_local_dashboard.sh 8787
```

Open in browser:

- `http://127.0.0.1:8787/dashboard/`

## Public publish (GitHub Pages)

This repo includes a ready workflow to publish the dashboard for external users:

- Workflow file: `.github/workflows/initial-jobless-dashboard-pages.yml`
- Build script: `data_pipeline/initial_jobless_claims/scripts/prepare_public_site.py`
- Publish artifact dir: `data_pipeline/initial_jobless_claims/public_site/`

### One-time setup

1. Push this repository to GitHub.
2. In GitHub repository settings, enable **Pages** and set source to **GitHub Actions**.

### Publish / update

1. Update your local data (if needed).
2. Commit and push changes to `main` (or `master`).
3. The workflow will auto-deploy and provide a public URL in Actions logs.

You can also trigger deployment manually from Actions with `workflow_dispatch`.

# CivicLens Cook County

Public civic transparency database + MCP server. Enter any Cook County address → see every layer of local government you live under, who represents you, where the money goes, and what's on the next agenda.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in DATABASE_URL (Supabase → Settings → Database)
```

Enable PostGIS in Supabase: Dashboard → Database → Extensions → `postgis`.

## Load data

Fixture mode (no downloads needed — approximate boundaries, fake finances):

```bash
cd ingest
python tiger_loader.py --fixtures
python comptroller_loader.py --fixtures
```

Real data (see Build Spec §6 for sources):

```bash
python tiger_loader.py --cousub data/tl_2024_17_cousub.zip --place data/tl_2024_17_place.zip
python comptroller_loader.py --csv data/afr_export.csv
```

## Run API

```bash
uvicorn api.main:app --reload
```

| Endpoint | Purpose |
|---|---|
| `GET /governments?address=...` | Address → all containing units |
| `GET /units?type=township&query=...` | List/search units |
| `GET /units/{id}` | Unit profile + coverage flags |
| `GET /units/{id}/finances?years_back=3` | AFR summaries, per-capita |
| `GET /compare?unit_ids=a,b&metric=per_capita_expenditures` | Compare units |
| `GET /freshness` | Per-table as_of dates |

Every response carries a `provenance` block: `{source_url, as_of, certainty, note?}`.

## Data certainty levels

- `verified` — from official filing, human-checked
- `extracted` — parsed from PDF, may contain errors
- `stale_risk` — older than its expected update cycle

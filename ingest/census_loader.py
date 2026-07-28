"""Load Census ACS population and context figures for every unit.

Fills the population gap (149 of 178 units had none) and adds the context
needed to read per-capita spending honestly — $170/resident in a wealthy
township means something different than in a poor one.

Two geographies cover the whole dataset:
  municipalities -> place, in state:17
  townships      -> county subdivision, in state:17 county:031

Requires CENSUS_API_KEY in .env (free: https://api.census.gov/data/key_signup.html).

    python census_loader.py --dry-run
    python census_loader.py
    python census_loader.py --year 2023
"""
import argparse
import datetime as dt
import os
import re
import sys

import httpx

from db import apply_schema, connect

BASE = "https://api.census.gov/data/{year}/acs/acs5"
SOURCE_URL = "https://www.census.gov/programs-surveys/acs"
DEFAULT_YEAR = 2023

VARIABLES = {
    "B01003_001E": "population",
    "B19013_001E": "median_income",
    "B17001_002E": "poverty_count",
    "B25001_001E": "housing_units",
}

# Census suppresses small-sample estimates with large negative sentinels.
SUPPRESSED = -666666666


def norm(name: str) -> str:
    """Strip the Census entity suffix so 'Berwyn city, Illinois' == 'Berwyn'."""
    name = name.split(",")[0]
    name = re.sub(r"\b(city|village|town|CDP|township|borough)\b", "", name, flags=re.I)
    return re.sub(r"[^a-z0-9]", "", name.lower())


def to_int(v):
    if v in (None, "", "null"):
        return None
    n = int(float(v))
    return None if n <= SUPPRESSED else n


def fetch(year: int, key: str, geo: str, scope: dict) -> list[dict]:
    """One ACS call. httpx encodes params, which matters: a raw '*' or the
    space in 'county subdivision' makes the API answer 'Invalid Key' — an
    error that points at the wrong thing entirely."""
    params = {
        "get": "NAME," + ",".join(VARIABLES),
        "for": f"{geo}:*",
        "key": key,
        **scope,
    }
    r = httpx.get(BASE.format(year=year), params=params, timeout=90, follow_redirects=True)
    if r.status_code != 200 or not r.text.lstrip().startswith("["):
        raise SystemExit(f"Census API error for {geo}: HTTP {r.status_code} — {r.text[:200]}")
    rows = r.json()
    header = rows[0]
    out = []
    for row in rows[1:]:
        rec = dict(zip(header, row))
        out.append({
            "name": rec["NAME"],
            **{field: to_int(rec[var]) for var, field in VARIABLES.items()},
        })
    return out


def load(conn, year: int, dry_run: bool):
    key = os.environ.get("CENSUS_API_KEY")
    if not key:
        raise SystemExit("CENSUS_API_KEY not set — add it to .env")

    places = fetch(year, key, "place", {"in": "state:17"})
    cousub = fetch(year, key, "county subdivision", {"in": "state:17 county:031"})
    print(f"fetched {len(places)} IL places, {len(cousub)} Cook county subdivisions")

    index = {"municipality": {}, "township": {}, "county": {}}
    for rec in places:
        index["municipality"].setdefault(norm(rec["name"]), rec)
    for rec in cousub:
        index["township"].setdefault(norm(rec["name"]), rec)

    units = conn.execute("select id, name, type, population from units order by type, name").fetchall()
    vintage = f"ACS {year} 5-year"
    today = dt.date.today()
    matched, unmatched, changed = 0, [], 0

    for u in units:
        if u["type"] == "county":
            rec = {"name": "Cook County, Illinois"}
            r = httpx.get(
                BASE.format(year=year),
                params={"get": "NAME," + ",".join(VARIABLES), "for": "county:031",
                        "in": "state:17", "key": key},
                timeout=60, follow_redirects=True,
            )
            row = dict(zip(r.json()[0], r.json()[1]))
            rec |= {f: to_int(row[v]) for v, f in VARIABLES.items()}
        else:
            rec = index[u["type"]].get(norm(u["name"]))

        if not rec:
            unmatched.append(u)
            continue

        matched += 1
        if u["population"] != rec["population"]:
            changed += 1
        if dry_run:
            if changed <= 8 and u["population"] != rec["population"]:
                print(f"  {u['name']:30s} {str(u['population'] or '—'):>9s} -> {rec['population']}")
            continue

        conn.execute(
            """insert into unit_demographics
                 (unit_id, population, median_income, poverty_count, housing_units,
                  vintage, source_url, as_of)
               values (%s,%s,%s,%s,%s,%s,%s,%s)
               on conflict (unit_id) do update set
                 population=excluded.population,
                 median_income=excluded.median_income,
                 poverty_count=excluded.poverty_count,
                 housing_units=excluded.housing_units,
                 vintage=excluded.vintage,
                 source_url=excluded.source_url,
                 as_of=excluded.as_of""",
            (u["id"], rec["population"], rec["median_income"], rec["poverty_count"],
             rec["housing_units"], vintage, SOURCE_URL, today),
        )
        # units.population is the display value; rewrite it so every unit is
        # on one vintage rather than a mix that gets compared per-capita.
        conn.execute("update units set population=%s where id=%s", (rec["population"], u["id"]))

    print(f"\nmatched {matched}/{len(units)} units ({vintage}), {changed} population values changed")

    if unmatched:
        print(f"\nUNMATCHED ({len(unmatched)}) — these would silently lose population:")
        for u in unmatched:
            print(f"  {u['type']:14s} {u['id']:34s} {u['name']}")
        raise SystemExit("refusing to continue with unmatched units; fix the name mapping first")

    if not dry_run:
        conn.commit()
        print("committed")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=DEFAULT_YEAR)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = connect()
    apply_schema(conn)
    load(conn, args.year, args.dry_run)


if __name__ == "__main__":
    main()

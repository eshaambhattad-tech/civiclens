"""Load Cook County township officials directly from Cook County Clerk Socrata API.

No CSV download needed — pulls live from the public API.

    python officials_api_loader.py              # load all
    python officials_api_loader.py --dry-run    # preview
"""
import argparse
import datetime as dt
import re

import httpx
from db import apply_schema, connect

API_URL = "https://datacatalog.cookcountyil.gov/resource/jsup-zs8y.json"
SOURCE_URL = "https://datacatalog.cookcountyil.gov/d/jsup-zs8y"
NEXT_CONSOLIDATED_ELECTION = dt.date(2027, 4, 6)

ROLE_MAP = {
    "supervisor": "supervisor",
    "trustee": "trustee",
    "clerk": "clerk",
    "assessor": "assessor",
    "highway commissioner": "highway_commissioner",
    "collector": "collector",
}


def fetch_officials():
    r = httpx.get(
        API_URL,
        params={
            "$where": "jurisdiction like '%Township%'",
            "$limit": 5000,
            "$order": "jurisdiction,office",
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def load(dry_run=False):
    conn = connect()
    apply_schema(conn)

    township_ids = {}
    for row in conn.execute("select id, name from units where type='township'").fetchall():
        township_ids[row["name"].lower()] = row["id"]

    records = fetch_officials()
    print(f"fetched {len(records)} records from Socrata API")

    today = dt.date.today()
    n, skipped = 0, 0
    seen_units = set()
    loaded_by_unit = {}

    for rec in records:
        jurisdiction = (rec.get("jurisdiction") or "").strip()

        # Skip school districts, trustees of schools, libraries, treasurers
        if any(x in jurisdiction.lower() for x in ["school", "library", "treasurer"]):
            continue

        uid = township_ids.get(jurisdiction.lower())
        if not uid:
            skipped += 1
            continue

        role = ROLE_MAP.get((rec.get("office") or "").strip().lower())
        if not role:
            continue

        name_parts = [rec.get("first_name"), rec.get("middle_name"), rec.get("last_name")]
        name = " ".join(p.strip() for p in name_parts if p and p.strip())
        name = re.sub(r"\s+", " ", name).strip()
        if not name:
            continue

        email = (rec.get("email") or "").strip() or None
        phone = (rec.get("phone") or "").strip() or None
        website = None
        if rec.get("website") and isinstance(rec["website"], dict):
            website = rec["website"].get("url")

        if dry_run:
            print(f"  {uid:40s} {role:25s} {name}")
            loaded_by_unit.setdefault(uid, []).append(name)
            n += 1
            continue

        if uid not in seen_units:
            conn.execute("delete from officials where unit_id=%s and source_url=%s", (uid, SOURCE_URL))
            if website:
                conn.execute("update units set website=coalesce(website,%s) where id=%s", (website, uid))
            seen_units.add(uid)

        conn.execute(
            """insert into officials (unit_id, role, name, email, phone, term_end, certainty, source_url, as_of)
               values (%s,%s,%s,%s,%s,%s,'extracted',%s,%s)""",
            (uid, role, name, email, phone, NEXT_CONSOLIDATED_ELECTION, SOURCE_URL, today),
        )
        loaded_by_unit.setdefault(uid, []).append(name)
        n += 1

    if not dry_run:
        conn.commit()

    print(f"\n{'would load' if dry_run else 'loaded'} {n} officials across {len(loaded_by_unit)} townships")
    if skipped:
        print(f"skipped {skipped} records (no matching unit)")

    print("\nPer-unit breakdown:")
    for uid in sorted(loaded_by_unit):
        print(f"  {uid:40s} {len(loaded_by_unit[uid]):3d} officials")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    load(ap.parse_args().dry_run)

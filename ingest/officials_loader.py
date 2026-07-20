"""Load Cook County Clerk elected-officials directory CSV into `officials`.

Source: datacatalog.cookcountyil.gov dataset jsup-zs8y.
v1 scope: township officials only (municipalities are Phase 2).

    python officials_loader.py --csv path/to/directory.csv
"""
import argparse
import csv
import datetime as dt
import re

from db import apply_schema, connect

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


def load(conn, path):
    township_ids = {
        name.lower(): uid
        for uid, name in conn.execute("select id, name from units where type='township'").fetchall()
    }
    today = dt.date.today()
    n, skipped_roles = 0, set()
    seen_units = set()
    with open(path) as f:
        for row in csv.DictReader(f):
            j = (row["Jurisdiction"] or "").strip()
            uid = township_ids.get(j.lower())
            if not uid:
                continue
            role = ROLE_MAP.get(row["Office"].strip().lower())
            if not role:
                skipped_roles.add(row["Office"].strip())
                continue
            if uid not in seen_units:
                conn.execute("delete from officials where unit_id=%s and source_url=%s", (uid, SOURCE_URL))
                if row.get("Website"):
                    conn.execute("update units set website=coalesce(website,%s) where id=%s",
                                 (row["Website"].strip(), uid))
                seen_units.add(uid)
            name = " ".join(p for p in (row["First Name"], row["Middle Name"], row["Last Name"]) if p and p.strip())
            name = re.sub(r"\s+", " ", name).strip()
            conn.execute(
                """
                insert into officials (unit_id, role, name, email, phone, term_end, certainty, source_url, as_of)
                values (%s,%s,%s,%s,%s,%s,'extracted',%s,%s)
                """,
                (uid, role, name, (row.get("Email") or "").strip() or None,
                 (row.get("Phone") or "").strip() or None,
                 NEXT_CONSOLIDATED_ELECTION, SOURCE_URL, today),
            )
            n += 1
    conn.commit()
    print(f"loaded {n} officials across {len(seen_units)} townships")
    if skipped_roles:
        print(f"skipped offices (not township government roles): {sorted(skipped_roles)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    conn = connect()
    apply_schema(conn)
    load(conn, ap.parse_args().csv)

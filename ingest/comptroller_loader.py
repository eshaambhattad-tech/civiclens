"""Load IL Comptroller AFR data into `afr_summaries`.

Real data: the Comptroller Financial Databases bulk export (Excel/Access).
Export/convert to CSV first, then run:
    python comptroller_loader.py --csv path/to/afr.csv

Expected CSV columns (rename in --map if the export differs):
    unit_name, ioc_code, fiscal_year, total_revenues, total_expenditures,
    fund_balance, total_debt, filed_on_time, source_url
Optional: fund_detail (JSON string of per-fund rev/exp).

Fixture mode: --fixtures loads ingest/fixtures/afr.csv.
"""
import argparse
import csv
import json
import os

from db import apply_schema, connect

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "afr.csv")


def to_num(v):
    if v in (None, "", "NA"):
        return None
    return float(str(v).replace(",", "").replace("$", ""))


def load_csv(conn, path):
    n, skipped = 0, []
    with open(path) as f:
        for row in csv.DictReader(f):
            unit_id = row.get("unit_id") or match_unit(conn, row)
            if not unit_id:
                skipped.append(row.get("unit_name"))
                continue
            if row.get("ioc_code"):
                conn.execute("update units set ioc_code=%s where id=%s", (row["ioc_code"], unit_id))
            conn.execute(
                """
                insert into afr_summaries
                  (unit_id, fiscal_year, total_revenues, total_expenditures,
                   fund_balance, total_debt, fund_detail, filed_on_time, source_url)
                values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                on conflict (unit_id, fiscal_year) do update set
                  total_revenues=excluded.total_revenues,
                  total_expenditures=excluded.total_expenditures,
                  fund_balance=excluded.fund_balance,
                  total_debt=excluded.total_debt,
                  fund_detail=excluded.fund_detail,
                  filed_on_time=excluded.filed_on_time,
                  source_url=excluded.source_url
                """,
                (
                    unit_id,
                    int(row["fiscal_year"]),
                    to_num(row.get("total_revenues")),
                    to_num(row.get("total_expenditures")),
                    to_num(row.get("fund_balance")),
                    to_num(row.get("total_debt")),
                    row.get("fund_detail") or None,
                    str(row.get("filed_on_time", "")).lower() in ("true", "1", "yes", "y"),
                    row.get("source_url") or "https://illinoiscomptroller.gov/financial-reports-data/data-sets-portals/local-government-financial-databases",
                ),
            )
            n += 1
    if skipped:
        print(f"skipped {len(skipped)} rows with no matching unit: {sorted(set(skipped))[:10]}")
    return n


def match_unit(conn, row):
    if row.get("ioc_code"):
        r = conn.execute("select id from units where ioc_code=%s", (row["ioc_code"],)).fetchone()
        if r:
            return r[0]
    name = (row.get("unit_name") or "").strip()
    if not name:
        return None
    r = conn.execute(
        "select id from units where lower(name)=lower(%s) order by type limit 1", (name,)
    ).fetchone()
    return r[0] if r else None


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures", action="store_true")
    ap.add_argument("--csv")
    args = ap.parse_args()

    conn = connect()
    apply_schema(conn)
    n = load_csv(conn, FIXTURES if args.fixtures else args.csv)
    conn.commit()
    print(f"loaded {n} AFR rows")

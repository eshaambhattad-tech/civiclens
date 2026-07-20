"""Load IL Comptroller Financial Database (.accdb) into afr_summaries.

Requires mdbtools (`brew install mdbtools`).
Accepts multiple accdb files to build a multi-year dataset:

    python ioc_loader.py --accdb ~/Downloads/data2023.accdb ~/Downloads/data2024.accdb ~/Downloads/data2025.accdb
"""
import argparse
import csv
import datetime as dt
import io
import json
import subprocess
from collections import defaultdict

from chart_of_accounts import FUND_LABELS, label_category, label_fund
from db import apply_schema, connect

FUND_COLS = ["GN", "SR", "CP", "DS", "EP", "TS", "FD", "DP", "OT"]
SOURCE_URL = "https://illinoiscomptroller.gov/financial-reports-data/data-sets-portals/local-government-financial-databases"


def export(accdb, table):
    out = subprocess.run(["mdb-export", accdb, table], capture_output=True, text=True, check=True)
    return list(csv.DictReader(io.StringIO(out.stdout)))


def sum_funds(row):
    return sum(float(row[c]) for c in FUND_COLS if row.get(c) not in (None, ""))


def by_fund_labeled(rows):
    agg = defaultdict(float)
    for r in rows:
        for c in FUND_COLS:
            if r.get(c) not in (None, ""):
                agg[label_fund(c)] += float(r[c])
    return {k: v for k, v in agg.items() if v}


def by_category_labeled(rows, is_revenue):
    return {label_category(r["Category"], is_revenue): sum_funds(r) for r in rows if sum_funds(r)}


def load(accdb_paths):
    conn = connect()
    apply_schema(conn)

    all_units = {}
    all_revs, all_exps, all_fbs = [], [], []
    all_audits = defaultdict(list)
    all_stats = {}

    for accdb in accdb_paths:
        print(f"reading {accdb}...")
        units = export(accdb, "UnitData")
        cook = {u["Code"]: u for u in units if u["County"] == "Cook"}
        all_units.update(cook)

        for r in export(accdb, "UnitStats"):
            if r["Code"] in cook:
                all_stats[r["Code"]] = r

        for r in export(accdb, "Audits"):
            if r["Code"] in cook and r.get("Deleted") != "Y":
                all_audits[(r["Code"], r["FY"])].append(r)

        for table, dest in [("Revenues", all_revs), ("Expenditures", all_exps), ("FundBalances", all_fbs)]:
            dest.extend(r for r in export(accdb, table) if r["Code"] in cook)

    id_by_code = {}
    for code, u in all_units.items():
        if u["C1"] == "TW":
            uid = "cook-" + u["UnitName"].lower().replace(" ", "-").replace(".", "") + "-township"
        elif u["Description"] == "County" and u["UnitName"] == "Cook":
            uid = "cook-county"
        else:
            continue
        r = conn.execute("select 1 from units where id=%s", (uid,)).fetchone()
        if r:
            id_by_code[code] = uid
            conn.execute("update units set ioc_code=%s where id=%s", (code, uid))

    for code, r in all_stats.items():
        if code in id_by_code and r.get("Pop"):
            conn.execute("update units set population=%s where id=%s",
                         (int(float(r["Pop"])), id_by_code[code]))

    # filter to matched units
    revs = [r for r in all_revs if r["Code"] in id_by_code]
    exps = [r for r in all_exps if r["Code"] in id_by_code]
    fbs = [r for r in all_fbs if r["Code"] in id_by_code]

    def t_rows(rows, code, fy):
        return [r for r in rows if r["Code"] == code and r["FY"] == fy and r["Category"].endswith("t")]

    fys = sorted({r["FY"] for r in revs} | {r["FY"] for r in exps})
    n = 0
    for code, uid in id_by_code.items():
        for fy in fys:
            rv, ex = t_rows(revs, code, fy), t_rows(exps, code, fy)
            if not rv and not ex:
                continue
            fb = [r for r in fbs if r["Code"] == code and r["FY"] == fy and r["Category"] == "307t"]
            filed_on_time = None
            for a in all_audits.get((code, fy), []):
                if a.get("FYEnd") and a.get("RecDate"):
                    fy_end = dt.date.fromisoformat(a["FYEnd"][:10])
                    rec = dt.date.fromisoformat(a["RecDate"][:10])
                    filed_on_time = rec <= fy_end + dt.timedelta(days=180)
                    break

            fund_detail = {
                "revenues_by_fund": by_fund_labeled(rv),
                "expenditures_by_fund": by_fund_labeled(ex),
                "revenues_by_category": by_category_labeled(rv, is_revenue=True),
                "expenditures_by_category": by_category_labeled(ex, is_revenue=False),
            }
            conn.execute(
                """
                insert into afr_summaries (unit_id, fiscal_year, total_revenues, total_expenditures,
                                           fund_balance, total_debt, fund_detail, filed_on_time, source_url)
                values (%s,%s,%s,%s,%s,null,%s,%s,%s)
                on conflict (unit_id, fiscal_year) do update set
                  total_revenues=excluded.total_revenues,
                  total_expenditures=excluded.total_expenditures,
                  fund_balance=excluded.fund_balance,
                  fund_detail=excluded.fund_detail,
                  filed_on_time=excluded.filed_on_time,
                  source_url=excluded.source_url
                """,
                (uid, int(fy), sum(sum_funds(r) for r in rv), sum(sum_funds(r) for r in ex),
                 sum(sum_funds(r) for r in fb) if fb else None,
                 json.dumps(fund_detail), filed_on_time, SOURCE_URL),
            )
            n += 1
    conn.commit()
    print(f"matched {len(id_by_code)} Cook units, loaded {n} AFR rows across FYs {fys}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--accdb", nargs="+", required=True)
    load(ap.parse_args().accdb)

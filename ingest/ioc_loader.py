"""Load IL Comptroller Financial Database (.accdb) into afr_summaries.

Requires mdbtools (`brew install mdbtools`).
Accepts multiple accdb files to build a multi-year dataset:

    python ioc_loader.py --accdb ~/Downloads/data2023.accdb ~/Downloads/data2024.accdb ~/Downloads/data2025.accdb
"""
import argparse
import collections
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

# IOC spells a few Cook municipalities differently than TIGER does.
MUNI_ALIASES = {
    "elk grove": "Elk Grove Village",
    "mc cook": "McCook",
    "mt. prospect": "Mount Prospect",
}


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


def match_municipality(conn, name):
    """Resolve an IOC municipality by name, refusing anything ambiguous.

    Several Cook park districts, libraries and townships share a name with a
    village, so matching on name alone would file one government's budget under
    another's.
    """
    wanted = MUNI_ALIASES.get(name.strip().lower(), name.strip())
    rows = conn.execute(
        "select id from units where lower(name)=lower(%s) and type='municipality'",
        (wanted,),
    ).fetchall()
    return rows[0]["id"] if len(rows) == 1 else None


def load(accdb_paths, dry_run=False):
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
    kind_by_code = {}
    unmatched = defaultdict(list)
    for code, u in all_units.items():
        if u["C1"] == "TW":
            uid = "cook-" + u["UnitName"].lower().replace(" ", "-").replace(".", "") + "-township"
        elif u["Description"] == "County" and u["UnitName"] == "Cook":
            uid = "cook-county"
        elif u["C1"] == "MU":
            uid = match_municipality(conn, u["UnitName"])
            if not uid:
                unmatched["municipality"].append(u["UnitName"])
                continue
        else:
            continue
        r = conn.execute("select 1 from units where id=%s", (uid,)).fetchone()
        if r:
            id_by_code[code] = uid
            kind_by_code[code] = u["C1"]
            conn.execute("update units set ioc_code=%s where id=%s", (code, uid))
        else:
            unmatched[u["C1"]].append(u["UnitName"])

    for code, r in all_stats.items():
        if code in id_by_code and r.get("Pop"):
            # Census figures are better for municipalities; only fill the gaps.
            guard = " and population is null" if kind_by_code[code] == "MU" else ""
            conn.execute("update units set population=%s where id=%s" + guard,
                         (int(float(r["Pop"])), id_by_code[code]))

    # filter to matched units
    revs = [r for r in all_revs if r["Code"] in id_by_code]
    exps = [r for r in all_exps if r["Code"] in id_by_code]
    fbs = [r for r in all_fbs if r["Code"] in id_by_code]

    def t_rows(rows, code, fy):
        return [r for r in rows if r["Code"] == code and r["FY"] == fy and r["Category"].endswith("t")]

    matched_kinds = collections.Counter(kind_by_code.values())
    print(f"\nmatched {len(id_by_code)} Cook units: "
          + ", ".join(f"{k}={v}" for k, v in sorted(matched_kinds.items())))
    for kind, names in sorted(unmatched.items()):
        print(f"  unmatched {kind}: {len(names)} -> {sorted(names)[:8]}")

    fys = sorted({r["FY"] for r in revs} | {r["FY"] for r in exps})
    rows_by_kind = collections.Counter()
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

            rows_by_kind[kind_by_code[code]] += 1
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

    detail = ", ".join(f"{k}={v}" for k, v in sorted(rows_by_kind.items()))
    if dry_run:
        conn.rollback()
        print(f"\nDRY RUN - nothing written. Would load {n} AFR rows ({detail}) across FYs {fys}")
    else:
        conn.commit()
        print(f"\nloaded {n} AFR rows ({detail}) across FYs {fys}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--accdb", nargs="+", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    load(args.accdb, dry_run=args.dry_run)

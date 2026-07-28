"""Phase 0 data-integrity repairs.

Fixes four defects that make the site state things the sources do not support:

  0.1  afr_summaries.source_url points at a Comptroller page that now 404s.
  0.2  officials.term_end was derived from a hardcoded future election date,
       and as_of recorded the scrape date rather than the data vintage. The
       source dataset (Cook County jsup-zs8y) last updated its rows on
       2014-10-27, newest election_id 40913 == 2013-04-09.
  0.3  One general contact email was written onto every official in a unit,
       so individuals appear reachable at addresses that are not theirs.
  0.4  fund_detail carries both "Property Tax" and "Property Taxes", which
       render and sum as separate categories.

    python scripts/fix_data_integrity.py --dry-run
    python scripts/fix_data_integrity.py --apply
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

DEAD_URL = "https://illinoiscomptroller.gov/financial-reports-data/data-sets-portals/local-government-financial-databases"
LIVE_URL = "https://illinoiscomptroller.gov/constituent-services/local-government/local-government-warehouse"

# Cook County jsup-zs8y: newest election_id 40913 -> April 9, 2013.
OFFICIALS_VINTAGE = "2013-04-09"


def fix_provenance(conn, apply):
    n = conn.execute(
        "select count(*) as n from afr_summaries where source_url = %s", (DEAD_URL,)
    ).fetchone()["n"]
    print(f"0.1  afr_summaries rows with dead source_url: {n}")
    if apply and n:
        conn.execute(
            "update afr_summaries set source_url = %s where source_url = %s",
            (LIVE_URL, DEAD_URL),
        )
        print(f"     -> repointed {n} rows to the live warehouse URL")


def fix_officials_vintage(conn, apply):
    row = conn.execute(
        """select count(*) as total,
                  count(*) filter (where term_end is not null) as with_term,
                  count(*) filter (where certainty <> 'stale_risk') as not_flagged
           from officials"""
    ).fetchone()
    print(f"0.2  officials: {row['total']} total, {row['with_term']} carry a "
          f"fabricated term_end, {row['not_flagged']} not flagged stale")
    if apply:
        conn.execute(
            """update officials
                  set term_end  = null,
                      as_of     = %s,
                      certainty = 'stale_risk'""",
            (OFFICIALS_VINTAGE,),
        )
        print(f"     -> cleared term_end, as_of={OFFICIALS_VINTAGE}, certainty=stale_risk")


def fix_shared_emails(conn, apply):
    """Null emails that cannot be attributed to a specific person.

    An address shared by two or more distinct people in the same unit is a
    general office mailbox, not that individual's contact.
    """
    shared = conn.execute(
        """select unit_id, email, count(distinct name) as people
             from officials
            where email is not null
         group by unit_id, email
           having count(distinct name) > 1
         order by people desc"""
    ).fetchall()
    affected = conn.execute(
        """select count(*) as n from officials o
            where o.email is not null
              and exists (select 1 from officials x
                           where x.unit_id = o.unit_id and x.email = o.email
                             and x.name <> o.name)"""
    ).fetchone()["n"]
    print(f"0.3  shared-email groups: {len(shared)} across "
          f"{len({s['unit_id'] for s in shared})} units, {affected} official rows affected")
    for s in shared[:5]:
        print(f"       {s['unit_id']:32s} {s['email']:34s} {s['people']} people")
    print(f"       -> preserving each as the unit's general contact before nulling")
    if apply and affected:
        # The shared address is the office mailbox; keep it at unit level so
        # contact info survives, then detach it from individuals.
        conn.execute(
            """alter table units add column if not exists general_email text;
               alter table units add column if not exists general_phone text;"""
        )
        for s in shared:
            phone = conn.execute(
                """select phone from officials
                    where unit_id = %s and email = %s and phone is not null limit 1""",
                (s["unit_id"], s["email"]),
            ).fetchone()
            conn.execute(
                "update units set general_email = %s, general_phone = coalesce(general_phone, %s) where id = %s",
                (s["email"], phone["phone"] if phone else None, s["unit_id"]),
            )
        conn.execute(
            """update officials o set email = null
                where o.email is not null
                  and exists (select 1 from officials x
                               where x.unit_id = o.unit_id and x.email = o.email
                                 and x.name <> o.name)"""
        )
        print(f"     -> nulled {affected} unattributable emails")


def fix_category_dupe(conn, apply):
    rows = conn.execute(
        """select unit_id, fiscal_year, fund_detail
             from afr_summaries
            where fund_detail -> 'revenues_by_category' ? 'Property Taxes'"""
    ).fetchall()
    print(f"0.4  AFR rows using 'Property Taxes' instead of 'Property Tax': {len(rows)}")
    if apply and rows:
        for r in rows:
            fd = r["fund_detail"]
            rev = fd.get("revenues_by_category", {})
            rev["Property Tax"] = rev.get("Property Tax", 0) + rev.pop("Property Taxes")
            fd["revenues_by_category"] = rev
            conn.execute(
                "update afr_summaries set fund_detail = %s where unit_id = %s and fiscal_year = %s",
                (json.dumps(fd), r["unit_id"], r["fiscal_year"]),
            )
        print(f"     -> merged into 'Property Tax' on {len(rows)} rows")


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    apply = args.apply

    print("APPLYING CHANGES\n" if apply else "DRY RUN — no writes\n")
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as conn:
        fix_provenance(conn, apply)
        fix_officials_vintage(conn, apply)
        fix_shared_emails(conn, apply)
        fix_category_dupe(conn, apply)
        if apply:
            conn.commit()
            print("\ncommitted")
        else:
            print("\nre-run with --apply to write")


if __name__ == "__main__":
    main()

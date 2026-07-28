"""Load municipal contacts and officials from the Cook County Clerk
jurisdiction directory.

IMPORTANT — vintage: this dataset's rows were last updated 2014-10-27 and its
newest election_id is 40913 (April 9, 2013). Every person in it is a
*historical* officeholder, not a current one. Rows are therefore written with
as_of = 2013-04-09 and certainty = 'stale_risk', which the unit page renders
as an explicit "may be out of date" warning. This is the same treatment the
township officials get from the same source — showing a labeled historical
record beats showing nothing, but neither is a current roster.

Institutional contacts (website, hall phone) survive officeholder turnover,
so those are loaded with more confidence than the names.

    python contacts_loader.py --dry-run
    python contacts_loader.py
    python contacts_loader.py --contacts-only
"""
import argparse
import datetime as dt
import re

import httpx

from db import apply_schema, connect

API_URL = "https://datacatalog.cookcountyil.gov/resource/vw2r-zys4.json"
SOURCE_URL = "https://datacatalog.cookcountyil.gov/d/vw2r-zys4"
DATA_VINTAGE = dt.date(2013, 4, 9)

# Cook County's directory rows each carry the individual office's site
# (assessor, recorder, sheriff...). None is the county's own front door.
COUNTY_WEBSITE = "https://www.cookcountyil.gov"

ROLE_MAP = {
    "president": "president",
    "mayor": "mayor",
    "clerk": "clerk",
    "trustee": "trustee",
    "alderman": "alderman",
    "treasurer": "treasurer",
    "councilman": "councilman",
    "commissioner": "commissioner",
    "supervisor": "supervisor",
    "assessor": "assessor",
    "collector": "collector",
    "highway commissioner": "highway_commissioner",
}

# A library board is a separate taxing body, not the municipality's board.
SKIP_OFFICES = {"library trustee"}

# Ward/district suffixes: "City of Chicago, Ward 5"
JURIS_SUFFIX = re.compile(r",.*$")
MUNI_PREFIX = re.compile(r"^(village|city|town) of\s+", re.I)


def bare(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def classify(jurisdiction: str) -> tuple[str, str] | None:
    """Map a directory jurisdiction to (unit_type, normalized_name).

    Type matters: Cook County has many township/village pairs sharing a name
    (Barrington, Berwyn, Cicero, Oak Park, Thornton...). Matching on name
    alone hands the Village of Barrington the township's website.
    """
    j = JURIS_SUFFIX.sub("", jurisdiction or "").strip()
    if not j:
        return None
    if re.search(r"\btownship\b", j, re.I):
        return "township", bare(re.sub(r"\btownship\b", "", j, flags=re.I))
    if MUNI_PREFIX.match(j):
        return "municipality", bare(MUNI_PREFIX.sub("", j))
    if j.lower() == "cook county":
        return "county", "cookcounty"
    return None


def fetch():
    r = httpx.get(API_URL, params={"$limit": 50000}, timeout=90, follow_redirects=True)
    r.raise_for_status()
    return r.json()


def load(conn, dry_run: bool):
    records = fetch()
    print(f"fetched {len(records)} directory records")

    # Collapse to one contact per jurisdiction, preferring rows that carry the
    # most institutional detail.
    best: dict[tuple[str, str], dict] = {}
    for rec in records:
        key = classify(rec.get("jurisdiction"))
        if not key:
            continue
        score = sum(bool(rec.get(f)) for f in ("website", "phone", "email", "address"))
        if score > best.get(key, {}).get("_score", -1):
            best[key] = {**rec, "_score": score}

    units = conn.execute(
        "select id, name, type, website, general_email, general_phone from units order by type, name"
    ).fetchall()

    filled_web, filled_phone, filled_email, no_match = 0, 0, 0, []
    for u in units:
        lookup = bare(re.sub(r"\btownship\b", "", u["name"], flags=re.I))
        rec = best.get((u["type"], lookup))
        if not rec:
            no_match.append(u)
            continue

        site = (rec.get("website") or {}).get("url") or None
        if u["type"] == "county":
            site = COUNTY_WEBSITE
        phone = (rec.get("phone") or "").strip() or None
        email = (rec.get("email") or "").strip() or None

        new_web = site if (site and not u["website"]) else None
        new_phone = phone if (phone and not u["general_phone"]) else None
        new_email = email if (email and not u["general_email"]) else None

        if new_web:
            filled_web += 1
        if new_phone:
            filled_phone += 1
        if new_email:
            filled_email += 1

        if dry_run:
            if new_web and filled_web <= 8:
                print(f"  {u['name']:26s} website -> {new_web}")
            continue

        if new_web or new_phone or new_email:
            conn.execute(
                """update units
                      set website       = coalesce(website, %s),
                          general_phone = coalesce(general_phone, %s),
                          general_email = coalesce(general_email, %s)
                    where id = %s""",
                (site, phone, email, u["id"]),
            )

    print(f"\nfilled: {filled_web} websites, {filled_phone} phones, {filled_email} emails")
    if no_match:
        print(f"no directory entry for {len(no_match)} units:")
        for u in no_match[:12]:
            print(f"  {u['type']:14s} {u['name']}")
    return records, units


def load_officials(conn, records, units, dry_run: bool):
    """Load historical officeholders for municipalities.

    Townships already have rows from officials_api_loader; this fills the
    municipal side of the same directory so the two are treated consistently.
    """
    unit_by_key = {
        (u["type"], bare(re.sub(r"\btownship\b", "", u["name"], flags=re.I))): u["id"]
        for u in units
    }

    by_unit: dict[str, list[dict]] = {}
    for rec in records:
        key = classify(rec.get("jurisdiction"))
        if not key or key[0] != "municipality":
            continue
        uid = unit_by_key.get(key)
        if not uid:
            continue
        office = (rec.get("office") or "").strip()
        if office.lower() in SKIP_OFFICES:
            continue
        role = ROLE_MAP.get(office.lower())
        if not role:
            continue
        name = " ".join(
            p for p in (rec.get("first_name"), rec.get("middle_name"), rec.get("last_name")) if p
        ).strip()
        if not name:
            continue
        by_unit.setdefault(uid, []).append({
            "role": role,
            "name": name,
            "email": (rec.get("email") or "").strip() or None,
            "phone": (rec.get("phone") or "").strip() or None,
        })

    total = sum(len(v) for v in by_unit.values())
    leaders = sum(1 for v in by_unit.values() for o in v if o["role"] in ("president", "mayor"))
    print(f"\nmunicipal officials: {total} across {len(by_unit)} units "
          f"({leaders} presidents/mayors)")

    if dry_run:
        for uid, people in list(by_unit.items())[:4]:
            head = next((p for p in people if p["role"] in ("president", "mayor")), people[0])
            print(f"  {uid:28s} {len(people):2d} officials, lead: {head['role']} {head['name']}")
        return

    for uid, people in by_unit.items():
        conn.execute(
            "delete from officials where unit_id=%s and source_url=%s", (uid, SOURCE_URL)
        )
        # Same rule as elsewhere: an address shared by several people is an
        # office mailbox, not an individual's contact.
        counts: dict[str, int] = {}
        for p in people:
            if p["email"]:
                counts[p["email"]] = counts.get(p["email"], 0) + 1
        for p in people:
            email = p["email"] if p["email"] and counts.get(p["email"], 0) == 1 else None
            conn.execute(
                """insert into officials
                     (unit_id, role, name, email, phone, term_end, certainty, source_url, as_of)
                   values (%s,%s,%s,%s,%s,null,'stale_risk',%s,%s)""",
                (uid, p["role"], p["name"], email, p["phone"], SOURCE_URL, DATA_VINTAGE),
            )


def run(conn, dry_run: bool, contacts_only: bool):
    records, units = load(conn, dry_run)
    if not contacts_only:
        load_officials(conn, records, units, dry_run)
    if not dry_run:
        conn.commit()
        print("\ncommitted")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--contacts-only", action="store_true",
                    help="skip officeholder names, load only website/phone/email")
    args = ap.parse_args()
    conn = connect()
    apply_schema(conn)
    run(conn, args.dry_run, args.contacts_only)


if __name__ == "__main__":
    main()

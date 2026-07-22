"""Audit data coverage across all units to identify the 'gold set' for MVP."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import psycopg
from psycopg.rows import dict_row

conn = psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)

print("=" * 80)
print("CIVICLENS DATA COVERAGE AUDIT")
print("=" * 80)

# 1. Overall counts
print("\n── SYSTEM-WIDE COUNTS ──")
for table, col in [("units", "*"), ("officials", "*"), ("afr_summaries", "*"),
                   ("spend_lines", "*"), ("meetings", "*"), ("agenda_items", "*"), ("documents", "*")]:
    row = conn.execute(f"select count({col}) as n from {table}").fetchone()
    print(f"  {table:20s}: {row['n']:,}")

# 2. Units by type
print("\n── UNITS BY TYPE ──")
rows = conn.execute("select type, count(*) as n from units group by type order by n desc").fetchall()
for r in rows:
    print(f"  {r['type']:20s}: {r['n']}")

# 3. Per-unit coverage breakdown
print("\n── PER-UNIT COVERAGE ──")
print(f"{'Unit ID':30s} {'Name':30s} {'Type':12s} {'Pop':>8s} {'Ofcls':>5s} {'AFR Yrs':>7s} {'Spend':>7s} {'Mtgs':>5s} {'Agenda':>6s} {'Docs':>5s} {'Geom':>5s}")
print("-" * 150)

rows = conn.execute("""
    select u.id, u.name, u.type, u.population,
           (select count(*) from officials o where o.unit_id = u.id) as officials_count,
           (select count(*) from afr_summaries a where a.unit_id = u.id) as afr_years,
           (select max(fiscal_year) from afr_summaries a where a.unit_id = u.id) as latest_fy,
           (select count(*) from spend_lines s where s.unit_id = u.id) as spend_lines,
           (select count(*) from meetings m where m.unit_id = u.id) as meetings,
           (select count(*) from agenda_items ai join meetings m on m.id = ai.meeting_id where m.unit_id = u.id) as agenda_items,
           (select count(*) from documents d where d.unit_id = u.id) as documents,
           (u.geom is not null) as has_geom
    from units u
    order by u.type, u.name
""").fetchall()

# Score each unit
scored = []
for r in rows:
    score = 0
    if r["has_geom"]: score += 1
    if r["officials_count"] > 0: score += 2
    if r["afr_years"] > 0: score += 2
    if r["afr_years"] >= 3: score += 1  # bonus for multi-year
    if r["spend_lines"] > 0: score += 2
    if r["meetings"] > 0: score += 1
    if r["agenda_items"] > 0: score += 1
    r["score"] = score
    scored.append(r)

    print(f"{r['id']:30s} {r['name']:30s} {r['type']:12s} {(r['population'] or 0):>8,d} {r['officials_count']:>5d} {r['afr_years']:>7d} {r['spend_lines']:>7,d} {r['meetings']:>5d} {r['agenda_items']:>6d} {r['documents']:>5d} {'Y' if r['has_geom'] else 'N':>5s}")

# 4. Gold set recommendation
print("\n── GOLD SET (score >= 4, sorted by score desc) ──")
gold = sorted([r for r in scored if r["score"] >= 4], key=lambda x: -x["score"])
print(f"{'Score':>5s} {'Unit ID':30s} {'Name':30s} {'Type':12s} {'Pop':>8s} {'Ofcls':>5s} {'AFR':>4s} {'Spend':>7s} {'Mtgs':>5s}")
print("-" * 120)
for r in gold:
    print(f"{r['score']:>5d} {r['id']:30s} {r['name']:30s} {r['type']:12s} {(r['population'] or 0):>8,d} {r['officials_count']:>5d} {r['afr_years']:>4d} {r['spend_lines']:>7,d} {r['meetings']:>5d}")

print(f"\nGold set count: {len(gold)}")
print(f"Total units: {len(scored)}")

# 5. AFR fiscal year range
print("\n── AFR FISCAL YEAR RANGE ──")
fy = conn.execute("select min(fiscal_year) as mn, max(fiscal_year) as mx from afr_summaries").fetchone()
print(f"  Earliest: FY{fy['mn']}  Latest: FY{fy['mx']}")

# 6. Spend data date range
print("\n── SPEND DATA DATE RANGE ──")
sp = conn.execute("select min(meeting_date) as mn, max(meeting_date) as mx, count(distinct unit_id) as units from spend_lines").fetchone()
print(f"  Earliest: {sp['mn']}  Latest: {sp['mx']}  Units with spend data: {sp['units']}")

# 7. Meeting data date range
print("\n── MEETING DATA DATE RANGE ──")
mt = conn.execute("select min(meeting_ts) as mn, max(meeting_ts) as mx, count(distinct unit_id) as units from meetings").fetchone()
print(f"  Earliest: {mt['mn']}  Latest: {mt['mx']}  Units with meetings: {mt['units']}")

conn.close()

"""Extract warrant/payment totals from agenda packet PDFs into spend_lines.

Parses fund-level warrant totals from agenda text (e.g. "Town Fund Warrant
2026-2027 #5 $419,956.93"). These are aggregate amounts approved at each
board meeting, not individual vendor payments.

Usage:
    python warrant_extractor.py                          # all townships with packet data
    python warrant_extractor.py --unit cook-schaumburg-township
    python warrant_extractor.py --dry-run
"""
import argparse
import re

from psycopg.rows import dict_row

from db import connect as _connect


def connect():
    conn = _connect()
    conn.row_factory = dict_row
    return conn


# Match warrant lines like:
# "Town Fund Warrant    2026-2027  #5  $419,956.93"
# "Road & Bridge Warrant   2024 -2025 # 10 $   51,806.09"
# "MHB  Warrant: 5/30/26 – 7/3/26 | $96,563.65"
WARRANT_LINE = re.compile(
    r'(Town\s*Fund|Road\s*(?:&|and)\s*Bridge|Welfare\s*Services?|'
    r'General\s*Assistance|Capital(?:\s*Fund)?|Mental\s*Health|MHB)\s*'
    r'Warrant[^$]*\$\s*([\d,]+\.\d{2})',
    re.I
)

FUND_MAP = {
    "town fund": "General",
    "road & bridge": "Road & Bridge",
    "road and bridge": "Road & Bridge",
    "welfare services": "General Assistance",
    "welfare service": "General Assistance",
    "general assistance": "General Assistance",
    "capital": "Capital Projects",
    "capital fund": "Capital Projects",
    "mental health": "Mental Health",
    "mhb": "Mental Health",
}


def extract_warrants(text, unit_id, meeting_date, doc_id):
    lines = []
    for match in WARRANT_LINE.finditer(text):
        fund_raw = match.group(1).strip()
        amount_str = match.group(2).replace(",", "")
        try:
            amount = float(amount_str)
        except ValueError:
            continue
        if amount < 1 or amount > 100_000_000:
            continue

        fund = FUND_MAP.get(fund_raw.lower(), fund_raw)
        lines.append({
            "unit_id": unit_id,
            "meeting_date": meeting_date,
            "vendor_raw": f"Warrant Total — {fund}",
            "vendor_canon": f"WARRANT_TOTAL_{fund.upper().replace(' ', '_')}",
            "amount": amount,
            "fund": fund,
            "category": "warrant_approval",
            "description": f"Board-approved warrant total for {fund} fund",
            "certainty": "extracted",
            "source_doc_id": doc_id,
        })
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--unit", help="process only this unit_id")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = connect()

    sql = """
        select d.id, d.unit_id, d.extracted_text, m.meeting_ts::date as meeting_date
        from documents d
        join meetings m on m.agenda_doc_id = d.id
        where d.extracted_text is not null
          and d.kind = 'agenda'
          and not exists (select 1 from spend_lines s where s.source_doc_id = d.id)
    """
    params = []
    if args.unit:
        sql += " and d.unit_id = %s"
        params.append(args.unit)
    sql += " order by m.meeting_ts desc"

    docs = conn.execute(sql, params).fetchall()
    print(f"scanning {len(docs)} documents for warrant data")

    total_lines = 0
    docs_with_data = 0
    for doc in docs:
        lines = extract_warrants(
            doc["extracted_text"], doc["unit_id"], doc["meeting_date"], doc["id"]
        )
        if not lines:
            continue
        docs_with_data += 1
        total_lines += len(lines)
        if args.dry_run:
            print(f"\n{doc['unit_id']} — {doc['meeting_date']}:")
            for l in lines:
                print(f"  {l['fund']:20s}  ${l['amount']:>12,.2f}")
        else:
            for l in lines:
                conn.execute(
                    """insert into spend_lines (unit_id, meeting_date, vendor_raw, vendor_canon,
                                                amount, fund, category, description, certainty, source_doc_id)
                       values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (l["unit_id"], l["meeting_date"], l["vendor_raw"], l["vendor_canon"],
                     l["amount"], l["fund"], l["category"], l["description"],
                     l["certainty"], l["source_doc_id"]),
                )

    if not args.dry_run:
        conn.commit()
    print(f"\ndone: {total_lines} spend lines from {docs_with_data}/{len(docs)} documents")


if __name__ == "__main__":
    main()

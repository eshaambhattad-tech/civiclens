"""Extract agenda items from downloaded agenda PDFs into agenda_items table.

Downloads agenda PDFs from the documents table, extracts text via PyPDF2,
splits into individual agenda items, and populates the agenda_items table
with full-text search vectors.

Usage:
    python agenda_extractor.py                          # process all unextracted agenda docs
    python agenda_extractor.py --unit cook-niles-township  # one township
    python agenda_extractor.py --limit 10               # process N docs
    python agenda_extractor.py --dry-run                # preview without DB writes
"""
import argparse
import datetime as dt
import os
import re
import tempfile

import httpx
from PyPDF2 import PdfReader

from psycopg.rows import dict_row

from db import connect as _connect


def connect():
    conn = _connect()
    conn.row_factory = dict_row
    return conn

HEADERS = {"User-Agent": "CivicLens/1.0 (civic transparency research)"}


def download_pdf(url):
    r = httpx.get(url, headers=HEADERS, timeout=30, follow_redirects=True)
    r.raise_for_status()
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.write(r.content)
    tmp.close()
    return tmp.name


def extract_text(pdf_path):
    reader = PdfReader(pdf_path)
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text)
    return "\n\n".join(pages), len(reader.pages)


def parse_agenda_items(text):
    """Split agenda text into individual items. Handles common formats:
    - Numbered items: "1.", "2.", "I.", "II.", "A.", etc.
    - Roman numerals: "I.", "II.", "III.", etc.
    - Lettered items: "A.", "B.", etc.
    - Items after headers like "NEW BUSINESS", "OLD BUSINESS", "REPORTS"
    """
    items = []
    current_section = None

    # detect section headers
    section_pattern = re.compile(
        r'^((?:NEW|OLD|UNFINISHED)\s+BUSINESS|REPORTS?|COMMUNICATIONS?|'
        r'PUBLIC\s+(?:COMMENT|HEARING)|CONSENT\s+AGENDA|ACTION\s+ITEMS?|'
        r'DISCUSSION\s+ITEMS?|EXECUTIVE\s+SESSION|ADJOURNMENT|'
        r'CALL\s+TO\s+ORDER|ROLL\s+CALL|APPROVAL\s+OF\s+MINUTES|'
        r'TREASURER.S?\s+REPORT|SUPERVISOR.S?\s+REPORT|'
        r'COMMITTEE\s+REPORTS?|ANNOUNCEMENTS?)',
        re.I | re.MULTILINE
    )

    # numbered item pattern
    item_pattern = re.compile(
        r'^(?:\s*)(?:(\d+|[IVXLC]+|[A-Z])[\.\)]\s+)(.*)',
        re.MULTILINE
    )

    lines = text.split('\n')
    current_item = None

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # check for section header
        sec_match = section_pattern.match(line)
        if sec_match:
            if current_item:
                items.append(current_item)
                current_item = None
            current_section = sec_match.group(1).strip().title()
            # the section header itself is an item
            items.append({
                "item_no": None,
                "title": current_section,
                "topic": _classify_topic(current_section, ""),
            })
            continue

        # check for numbered item
        item_match = item_pattern.match(line)
        if item_match:
            if current_item:
                items.append(current_item)
            num = item_match.group(1)
            title = item_match.group(2).strip()
            current_item = {
                "item_no": num,
                "title": title,
                "topic": _classify_topic(current_section or "", title),
            }
        elif current_item and len(line) > 10:
            # continuation of current item
            current_item["title"] += " " + line

    if current_item:
        items.append(current_item)

    # dedupe and clean
    seen = set()
    clean = []
    for item in items:
        title = item["title"].strip()
        if len(title) < 3:
            continue
        key = title[:80].lower()
        if key not in seen:
            seen.add(key)
            item["title"] = title[:500]
            clean.append(item)

    return clean


TOPIC_KEYWORDS = {
    "finance": ["budget", "tax", "levy", "appropriation", "fund", "audit", "treasurer", "financial",
                "expenditure", "revenue", "payment", "warrant", "payroll", "fiscal"],
    "public_safety": ["police", "fire", "emergency", "safety", "security"],
    "infrastructure": ["road", "highway", "bridge", "water", "sewer", "utility", "maintenance",
                       "construction", "paving", "sidewalk"],
    "social_services": ["general assistance", "welfare", "senior", "youth", "disability",
                        "mental health", "food pantry", "housing"],
    "governance": ["ordinance", "resolution", "bylaw", "appointment", "election", "vacancy",
                   "minutes", "roll call", "adjournment", "call to order", "consent agenda"],
    "zoning": ["zoning", "variance", "planning", "subdivision", "permit", "building"],
    "personnel": ["hire", "salary", "employee", "personnel", "position", "compensation"],
    "community": ["event", "park", "recreation", "library", "community", "volunteer"],
}


def _classify_topic(section, title):
    combined = (section + " " + title).lower()
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(kw in combined for kw in keywords):
            return topic
    return "general"


def process_document(conn, doc, dry_run=False):
    """Download, extract, and parse one agenda document."""
    url = doc["url"]
    doc_id = doc["id"]
    meeting_id = doc.get("meeting_id")

    try:
        pdf_path = download_pdf(url)
    except Exception as e:
        print(f"    download failed: {e}")
        return 0

    try:
        text, page_count = extract_text(pdf_path)
    except Exception as e:
        print(f"    PDF parse failed: {e}")
        return 0
    finally:
        os.unlink(pdf_path)

    if not text.strip():
        print(f"    empty PDF")
        return 0

    items = parse_agenda_items(text)

    if dry_run:
        for it in items[:10]:
            print(f"    [{it.get('item_no', '-'):>4s}] ({it['topic']:15s}) {it['title'][:80]}")
        if len(items) > 10:
            print(f"    ... and {len(items) - 10} more items")
        return len(items)

    # save extracted text to document
    conn.execute(
        "update documents set extracted_text = %s, pages = %s, fetched_at = now() where id = %s",
        (text[:50000], page_count, doc_id),
    )

    # insert agenda items
    for it in items:
        conn.execute(
            """insert into agenda_items (meeting_id, item_no, title, topic, fts)
               values (%s, %s, %s, %s, to_tsvector('english', %s))""",
            (meeting_id, it.get("item_no"), it["title"], it["topic"],
             it["title"]),
        )

    return len(items)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--unit", help="process only this unit_id")
    ap.add_argument("--limit", type=int, default=0, help="max documents to process")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = connect()

    # find agenda documents that haven't been extracted yet
    sql = """
        select d.id, d.url, d.unit_id, m.id as meeting_id
        from documents d
        join meetings m on m.agenda_doc_id = d.id
        where d.kind = 'agenda' and d.fetched_at is null
    """
    params = []
    if args.unit:
        sql += " and d.unit_id = %s"
        params.append(args.unit)
    sql += " order by m.meeting_ts desc"
    if args.limit:
        sql += " limit %s"
        params.append(args.limit)

    docs = conn.execute(sql, params).fetchall()
    print(f"found {len(docs)} unextracted agenda documents")

    total_items = 0
    for i, doc in enumerate(docs):
        print(f"[{i+1}/{len(docs)}] {doc['unit_id']} — {doc['url'][:80]}...")
        n = process_document(conn, doc, dry_run=args.dry_run)
        total_items += n
        print(f"    → {n} agenda items")

    if not args.dry_run:
        conn.commit()
    print(f"\ndone: {total_items} agenda items from {len(docs)} documents")


if __name__ == "__main__":
    main()

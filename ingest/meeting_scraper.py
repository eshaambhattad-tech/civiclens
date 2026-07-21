"""Scrape meeting agendas & minutes from Cook County township websites.

Supports three site patterns:
  - CivicPlus AgendaCenter (Niles, Bloom, Leyden)
  - WordPress PDF pages (Schaumburg, Palatine, Thornton)
  - Custom PHP + PDF links (Maine)

Usage:
    python meeting_scraper.py                   # scrape all configured townships
    python meeting_scraper.py --unit cook-niles-township  # scrape one
    python meeting_scraper.py --dry-run         # preview without DB writes
"""
import argparse
import datetime as dt
import re
from urllib.parse import urljoin

import httpx
from db import apply_schema, connect

HEADERS = {"User-Agent": "CivicLens/1.0 (civic transparency research)"}
TIMEOUT = 20

TOWNSHIP_SOURCES = [
    # CivicPlus AgendaCenter sites
    {
        "unit_id": "cook-niles-township",
        "type": "civicplus",
        "base_url": "https://nilestownshipgov.com",
        "agenda_path": "/AgendaCenter/Township-Board-2",
    },
    {
        "unit_id": "cook-bloom-township",
        "type": "civicplus",
        "base_url": "https://bloomtownship.org",
        "agenda_path": "/AgendaCenter",
    },
    {
        "unit_id": "cook-leyden-township",
        "type": "civicplus",
        "base_url": "https://leydentownship.com",
        "agenda_path": "/AgendaCenter",
    },
    # WordPress PDF sites
    {
        "unit_id": "cook-schaumburg-township",
        "type": "wordpress",
        "url": "https://schaumburgtownship.org/transparency/agenda-minutes/",
    },
    {
        "unit_id": "cook-palatine-township",
        "type": "wordpress",
        "url": "https://palatinetownship-il.gov/documents/",
    },
    {
        "unit_id": "cook-thornton-township",
        "type": "wordpress",
        "url": "https://thorntontownship.com/agendas-notices-minutes/",
    },
    # Custom PHP
    {
        "unit_id": "cook-maine-township",
        "type": "custom_php",
        "url": "https://mainetown.com/government/agendas_minutes.php",
    },
]


def fetch(url):
    r = httpx.get(url, headers=HEADERS, timeout=TIMEOUT, follow_redirects=True)
    r.raise_for_status()
    return r.text


def parse_date_from_text(text):
    """Try to extract a date from text like '07/13/2026', 'July 13, 2026', '7.20.26', etc."""
    # MM/DD/YYYY or MM-DD-YYYY
    m = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})', text)
    if m:
        try:
            return dt.date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
        except ValueError:
            pass
    # M.DD.YY
    m = re.search(r'(\d{1,2})\.(\d{1,2})\.(\d{2,4})', text)
    if m:
        y = int(m.group(3))
        if y < 100:
            y += 2000
        try:
            return dt.date(y, int(m.group(1)), int(m.group(2)))
        except ValueError:
            pass
    # Month DD, YYYY
    m = re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})', text, re.I)
    if m:
        months = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
                  "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12}
        try:
            return dt.date(int(m.group(3)), months[m.group(1).lower()], int(m.group(2)))
        except ValueError:
            pass
    # MMDDYYYY (from CivicPlus URLs like _07132026-248)
    m = re.search(r'_(\d{8})-', text)
    if m:
        s = m.group(1)
        try:
            return dt.date(int(s[4:8]), int(s[0:2]), int(s[2:4]))
        except ValueError:
            pass
    return None


def scrape_civicplus(source):
    """Scrape CivicPlus AgendaCenter pages. Returns list of meeting dicts."""
    base = source["base_url"]
    url = base + source["agenda_path"]
    html = fetch(url)
    meetings = []
    # CivicPlus AgendaCenter uses links like /AgendaCenter/ViewFile/Agenda/_MMDDYYYY-ID
    agenda_links = re.findall(r'href="([^"]*AgendaCenter/ViewFile/[^"]*)"', html)
    minutes_links = re.findall(r'href="([^"]*AgendaCenter/ViewFile/Minutes[^"]*)"', html)
    packet_links = re.findall(r'href="([^"]*AgendaCenter/ViewFile/Agenda\s*Packet[^"]*)"', html, re.I)

    # Group by date from URL pattern _MMDDYYYY-ID
    seen_dates = {}
    for link in agenda_links:
        date = parse_date_from_text(link)
        if not date:
            continue
        full_url = urljoin(base, link)
        if date not in seen_dates:
            seen_dates[date] = {"date": date, "agenda_url": full_url, "minutes_url": None, "packet_url": None}
        if "Packet" in link:
            seen_dates[date]["packet_url"] = full_url
        else:
            seen_dates[date]["agenda_url"] = full_url

    for link in minutes_links:
        date = parse_date_from_text(link)
        if date and date in seen_dates:
            seen_dates[date]["minutes_url"] = urljoin(base, link)

    for link in packet_links:
        date = parse_date_from_text(link)
        if date and date in seen_dates:
            seen_dates[date]["packet_url"] = urljoin(base, link)

    for d, info in sorted(seen_dates.items()):
        if d.year < 2020 or d.year > 2030:
            continue
        meetings.append({
            "unit_id": source["unit_id"],
            "body": "Board of Trustees",
            "meeting_ts": dt.datetime.combine(d, dt.time(19, 0)),
            "status": "minutes_available" if info["minutes_url"] else "scheduled",
            "agenda_url": info["agenda_url"],
            "minutes_url": info["minutes_url"],
            "source": "civicplus",
        })
    return meetings


def scrape_wordpress(source):
    """Scrape WordPress sites that list agenda PDFs via wp-content/uploads."""
    html = fetch(source["url"])
    meetings = []
    pdf_links = re.findall(r'href="([^"]*\.pdf[^"]*)"', html, re.I)
    seen_dates = {}

    for link in pdf_links:
        full_url = urljoin(source["url"], link)
        date = parse_date_from_text(link)
        if not date:
            continue
        if date not in seen_dates:
            seen_dates[date] = {"date": date, "agenda_url": None, "minutes_url": None}
        link_lower = link.lower()
        if "minute" in link_lower:
            seen_dates[date]["minutes_url"] = full_url
        elif "agenda" in link_lower or "packet" in link_lower:
            seen_dates[date]["agenda_url"] = full_url

    for d, info in sorted(seen_dates.items()):
        if not info["agenda_url"] and not info["minutes_url"]:
            continue
        if d.year < 2020 or d.year > 2030:
            continue
        meetings.append({
            "unit_id": source["unit_id"],
            "body": "Board of Trustees",
            "meeting_ts": dt.datetime.combine(d, dt.time(19, 0)),
            "status": "minutes_available" if info["minutes_url"] else "scheduled",
            "agenda_url": info["agenda_url"],
            "minutes_url": info["minutes_url"],
            "source": "wordpress",
        })
    return meetings


def _parse_maine_date(filename):
    """Parse Maine's YY-MM-DD pattern from filenames like agenda_26-06-30.pdf"""
    m = re.search(r'(\d{2})-(\d{2})-(\d{2})', filename)
    if m:
        y = 2000 + int(m.group(1))
        try:
            return dt.date(y, int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    return None


def scrape_custom_php(source):
    """Scrape Maine Township style PHP pages with PDF links."""
    html = fetch(source["url"])
    meetings = []
    pdf_links = re.findall(r'href="([^"]*\.pdf[^"]*)"', html, re.I)
    seen_dates = {}

    for link in pdf_links:
        full_url = urljoin(source["url"], link)
        date = _parse_maine_date(link) or parse_date_from_text(link)
        if not date or date.year < 2020 or date.year > 2030:
            continue
        if date not in seen_dates:
            seen_dates[date] = {"date": date, "agenda_url": None, "minutes_url": None}
        # use filename only to avoid false matches from path like "Agenda & Minutes/"
        filename = link.rsplit("/", 1)[-1].lower()
        if "minute" in filename:
            seen_dates[date]["minutes_url"] = full_url
        elif "agenda" in filename or "packet" in filename:
            seen_dates[date]["agenda_url"] = full_url

    for d, info in sorted(seen_dates.items()):
        if not info["agenda_url"] and not info["minutes_url"]:
            continue
        meetings.append({
            "unit_id": source["unit_id"],
            "body": "Board of Trustees",
            "meeting_ts": dt.datetime.combine(d, dt.time(19, 0)),
            "status": "minutes_available" if info["minutes_url"] else "scheduled",
            "agenda_url": info["agenda_url"],
            "minutes_url": info["minutes_url"],
            "source": "custom_php",
        })
    return meetings


SCRAPERS = {
    "civicplus": scrape_civicplus,
    "wordpress": scrape_wordpress,
    "custom_php": scrape_custom_php,
}


def save_meetings(meetings, dry_run=False):
    if dry_run:
        for m in meetings:
            print(f"  {m['meeting_ts'].date()}  {m['unit_id']:40s}  agenda={'yes' if m.get('agenda_url') else 'no ':3s}  minutes={'yes' if m.get('minutes_url') else 'no '}")
        return

    conn = connect()
    apply_schema(conn)
    inserted = 0
    for m in meetings:
        # insert agenda doc if we have one
        agenda_doc_id = None
        if m.get("agenda_url"):
            conn.execute(
                "insert into documents (unit_id, kind, url) values (%s, 'agenda', %s) on conflict do nothing returning id",
                (m["unit_id"], m["agenda_url"]),
            )
            row = conn.execute("select id from documents where url = %s", (m["agenda_url"],)).fetchone()
            if row:
                agenda_doc_id = row[0]

        minutes_doc_id = None
        if m.get("minutes_url"):
            conn.execute(
                "insert into documents (unit_id, kind, url) values (%s, 'minutes', %s) on conflict do nothing returning id",
                (m["unit_id"], m["minutes_url"]),
            )
            row = conn.execute("select id from documents where url = %s", (m["minutes_url"],)).fetchone()
            if row:
                minutes_doc_id = row[0]

        existing = conn.execute(
            "select id from meetings where unit_id = %s and meeting_ts = %s",
            (m["unit_id"], m["meeting_ts"]),
        ).fetchone()
        if existing:
            conn.execute(
                "update meetings set status=%s, agenda_doc_id=%s, minutes_doc_id=%s where id=%s",
                (m["status"], agenda_doc_id, minutes_doc_id, existing[0]),
            )
        else:
            conn.execute(
                "insert into meetings (unit_id, body, meeting_ts, status, agenda_doc_id, minutes_doc_id) values (%s,%s,%s,%s,%s,%s)",
                (m["unit_id"], m["body"], m["meeting_ts"], m["status"], agenda_doc_id, minutes_doc_id),
            )
            inserted += 1

    conn.commit()
    print(f"saved {inserted} new meetings, {len(meetings) - inserted} updated")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--unit", help="scrape only this unit_id")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    sources = TOWNSHIP_SOURCES
    if args.unit:
        sources = [s for s in sources if s["unit_id"] == args.unit]
        if not sources:
            print(f"no config for {args.unit}")
            return

    all_meetings = []
    for src in sources:
        scraper = SCRAPERS[src["type"]]
        print(f"scraping {src['unit_id']} ({src['type']})...")
        try:
            meetings = scraper(src)
            print(f"  found {len(meetings)} meetings")
            all_meetings.extend(meetings)
        except Exception as e:
            print(f"  ERROR: {e}")

    print(f"\ntotal: {len(all_meetings)} meetings across {len(sources)} townships")
    save_meetings(all_meetings, dry_run=args.dry_run)


if __name__ == "__main__":
    main()

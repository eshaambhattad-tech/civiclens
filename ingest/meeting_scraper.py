"""Scrape meeting agendas & minutes from unit websites.

Sources come from units.agenda_platform + units.packet_url (populated by
platform_detector.py). One adapter per platform:

  - civicplus   CivicPlus AgendaCenter
  - wordpress   WordPress pages that list agenda PDFs
  - custom_php  Custom PHP pages with PDF links (Maine-style)
  - pdf_list    Generic pages that list dated PDF agendas/minutes

Usage:
    python meeting_scraper.py                      # all supported units
    python meeting_scraper.py --type township
    python meeting_scraper.py --platform civicplus
    python meeting_scraper.py --unit cook-niles-township
    python meeting_scraper.py --dry-run
"""
import argparse
import datetime as dt
import re
from urllib.parse import urljoin, urlparse

import httpx
from db import apply_schema, connect

HEADERS = {"User-Agent": "CivicLens/1.0 (civic transparency research)"}
TIMEOUT = 20

SUPPORTED_PLATFORMS = ("civicplus", "wordpress", "custom_php", "pdf_list")

# Known oddballs where detector/path heuristics still get the scrape type wrong.
OVERRIDES = {
    "cook-maine-township": {
        "type": "custom_php",
        "url": "https://mainetown.com/government/agendas_minutes.php",
    },
    "cook-niles-township": {
        "type": "civicplus",
        "base_url": "https://nilestownshipgov.com",
        "agenda_path": "/AgendaCenter/Township-Board-2",
    },
    # Detector lands on /meetings-events/ (calendar); PDFs live under /documents/.
    "cook-palatine-township": {
        "type": "wordpress",
        "url": "https://palatinetownship-il.gov/documents/",
    },
}


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
    # compact YYYYMMDD or MM-DD-YYYY in filenames like Agenda+071526.pdf
    m = re.search(r'(?:agenda|minutes?)[+_\-]?(\d{2})(\d{2})(\d{2,4})', text, re.I)
    if m:
        y = int(m.group(3))
        if y < 100:
            y += 2000
        try:
            return dt.date(y, int(m.group(1)), int(m.group(2)))
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


def _scrape_pdf_page(source, source_label):
    """Shared PDF-list scraper used by wordpress, custom_php, and pdf_list."""
    html = fetch(source["url"])
    meetings = []
    pdf_links = re.findall(r'href="([^"]*\.pdf[^"]*)"', html, re.I)
    seen_dates = {}

    for link in pdf_links:
        full_url = urljoin(source["url"], link)
        filename = link.rsplit("/", 1)[-1]
        date = None
        if source_label == "custom_php":
            date = _parse_maine_date(filename)
        date = date or parse_date_from_text(filename) or parse_date_from_text(link)
        if not date or date.year < 2020 or date.year > 2030:
            continue
        if date not in seen_dates:
            seen_dates[date] = {"date": date, "agenda_url": None, "minutes_url": None}
        # filename only — path segments like "Agenda & Minutes/" false-positive
        name_lower = filename.lower()
        if "minute" in name_lower:
            seen_dates[date]["minutes_url"] = full_url
        elif "agenda" in name_lower or "packet" in name_lower or source_label == "pdf_list":
            # pdf_list: undated keyword-less PDFs with a parseable date still count as agendas
            if "agenda" in name_lower or "packet" in name_lower or "minute" not in name_lower:
                if not seen_dates[date]["agenda_url"] or "agenda" in name_lower:
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
            "source": source_label,
        })
    return meetings


def scrape_wordpress(source):
    """Scrape WordPress sites that list agenda PDFs via wp-content/uploads."""
    return _scrape_pdf_page(source, "wordpress")


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
    return _scrape_pdf_page(source, "custom_php")


def scrape_pdf_list(source):
    """Scrape generic pages that list dated PDF agendas/minutes."""
    return _scrape_pdf_page(source, "pdf_list")


SCRAPERS = {
    "civicplus": scrape_civicplus,
    "wordpress": scrape_wordpress,
    "custom_php": scrape_custom_php,
    "pdf_list": scrape_pdf_list,
}


def _source_from_row(row):
    """Build a scraper source dict from a units row (+ overrides)."""
    unit_id = row["id"]
    if unit_id in OVERRIDES:
        src = {"unit_id": unit_id, **OVERRIDES[unit_id]}
        return src

    platform = row["agenda_platform"]
    packet = row["packet_url"]
    if not platform or not packet or platform not in SCRAPERS:
        return None

    if platform == "civicplus":
        parsed = urlparse(packet)
        base = f"{parsed.scheme}://{parsed.netloc}"
        path = parsed.path or "/AgendaCenter"
        return {
            "unit_id": unit_id,
            "type": "civicplus",
            "base_url": base,
            "agenda_path": path,
        }

    return {"unit_id": unit_id, "type": platform, "url": packet}


def load_sources(conn, unit_id=None, unit_type=None, platform=None):
    """Load scrape targets from units.agenda_platform / packet_url."""
    platforms = [platform] if platform else list(SUPPORTED_PLATFORMS)
    sql = """
        select id, name, type, agenda_platform, packet_url, website
        from units
        where (
            (agenda_platform = any(%s) and packet_url is not null)
            or id = any(%s)
        )
    """
    params = [platforms, list(OVERRIDES.keys())]
    if unit_id:
        sql += " and id = %s"
        params.append(unit_id)
    if unit_type:
        sql += " and type = %s"
        params.append(unit_type)
    if platform:
        sql += " and (agenda_platform = %s or id = any(%s))"
        params.extend([platform, [
            uid for uid, ov in OVERRIDES.items() if ov["type"] == platform
        ]])
    sql += " order by type, name"
    rows = conn.execute(sql, params).fetchall()

    sources = []
    for row in rows:
        src = _source_from_row(row)
        if src and src["type"] in SCRAPERS:
            if platform and src["type"] != platform:
                continue
            sources.append(src)
    return sources


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
                agenda_doc_id = row["id"]

        minutes_doc_id = None
        if m.get("minutes_url"):
            conn.execute(
                "insert into documents (unit_id, kind, url) values (%s, 'minutes', %s) on conflict do nothing returning id",
                (m["unit_id"], m["minutes_url"]),
            )
            row = conn.execute("select id from documents where url = %s", (m["minutes_url"],)).fetchone()
            if row:
                minutes_doc_id = row["id"]

        existing = conn.execute(
            "select id from meetings where unit_id = %s and meeting_ts = %s",
            (m["unit_id"], m["meeting_ts"]),
        ).fetchone()
        if existing:
            conn.execute(
                "update meetings set status=%s, agenda_doc_id=%s, minutes_doc_id=%s where id=%s",
                (m["status"], agenda_doc_id, minutes_doc_id, existing["id"]),
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
    ap.add_argument("--type", help="limit to unit type (township, municipality, …)")
    ap.add_argument("--platform", help="limit to one agenda platform", choices=SUPPORTED_PLATFORMS)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = connect()
    apply_schema(conn)
    sources = load_sources(conn, unit_id=args.unit, unit_type=args.type, platform=args.platform)
    if args.unit and not sources:
        print(f"no scrapable source for {args.unit} "
              f"(need agenda_platform in {SUPPORTED_PLATFORMS} + packet_url)")
        return
    if not sources:
        print("no units with supported agenda_platform + packet_url")
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

    print(f"\ntotal: {len(all_meetings)} meetings across {len(sources)} units")
    save_meetings(all_meetings, dry_run=args.dry_run)


if __name__ == "__main__":
    main()

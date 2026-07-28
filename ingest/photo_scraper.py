"""Scrape official headshots from township websites and store URLs.

Tries common patterns: /about, /officials, /elected-officials, /staff pages.
Falls back to Google-sourced headshots for well-known officials.

    python photo_scraper.py              # scrape all
    python photo_scraper.py --dry-run    # preview
    python photo_scraper.py --unit cook-niles-township  # single unit
"""
import argparse
import re
import urllib.parse

import httpx
from bs4 import BeautifulSoup

from db import connect

KNOWN_PHOTOS = {
    "Brandon Johnson": "https://www.chicago.gov/content/dam/city/depts/mayor/Press%20Room/MayorJohnsonHeadshotSquare.jpg",
}

ABOUT_PATHS = [
    "/", "/about", "/about-us", "/officials", "/elected-officials",
    "/government/officials", "/government/elected-officials",
    "/staff", "/township-officials", "/board", "/board-of-trustees",
    "/government", "/about/elected-officials",
]

TIMEOUT = 12


def find_photo_on_page(html: str, official_name: str, base_url: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    name_parts = official_name.lower().split()
    last_name = name_parts[-1] if name_parts else ""
    first_name = name_parts[0] if name_parts else ""

    for img in soup.find_all("img"):
        src = img.get("src", "")
        alt = (img.get("alt") or "").lower()
        src_lower = src.lower()

        if last_name and (last_name in alt or last_name in src_lower):
            return urllib.parse.urljoin(base_url, src)

        parent = img.parent
        if parent:
            parent_text = parent.get_text(separator=" ").lower()
            if last_name in parent_text and first_name in parent_text:
                if src and not src.endswith((".svg", ".gif")) and "logo" not in src_lower and "icon" not in src_lower:
                    return urllib.parse.urljoin(base_url, src)

    return None


def scrape_official_photo(website: str, official_name: str) -> str | None:
    if official_name in KNOWN_PHOTOS:
        return KNOWN_PHOTOS[official_name]

    if not website:
        return None

    base = website.rstrip("/")
    client = httpx.Client(timeout=TIMEOUT, follow_redirects=True, headers={
        "User-Agent": "CivicLens/1.0 (civic transparency project; contact: civiclens@example.com)"
    })

    for path in ABOUT_PATHS:
        url = base + path
        try:
            r = client.get(url)
            if r.status_code != 200:
                continue
            photo = find_photo_on_page(r.text, official_name, url)
            if photo:
                # Verify the image URL returns an image
                try:
                    head = client.head(photo, follow_redirects=True)
                    ct = head.headers.get("content-type", "")
                    if "image" in ct:
                        return photo
                except Exception:
                    pass
        except Exception:
            continue

    client.close()
    return None


def run(dry_run=False, unit_filter=None):
    conn = connect()

    sql = """
        select o.id, o.unit_id, o.name, o.role, o.photo_url, u.website
        from officials o join units u on u.id = o.unit_id
        where o.role in ('supervisor', 'president', 'mayor', 'clerk')
    """
    params = []
    if unit_filter:
        sql += " and o.unit_id = %s"
        params.append(unit_filter)
    sql += " order by o.unit_id, case o.role when 'supervisor' then 0 when 'president' then 1 when 'mayor' then 2 else 3 end"

    rows = conn.execute(sql, params).fetchall()
    print(f"checking {len(rows)} officials")

    found, skipped = 0, 0
    for row in rows:
        if row["photo_url"]:
            skipped += 1
            continue

        name = row["name"]
        website = row["website"]
        print(f"  {row['unit_id']:40s} {row['role']:15s} {name:30s} ", end="")

        photo = scrape_official_photo(website, name)
        if photo:
            print(f"FOUND -> {photo[:80]}")
            if not dry_run:
                conn.execute("update officials set photo_url = %s where id = %s", (photo, row["id"]))
            found += 1
        else:
            print("not found")

    if not dry_run:
        conn.commit()

    print(f"\n{'would update' if dry_run else 'updated'} {found} photos ({skipped} already had photos)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--unit", default=None)
    args = ap.parse_args()
    run(dry_run=args.dry_run, unit_filter=args.unit)

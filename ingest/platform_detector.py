"""Detect which agenda platform each unit's website runs.

Cook County's 178 governments do not need 178 scrapers — most sit on a
handful of vendor platforms. This probes each unit's site, records the
platform in units.agenda_platform, and captures the agenda URL when the
platform exposes a predictable one, so meeting_scraper only needs an
adapter per platform.

    python platform_detector.py --dry-run
    python platform_detector.py
    python platform_detector.py --type municipality
"""
import argparse
import concurrent.futures as cf
import re
from urllib.parse import urljoin, urlparse

import httpx

from db import apply_schema, connect

HEADERS = {"User-Agent": "CivicLens/1.0 (civic transparency research; contact via GitHub)"}
TIMEOUT = 15
THIN_HTML = 500  # bytes — homepage too small to fingerprint (JS shells, etc.)

# Ordered: first match wins, so put distinctive fingerprints first.
# wordpress last — many vendor sites sit on WP underneath.
SIGNATURES = [
    ("civicplus",   [r"/AgendaCenter", r"civicplus\.com", r"CivicPlus"]),
    ("legistar",    [r"legistar\.com", r"\.legistar\b"]),
    ("granicus",    [r"granicus\.com", r"granicusideas"]),
    ("civicclerk",  [r"civicclerk\.com", r"\.civicweb\.net"]),
    ("boarddocs",   [r"boarddocs\.com"]),
    ("municode",    [r"municode\.com", r"municodemeetings"]),
    ("revize",      [r"revize\.com", r"revizeurl"]),
    ("novusagenda", [r"novusagenda\.com"]),
    ("wordpress",   [r"/wp-content/", r"/wp-includes/", r"wp-json"]),
]

# Common paths that hold agendas, tried in order.
AGENDA_PATHS = [
    "/AgendaCenter", "/agendacenter",
    "/agendas", "/agendas-minutes", "/agendas-and-minutes",
    "/meetings", "/meeting-agendas", "/board-meetings",
    "/government/agendas-minutes", "/government/meetings",
    "/minutes", "/public-meetings",
]

AGENDA_HINT = re.compile(r"agenda|minutes|meeting", re.I)

# Host/path patterns that override homepage CMS branding.
# Maine is CivicPlus-hosted but serves agendas via custom PHP.
URL_PLATFORM_RULES = [
    (r"legistar\.com|\.legistar\b", "legistar"),
    (r"granicus\.com|granicusideas", "granicus"),
    (r"civicclerk\.com|\.civicweb\.net", "civicclerk"),
    (r"boarddocs\.com", "boarddocs"),
    (r"municode\.com|municodemeetings", "municode"),
    (r"novusagenda\.com", "novusagenda"),
    (r"/AgendaCenter", "civicplus"),
    (r"\.php(?:$|\?)", "custom_php"),
]


def normalize(url: str) -> str:
    if not url:
        return ""
    if not urlparse(url).scheme:
        url = "http://" + url
    return url


def fingerprint(html: str) -> str | None:
    for platform, patterns in SIGNATURES:
        if any(re.search(p, html, re.I) for p in patterns):
            return platform
    return None


def platform_from_url(url: str) -> str | None:
    """Classify by agenda URL structure — beats CMS branding on the homepage."""
    if not url:
        return None
    for pattern, platform in URL_PLATFORM_RULES:
        if re.search(pattern, url, re.I):
            return platform
    return None


def count_dated_pdfs(html: str) -> int:
    """How many PDF links look like dated agenda/minutes docs."""
    n = 0
    for href in re.findall(r'href="([^"]*\.pdf[^"]*)"', html, re.I):
        if re.search(r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|_\d{8}-|"
                     r"(?:January|February|March|April|May|June|July|August|"
                     r"September|October|November|December)", href, re.I):
            n += 1
    return n


def find_agenda_link(html: str, base: str) -> str | None:
    for href, text in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.S | re.I):
        label = re.sub(r"<[^>]+>", " ", text)
        if AGENDA_HINT.search(label) or AGENDA_HINT.search(href):
            if re.search(r"agenda|minutes|meeting", href, re.I):
                return urljoin(base, href)
    return None


def probe_agenda_paths(base: str) -> str | None:
    for path in AGENDA_PATHS:
        candidate = urljoin(base, path)
        try:
            h = httpx.head(candidate, headers=HEADERS, timeout=8, follow_redirects=True)
            if h.status_code < 400:
                return str(h.url)
        except Exception:
            continue
    return None


def reclassify(platform: str | None, agenda_url: str | None, agenda_html: str | None = None) -> str:
    """Prefer agenda-URL structure over homepage CMS fingerprint."""
    from_url = platform_from_url(agenda_url or "")
    if from_url:
        return from_url

    # Homepage said CivicPlus (footer branding) but agenda page is plain PDFs / PHP.
    if platform == "civicplus" and agenda_url and "/AgendaCenter" not in (agenda_url or ""):
        if agenda_html is not None and count_dated_pdfs(agenda_html) >= 2:
            return "pdf_list"
        if agenda_url and agenda_url.lower().endswith(".php"):
            return "custom_php"

    if platform and platform != "unknown":
        # municode-on-wordpress etc.: keep the more specific non-wordpress hit
        return platform

    if agenda_html is not None and count_dated_pdfs(agenda_html) >= 2:
        return "pdf_list"

    if agenda_url:
        return "pdf_list"

    return platform or "unknown"


def probe(unit) -> dict:
    """Fetch a unit's homepage, fingerprint the platform, find an agenda link."""
    url = normalize(unit["website"])
    result = {"unit_id": unit["id"], "name": unit["name"], "type": unit["type"],
              "website": url, "platform": None, "agenda_url": None, "note": ""}
    if not url:
        result["note"] = "no website"
        return result

    try:
        r = httpx.get(url, headers=HEADERS, timeout=TIMEOUT, follow_redirects=True)
    except Exception as e:
        result["note"] = f"unreachable: {type(e).__name__}"
        return result

    if r.status_code >= 400:
        result["note"] = f"HTTP {r.status_code}"
        return result

    html = r.text
    final = str(r.url)
    result["website"] = final

    platform = fingerprint(html)
    if len(html) < THIN_HTML:
        platform = None  # don't trust a stub page

    result["agenda_url"] = find_agenda_link(html, final)
    if not result["agenda_url"]:
        result["agenda_url"] = probe_agenda_paths(final)

    agenda_html = None
    if result["agenda_url"]:
        # Fetch agenda page when we need it for pdf_list / reclassification.
        need_fetch = (
            platform in (None, "unknown", "civicplus", "wordpress", "revize")
            or platform_from_url(result["agenda_url"]) is None
        )
        if need_fetch:
            try:
                ar = httpx.get(result["agenda_url"], headers=HEADERS, timeout=TIMEOUT,
                               follow_redirects=True)
                if ar.status_code < 400:
                    agenda_html = ar.text
                    result["agenda_url"] = str(ar.url)
                    # Thin homepage may still have a real AgendaCenter behind it.
                    if not platform:
                        platform = fingerprint(agenda_html) or platform
            except Exception:
                pass

    result["platform"] = reclassify(platform or "unknown", result["agenda_url"], agenda_html)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--type", help="limit to one unit type")
    ap.add_argument("--workers", type=int, default=12)
    args = ap.parse_args()

    conn = connect()
    apply_schema(conn)

    sql = "select id, name, type, website from units where website is not null"
    params = []
    if args.type:
        sql += " and type = %s"
        params.append(args.type)
    sql += " order by type, name"
    units = conn.execute(sql, params).fetchall()
    print(f"probing {len(units)} sites with {args.workers} workers…\n")

    results = []
    with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for res in pool.map(probe, units):
            results.append(res)
            flag = "✓" if res["agenda_url"] else " "
            print(f" {flag} {res['name'][:26]:26s} {str(res['platform']):12s} "
                  f"{res['note'] or (res['agenda_url'] or '')[:60]}")

    print("\n── platform distribution ──")
    counts: dict[str, int] = {}
    for r in results:
        counts[r["platform"] or "no website"] = counts.get(r["platform"] or "no website", 0) + 1
    for p, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {str(p):14s} {n:4d}")

    with_agenda = [r for r in results if r["agenda_url"]]
    print(f"\nagenda URL found for {len(with_agenda)}/{len(results)}")

    if args.dry_run:
        print("\ndry run — no writes")
        return

    # Normalize legacy 'custom' label used by early seed data.
    conn.execute("update units set agenda_platform='custom_php' where agenda_platform='custom'")

    for r in results:
        if r["platform"] and r["platform"] != "unknown":
            conn.execute(
                "update units set agenda_platform=%s, packet_url=coalesce(%s, packet_url) where id=%s",
                (r["platform"], r["agenda_url"], r["unit_id"]),
            )
        elif r["agenda_url"]:
            conn.execute(
                "update units set packet_url=coalesce(%s, packet_url) where id=%s",
                (r["agenda_url"], r["unit_id"]),
            )
    conn.commit()
    print("committed")


if __name__ == "__main__":
    main()

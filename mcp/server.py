"""CivicLens Cook County — MCP server.

Exposes the same data as the REST API as MCP tools for Claude Desktop / Claude Code.
Runs over stdio (default) or streamable-http.

    # stdio (Claude Desktop)
    python mcp/server.py

    # HTTP
    python mcp/server.py --http --port 8080
"""
import datetime as dt
import hashlib
import json
import logging
import os
import re
import sys
import time

import httpx
import psycopg
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

log = logging.getLogger("civiclens")

VALID_METRICS = {"total_expenditures", "per_capita_expenditures", "fund_balance", "debt", "ga_spend"}
DB_STATEMENT_TIMEOUT_MS = 10_000  # 10 s — kill any query that runs longer
DB_POOL_TIMEOUT_S = 5  # max wait for a connection from the pool
GEOCODER_RETRIES = 3
GEOCODER_TIMEOUT_S = 10

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

GEOCODER = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
COMPTROLLER_URL = "https://illinoiscomptroller.gov/financial-reports-data/data-sets-portals/local-government-financial-databases"

mcp = FastMCP(
    "illinois-civic",
    instructions=(
        "CivicLens exposes public civic data for Cook County, Illinois. "
        "Every response includes a provenance block with source_url, as_of, and certainty. "
        "Always cite the as_of date and source when presenting data to users. "
        "Certainty levels: verified (official filing), extracted (parsed from PDF, may have errors), stale_risk (older than update cycle). "
        "AFR financial data is self-reported by governments and may contain filing errors. "
        "Officials data will change after the April 2027 consolidated election."
    ),
)

_pool = ConnectionPool(
    os.environ["DATABASE_URL"],
    min_size=1, max_size=5, max_idle=300,
    timeout=DB_POOL_TIMEOUT_S,
    check=ConnectionPool.check_connection,
    kwargs={
        "row_factory": dict_row,
        "options": f"-c statement_timeout={DB_STATEMENT_TIMEOUT_MS}",
    },
)

_geocode_cache: dict[str, dict] = {}


def get_conn():
    """Get a connection from the pool.  Raises PoolTimeout after DB_POOL_TIMEOUT_S."""
    return _pool.connection(timeout=DB_POOL_TIMEOUT_S)


def log_usage(tool: str, unit_id: str = None, params: dict = None):
    h = hashlib.sha256(json.dumps(params or {}, sort_keys=True).encode()).hexdigest()[:16]
    try:
        with get_conn() as conn:
            conn.execute(
                "insert into usage_events (surface, tool, unit_id, params_hash) values (%s,%s,%s,%s)",
                ("mcp", tool, unit_id, h),
            )
    except Exception:
        pass


def provenance(source_url=None, as_of=None, certainty="verified", note=None):
    p = {
        "source_url": source_url or "none",
        "as_of": str(as_of) if as_of else str(dt.date.today()),
        "certainty": certainty,
    }
    if note:
        p["note"] = note
    return p


def error_response(code, message, suggestion):
    return {
        "error": {"code": code, "message": message, "suggestion": suggestion},
        "provenance": provenance(note=message),
    }


def coverage_level(officials: int, afr_years: int, spend: int, meetings: int) -> str:
    if officials > 0 and afr_years > 0 and spend > 0 and meetings > 0:
        return "full"
    if officials > 0 and afr_years > 0 and meetings > 0:
        return "rich"
    if officials > 0 and afr_years > 0:
        return "core"
    if afr_years > 0 or officials > 0:
        return "partial"
    return "boundary_only"


COVERAGE_DESCRIPTIONS = {
    "full": "Officials, finances, line-item spending, and meeting data available.",
    "rich": "Officials, finances, and meeting data available. No line-item spending.",
    "core": "Officials and finances available. No meeting or spending detail.",
    "partial": "Limited data — only officials or finances loaded, not both.",
    "boundary_only": "Geographic boundary only — no financial, official, or meeting data yet.",
}


def _normalize_address(address: str) -> str:
    return re.sub(r"\s+", " ", address.strip().upper())


def geocode(address: str) -> dict | None:
    """Geocode an address via memory cache → DB cache → Census API (with retry).

    Returns {"matched_address", "lat", "lng"} or None if the address is
    genuinely unmatched.  Raises RuntimeError if the geocoder is unreachable
    after retries so callers can surface a clear message.
    """
    key = _normalize_address(address)
    if key in _geocode_cache:
        return _geocode_cache[key]

    # DB cache
    addr_hash = hashlib.sha256(key.encode()).hexdigest()[:32]
    try:
        with get_conn() as conn:
            row = conn.execute(
                "select matched_address, lat, lng from geocode_cache where addr_hash = %s",
                (addr_hash,),
            ).fetchone()
        if row:
            result = {"matched_address": row["matched_address"], "lat": row["lat"], "lng": row["lng"]}
            _geocode_cache[key] = result
            return result
    except Exception as exc:
        log.warning("geocode DB cache lookup failed: %s", exc)

    # Census API with retry + backoff
    last_exc = None
    for attempt in range(1, GEOCODER_RETRIES + 1):
        try:
            r = httpx.get(
                GEOCODER,
                params={"address": address, "benchmark": "Public_AR_Current", "format": "json"},
                timeout=GEOCODER_TIMEOUT_S,
            )
            r.raise_for_status()
            matches = r.json()["result"]["addressMatches"]
            break  # success
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            last_exc = exc
            if attempt < GEOCODER_RETRIES:
                backoff = 1.5 ** attempt
                log.warning("Geocoder attempt %d/%d failed (%s), retrying in %.1fs",
                            attempt, GEOCODER_RETRIES, exc, backoff)
                time.sleep(backoff)
        except httpx.HTTPStatusError as exc:
            last_exc = exc
            if attempt < GEOCODER_RETRIES and exc.response.status_code >= 500:
                time.sleep(1.5 ** attempt)
            else:
                raise RuntimeError(
                    f"Census geocoder returned HTTP {exc.response.status_code}. "
                    "This is an upstream issue — try again in a few minutes."
                ) from exc
        except Exception as exc:
            raise RuntimeError(
                f"Census geocoder returned unexpected data: {exc}"
            ) from exc
    else:
        raise RuntimeError(
            f"Census geocoder unreachable after {GEOCODER_RETRIES} attempts "
            f"(last error: {last_exc}). The service may be down — try again in a few minutes."
        )

    if not matches:
        return None

    m = matches[0]
    result = {"matched_address": m["matchedAddress"], "lat": m["coordinates"]["y"], "lng": m["coordinates"]["x"]}

    # persist to DB cache (best-effort)
    try:
        with get_conn() as conn:
            conn.execute(
                "insert into geocode_cache (addr_hash, input_address, matched_address, lat, lng) "
                "values (%s,%s,%s,%s,%s) on conflict do nothing",
                (addr_hash, address, result["matched_address"], result["lat"], result["lng"]),
            )
    except Exception as exc:
        log.warning("geocode cache write failed: %s", exc)

    _geocode_cache[key] = result
    return result


def serialize(obj):
    if isinstance(obj, (dt.date, dt.datetime)):
        return obj.isoformat()
    if isinstance(obj, (int, float, str, bool, type(None))):
        return obj
    if isinstance(obj, dict):
        return {k: serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [serialize(v) for v in obj]
    return str(obj)


def parse_unit_ids(unit_ids) -> list[str]:
    if isinstance(unit_ids, str):
        return [i.strip() for i in unit_ids.split(",") if i.strip()]
    if isinstance(unit_ids, list):
        out = []
        for item in unit_ids:
            if isinstance(item, str) and "," in item:
                out.extend(i.strip() for i in item.split(",") if i.strip())
            elif isinstance(item, str):
                out.append(item.strip())
        return out
    return []


def extract_ga_spend(fund_detail: dict) -> float | None:
    """General Assistance is a fund in township accounting, not a category."""
    if not fund_detail:
        return None
    rev_by_fund = fund_detail.get("revenues_by_fund", {})
    exp_by_fund = fund_detail.get("expenditures_by_fund", {})
    # In township AFR data, GA is tracked via the Enterprise fund (EP)
    # or may appear as a labeled fund "General Assistance" in our labeled data
    for key in ("General Assistance", "Enterprise"):
        if key in exp_by_fund:
            return exp_by_fund[key]
    return None


# ── Tools ──────────────────────────────────────────────────────────────


@mcp.tool()
def find_my_governments(address: str) -> dict:
    """Given a Cook County, IL street address, return every layer of local
    government the resident lives under (county, township, municipality,
    districts where loaded), with links to officials, finances, and meetings
    for each. This is the best starting tool when a user mentions an address.

    Example: find_my_governments("1225 Waukegan Rd, Glenview, IL")
    """
    try:
        loc = geocode(address)
    except RuntimeError as exc:
        return error_response("GEOCODER_UNAVAILABLE", str(exc),
                              "The Census geocoder may be down. Try again in a few minutes.")
    if not loc:
        return error_response("ADDRESS_NOT_FOUND",
                              f"Census geocoder found no match for '{address}'.",
                              "Check spelling; include city and IL.")
    with get_conn() as conn:
        rows = conn.execute(
            """
            select u.id, u.name, u.type, u.as_of, u.population,
                   (select count(*) from officials o where o.unit_id = u.id) as officials_count,
                   (select count(*) from afr_summaries a where a.unit_id = u.id) as afr_years,
                   (select max(fiscal_year) from afr_summaries a where a.unit_id = u.id) as latest_fy,
                   (select count(*) from spend_lines s where s.unit_id = u.id) as spend_lines,
                   (select count(*) from meetings m where m.unit_id = u.id) as meetings_count,
                   (select min(meeting_ts) from meetings m where m.unit_id = u.id and m.meeting_ts > now()) as next_meeting
            from units u
            where ST_Contains(u.geom, ST_SetSRID(ST_Point(%s, %s), 4326))
            order by case u.type when 'county' then 0 when 'township' then 1 when 'municipality' then 2 else 3 end
            """,
            (loc["lng"], loc["lat"]),
        ).fetchall()
    for r in rows:
        level = coverage_level(r["officials_count"], r["afr_years"], r["spend_lines"], r["meetings_count"])
        r["coverage_level"] = level
        r["coverage_note"] = COVERAGE_DESCRIPTIONS[level]
    log_usage("find_my_governments", params={"address": address})
    return serialize({
        "matched_address": loc["matched_address"],
        "point": {"lat": loc["lat"], "lng": loc["lng"]},
        "units": rows,
        "provenance": provenance(
            "https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html",
            max((r["as_of"] for r in rows), default=None),
            note="Boundaries from Census TIGER/Line; geocoding by Census Geocoder."),
    })


@mcp.tool()
def list_units(type: str = None, query: str = None, limit: int = 25) -> dict:
    """List or search governmental units in Cook County.

    Args:
        type: Filter by unit type: county, township, municipality, or special_district.
        query: Fuzzy name search, e.g. "North" matches Northfield Township.
        limit: Max results (default 25).
    """
    sql = "select id, name, type, website, population, as_of from units where true"
    params = []
    if type:
        sql += " and type = %s"
        params.append(type)
    if query:
        sql += " and name ilike %s"
        params.append(f"%{query}%")
    sql += " order by name limit %s"
    params.append(limit)
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    log_usage("list_units", params={"type": type, "query": query})
    return serialize({"units": rows})


@mcp.tool()
def get_unit(unit_id: str) -> dict:
    """Get a detailed profile for a single governmental unit.
    Includes data coverage flags (has_spend_detail, has_meetings),
    officials count, latest AFR year, and filing timeliness.

    Use list_units to find valid unit_id values.
    """
    with get_conn() as conn:
        u = conn.execute(
            """
            select id, name, type, county, website, fy_start, population, ioc_code,
                   agenda_platform, as_of,
                   (select count(*) from spend_lines s where s.unit_id = units.id) as spend_line_count,
                   (select count(*) from meetings m where m.unit_id = units.id) as meetings_count,
                   (select count(*) from officials o where o.unit_id = units.id) as officials_count,
                   (select count(*) from afr_summaries a where a.unit_id = units.id) as afr_years,
                   (select max(fiscal_year) from afr_summaries a where a.unit_id = units.id) as latest_afr_year,
                   (select filed_on_time from afr_summaries a where a.unit_id = units.id
                    order by fiscal_year desc limit 1) as latest_afr_filed_on_time
            from units where id = %s
            """,
            (unit_id,),
        ).fetchone()
    if not u:
        return error_response("UNIT_NOT_FOUND", f"No unit '{unit_id}'.",
                              "Use list_units to find valid unit ids.")
    level = coverage_level(u["officials_count"], u["afr_years"], u["spend_line_count"], u["meetings_count"])
    u["coverage_level"] = level
    u["coverage_note"] = COVERAGE_DESCRIPTIONS[level]
    u["has_spend_detail"] = u["spend_line_count"] > 0
    u["has_meetings"] = u["meetings_count"] > 0
    log_usage("get_unit", unit_id=unit_id)
    u["provenance"] = provenance(u.get("website") or COMPTROLLER_URL, u["as_of"])
    return serialize(u)


@mcp.tool()
def get_officials(unit_id: str) -> dict:
    """Get elected/appointed officials for a governmental unit.
    Returns role, name, contact info, term end date, and data certainty.

    IMPORTANT: Always state the as_of date when reporting who holds office.
    The April 2027 consolidated election will change these rows.
    Officials are currently loaded for townships only.
    """
    with get_conn() as conn:
        u = conn.execute("select id from units where id=%s", (unit_id,)).fetchone()
        if not u:
            return error_response("UNIT_NOT_FOUND", f"No unit '{unit_id}'.",
                                  "Use list_units to find valid unit ids.")
        rows = conn.execute(
            """select role, name, email, phone, term_end, certainty, source_url, as_of
               from officials where unit_id = %s
               order by case role when 'supervisor' then 0 when 'clerk' then 1 else 2 end, role, name""",
            (unit_id,),
        ).fetchall()
    log_usage("get_officials", unit_id=unit_id)
    if not rows:
        return serialize({
            "unit_id": unit_id,
            "officials": [],
            "note": "No officials on file. Officials data is currently loaded for townships only.",
            "provenance": provenance(note="No officials data for this unit."),
        })
    return serialize({
        "unit_id": unit_id,
        "officials": rows,
        "provenance": provenance(
            rows[0]["source_url"], max(r["as_of"] for r in rows),
            certainty=rows[0]["certainty"],
            note="State the as_of date when reporting who holds office; the April 2027 consolidated election will change these rows."),
    })


@mcp.tool()
def get_finances(unit_id: str, fiscal_year: int = None, years_back: int = 1) -> dict:
    """Get Annual Financial Report (AFR) summaries for a governmental unit.
    Returns total revenues, expenditures, fund balance, per-capita figures,
    and detailed breakdowns by fund type and spending category.

    IMPORTANT: AFR data is self-reported and may contain filing errors.
    Fiscal years may differ across units. Always note these caveats.

    Args:
        unit_id: The unit to query.
        fiscal_year: Specific year (omit for latest).
        years_back: Number of years for trend data (default 1).
    """
    with get_conn() as conn:
        u = conn.execute("select id, population from units where id=%s", (unit_id,)).fetchone()
        if not u:
            return error_response("UNIT_NOT_FOUND", f"No unit '{unit_id}'.",
                                  "Use list_units to find valid unit ids.")
        sql = """select fiscal_year, total_revenues, total_expenditures, fund_balance,
                        total_debt, fund_detail, filed_on_time, source_url
                 from afr_summaries where unit_id = %s"""
        params = [unit_id]
        if fiscal_year:
            sql += " and fiscal_year <= %s"
            params.append(fiscal_year)
        sql += " order by fiscal_year desc limit %s"
        params.append(max(years_back, 1))
        rows = conn.execute(sql, params).fetchall()
    if not rows:
        return error_response("NO_FINANCES", f"No AFR data on file for '{unit_id}'.",
                              "AFR filings lag a year or more; check data_freshness.")
    pop = u["population"]
    caveats = ["AFR data is self-reported by the government and may contain filing errors."]
    for r in rows:
        if pop and r["total_expenditures"] is not None:
            r["per_capita_expenditures"] = round(float(r["total_expenditures"]) / pop, 2)
        if pop and r["total_revenues"] is not None:
            r["per_capita_revenues"] = round(float(r["total_revenues"]) / pop, 2)
        if not pop:
            caveats.append(f"No population data — per-capita figures unavailable for FY{r['fiscal_year']}.")
        if r.get("filed_on_time") is False:
            caveats.append(f"FY{r['fiscal_year']} AFR was filed late, which may indicate data quality issues.")
    log_usage("get_finances", unit_id=unit_id, params={"fiscal_year": fiscal_year})
    return serialize({
        "unit_id": unit_id,
        "years": rows,
        "caveats": list(dict.fromkeys(caveats)),
        "provenance": provenance(
            rows[0]["source_url"], f"FY{rows[0]['fiscal_year']}",
            note="Self-reported Annual Financial Report data; may contain filing errors."),
    })


@mcp.tool()
def get_spending_detail(
    unit_id: str,
    fiscal_year: int = None,
    fund: str = None,
    category: str = None,
    vendor: str = None,
    min_amount: float = None,
    group_by: str = "vendor",
    limit: int = 50,
) -> dict:
    """Get warrant-register level spending detail for instrumented units.
    This is the line-item expenditure data — who got paid, how much, from which fund.

    Only available for a subset of townships with extracted warrant data.
    If no data exists, falls back to get_finances for AFR-level summaries.

    Args:
        unit_id: The unit to query.
        fiscal_year: Filter by fiscal year.
        fund: Filter by fund name.
        category: Filter by spending category.
        vendor: Fuzzy match on vendor name.
        min_amount: Minimum dollar amount.
        group_by: One of: vendor, fund, category, month, none (default: vendor).
        limit: Max results (default 50).
    """
    with get_conn() as conn:
        u = conn.execute("select id from units where id=%s", (unit_id,)).fetchone()
        if not u:
            return error_response("UNIT_NOT_FOUND", f"No unit '{unit_id}'.",
                                  "Use list_units to find valid unit ids.")
        sql = "select * from spend_lines where unit_id = %s"
        params = [unit_id]
        if fiscal_year:
            sql += " and extract(year from meeting_date) = %s"
            params.append(fiscal_year)
        if fund:
            sql += " and fund ilike %s"
            params.append(f"%{fund}%")
        if category:
            sql += " and category ilike %s"
            params.append(f"%{category}%")
        if vendor:
            sql += " and (vendor_canon ilike %s or vendor_raw ilike %s)"
            params.extend([f"%{vendor}%", f"%{vendor}%"])
        if min_amount:
            sql += " and amount >= %s"
            params.append(min_amount)
        sql += " order by amount desc limit %s"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    log_usage("get_spending_detail", unit_id=unit_id, params={"fiscal_year": fiscal_year, "vendor": vendor})
    if not rows:
        return serialize({
            "unit_id": unit_id,
            "lines": [],
            "note": "No warrant-level spend data for this unit. Warrant data exists only for instrumented units. Use get_finances for AFR-level summaries.",
            "provenance": provenance(note="No spend data available."),
        })
    return serialize({"unit_id": unit_id, "lines": rows,
                      "provenance": provenance(COMPTROLLER_URL, rows[0].get("meeting_date"), certainty="extracted")})


@mcp.tool()
def top_vendors(unit_id: str, fiscal_year: int = None, n: int = 10) -> dict:
    """Get the top N vendors by total spend for a unit.
    Shows total amount, percentage of tracked spend, and which funds they appear in.
    Only available for units with warrant-register data.

    Args:
        unit_id: The unit to query.
        fiscal_year: Filter by fiscal year (omit for all available).
        n: Number of top vendors to return (default 10).
    """
    with get_conn() as conn:
        sql = """
            select coalesce(vendor_canon, vendor_raw) as vendor,
                   sum(amount) as total, count(*) as line_count,
                   array_agg(distinct fund) filter (where fund is not null) as funds
            from spend_lines where unit_id = %s
        """
        params = [unit_id]
        if fiscal_year:
            sql += " and extract(year from meeting_date) = %s"
            params.append(fiscal_year)
        sql += " group by 1 order by 2 desc limit %s"
        params.append(n)
        rows = conn.execute(sql, params).fetchall()
        total_row = conn.execute(
            "select sum(amount) as total from spend_lines where unit_id = %s" +
            (" and extract(year from meeting_date) = %s" if fiscal_year else ""),
            params[:2] if fiscal_year else params[:1],
        ).fetchone()
        total_spend = total_row["total"] if total_row else None
    if not rows:
        return serialize({
            "unit_id": unit_id,
            "total_tracked_spend": None,
            "vendors": [],
            "note": "No warrant-level spend data for this unit. Use get_finances for AFR-level summaries.",
            "provenance": provenance(note="No spend data available."),
        })
    for r in rows:
        if total_spend:
            r["pct_of_total"] = round(float(r["total"]) / float(total_spend) * 100, 1)
    log_usage("top_vendors", unit_id=unit_id, params={"fiscal_year": fiscal_year})
    return serialize({"unit_id": unit_id, "total_tracked_spend": total_spend, "vendors": rows})


@mcp.tool()
def compare_units(unit_ids: list[str], metric: str, fiscal_year: int = None) -> dict:
    """Compare up to 8 governmental units on a single financial metric.

    IMPORTANT: AFR data is self-reported; fiscal years may differ across units.
    Always note both caveats when presenting comparison results.

    Args:
        unit_ids: List of unit IDs to compare (max 8). Also accepts a comma-separated string.
        metric: One of: total_expenditures, per_capita_expenditures, fund_balance, debt, ga_spend.
        fiscal_year: Compare at a specific year (omit for latest available per unit).
    """
    ids = parse_unit_ids(unit_ids)[:8]
    if not ids:
        return error_response("MISSING_PARAM", "No valid unit IDs provided.",
                              "Use list_units to find valid unit ids, then pass as a list.")
    if metric not in VALID_METRICS:
        return error_response("INVALID_METRIC",
                              f"Unknown metric '{metric}'.",
                              f"Valid metrics: {', '.join(sorted(VALID_METRICS))}")
    col = {"debt": "total_debt"}.get(metric, metric)
    results = []
    with get_conn() as conn:
        for uid in ids:
            row = conn.execute(
                """
                select a.unit_id, u.name, u.population, a.fiscal_year, a.total_expenditures,
                       a.fund_balance, a.total_debt, a.fund_detail
                from afr_summaries a join units u on u.id = a.unit_id
                where a.unit_id = %s and (%s::int is null or a.fiscal_year = %s)
                order by a.fiscal_year desc limit 1
                """,
                (uid, fiscal_year, fiscal_year),
            ).fetchone()
            if not row:
                name_row = conn.execute("select name from units where id = %s", (uid,)).fetchone()
                results.append({"unit_id": uid, "name": name_row["name"] if name_row else uid,
                                "fiscal_year": None, "value": None, "note": "no AFR data"})
                continue
            if metric == "per_capita_expenditures":
                val = round(float(row["total_expenditures"]) / row["population"], 2) \
                    if row["population"] and row["total_expenditures"] else None
            elif metric == "ga_spend":
                val = extract_ga_spend(row["fund_detail"])
            else:
                val = row.get(col)
            results.append({"unit_id": uid, "name": row["name"], "fiscal_year": row["fiscal_year"], "value": val})
    caveats = ["AFR data is self-reported by each government and may contain filing errors."]
    fiscal_years = {r["fiscal_year"] for r in results if r.get("fiscal_year")}
    if len(fiscal_years) > 1:
        fy_list = ", ".join(f"FY{fy}" for fy in sorted(fiscal_years))
        caveats.append(
            f"WARNING: These units are reporting different fiscal years ({fy_list}). "
            "Direct comparison may be misleading — consider filtering to a single fiscal_year."
        )
    missing = [r["name"] for r in results if r.get("value") is None]
    if missing:
        caveats.append(f"No data available for: {', '.join(missing)}.")
    if metric == "per_capita_expenditures":
        no_pop = [r["name"] for r in results if r.get("value") is None and r.get("fiscal_year")]
        if no_pop:
            caveats.append(f"Per-capita calculation requires population data, which is missing for some units.")
    log_usage("compare_units", params={"unit_ids": ids, "metric": metric})
    return serialize({
        "metric": metric,
        "results": results,
        "caveats": caveats,
        "provenance": provenance(
            COMPTROLLER_URL, fiscal_year or "latest per unit",
            note="AFR data is self-reported; fiscal years may differ across units."),
    })


@mcp.tool()
def upcoming_meetings(unit_id: str = None, address: str = None, days_ahead: int = 30) -> dict:
    """Find upcoming public meetings for a unit or address.
    Use this when someone asks "when can I show up and speak" or wants to attend a board meeting.

    Args:
        unit_id: Look up meetings for this unit (provide either unit_id or address).
        address: Find meetings for all governments at this address.
        days_ahead: How far ahead to look (default 30, max 365).
    """
    days_ahead = max(1, min(days_ahead, 365))

    unit_ids = []
    if address:
        try:
            loc = geocode(address)
        except RuntimeError as exc:
            return error_response("GEOCODER_UNAVAILABLE", str(exc),
                                  "The Census geocoder may be down. Try again in a few minutes.")
        if not loc:
            return error_response("ADDRESS_NOT_FOUND",
                                  f"Census geocoder found no match for '{address}'.",
                                  "Check spelling; include city and IL.")
        with get_conn() as conn:
            rows = conn.execute(
                "select id from units where ST_Contains(geom, ST_SetSRID(ST_Point(%s,%s),4326))",
                (loc["lng"], loc["lat"]),
            ).fetchall()
        unit_ids = [r["id"] for r in rows]
    elif unit_id:
        unit_ids = [unit_id]
    else:
        return error_response("MISSING_PARAM", "Provide either unit_id or address.",
                              "Use find_my_governments first to get unit IDs.")

    with get_conn() as conn:
        rows = conn.execute(
            """
            select m.id, u.name as unit_name, m.body, m.meeting_ts, m.status,
                   d.url as agenda_url
            from meetings m
            join units u on u.id = m.unit_id
            left join documents d on d.id = m.agenda_doc_id
            where m.unit_id = any(%s)
              and m.meeting_ts between now() and now() + make_interval(days => %s)
            order by m.meeting_ts
            """,
            (unit_ids, days_ahead),
        ).fetchall()
    log_usage("upcoming_meetings", params={"unit_ids": unit_ids})
    if not rows:
        return serialize({
            "meetings": [],
            "note": "No upcoming meetings found. Meeting data coverage varies by unit; check data_freshness.",
            "provenance": provenance(note="No meeting data returned."),
        })
    return serialize({
        "meetings": rows,
        "provenance": provenance(note="Meeting data coverage varies by unit."),
    })


@mcp.tool()
def search_meetings(
    query: str,
    unit_id: str = None,
    topic: str = None,
    after: str = None,
    before: str = None,
    limit: int = 20,
) -> dict:
    """Full-text search over meeting agendas and minutes.
    Find when topics like 'cannabis', 'senior transportation', or 'TIF' were discussed.

    Args:
        query: Search terms, e.g. 'cannabis', 'budget amendment'.
        unit_id: Limit search to one unit (omit to search county-wide).
        topic: Filter by topic taxonomy.
        after: Only meetings after this date (YYYY-MM-DD).
        before: Only meetings before this date (YYYY-MM-DD).
        limit: Max results (default 20).
    """
    sql = """
        select ai.id, ai.item_no, ai.title, ai.topic, ai.action,
               m.meeting_ts, m.body, u.name as unit_name, u.id as unit_id,
               d.url as source_url
        from agenda_items ai
        join meetings m on m.id = ai.meeting_id
        join units u on u.id = m.unit_id
        left join documents d on d.id = m.agenda_doc_id
        where ai.fts @@ plainto_tsquery('english', %s)
    """
    params = [query]
    if unit_id:
        sql += " and m.unit_id = %s"
        params.append(unit_id)
    if topic:
        sql += " and ai.topic = %s"
        params.append(topic)
    if after:
        sql += " and m.meeting_ts >= %s"
        params.append(after)
    if before:
        sql += " and m.meeting_ts <= %s"
        params.append(before)
    sql += " order by m.meeting_ts desc limit %s"
    params.append(limit)
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    log_usage("search_meetings", params={"query": query, "unit_id": unit_id})
    return serialize({
        "query": query,
        "results": rows,
        "note": "Action field (approved/denied/tabled) is best-effort extraction, marked 'extracted'. v1 promises search, not vote records.",
        "provenance": provenance(COMPTROLLER_URL, dt.date.today(), certainty="extracted"),
    })


@mcp.tool()
def get_document(doc_id: int) -> dict:
    """Retrieve a source document's extracted text and metadata.
    Use this to quote directly from meeting minutes or agenda packets.

    Args:
        doc_id: The document ID (from meeting or agenda_item results).
    """
    with get_conn() as conn:
        doc = conn.execute(
            "select id, unit_id, kind, url, fetched_at, extracted_text, pages from documents where id = %s",
            (doc_id,),
        ).fetchone()
    if not doc:
        return error_response("DOC_NOT_FOUND", f"No document with id {doc_id}.",
                              "Document IDs come from meeting and search results.")
    log_usage("get_document", params={"doc_id": doc_id})
    return serialize(doc)


@mcp.tool()
def data_freshness(unit_id: str = None) -> dict:
    """Check how fresh the data is — per-table row counts and latest dates.
    Use this tool when you're unsure whether data exists for a unit, or to
    set expectations about data coverage.

    This is also the trust tool: it tells users exactly what we have and don't have.

    Args:
        unit_id: Check freshness for a specific unit (omit for system-wide).
    """
    with get_conn() as conn:
        out = {}
        w, p = ("where unit_id = %s", (unit_id,)) if unit_id else ("", ())
        out["units"] = conn.execute(
            f"select count(*) as rows, max(as_of) as as_of from units {w.replace('unit_id', 'id')}", p).fetchone()
        out["officials"] = conn.execute(
            f"select count(*) as rows, max(as_of) as as_of from officials {w}", p).fetchone()
        out["afr_summaries"] = conn.execute(
            f"select count(*) as rows, max(fiscal_year) as latest_fy from afr_summaries {w}", p).fetchone()
        out["spend_lines"] = conn.execute(
            f"select count(*) as rows, max(meeting_date) as latest from spend_lines {w}", p).fetchone()
        out["meetings"] = conn.execute(
            f"select count(*) as rows, max(meeting_ts) as latest from meetings {w}", p).fetchone()
    log_usage("data_freshness", unit_id=unit_id)
    return serialize(out)


if __name__ == "__main__":
    if "--http" in sys.argv:
        import argparse
        ap = argparse.ArgumentParser()
        ap.add_argument("--http", action="store_true")
        ap.add_argument("--port", type=int, default=8080)
        args = ap.parse_args()
        mcp.run(transport="streamable-http", host="0.0.0.0", port=args.port)
    else:
        mcp.run(transport="stdio")

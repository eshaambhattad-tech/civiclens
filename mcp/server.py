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
import os
import re
import sys

import httpx
import psycopg
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

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
    check=ConnectionPool.check_connection,
    kwargs={"row_factory": dict_row},
)

# geocode cache: normalized address hash → {matched_address, lat, lng}
_geocode_cache: dict[str, dict] = {}


def get_conn():
    return _pool.connection()


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


def _normalize_address(address: str) -> str:
    return re.sub(r"\s+", " ", address.strip().upper())


def geocode(address: str):
    key = _normalize_address(address)
    if key in _geocode_cache:
        return _geocode_cache[key]

    # check DB cache
    addr_hash = hashlib.sha256(key.encode()).hexdigest()[:32]
    with get_conn() as conn:
        row = conn.execute(
            "select matched_address, lat, lng from geocode_cache where addr_hash = %s",
            (addr_hash,),
        ).fetchone()
    if row:
        result = {"matched_address": row["matched_address"], "lat": row["lat"], "lng": row["lng"]}
        _geocode_cache[key] = result
        return result

    try:
        r = httpx.get(GEOCODER, params={"address": address, "benchmark": "Public_AR_Current", "format": "json"}, timeout=15)
        r.raise_for_status()
        matches = r.json()["result"]["addressMatches"]
    except Exception:
        return None
    if not matches:
        return None
    m = matches[0]
    result = {"matched_address": m["matchedAddress"], "lat": m["coordinates"]["y"], "lng": m["coordinates"]["x"]}

    # persist to DB
    try:
        with get_conn() as conn:
            conn.execute(
                "insert into geocode_cache (addr_hash, input_address, matched_address, lat, lng) values (%s,%s,%s,%s,%s) on conflict do nothing",
                (addr_hash, address, result["matched_address"], result["lat"], result["lng"]),
            )
    except Exception:
        pass

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
    loc = geocode(address)
    if not loc:
        return error_response("ADDRESS_NOT_FOUND",
                              f"Census geocoder found no match for '{address}'.",
                              "Check spelling; include city and IL.")
    with get_conn() as conn:
        rows = conn.execute(
            """
            select u.id, u.name, u.type, u.as_of,
                   (select count(*) from officials o where o.unit_id = u.id) as officials_count,
                   (select max(fiscal_year) from afr_summaries a where a.unit_id = u.id) as latest_fy,
                   (select min(meeting_ts) from meetings m where m.unit_id = u.id and m.meeting_ts > now()) as next_meeting
            from units u
            where ST_Contains(u.geom, ST_SetSRID(ST_Point(%s, %s), 4326))
            order by case u.type when 'county' then 0 when 'township' then 1 when 'municipality' then 2 else 3 end
            """,
            (loc["lng"], loc["lat"]),
        ).fetchall()
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
                   exists(select 1 from spend_lines s where s.unit_id = units.id) as has_spend_detail,
                   exists(select 1 from meetings m where m.unit_id = units.id) as has_meetings,
                   (select count(*) from officials o where o.unit_id = units.id) as officials_count,
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
    if not rows:
        return error_response("NO_OFFICIALS", f"No officials on file for '{unit_id}'.",
                              "Officials are loaded for townships only in v1; check data_freshness.")
    log_usage("get_officials", unit_id=unit_id)
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
    for r in rows:
        if pop and r["total_expenditures"] is not None:
            r["per_capita_expenditures"] = round(float(r["total_expenditures"]) / pop, 2)
        if pop and r["total_revenues"] is not None:
            r["per_capita_revenues"] = round(float(r["total_revenues"]) / pop, 2)
    log_usage("get_finances", unit_id=unit_id, params={"fiscal_year": fiscal_year})
    return serialize({
        "unit_id": unit_id,
        "years": rows,
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
    if not rows:
        return error_response("NO_SPEND_DETAIL",
                              f"No warrant-level spend data for '{unit_id}'.",
                              "Warrant data exists only for instrumented units. Use get_finances for AFR-level summaries.")
    log_usage("get_spending_detail", unit_id=unit_id, params={"fiscal_year": fiscal_year, "vendor": vendor})
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
        return error_response("NO_SPEND_DETAIL",
                              f"No warrant-level spend data for '{unit_id}'.",
                              "Use get_finances for AFR-level summaries.")
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
                results.append({"unit_id": uid, "value": None, "note": "no AFR data"})
                continue
            if metric == "per_capita_expenditures":
                val = round(float(row["total_expenditures"]) / row["population"], 2) \
                    if row["population"] and row["total_expenditures"] else None
            elif metric == "ga_spend":
                val = extract_ga_spend(row["fund_detail"])
            else:
                val = row.get(col)
            results.append({"unit_id": uid, "name": row["name"], "fiscal_year": row["fiscal_year"], "value": val})
    log_usage("compare_units", params={"unit_ids": ids, "metric": metric})
    return serialize({
        "metric": metric,
        "results": results,
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
        loc = geocode(address)
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

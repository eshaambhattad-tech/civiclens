import hashlib
import json
import os
import re
from contextlib import asynccontextmanager

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from psycopg_pool import AsyncConnectionPool
from psycopg.rows import dict_row

load_dotenv()

GEOCODER = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
COMPTROLLER_URL = "https://illinoiscomptroller.gov/financial-reports-data/data-sets-portals/local-government-financial-databases"

pool: AsyncConnectionPool = None
_geocode_cache: dict[str, dict] = {}


@asynccontextmanager
async def lifespan(app):
    global pool
    pool = AsyncConnectionPool(os.environ["DATABASE_URL"], open=False, max_idle=120,
                               check=AsyncConnectionPool.check_connection,
                               kwargs={"row_factory": dict_row})
    await pool.open()
    yield
    await pool.close()


app = FastAPI(title="CivicLens Cook County", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


async def log_usage(request: Request, tool: str, unit_id: str = None, params: dict = None):
    h = hashlib.sha256(json.dumps(params or {}, sort_keys=True).encode()).hexdigest()[:16]
    try:
        async with pool.connection() as conn:
            await conn.execute(
                "insert into usage_events (surface, tool, unit_id, params_hash) values (%s,%s,%s,%s)",
                (request.headers.get("x-surface", "web"), tool, unit_id, h),
            )
    except Exception:
        pass


def provenance(source_url=None, as_of=None, certainty="verified", note=None):
    p = {"source_url": source_url or "none", "as_of": str(as_of) if as_of else "unknown", "certainty": certainty}
    if note:
        p["note"] = note
    return p


def err(code, message, suggestion):
    raise HTTPException(status_code=404 if "NOT_FOUND" in code else 400,
                        detail={"error": {"code": code, "message": message, "suggestion": suggestion},
                                "provenance": provenance(note=message)})


def _normalize_address(address: str) -> str:
    return re.sub(r"\s+", " ", address.strip().upper())


async def geocode(address: str):
    key = _normalize_address(address)
    if key in _geocode_cache:
        return _geocode_cache[key]

    addr_hash = hashlib.sha256(key.encode()).hexdigest()[:32]
    async with pool.connection() as conn:
        row = await (await conn.execute(
            "select matched_address, lat, lng from geocode_cache where addr_hash = %s",
            (addr_hash,),
        )).fetchone()
    if row:
        result = {"matched_address": row["matched_address"], "lat": row["lat"], "lng": row["lng"]}
        _geocode_cache[key] = result
        return result

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(GEOCODER, params={"address": address, "benchmark": "Public_AR_Current", "format": "json"})
            r.raise_for_status()
        matches = r.json()["result"]["addressMatches"]
    except Exception:
        return None
    if not matches:
        return None
    m = matches[0]
    result = {"matched_address": m["matchedAddress"], "lat": m["coordinates"]["y"], "lng": m["coordinates"]["x"]}

    try:
        async with pool.connection() as conn:
            await conn.execute(
                "insert into geocode_cache (addr_hash, input_address, matched_address, lat, lng) values (%s,%s,%s,%s,%s) on conflict do nothing",
                (addr_hash, address, result["matched_address"], result["lat"], result["lng"]),
            )
    except Exception:
        pass

    _geocode_cache[key] = result
    return result


def extract_ga_spend(fund_detail: dict) -> float | None:
    if not fund_detail:
        return None
    exp_by_fund = fund_detail.get("expenditures_by_fund", {})
    for key in ("General Assistance", "Enterprise"):
        if key in exp_by_fund:
            return exp_by_fund[key]
    return None


@app.get("/governments")
async def find_my_governments(request: Request, address: str = Query(...)):
    loc = await geocode(address)
    if not loc:
        err("ADDRESS_NOT_FOUND", f"Census geocoder found no match for '{address}'.",
            "Check spelling; include city and IL, e.g. '1225 Waukegan Rd, Glenview, IL'.")
    async with pool.connection() as conn:
        rows = await (await conn.execute(
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
        )).fetchall()
    await log_usage(request, "find_my_governments", params={"address": address})
    return {
        "matched_address": loc["matched_address"],
        "point": {"lat": loc["lat"], "lng": loc["lng"]},
        "units": rows,
        "provenance": provenance("https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html",
                                 max((r["as_of"] for r in rows), default=None),
                                 note="Boundaries from Census TIGER/Line; geocoding by Census Geocoder."),
    }


@app.get("/units")
async def list_units(request: Request, type: str = None, query: str = None, limit: int = 25):
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
    async with pool.connection() as conn:
        rows = await (await conn.execute(sql, params)).fetchall()
    await log_usage(request, "list_units", params={"type": type, "query": query})
    return {"units": rows}


@app.get("/units/geojson")
async def units_geojson(request: Request, type: str = None):
    sql = """
        select id, name, type, population, website,
               ST_AsGeoJSON(geom)::json as geometry,
               (select max(fiscal_year) from afr_summaries a where a.unit_id = units.id) as latest_fy,
               (select count(*) from officials o where o.unit_id = units.id) as officials_count
        from units where geom is not null
    """
    params = []
    if type:
        sql += " and type = %s"
        params.append(type)
    sql += " order by name"
    async with pool.connection() as conn:
        rows = await (await conn.execute(sql, params)).fetchall()
    features = []
    for r in rows:
        features.append({
            "type": "Feature",
            "properties": {
                "id": r["id"],
                "name": r["name"],
                "unit_type": r["type"],
                "population": r["population"],
                "website": r["website"],
                "latest_fy": r["latest_fy"],
                "officials_count": r["officials_count"],
            },
            "geometry": r["geometry"],
        })
    await log_usage(request, "units_geojson", params={"type": type})
    return {"type": "FeatureCollection", "features": features}


@app.get("/units/{unit_id}")
async def get_unit(request: Request, unit_id: str):
    async with pool.connection() as conn:
        u = await (await conn.execute(
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
        )).fetchone()
    if not u:
        err("UNIT_NOT_FOUND", f"No unit '{unit_id}'.", "Use /units to list valid unit ids.")
    await log_usage(request, "get_unit", unit_id=unit_id)
    u["provenance"] = provenance(u.get("website") or COMPTROLLER_URL, u["as_of"])
    return u


@app.get("/units/{unit_id}/officials")
async def get_officials(request: Request, unit_id: str):
    async with pool.connection() as conn:
        u = await (await conn.execute("select id from units where id=%s", (unit_id,))).fetchone()
        if not u:
            err("UNIT_NOT_FOUND", f"No unit '{unit_id}'.", "Use /units to list valid unit ids.")
        rows = await (await conn.execute(
            """select role, name, email, phone, term_end, certainty, source_url, as_of
               from officials where unit_id = %s
               order by case role when 'supervisor' then 0 when 'clerk' then 1 else 2 end, role, name""",
            (unit_id,),
        )).fetchall()
    if not rows:
        err("NO_OFFICIALS", f"No officials on file for '{unit_id}'.",
            "Officials are loaded for townships only in v1; check data_freshness.")
    await log_usage(request, "get_officials", unit_id=unit_id)
    return {
        "unit_id": unit_id,
        "officials": rows,
        "provenance": provenance(rows[0]["source_url"], max(r["as_of"] for r in rows),
                                 certainty=rows[0]["certainty"],
                                 note="State the as_of date when reporting who holds office; the April 2027 consolidated election will change these rows."),
    }


@app.get("/units/{unit_id}/finances")
async def get_finances(request: Request, unit_id: str, fiscal_year: int = None, years_back: int = 1):
    async with pool.connection() as conn:
        u = await (await conn.execute("select id, population from units where id=%s", (unit_id,))).fetchone()
        if not u:
            err("UNIT_NOT_FOUND", f"No unit '{unit_id}'.", "Use /units to list valid unit ids.")
        sql = """select fiscal_year, total_revenues, total_expenditures, fund_balance,
                        total_debt, fund_detail, filed_on_time, source_url
                 from afr_summaries where unit_id = %s"""
        params = [unit_id]
        if fiscal_year:
            sql += " and fiscal_year <= %s"
            params.append(fiscal_year)
        sql += " order by fiscal_year desc limit %s"
        params.append(max(years_back, 1))
        rows = await (await conn.execute(sql, params)).fetchall()
    if not rows:
        err("NO_FINANCES", f"No AFR data on file for '{unit_id}'.",
            "AFR filings lag a year or more; check data_freshness.")
    pop = u["population"]
    for r in rows:
        if pop and r["total_expenditures"] is not None:
            r["per_capita_expenditures"] = round(float(r["total_expenditures"]) / pop, 2)
        if pop and r["total_revenues"] is not None:
            r["per_capita_revenues"] = round(float(r["total_revenues"]) / pop, 2)
    await log_usage(request, "get_finances", unit_id=unit_id, params={"fiscal_year": fiscal_year})
    return {
        "unit_id": unit_id,
        "years": rows,
        "provenance": provenance(rows[0]["source_url"], f"FY{rows[0]['fiscal_year']}",
                                 note="Self-reported Annual Financial Report data; may contain filing errors."),
    }


@app.get("/compare")
async def compare_units(request: Request, unit_ids: str = Query(..., description="comma-separated, max 8"),
                        metric: str = Query(..., pattern="^(total_expenditures|per_capita_expenditures|fund_balance|debt|ga_spend)$"),
                        fiscal_year: int = None):
    ids = [i.strip() for i in unit_ids.split(",") if i.strip()][:8]
    col = {"debt": "total_debt"}.get(metric, metric)
    results = []
    async with pool.connection() as conn:
        for uid in ids:
            row = await (await conn.execute(
                """
                select a.unit_id, u.name, u.population, a.fiscal_year, a.total_expenditures,
                       a.fund_balance, a.total_debt, a.fund_detail
                from afr_summaries a join units u on u.id = a.unit_id
                where a.unit_id = %s and (%s::int is null or a.fiscal_year = %s)
                order by a.fiscal_year desc limit 1
                """,
                (uid, fiscal_year, fiscal_year),
            )).fetchone()
            if not row:
                name_row = await (await conn.execute("select name from units where id = %s", (uid,))).fetchone()
                results.append({"unit_id": uid, "name": name_row["name"] if name_row else uid, "fiscal_year": None, "value": None, "note": "no AFR data"})
                continue
            if metric == "per_capita_expenditures":
                val = round(float(row["total_expenditures"]) / row["population"], 2) \
                    if row["population"] and row["total_expenditures"] else None
            elif metric == "ga_spend":
                val = extract_ga_spend(row["fund_detail"])
            else:
                val = row.get(col)
            results.append({"unit_id": uid, "name": row["name"], "fiscal_year": row["fiscal_year"], "value": val})
    await log_usage(request, "compare_units", params={"unit_ids": ids, "metric": metric})
    return {
        "metric": metric,
        "results": results,
        "provenance": provenance(COMPTROLLER_URL, fiscal_year or "latest per unit",
                                 note="AFR data is self-reported; fiscal years may differ across units."),
    }


@app.get("/freshness")
async def data_freshness(request: Request, unit_id: str = None):
    async with pool.connection() as conn:
        out = {}
        w, p = ("where unit_id = %s", (unit_id,)) if unit_id else ("", ())
        out["units"] = (await (await conn.execute(
            f"select count(*) as rows, max(as_of) as as_of from units {w.replace('unit_id', 'id')}", p)).fetchone())
        out["officials"] = (await (await conn.execute(
            f"select count(*) as rows, max(as_of) as as_of from officials {w}", p)).fetchone())
        out["afr_summaries"] = (await (await conn.execute(
            f"select count(*) as rows, max(fiscal_year) as latest_fy from afr_summaries {w}", p)).fetchone())
        out["spend_lines"] = (await (await conn.execute(
            f"select count(*) as rows, max(meeting_date) as latest from spend_lines {w}", p)).fetchone())
        out["meetings"] = (await (await conn.execute(
            f"select count(*) as rows, max(meeting_ts) as latest from meetings {w}", p)).fetchone())
    await log_usage(request, "data_freshness", unit_id=unit_id)
    return out

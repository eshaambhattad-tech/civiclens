"""Township financial-management grades from AFR filings.

Peer-relative among Cook County townships for one substantially complete
fiscal year. This is not an audit opinion — it ranks how filings look on
compliance, transparency, program mix, reserves, and resident cost.

Dimensions (weights sum to 1.0):
  filing        0.20  on-time AFR filings + multi-year continuity
  transparency  0.25  low share of catch-all categories (Other + Contingencies)
  program_mix   0.20  program spending (Social Services + Transportation) vs admin
  reserves      0.20  fund balance as months of expenditure cover
  cost_burden   0.15  per-capita expenditure vs township peers (lower → higher)

Letter scale is peer-rank quintiles among graded townships (top 20% = A,
…, bottom 20% = F). Numeric score remains the weighted dimension average.
Ungraded if no AFR.
"""
from __future__ import annotations

from statistics import median

WEIGHTS = {
    "filing": 0.20,
    "transparency": 0.25,
    "program_mix": 0.20,
    "reserves": 0.20,
    "cost_burden": 0.15,
}

DIMENSION_LABELS = {
    "filing": "Filing compliance",
    "transparency": "Reporting transparency",
    "program_mix": "Program vs administration",
    "reserves": "Fiscal reserves",
    "cost_burden": "Resident cost burden",
}

DIMENSION_NOTES = {
    "filing": "On-time Annual Financial Reports and unbroken recent filing years.",
    "transparency": "Share of spending left in catch-all lines (Other Expenditures, Contingencies).",
    "program_mix": "Social services and roads relative to general government overhead.",
    "reserves": "Fund balance relative to annual spending (months of cushion).",
    "cost_burden": "Per-resident spending versus other Cook County townships.",
}

CATCH_ALL = ("Other Expenditures", "Contingencies")
PROGRAM = ("Social Services", "Transportation")
ADMIN = ("General Government",)


def letter_for_rank(rank: int, peer_count: int) -> str | None:
    """Assign A–F by peer-rank quintile (1 = best)."""
    if peer_count <= 0:
        return None
    # Fraction from the top: rank 1 → ~0, last → ~1
    from_top = (rank - 0.5) / peer_count
    if from_top < 0.20:
        return "A"
    if from_top < 0.40:
        return "B"
    if from_top < 0.60:
        return "C"
    if from_top < 0.80:
        return "D"
    return "F"


def _pct_rank(value: float, peers: list[float], *, higher_is_better: bool) -> float:
    """Percentile rank 0–100 among peers. Ties get the average rank."""
    if not peers:
        return 50.0
    if higher_is_better:
        below = sum(1 for p in peers if p < value)
        equal = sum(1 for p in peers if p == value)
    else:
        below = sum(1 for p in peers if p > value)
        equal = sum(1 for p in peers if p == value)
    return 100.0 * (below + 0.5 * equal) / len(peers)


def _cat_share(cats: dict, keys: tuple[str, ...], total: float) -> float:
    if not total:
        return 0.0
    return sum(float(cats.get(k) or 0) for k in keys) / total


def _pick_peer_year(year_counts: dict[int, int]) -> int | None:
    """Most complete recent year (≥80% of peak filing count).

    Prefers higher filing counts over a sparse newer year, then the latest
    year among ties — so FY2024 (27 townships) beats incomplete FY2025.
    """
    if not year_counts:
        return None
    peak = max(year_counts.values())
    eligible = [(n, y) for y, n in year_counts.items() if n >= 0.8 * peak]
    if not eligible:
        return max(year_counts.items(), key=lambda kv: (kv[1], kv[0]))[0]
    return max(eligible)[1]


def build_township_grades(rows: list[dict]) -> dict:
    """Compute grades for a set of township AFR rows.

    Each row needs: unit_id, name, population, fiscal_year, total_expenditures,
    total_revenues, fund_balance, filed_on_time, expenditures_by_category (dict),
    and optionally afr_year_count, on_time_count (across available years).
    Rows for multiple years for the same unit are OK — peer year is chosen,
    filing continuity uses the per-unit aggregates when provided.
    """
    by_fy: dict[int, list[dict]] = {}
    no_afr: list[dict] = []
    for r in rows:
        fy = int(r["fiscal_year"] or 0)
        if fy <= 0 or r.get("total_expenditures") is None:
            if not any(u["unit_id"] == r["unit_id"] for u in no_afr):
                no_afr.append({"unit_id": r["unit_id"], "name": r["name"],
                               "reason": "No Annual Financial Report on file."})
            continue
        by_fy.setdefault(fy, []).append(r)

    peer_fy = _pick_peer_year({fy: len(rs) for fy, rs in by_fy.items()})
    if peer_fy is None:
        return {
            "fiscal_year": None,
            "grades": [],
            "methodology": _methodology(),
            "ungraded": no_afr,
        }

    peer_rows = by_fy[peer_fy]
    # One row per unit (latest if dupes)
    latest: dict[str, dict] = {}
    for r in peer_rows:
        latest[r["unit_id"]] = r
    peers = list(latest.values())

    catch_shares, program_shares, reserve_months, per_capitas = [], [], [], []
    features = {}
    for r in peers:
        exp = float(r["total_expenditures"] or 0)
        cats = r.get("expenditures_by_category") or {}
        pop = r.get("population") or 0
        fb = float(r["fund_balance"] or 0)
        catch = _cat_share(cats, CATCH_ALL, exp)
        prog = _cat_share(cats, PROGRAM, exp)
        admin = _cat_share(cats, ADMIN, exp)
        mix = prog / (prog + admin) if (prog + admin) > 0 else 0.0
        months = (fb / exp * 12) if exp > 0 else 0.0
        # Cap reserve signal: past 18 months doesn't earn more (avoid hoarding bias)
        months_capped = min(months, 18.0)
        pc = (exp / pop) if pop and exp else None

        features[r["unit_id"]] = {
            "catch_share": catch,
            "program_mix": mix,
            "reserve_months": months,
            "reserve_months_scored": months_capped,
            "per_capita": pc,
            "exp": exp,
            "filed_on_time": r.get("filed_on_time"),
            "afr_year_count": int(r.get("afr_year_count") or 1),
            "on_time_count": int(r.get("on_time_count") or (1 if r.get("filed_on_time") else 0)),
            "name": r["name"],
            "population": pop,
        }
        catch_shares.append(catch)
        program_shares.append(mix)
        reserve_months.append(months_capped)
        if pc is not None:
            per_capitas.append(pc)

    grades = []
    for uid, f in features.items():
        filing = _filing_score(f["on_time_count"], f["afr_year_count"], f["filed_on_time"])
        transparency = _pct_rank(f["catch_share"], catch_shares, higher_is_better=False)
        program_mix = _pct_rank(f["program_mix"], program_shares, higher_is_better=True)
        reserves = _pct_rank(f["reserve_months_scored"], reserve_months, higher_is_better=True)
        if f["per_capita"] is None or not per_capitas:
            cost_burden = 50.0
        else:
            cost_burden = _pct_rank(f["per_capita"], per_capitas, higher_is_better=False)

        dimensions = {
            "filing": round(filing, 1),
            "transparency": round(transparency, 1),
            "program_mix": round(program_mix, 1),
            "reserves": round(reserves, 1),
            "cost_burden": round(cost_burden, 1),
        }
        score = sum(dimensions[k] * WEIGHTS[k] for k in WEIGHTS)

        flags = []
        if f["catch_share"] >= 0.20:
            flags.append(f"Catch-all categories are {f['catch_share']*100:.0f}% of spending.")
        if f["filed_on_time"] is False:
            flags.append("Latest AFR was filed late.")
        if f["reserve_months"] < 3:
            flags.append(f"Reserves cover only {f['reserve_months']:.1f} months of spending.")
        if f["reserve_months"] > 24:
            flags.append(f"Large reserve cushion ({f['reserve_months']:.0f} months) — ask what it is for.")
        if f["per_capita"] is not None and per_capitas:
            med = median(per_capitas)
            if f["per_capita"] > 1.5 * med:
                flags.append("Per-resident spending is well above the township median.")

        grades.append({
            "unit_id": uid,
            "name": f["name"],
            "type": "township",
            "fiscal_year": peer_fy,
            "letter": None,  # filled after ranking
            "score": round(score, 1),
            "dimensions": dimensions,
            "signals": {
                "catch_all_share": round(f["catch_share"], 4),
                "program_mix_ratio": round(f["program_mix"], 4),
                "reserve_months": round(f["reserve_months"], 2),
                "per_capita_expenditures": round(f["per_capita"], 2) if f["per_capita"] is not None else None,
                "filed_on_time": f["filed_on_time"],
                "afr_years": f["afr_year_count"],
            },
            "flags": flags,
            "population": f["population"] or None,
        })

    grades.sort(key=lambda g: (-g["score"], g["name"]))
    n = len(grades)
    for i, g in enumerate(grades, 1):
        g["rank"] = i
        g["peer_count"] = n
        g["letter"] = letter_for_rank(i, n)

    # Units present in input but missing peer-year AFR
    graded_ids = {g["unit_id"] for g in grades}
    ungraded = list(no_afr)
    seen = {u["unit_id"] for u in ungraded}
    for r in rows:
        uid = r["unit_id"]
        if uid in graded_ids or uid in seen:
            continue
        seen.add(uid)
        ungraded.append({
            "unit_id": uid,
            "name": r["name"],
            "reason": f"No AFR on file for peer year FY{peer_fy}.",
        })

    return {
        "fiscal_year": peer_fy,
        "grades": grades,
        "ungraded": ungraded,
        "methodology": _methodology(),
        "peer_median": {
            "score": round(median([g["score"] for g in grades]), 1) if grades else None,
            "per_capita_expenditures": round(median(per_capitas), 2) if per_capitas else None,
            "reserve_months": round(median([f["reserve_months"] for f in features.values()]), 2) if features else None,
            "catch_all_share": round(median(catch_shares), 4) if catch_shares else None,
        },
    }


def _filing_score(on_time_count: int, afr_year_count: int, latest_on_time) -> float:
    if afr_year_count <= 0:
        return 0.0
    on_time_rate = on_time_count / afr_year_count
    continuity = min(afr_year_count, 3) / 3.0
    latest_bonus = 0.1 if latest_on_time is True else 0.0
    return 100.0 * min(1.0, 0.7 * on_time_rate + 0.2 * continuity + latest_bonus)


def grade_for_unit(bundle: dict, unit_id: str) -> dict | None:
    for g in bundle["grades"]:
        if g["unit_id"] == unit_id:
            return {
                **g,
                "methodology": bundle["methodology"],
                "peer_median": bundle["peer_median"],
                "fiscal_year": bundle["fiscal_year"],
            }
    for u in bundle.get("ungraded") or []:
        if u["unit_id"] == unit_id:
            return {
                "unit_id": unit_id,
                "name": u["name"],
                "letter": None,
                "score": None,
                "ungraded_reason": u["reason"],
                "methodology": bundle["methodology"],
                "fiscal_year": bundle["fiscal_year"],
            }
    return None


def _methodology() -> dict:
    return {
        "summary": (
            "Peer-relative grade of Cook County townships using Illinois Comptroller "
            "Annual Financial Reports. Not an audit. Higher scores mean better filing "
            "discipline, clearer categorization, more program spending relative to "
            "overhead, healthier reserves, and lower per-resident cost versus peers."
        ),
        "weights": WEIGHTS,
        "dimensions": [
            {"key": k, "label": DIMENSION_LABELS[k], "weight": WEIGHTS[k], "note": DIMENSION_NOTES[k]}
            for k in WEIGHTS
        ],
        "letters": {
            "A": "top 20% of townships",
            "B": "60th–80th percentile",
            "C": "40th–60th percentile",
            "D": "20th–40th percentile",
            "F": "bottom 20% of townships",
        },
        "certainty": "extracted",
        "limitations": [
            "Based on self-reported AFR filings, which can contain errors.",
            "Does not include debt (not loaded), vendor-level spending, or service outcomes.",
            "Low spending can reflect under-service as well as efficiency.",
            "Townships without an AFR for the peer year are ungraded.",
        ],
    }

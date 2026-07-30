"use client";

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { getSpending, type SpendingOverview, type SpendingUnit } from "@/lib/api";
import { gsap, revealOnScroll, growBars, countUp } from "@/lib/gsap";
import CategoryPanel from "@/components/CategoryPanel";

const ALL = "__all__";

function dollars(n: number | null | undefined) {
  if (n === null || n === undefined) return "—";
  return n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
}

function compact(n: number | null | undefined) {
  if (n === null || n === undefined) return "—";
  const abs = Math.abs(n);
  const sign = n < 0 ? "−" : "";
  const v = abs;
  if (v >= 1_000_000_000) return `${sign}$${(v / 1_000_000_000).toFixed(1)}B`;
  if (v >= 1_000_000) return `${sign}$${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `${sign}$${(v / 1_000).toFixed(0)}K`;
  return dollars(n);
}

function pct(part: number, whole: number) {
  if (!whole) return "0%";
  return `${((part / whole) * 100).toFixed(1)}%`;
}

type Metric = "total" | "per_capita";
type UnitTypeFilter = "township" | "municipality" | "county" | "";

const LAYER_OPTIONS: { value: UnitTypeFilter; label: string }[] = [
  { value: "township", label: "Townships" },
  { value: "municipality", label: "Municipalities" },
  { value: "county", label: "County" },
  { value: "", label: "All layers" },
];

export default function SpendingExplorer() {
  const [data, setData] = useState<SpendingOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [year, setYear] = useState<number | undefined>(undefined);
  // Default to townships — summing county + city + townships double-counts the same geography.
  const [unitType, setUnitType] = useState<UnitTypeFilter>("township");
  const [metric, setMetric] = useState<Metric>("total");
  const [category, setCategory] = useState<string>(ALL);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [info, setInfo] = useState<{
    name: string;
    kind: "expenditure" | "revenue";
    amount: number;
    share?: string;
  } | null>(null);

  const rootRef = useRef<HTMLDivElement>(null);
  const statsRef = useRef<HTMLDivElement>(null);
  const catRef = useRef<HTMLDivElement>(null);
  const rankRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setCategory(ALL);
    setExpanded(null);
    getSpending(year, unitType || undefined)
      .then((d) => {
        if (cancelled) return;
        setData(d);
        setLoading(false);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e.message);
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [year, unitType]);

  const mixedLayers = unitType === "";

  const categories = useMemo(() => Object.keys(data?.totals.by_category ?? {}), [data]);

  const valueFor = (u: SpendingUnit) => {
    const base =
      category === ALL ? u.total_expenditures ?? 0 : u.expenditures_by_category[category] ?? 0;
    if (metric === "per_capita") return u.population ? base / u.population : null;
    return base;
  };

  const ranked = useMemo(() => {
    if (!data) return [];
    return data.units
      .map((u) => ({ unit: u, value: valueFor(u) }))
      .filter((r) => r.value !== null && r.value > 0)
      .sort((a, b) => (b.value as number) - (a.value as number));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, metric, category]);

  const maxValue = ranked.length ? (ranked[0].value as number) : 0;
  const rankedTotal = ranked.reduce((s, r) => s + (r.value as number), 0);

  const medianPerCapita = useMemo(() => {
    if (!data) return null;
    // Median across reporting units with population — not a single-type slice.
    const vals = data.units
      .map((u) => u.per_capita_expenditures)
      .filter((v): v is number => v !== null)
      .sort((a, b) => a - b);
    if (!vals.length) return null;
    const mid = Math.floor(vals.length / 2);
    return vals.length % 2 ? vals[mid] : (vals[mid - 1] + vals[mid]) / 2;
  }, [data]);

  const medianSub = useMemo(() => {
    if (!data?.units.length) return "per resident";
    const types = new Set(data.units.map((u) => u.type));
    if (types.size === 1 && types.has("township")) return "township spending";
    if (types.size === 1 && types.has("municipality")) return "municipal spending";
    return "among reporting units";
  }, [data]);

  const catMax = data ? Math.max(...Object.values(data.totals.by_category), 0) : 0;

  // Intro: stat tiles count up, category bars grow, sections reveal on scroll.
  useLayoutEffect(() => {
    if (!data || !rootRef.current) return;
    const ctx = gsap.context(() => {
      if (statsRef.current) {
        revealOnScroll(statsRef.current.querySelectorAll(".stat-tile"), { y: 14, stagger: 0.07 });
        statsRef.current.querySelectorAll<HTMLElement>("[data-count]").forEach((el) => {
          const to = Number(el.dataset.count);
          const kind = el.dataset.format;
          countUp(el, to, (n) =>
            kind === "compact"
              ? compact(n)
              : kind === "dollars"
                ? dollars(Math.round(n))
                : Math.round(n).toLocaleString()
          );
        });
      }
      if (catRef.current) {
        revealOnScroll(catRef.current.querySelectorAll(".cat-row"), { y: 10, stagger: 0.035 });
        growBars(".cat-bar", catRef.current);
      }
    }, rootRef);
    return () => ctx.revert();
  }, [data]);

  // Re-grow ranking bars whenever the ranking itself changes.
  useLayoutEffect(() => {
    if (!rankRef.current || !ranked.length) return;
    const ctx = gsap.context(() => {
      growBars(".rank-bar", rankRef.current!);
      revealOnScroll(rankRef.current!.querySelectorAll(".rank-row"), { y: 8, stagger: 0.02 });
    }, rankRef);
    return () => ctx.revert();
  }, [ranked, metric, category]);

  if (loading && !data) {
    return (
      <div className="max-w-5xl mx-auto px-6 py-20 text-muted text-sm">Loading spending data…</div>
    );
  }

  if (error) {
    return (
      <div className="max-w-5xl mx-auto px-6 py-20">
        <p className="text-sm font-semibold mb-1">Could not load spending data.</p>
        <p className="text-sm text-muted">{error}</p>
      </div>
    );
  }

  if (!data) return null;

  const totals = data.totals;

  return (
    <div ref={rootRef}>
      <style>{`
        .bar-track { background: var(--viz-bar-soft); }
        .bar-fill  { background: var(--viz-bar); }
        .seg-btn   { transition: color .15s ease, background .15s ease; }
        .rank-row  { transition: background .15s ease; }
        .rank-row:hover { background: var(--card-hover); }
        .cat-row:hover  { background: var(--card-hover); }
      `}</style>

      {/* Masthead */}
      <header style={{ background: "var(--accent-darkest)" }} className="text-white">
        <div className="max-w-5xl mx-auto px-6 py-9">
          <div className="flex flex-wrap items-end justify-between gap-5">
            <div>
              <div
                className="label-gov mb-2"
                style={{ color: "rgba(255,255,255,0.72)" }}
              >
                Cook County · Public Expenditure Record
              </div>
              <h1 className="text-[2rem] leading-tight font-bold tracking-tight">
                Where the money goes
              </h1>
              <p className="text-sm mt-2 max-w-xl" style={{ color: "rgba(255,255,255,0.78)" }}>
                One layer of government at a time — townships, municipalities, or the county —
                ranked by Annual Financial Reports filed with the Illinois Comptroller.
              </p>
            </div>
            <div className="flex flex-col items-stretch sm:items-end gap-2">
              <div className="flex items-center gap-0 border border-white/25 rounded-sm overflow-hidden">
                {LAYER_OPTIONS.map((opt) => (
                  <button
                    key={opt.value || "all"}
                    onClick={() => setUnitType(opt.value)}
                    className="seg-btn px-3 py-2 text-xs font-semibold"
                    style={
                      unitType === opt.value
                        ? { background: "#ffffff", color: "var(--accent-darkest)" }
                        : { color: "rgba(255,255,255,0.85)" }
                    }
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
              <div className="flex items-center gap-0 border border-white/25 rounded-sm overflow-hidden self-end">
                {data.available_years.map((y) => (
                  <button
                    key={y}
                    onClick={() => setYear(y)}
                    className="seg-btn px-4 py-2 text-sm font-semibold tabular-nums"
                    style={
                      y === data.fiscal_year
                        ? { background: "#ffffff", color: "var(--accent-darkest)" }
                        : { color: "rgba(255,255,255,0.85)" }
                    }
                  >
                    FY{y}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      </header>

      <div className="max-w-5xl mx-auto px-6 py-10">
        {mixedLayers && (
          <div
            className="mb-8 px-4 py-3 border-l-4 text-sm"
            style={{
              borderColor: "var(--status-warning)",
              background: "var(--status-warning-bg)",
              color: "var(--foreground)",
            }}
          >
            <strong className="font-semibold">These filings are not one budget.</strong>{" "}
            County, city, and township AFRs cover overlapping geography. Adding them
            (e.g. Cook County ~$28B + Chicago ~$19B) produces a ~$50B figure that
            double-counts the same residents. Prefer a single layer above.
          </div>
        )}

        {/* Key figures */}
        <section ref={statsRef} className="grid grid-cols-2 md:grid-cols-4 gap-px bg-border border border-border mb-14">
          {[
            {
              label: mixedLayers ? "Sum of filings" : "Total spending",
              raw: totals.total_expenditures,
              format: "compact",
              sub: mixedLayers
                ? `FY${data.fiscal_year} · not additive`
                : `FY${data.fiscal_year}`,
            },
            {
              label: "Governments reporting",
              raw: totals.unit_count,
              format: "int",
              sub:
                unitType === "township"
                  ? "townships with an AFR"
                  : unitType === "municipality"
                    ? "municipalities with an AFR"
                    : unitType === "county"
                      ? "county AFR"
                      : "with an AFR on file",
            },
            {
              label: "Residents covered",
              raw: totals.population,
              format: "int",
              sub: mixedLayers ? "county population (no double-count)" : "in reporting units",
            },
            {
              label: "Median per resident",
              raw: medianPerCapita ?? 0,
              format: "dollars",
              sub: medianSub,
            },
          ].map((t) => (
            <div key={t.label} className="stat-tile bg-card px-4 py-5" style={{ opacity: 0 }}>
              <div className="label-gov mb-2">{t.label}</div>
              <div
                className="text-[1.75rem] leading-none font-bold tracking-tight tabular-nums"
                style={{ color: "var(--accent-darkest)" }}
                data-count={t.raw}
                data-format={t.format}
              >
                —
              </div>
              <div className="text-xs text-muted mt-1.5">{t.sub}</div>
            </div>
          ))}
        </section>

        {/* Category breakdown */}
        <section ref={catRef} className="mb-14">
          <div className="rule-accent pt-3 mb-5">
            <h2 className="text-base font-bold tracking-tight">What it gets spent on</h2>
            <p className="text-sm text-muted mt-1">
              {compact(totals.total_expenditures)} across {totals.unit_count} governments, by
              reported expenditure category. Select a category to re-rank the table below.
            </p>
          </div>
          <div className="bg-card border border-border">
            {Object.entries(totals.by_category).map(([cat, amt]) => {
              const active = category === cat;
              return (
                <div
                  key={cat}
                  className="cat-row px-4 py-2.5 border-b border-border last:border-b-0"
                  style={{ opacity: 0, background: active ? "var(--accent-light)" : undefined }}
                >
                  <div className="flex items-baseline justify-between gap-3 mb-1.5">
                    <button
                      onClick={() => setCategory(active ? ALL : cat)}
                      className="text-sm font-semibold text-left hover:underline"
                      style={{ color: active ? "var(--accent-darkest)" : "var(--foreground)" }}
                      aria-pressed={active}
                      title={`Rank governments by ${cat}`}
                    >
                      {cat}
                    </button>
                    <div className="flex items-center gap-2.5 shrink-0">
                      <span className="text-sm tabular-nums text-muted">
                        {compact(amt)}{" "}
                        <span className="text-xs">({pct(amt, totals.total_expenditures)})</span>
                      </span>
                      <button
                        onClick={() =>
                          setInfo({
                            name: cat,
                            kind: "expenditure",
                            amount: amt,
                            share: pct(amt, totals.total_expenditures),
                          })
                        }
                        className="w-5 h-5 rounded-full border text-[11px] font-bold leading-none flex items-center justify-center hover:text-white transition-colors"
                        style={{ borderColor: "var(--accent)", color: "var(--accent)" }}
                        onMouseEnter={(e) =>
                          (e.currentTarget.style.background = "var(--accent)")
                        }
                        onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                        aria-label={`What is ${cat}?`}
                        title={`What counts as ${cat}?`}
                      >
                        i
                      </button>
                    </div>
                  </div>
                  <div className="bar-track h-1.5 w-full">
                    <div className="cat-bar bar-fill h-1.5" data-width={`${(amt / catMax) * 100}%`} />
                  </div>
                </div>
              );
            })}
          </div>
          {category !== ALL && (
            <div className="mt-3 flex items-center gap-3 text-xs">
              <span className="font-semibold" style={{ color: "var(--accent-dark)" }}>
                Filtered to {category}
              </span>
              <button
                onClick={() => setCategory(ALL)}
                className="text-muted underline hover:text-foreground"
              >
                Clear filter
              </button>
            </div>
          )}
        </section>

        {/* Ranking */}
        <section className="mb-12">
          <div className="rule-accent pt-3 mb-5">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <h2 className="text-base font-bold tracking-tight">Who spends what</h2>
                <p className="text-sm text-muted mt-1">
                  {category === ALL ? "Total expenditures" : category} ·{" "}
                  {metric === "total" ? "absolute dollars" : "per resident"} · FY
                  {data.fiscal_year}
                </p>
              </div>
              <div className="flex border border-border rounded-sm overflow-hidden bg-card">
                {(
                  [
                    ["total", "Total"],
                    ["per_capita", "Per resident"],
                  ] as [Metric, string][]
                ).map(([m, label]) => (
                  <button
                    key={m}
                    onClick={() => setMetric(m)}
                    className="seg-btn px-3.5 py-1.5 text-sm font-semibold"
                    style={
                      metric === m
                        ? { background: "var(--accent-dark)", color: "#fff" }
                        : { color: "var(--muted)" }
                    }
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div ref={rankRef} className="bg-card border border-border">
            <div className="flex items-center gap-3 px-4 py-2 border-b border-border bg-background/60">
              <span className="label-gov w-6 shrink-0">#</span>
              <span className="label-gov flex-1">Government</span>
              <span className="label-gov shrink-0">
                {metric === "total" ? "Spent" : "Per resident"}
              </span>
            </div>

            {ranked.map(({ unit, value }, i) => {
              const isOpen = expanded === unit.unit_id;
              const cats = Object.entries(unit.expenditures_by_category).sort((a, b) => b[1] - a[1]);
              const unitCatMax = cats.length ? cats[0][1] : 0;
              return (
                <div key={unit.unit_id} className="border-b border-border last:border-b-0">
                  <button
                    onClick={() => setExpanded(isOpen ? null : unit.unit_id)}
                    className="rank-row w-full text-left px-4 py-3"
                    style={{ opacity: 0 }}
                    aria-expanded={isOpen}
                  >
                    <div className="flex items-center gap-3 mb-2">
                      <span className="text-xs tabular-nums text-muted w-6 shrink-0">{i + 1}</span>
                      <span className="text-sm font-semibold flex-1">{unit.name}</span>
                      {unit.filed_on_time === false && (
                        <span
                          className="text-[10px] font-bold px-1.5 py-0.5 border shrink-0 tracking-wide"
                          style={{
                            color: "var(--status-warning)",
                            background: "var(--status-warning-bg)",
                            borderColor: "var(--status-warning-border)",
                          }}
                        >
                          ⚠ FILED LATE
                        </span>
                      )}
                      <span
                        className="text-sm font-bold tabular-nums shrink-0"
                        style={{ color: "var(--accent-darkest)" }}
                      >
                        {metric === "per_capita"
                          ? `${dollars(Math.round(value as number))}`
                          : compact(value as number)}
                      </span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="w-6 shrink-0" />
                      <div className="bar-track h-2 flex-1">
                        <div
                          className="rank-bar bar-fill h-2"
                          data-width={`${maxValue ? ((value as number) / maxValue) * 100 : 0}%`}
                        />
                      </div>
                      <span className="text-xs tabular-nums text-muted w-11 text-right shrink-0">
                        {pct(value as number, rankedTotal)}
                      </span>
                    </div>
                  </button>

                  {isOpen && (
                    <div className="px-4 pb-5 pt-1" style={{ background: "var(--background)" }}>
                      <div className="grid sm:grid-cols-3 gap-px bg-border border border-border mb-5 mt-3">
                        <div className="bg-card px-3 py-3">
                          <div className="label-gov mb-1">Revenues</div>
                          <div className="text-base font-bold tabular-nums">
                            {compact(unit.total_revenues)}
                          </div>
                        </div>
                        <div className="bg-card px-3 py-3">
                          <div className="label-gov mb-1">Expenditures</div>
                          <div className="text-base font-bold tabular-nums">
                            {compact(unit.total_expenditures)}
                          </div>
                        </div>
                        <div className="bg-card px-3 py-3">
                          <div className="label-gov mb-1">
                            {unit.surplus !== null && unit.surplus < 0 ? "Deficit" : "Surplus"}
                          </div>
                          <div
                            className="text-base font-bold tabular-nums"
                            style={{
                              color:
                                unit.surplus === null
                                  ? undefined
                                  : unit.surplus < 0
                                    ? "var(--viz-deficit)"
                                    : "var(--viz-surplus)",
                            }}
                          >
                            {unit.surplus === null
                              ? "—"
                              : `${unit.surplus < 0 ? "−" : "+"}${compact(Math.abs(unit.surplus))}`}
                          </div>
                        </div>
                      </div>

                      {cats.length > 0 && (
                        <>
                          <div className="label-gov mb-2.5">Spending by category</div>
                          <div className="space-y-2 mb-4">
                            {cats.map(([cat, amt]) => (
                              <div key={cat}>
                                <div className="flex items-baseline justify-between gap-3 mb-1">
                                  <button
                                    onClick={() =>
                                      setInfo({
                                        name: cat,
                                        kind: "expenditure",
                                        amount: amt,
                                        share: pct(amt, unit.total_expenditures ?? 0),
                                      })
                                    }
                                    className="text-xs text-left hover:underline"
                                    style={{ color: "var(--accent)" }}
                                    title={`What counts as ${cat}?`}
                                  >
                                    {cat} <span className="opacity-60">ⓘ</span>
                                  </button>
                                  <span className="text-xs tabular-nums text-muted shrink-0">
                                    {dollars(amt)}
                                    {unit.population ? (
                                      <span className="text-[11px]">
                                        {" · "}
                                        {dollars(Math.round(amt / unit.population))}/res
                                      </span>
                                    ) : null}
                                  </span>
                                </div>
                                <div className="bar-track h-1.5 w-full">
                                  <div
                                    className="bar-fill h-1.5"
                                    style={{
                                      width: `${unitCatMax ? (amt / unitCatMax) * 100 : 0}%`,
                                    }}
                                  />
                                </div>
                              </div>
                            ))}
                          </div>
                        </>
                      )}

                      <div className="flex flex-wrap items-center gap-4 text-xs">
                        <Link
                          href={`/unit/${unit.unit_id}`}
                          className="font-semibold hover:underline"
                          style={{ color: "var(--accent)" }}
                        >
                          Full profile →
                        </Link>
                        {unit.website && (
                          <a
                            href={unit.website}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-muted hover:text-foreground"
                          >
                            Official site ↗
                          </a>
                        )}
                        {unit.population ? (
                          <span className="text-muted tabular-nums">
                            Population {unit.population.toLocaleString()}
                          </span>
                        ) : null}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}

            {ranked.length === 0 && (
              <div className="px-4 py-10 text-sm text-muted text-center">
                No government reported spending in this category for FY{data.fiscal_year}.
              </div>
            )}
          </div>
        </section>

        <footer className="border-t border-border pt-5 text-xs text-muted space-y-1.5">
          <div className="label-gov mb-2">Notes &amp; provenance</div>
          {data.caveats.map((c) => (
            <p key={c}>· {c}</p>
          ))}
          <p className="pt-1">
            Source:{" "}
            <a
              href={data.provenance.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="underline hover:text-foreground"
            >
              Illinois Comptroller — Local Government Financial Databases
            </a>{" "}
            · {data.provenance.as_of}
          </p>
        </footer>
      </div>

      {info && (
        <CategoryPanel
          name={info.name}
          kind={info.kind}
          amount={info.amount}
          share={info.share}
          onClose={() => setInfo(null)}
        />
      )}
    </div>
  );
}

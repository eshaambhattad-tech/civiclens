"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { getDirectory, type Directory, type DirectoryUnit } from "@/lib/api";
import { GradeBadge } from "@/components/GradeBadge";

const TYPES = [
  { value: "all", label: "All" },
  { value: "township", label: "Townships" },
  { value: "municipality", label: "Municipalities" },
  { value: "county", label: "County" },
  { value: "special_district", label: "Special Districts" },
];

const TRACKED: { key: keyof DirectoryUnit["has"]; label: string; short: string }[] = [
  { key: "officials", label: "Officials", short: "Ofc" },
  { key: "finances", label: "Finances", short: "Fin" },
  { key: "meetings", label: "Meetings", short: "Mtg" },
  { key: "spending_detail", label: "Line-item spending", short: "Spd" },
];

type SortKey = "name" | "type" | "population" | "tracked_count" | "grade_score";
type Dir = "asc" | "desc";

function Check({ on }: { on: boolean }) {
  return on ? (
    <span
      className="inline-flex items-center justify-center w-5 h-5 rounded-sm text-white text-[11px] font-bold"
      style={{ background: "var(--accent)" }}
      aria-label="tracked"
    >
      ✓
    </span>
  ) : (
    <span
      className="inline-flex items-center justify-center w-5 h-5 rounded-sm text-[11px]"
      style={{ background: "var(--background)", color: "#a9aeb1", border: "1px solid var(--border)" }}
      aria-label="not tracked"
    >
      —
    </span>
  );
}

export default function UnitDirectory() {
  const [data, setData] = useState<Directory | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [type, setType] = useState("all");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<SortKey>("name");
  const [dir, setDir] = useState<Dir>("asc");
  const [onlyTracked, setOnlyTracked] = useState(false);

  useEffect(() => {
    getDirectory()
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);

  const rows = useMemo(() => {
    if (!data) return [];
    let out = data.units;
    if (type !== "all") out = out.filter((u) => u.type === type);
    if (q.trim()) {
      const needle = q.trim().toLowerCase();
      out = out.filter((u) => u.name.toLowerCase().includes(needle));
    }
    if (onlyTracked) out = out.filter((u) => u.tracked_count > 0);
    const mult = dir === "asc" ? 1 : -1;
    return [...out].sort((a, b) => {
      if (sort === "population") return ((a.population ?? -1) - (b.population ?? -1)) * mult;
      if (sort === "tracked_count") return (a.tracked_count - b.tracked_count) * mult;
      if (sort === "grade_score") {
        const av = a.grade_score ?? -1;
        const bv = b.grade_score ?? -1;
        return (av - bv) * mult || a.name.localeCompare(b.name);
      }
      if (sort === "type") return a.type.localeCompare(b.type) * mult || a.name.localeCompare(b.name);
      return a.name.localeCompare(b.name) * mult;
    });
  }, [data, type, q, sort, dir, onlyTracked]);

  function toggleSort(k: SortKey) {
    if (sort === k) setDir(dir === "asc" ? "desc" : "asc");
    else {
      setSort(k);
      setDir(k === "name" || k === "type" ? "asc" : "desc");
    }
  }

  const arrow = (k: SortKey) => (sort === k ? (dir === "asc" ? " ↑" : " ↓") : "");

  if (error) {
    return <p className="text-sm text-muted mt-8">Could not load the directory: {error}</p>;
  }
  if (!data) {
    return <p className="text-sm text-muted mt-8">Loading directory…</p>;
  }

  const counts = data.totals.by_type;

  return (
    <section className="mt-14">
      <div className="rule-accent pt-3 mb-5">
        <h2 className="text-xl font-bold tracking-tight">Every government we track</h2>
        <p className="text-sm text-muted mt-1">
          All {data.totals.units} units in Cook County, and exactly what CivicLens holds on each.
          Township money-management grades
          {data.grade_fiscal_year ? ` (FY${data.grade_fiscal_year})` : ""} are peer-relative
          from AFR filings — not an audit. A dash means ungraded or not yet ingested.
        </p>
      </div>

      {/* Controls */}
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <div className="flex border border-border rounded-sm overflow-hidden bg-card">
          {TYPES.map((t) => {
            const n = t.value === "all" ? data.totals.units : (counts[t.value]?.total ?? 0);
            return (
              <button
                key={t.value}
                onClick={() => setType(t.value)}
                className="px-3 py-1.5 text-xs font-semibold transition-colors"
                style={
                  type === t.value
                    ? { background: "var(--accent-darkest)", color: "#fff" }
                    : { color: "var(--muted)" }
                }
              >
                {t.label}
                <span className="ml-1.5 opacity-60 tabular-nums">{n}</span>
              </button>
            );
          })}
        </div>

        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Filter by name…"
          className="px-3 py-1.5 text-sm border border-border rounded-sm bg-card w-52 focus:outline-none focus:ring-2 focus:ring-accent"
        />

        <label className="flex items-center gap-2 text-xs text-muted cursor-pointer select-none">
          <input
            type="checkbox"
            checked={onlyTracked}
            onChange={(e) => setOnlyTracked(e.target.checked)}
            className="accent-[var(--accent)]"
          />
          Only units with data
        </label>

        <span className="text-xs text-muted ml-auto tabular-nums">
          {rows.length} shown
        </span>
      </div>

      {/* Table */}
      <div className="bg-card border border-border overflow-x-auto">
        <table className="w-full text-sm min-w-[720px]">
          <thead>
            <tr className="border-b border-border" style={{ background: "var(--background)" }}>
              <th className="text-left px-4 py-2.5">
                <button onClick={() => toggleSort("name")} className="label-gov hover:text-foreground">
                  Government{arrow("name")}
                </button>
              </th>
              <th className="text-left px-3 py-2.5">
                <button onClick={() => toggleSort("type")} className="label-gov hover:text-foreground">
                  Type{arrow("type")}
                </button>
              </th>
              <th className="text-right px-3 py-2.5">
                <button
                  onClick={() => toggleSort("population")}
                  className="label-gov hover:text-foreground"
                >
                  Population{arrow("population")}
                </button>
              </th>
              <th className="text-center px-3 py-2.5">
                <button
                  onClick={() => toggleSort("grade_score")}
                  className="label-gov hover:text-foreground"
                  title="Township money-management grade"
                >
                  Grade{arrow("grade_score")}
                </button>
              </th>
              {TRACKED.map((t) => (
                <th key={t.key} className="px-3 py-2.5 text-center">
                  <span className="label-gov" title={t.label}>
                    {t.short}
                  </span>
                </th>
              ))}
              <th className="text-right px-4 py-2.5">
                <button
                  onClick={() => toggleSort("tracked_count")}
                  className="label-gov hover:text-foreground"
                >
                  Tracked{arrow("tracked_count")}
                </button>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((u) => (
              <tr key={u.id} className="border-b border-border last:border-b-0 hover:bg-card-hover">
                <td className="px-4 py-2.5">
                  <Link href={`/unit/${u.id}`} className="font-semibold hover:underline">
                    {u.name}
                  </Link>
                </td>
                <td className="px-3 py-2.5 text-muted capitalize text-xs">
                  {u.type.replace("_", " ")}
                </td>
                <td className="px-3 py-2.5 text-right tabular-nums text-muted">
                  {u.population ? u.population.toLocaleString() : "—"}
                </td>
                <td className="px-3 py-2.5 text-center">
                  <div className="inline-flex flex-col items-center gap-0.5">
                    <GradeBadge
                      letter={u.grade_letter}
                      size="sm"
                      title={
                        u.grade_letter
                          ? `Grade ${u.grade_letter} (${u.grade_score}) · rank ${u.grade_rank}`
                          : u.type === "township"
                            ? "Ungraded — no peer-year AFR"
                            : "Grades are for townships only"
                      }
                    />
                    {u.grade_score != null && (
                      <span className="text-[10px] tabular-nums text-muted">{u.grade_score}</span>
                    )}
                  </div>
                </td>
                {TRACKED.map((t) => (
                  <td key={t.key} className="px-3 py-2.5 text-center">
                    <Check on={u.has[t.key]} />
                  </td>
                ))}
                <td className="px-4 py-2.5 text-right tabular-nums font-semibold">
                  {u.tracked_count}
                  <span className="text-muted font-normal">/4</span>
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={9} className="px-4 py-10 text-center text-muted">
                  No governments match that filter.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap gap-x-5 gap-y-1 mt-3 text-xs text-muted">
        {TRACKED.map((t) => (
          <span key={t.key}>
            <strong className="font-semibold text-foreground">{t.short}</strong> — {t.label}
          </span>
        ))}
      </div>
    </section>
  );
}

"use client";

import { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import gsap from "gsap";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const METRICS = [
  { value: "total_expenditures", label: "Total Expenditures", icon: "chart" },
  {
    value: "per_capita_expenditures",
    label: "Per Capita Expenditures",
    icon: "user",
  },
  { value: "fund_balance", label: "Fund Balance", icon: "wallet" },
  { value: "debt", label: "Total Debt", icon: "alert" },
  { value: "ga_spend", label: "General Assistance Spend", icon: "heart" },
];

interface Unit {
  id: string;
  name: string;
  type: string;
  population?: number;
}

interface Result {
  unit_id: string;
  name: string;
  fiscal_year: number;
  value: number | null;
  note?: string;
}

function dollars(n: number | null) {
  if (n == null) return "\u2014";
  return "$" + Number(n).toLocaleString("en-US", { maximumFractionDigits: 0 });
}

export default function ComparePage() {
  const [allUnits, setAllUnits] = useState<Unit[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [metric, setMetric] = useState("total_expenditures");
  const [results, setResults] = useState<Result[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [unitsLoading, setUnitsLoading] = useState(true);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [searchFilter, setSearchFilter] = useState("");

  const headerRef = useRef<HTMLDivElement>(null);
  const controlsRef = useRef<HTMLDivElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Load all townships on mount
  useEffect(() => {
    fetch(`${API_BASE}/units?type=township&limit=100`)
      .then((r) => r.json())
      .then((data) => {
        setAllUnits(data.units || []);
        setUnitsLoading(false);
      })
      .catch(() => setUnitsLoading(false));
  }, []);

  // GSAP entrance
  useEffect(() => {
    const tl = gsap.timeline({ defaults: { ease: "power3.out" } });
    tl.fromTo(
      headerRef.current,
      { y: 40, opacity: 0, filter: "blur(6px)" },
      { y: 0, opacity: 1, filter: "blur(0px)", duration: 0.8 }
    ).fromTo(
      controlsRef.current,
      { y: 30, opacity: 0 },
      { y: 0, opacity: 1, duration: 0.6 },
      "-=0.4"
    );
  }, []);

  // Close dropdown on outside click
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(e.target as Node)
      ) {
        setDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  function toggleUnit(id: string) {
    if (selected.includes(id)) {
      setSelected(selected.filter((s) => s !== id));
    } else if (selected.length < 8) {
      setSelected([...selected, id]);
    }
  }

  async function compare() {
    if (selected.length < 2) return;
    setLoading(true);
    try {
      const res = await fetch(
        `${API_BASE}/compare?unit_ids=${selected.join(",")}&metric=${metric}`
      );
      const data = await res.json();
      setResults(data.results || []);
    } catch {
      setResults(null);
    }
    setLoading(false);
  }

  const maxVal = results
    ? Math.max(...results.filter((r) => r.value != null).map((r) => r.value!))
    : 0;

  const filteredUnits = allUnits.filter((u) =>
    u.name.toLowerCase().includes(searchFilter.toLowerCase())
  );

  const selectedNames = allUnits.filter((u) => selected.includes(u.id));

  return (
    <div className="max-w-5xl mx-auto px-6 py-10">
      {/* Header */}
      <div ref={headerRef} style={{ opacity: 0 }}>
        <h1 className="text-3xl sm:text-4xl font-bold mb-2">
          Compare <span className="text-accent">Townships</span>
        </h1>
        <p className="text-muted mb-8 max-w-lg">
          Select up to 8 townships and a financial metric to compare them side
          by side.
        </p>
      </div>

      {/* Controls */}
      <div
        ref={controlsRef}
        className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-10"
        style={{ opacity: 0 }}
      >
        {/* Township multi-select dropdown */}
        <div className="lg:col-span-2" ref={dropdownRef}>
          <label className="text-sm font-medium text-foreground mb-2 block">
            Townships
          </label>
          <div className="relative">
            <button
              onClick={() => setDropdownOpen(!dropdownOpen)}
              className="w-full flex items-center justify-between px-4 py-3 rounded-lg border border-border bg-card text-sm hover:border-accent/50 transition-colors focus:outline-none focus:ring-2 focus:ring-accent"
            >
              <span className={selected.length === 0 ? "text-muted" : ""}>
                {selected.length === 0
                  ? "Select townships to compare..."
                  : `${selected.length} township${selected.length > 1 ? "s" : ""} selected`}
              </span>
              <svg
                className={`w-4 h-4 text-muted transition-transform ${dropdownOpen ? "rotate-180" : ""}`}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M19 9l-7 7-7-7"
                />
              </svg>
            </button>

            <AnimatePresence>
              {dropdownOpen && (
                <motion.div
                  initial={{ opacity: 0, y: -8, scale: 0.98 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: -8, scale: 0.98 }}
                  transition={{ duration: 0.2 }}
                  className="absolute z-50 mt-1 w-full rounded-lg border border-border bg-card shadow-lg"
                >
                  {/* Search within dropdown */}
                  <div className="p-2 border-b border-border">
                    <input
                      type="text"
                      value={searchFilter}
                      onChange={(e) => setSearchFilter(e.target.value)}
                      placeholder="Filter townships..."
                      className="w-full px-3 py-2 rounded-md border border-border bg-background text-sm focus:outline-none focus:ring-1 focus:ring-accent"
                      autoFocus
                    />
                  </div>

                  <div className="max-h-56 overflow-y-auto">
                    {unitsLoading ? (
                      <div className="px-4 py-6 text-center text-sm text-muted">
                        Loading townships...
                      </div>
                    ) : filteredUnits.length === 0 ? (
                      <div className="px-4 py-6 text-center text-sm text-muted">
                        No townships match &ldquo;{searchFilter}&rdquo;
                      </div>
                    ) : (
                      filteredUnits.map((u) => {
                        const isSelected = selected.includes(u.id);
                        const disabled = !isSelected && selected.length >= 8;
                        return (
                          <button
                            key={u.id}
                            onClick={() => !disabled && toggleUnit(u.id)}
                            disabled={disabled}
                            className={`w-full flex items-center gap-3 px-4 py-2.5 text-sm text-left border-b border-border/30 last:border-0 transition-colors
                              ${disabled ? "opacity-40 cursor-not-allowed" : "hover:bg-card-hover cursor-pointer"}
                              ${isSelected ? "bg-accent/5" : ""}`}
                          >
                            <div
                              className={`w-4 h-4 rounded border-2 flex items-center justify-center flex-shrink-0 transition-colors
                              ${isSelected ? "bg-accent border-accent" : "border-border"}`}
                            >
                              {isSelected && (
                                <svg
                                  className="w-2.5 h-2.5 text-white"
                                  fill="none"
                                  viewBox="0 0 24 24"
                                  stroke="currentColor"
                                  strokeWidth={3}
                                >
                                  <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    d="M5 13l4 4L19 7"
                                  />
                                </svg>
                              )}
                            </div>
                            <span className={isSelected ? "font-medium" : ""}>
                              {u.name}
                            </span>
                            {u.population && (
                              <span className="ml-auto text-xs text-muted">
                                Pop. {u.population.toLocaleString()}
                              </span>
                            )}
                          </button>
                        );
                      })
                    )}
                  </div>

                  {selected.length > 0 && (
                    <div className="p-2 border-t border-border flex justify-between items-center">
                      <span className="text-xs text-muted">
                        {selected.length}/8 selected
                      </span>
                      <button
                        onClick={() => setSelected([])}
                        className="text-xs text-red-500 hover:text-red-700"
                      >
                        Clear all
                      </button>
                    </div>
                  )}
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* Selected chips */}
          {selectedNames.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-3">
              {selectedNames.map((u) => (
                <motion.span
                  key={u.id}
                  initial={{ opacity: 0, scale: 0.8 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.8 }}
                  onClick={() => toggleUnit(u.id)}
                  className="inline-flex items-center gap-1 text-xs bg-accent/10 text-accent px-2.5 py-1 rounded-full cursor-pointer hover:bg-accent/20 transition-colors"
                >
                  {u.name.replace(" Township", "")}
                  <svg
                    className="w-3 h-3"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={2}
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M6 18L18 6M6 6l12 12"
                    />
                  </svg>
                </motion.span>
              ))}
            </div>
          )}
        </div>

        {/* Metric dropdown */}
        <div>
          <label className="text-sm font-medium text-foreground mb-2 block">
            Metric
          </label>
          <select
            value={metric}
            onChange={(e) => setMetric(e.target.value)}
            className="w-full px-4 py-3 rounded-lg border border-border bg-card text-sm focus:outline-none focus:ring-2 focus:ring-accent appearance-none cursor-pointer"
            style={{
              backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%236b7280'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'/%3E%3C/svg%3E")`,
              backgroundRepeat: "no-repeat",
              backgroundPosition: "right 12px center",
              backgroundSize: "16px",
            }}
          >
            {METRICS.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
          </select>

          <button
            onClick={compare}
            disabled={loading || selected.length < 2}
            className="mt-4 w-full px-4 py-3 bg-accent text-white rounded-lg font-medium hover:bg-accent/90 disabled:opacity-40 disabled:cursor-not-allowed transition-all active:scale-[0.98]"
          >
            {loading ? (
              <span className="flex items-center justify-center gap-2">
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Comparing...
              </span>
            ) : (
              `Compare ${selected.length < 2 ? "(select 2+)" : ""}`
            )}
          </button>
        </div>
      </div>

      {/* Results */}
      <AnimatePresence mode="wait">
        {results && (
          <motion.div
            key={metric + selected.join(",")}
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -15 }}
            transition={{ duration: 0.5 }}
            className="bg-card border border-border rounded-xl p-6"
          >
            <h2 className="text-xl font-semibold mb-1">
              {METRICS.find((m) => m.value === metric)?.label}
            </h2>
            <p className="text-xs text-muted mb-6">
              AFR data is self-reported; fiscal years may differ across units.
            </p>

            <div className="space-y-4">
              {results
                .sort((a, b) => (b.value || 0) - (a.value || 0))
                .map((r, i) => (
                  <motion.div
                    key={r.unit_id}
                    initial={{ opacity: 0, x: -40 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{
                      duration: 0.4,
                      delay: i * 0.08,
                      ease: "easeOut",
                    }}
                  >
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-sm font-medium truncate max-w-[200px]">
                        {r.name}
                      </span>
                      <div className="flex items-center gap-3">
                        <span className="text-sm font-mono font-semibold">
                          {r.value != null ? dollars(r.value) : "\u2014"}
                        </span>
                        {r.fiscal_year && (
                          <span className="text-xs text-muted bg-background px-2 py-0.5 rounded">
                            FY{r.fiscal_year}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="h-3 bg-accent/10 rounded-full overflow-hidden">
                      {r.value != null ? (
                        <motion.div
                          className="h-full rounded-full"
                          style={{
                            background:
                              "linear-gradient(90deg, #3b82f6, #1d4ed8)",
                          }}
                          initial={{ width: 0 }}
                          animate={{
                            width: `${Math.max((r.value / maxVal) * 100, 2)}%`,
                          }}
                          transition={{
                            duration: 0.8,
                            delay: i * 0.08 + 0.3,
                            ease: "easeOut",
                          }}
                        />
                      ) : (
                        <div className="h-full flex items-center px-2">
                          <span className="text-xs text-muted">
                            {r.note || "No data"}
                          </span>
                        </div>
                      )}
                    </div>
                  </motion.div>
                ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

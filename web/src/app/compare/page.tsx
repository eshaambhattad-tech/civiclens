"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import gsap from "gsap";
import dynamic from "next/dynamic";

const CompareMap = dynamic(() => import("@/components/CompareMap"), {
  ssr: false,
  loading: () => (
    <div className="h-full w-full flex items-center justify-center bg-[#f1f5f9] rounded-xl">
      <div className="flex flex-col items-center gap-3">
        <div className="w-8 h-8 border-2 border-accent border-t-transparent rounded-full animate-spin" />
        <span className="text-sm text-muted">Loading map...</span>
      </div>
    </div>
  ),
});

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface UnitWithOfficial {
  id: string;
  name: string;
  type: string;
  population: number | null;
  website: string | null;
  official_role: string | null;
  official_name: string | null;
  official_photo: string | null;
}

type SortField = "name" | "type";
type SortDir = "asc" | "desc";

function OfficialAvatar({
  photo,
  name,
  isSelected,
}: {
  photo: string | null;
  name: string;
  isSelected: boolean;
}) {
  const initials = name
    .split(" ")
    .map((w) => w[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  if (photo) {
    return (
      <img
        src={photo}
        alt={name}
        className={`w-10 h-10 rounded-md object-cover border-2 transition-colors ${
          isSelected ? "border-[#c41e2a]" : "border-transparent"
        }`}
        onError={(e) => {
          // Fallback to initials on broken image
          const el = e.currentTarget;
          el.style.display = "none";
          el.nextElementSibling?.classList.remove("hidden");
        }}
      />
    );
  }

  return (
    <div
      className={`w-10 h-10 rounded-md flex items-center justify-center text-white text-xs font-bold transition-colors ${
        isSelected ? "bg-[#c41e2a]" : "bg-accent/70"
      }`}
    >
      {initials}
    </div>
  );
}

export default function ComparePage() {
  const [units, setUnits] = useState<UnitWithOfficial[]>([]);
  const [geojson, setGeojson] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [address, setAddress] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchResult, setSearchResult] = useState<string | null>(null);
  const [sortField, setSortField] = useState<SortField>("name");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [filterType, setFilterType] = useState<string>("township");

  const headerRef = useRef<HTMLDivElement>(null);
  const tableBodyRef = useRef<HTMLTableSectionElement>(null);
  const infoCardRef = useRef<HTMLDivElement>(null);
  const hasAnimated = useRef(false);

  // Fetch data
  useEffect(() => {
    setLoading(true);
    hasAnimated.current = false;
    const url = filterType
      ? `${API_BASE}/units/with-officials?type=${filterType}`
      : `${API_BASE}/units/with-officials`;
    fetch(url)
      .then((r) => {
        if (!r.ok) throw new Error(`API ${r.status}`);
        return r.json();
      })
      .then((data) => {
        setUnits(data.units || []);
        setGeojson(data.geojson || null);
        setLoading(false);
      })
      .catch(() => {
        setError(true);
        setLoading(false);
      });
  }, [filterType]);

  // GSAP header entrance
  useEffect(() => {
    if (!headerRef.current) return;
    const tl = gsap.timeline({ defaults: { ease: "power3.out" } });
    tl.fromTo(
      headerRef.current,
      { y: 30, opacity: 0, filter: "blur(8px)" },
      { y: 0, opacity: 1, filter: "blur(0px)", duration: 0.7 }
    );
  }, []);

  // GSAP staggered row entrance after data loads
  useEffect(() => {
    if (loading || hasAnimated.current || !tableBodyRef.current) return;
    hasAnimated.current = true;

    const rows = tableBodyRef.current.querySelectorAll("tr");
    if (rows.length === 0) return;

    gsap.set(rows, { opacity: 0, y: 12, scale: 0.98 });
    gsap.to(rows, {
      opacity: 1,
      y: 0,
      scale: 1,
      duration: 0.4,
      stagger: 0.04,
      ease: "power2.out",
      clearProps: "transform",
    });
  }, [loading, units]);

  // GSAP info card animation
  useEffect(() => {
    if (!infoCardRef.current) return;
    if (selectedId) {
      gsap.fromTo(
        infoCardRef.current,
        { opacity: 0, y: -12, scale: 0.95 },
        { opacity: 1, y: 0, scale: 1, duration: 0.35, ease: "back.out(1.4)" }
      );
    }
  }, [selectedId]);

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!address.trim()) return;
    setSearching(true);
    setSearchResult(null);
    try {
      const res = await fetch(
        `${API_BASE}/governments?address=${encodeURIComponent(address.trim())}`
      );
      if (!res.ok) throw new Error();
      const data = await res.json();
      const match = data.units?.find(
        (u: any) => u.type === filterType || !filterType
      );
      if (match) {
        setSelectedId(match.id);
        setSearchResult(match.name);
      } else if (data.units?.length > 0) {
        setSelectedId(data.units[0].id);
        setSearchResult(data.units[0].name);
      } else {
        setSearchResult("No matching unit found");
      }
    } catch {
      setSearchResult("Could not search. Is the API running?");
    }
    setSearching(false);
  }

  function toggleSort(field: SortField) {
    if (sortField === field) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortField(field);
      setSortDir("asc");
    }
  }

  const sortedUnits = [...units].sort((a, b) => {
    const valA = String(a[sortField] || "");
    const valB = String(b[sortField] || "");
    const cmp = valA.localeCompare(valB);
    return sortDir === "asc" ? cmp : -cmp;
  });

  const handleMapSelect = useCallback((id: string | null) => {
    setSelectedId(id);
  }, []);

  const handleMapHover = useCallback((id: string | null) => {
    setHoveredId(id);
  }, []);

  const SortIcon = ({ field }: { field: SortField }) => (
    <svg
      className={`w-3.5 h-3.5 inline-block ml-1 transition-transform ${
        sortField === field ? "text-accent" : "text-muted/40"
      } ${sortField === field && sortDir === "desc" ? "rotate-180" : ""}`}
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M7 11l5-5 5 5M7 17l5-5 5 5"
      />
    </svg>
  );

  const typeLabel =
    filterType === "township"
      ? "Township"
      : filterType === "municipality"
        ? "Municipality"
        : filterType === "special_district"
          ? "District"
          : "Unit";

  const leaderLabel =
    filterType === "township"
      ? "Supervisor"
      : filterType === "municipality"
        ? "Mayor/President"
        : "Leader";

  const selectedUnit = selectedId
    ? units.find((u) => u.id === selectedId)
    : null;

  return (
    <div className="flex flex-col lg:flex-row h-[calc(100vh-64px)]">
      {/* Left panel */}
      <div className="w-full lg:w-[52%] xl:w-[48%] flex flex-col border-r border-border overflow-hidden">
        <div
          ref={headerRef}
          className="px-6 pt-8 pb-4"
          style={{ opacity: 0 }}
        >
          <h1 className="text-2xl sm:text-3xl font-bold mb-1">
            Find Your {typeLabel} &amp;{" "}
            <span className="text-accent">{leaderLabel}</span>
          </h1>
          <p className="text-sm text-muted mb-5 max-w-lg">
            Enter your address or browse the map to find which of Cook
            County&apos;s {units.length > 0 ? units.length : ""}{" "}
            {typeLabel.toLowerCase()}s you live in and who your{" "}
            {leaderLabel.toLowerCase()} is.
          </p>

          {/* Address search */}
          <form onSubmit={handleSearch} className="flex gap-2 mb-4">
            <input
              type="text"
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              placeholder="Enter your address"
              className="flex-1 px-4 py-2.5 rounded-lg border border-border bg-card text-sm focus:outline-none focus:ring-2 focus:ring-accent"
            />
            <button
              type="submit"
              disabled={searching || !address.trim()}
              className="px-5 py-2.5 bg-[#c41e2a] text-white rounded-lg font-medium text-sm hover:bg-[#a81823] disabled:opacity-40 disabled:cursor-not-allowed transition-all flex items-center gap-2"
            >
              {searching ? (
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <>
                  <svg
                    className="w-4 h-4"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={2}
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                    />
                  </svg>
                  Search
                </>
              )}
            </button>
          </form>

          {/* Type filter tabs */}
          <div className="flex gap-1 text-xs">
            {[
              { value: "township", label: "Townships" },
              { value: "municipality", label: "Municipalities" },
              { value: "", label: "All" },
            ].map((t) => (
              <button
                key={t.value}
                onClick={() => {
                  setFilterType(t.value);
                  setSelectedId(null);
                }}
                className={`px-3 py-1.5 rounded-md transition-colors ${
                  filterType === t.value
                    ? "bg-accent text-white"
                    : "bg-card border border-border text-muted hover:text-foreground"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>

        {/* Table */}
        <div className="flex-1 overflow-y-auto">
          {error ? (
            <div className="px-6 py-10 text-center text-sm text-red-600">
              Could not load data. Make sure the API is running at {API_BASE}
            </div>
          ) : loading ? (
            <div className="px-6 py-10 flex flex-col items-center gap-3">
              <div className="w-6 h-6 border-2 border-accent border-t-transparent rounded-full animate-spin" />
              <span className="text-sm text-muted">Loading officials...</span>
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-background z-10">
                <tr className="border-b border-border text-left">
                  <th className="w-14 px-3 py-3"></th>
                  <th
                    className="px-3 py-3 font-medium cursor-pointer select-none hover:text-accent transition-colors"
                    onClick={() => toggleSort("name")}
                  >
                    {leaderLabel}
                    <SortIcon field="name" />
                  </th>
                  <th
                    className="px-3 py-3 font-medium cursor-pointer select-none hover:text-accent transition-colors text-right"
                    onClick={() => toggleSort("type")}
                  >
                    {typeLabel}
                    <SortIcon field="type" />
                  </th>
                </tr>
              </thead>
              <tbody ref={tableBodyRef}>
                {sortedUnits.map((u) => {
                  const isSelected = selectedId === u.id;
                  const isHovered = hoveredId === u.id;
                  return (
                    <tr
                      key={u.id}
                      className={`border-b border-border/50 cursor-pointer transition-colors duration-150 ${
                        isSelected
                          ? "bg-[#c41e2a]/8"
                          : isHovered
                            ? "bg-accent/5"
                            : "hover:bg-card-hover"
                      }`}
                      onClick={() =>
                        setSelectedId(isSelected ? null : u.id)
                      }
                      onMouseEnter={() => setHoveredId(u.id)}
                      onMouseLeave={() => setHoveredId(null)}
                    >
                      <td className="px-3 py-2.5">
                        <div className="relative">
                          <OfficialAvatar
                            photo={u.official_photo}
                            name={u.official_name || u.name}
                            isSelected={isSelected}
                          />
                          {/* Hidden fallback for broken images */}
                          <div
                            className={`hidden w-10 h-10 rounded-md items-center justify-center text-white text-xs font-bold absolute inset-0 ${
                              isSelected ? "bg-[#c41e2a]" : "bg-accent/70"
                            }`}
                          >
                            {(u.official_name || u.name)
                              .split(" ")
                              .map((w) => w[0])
                              .slice(0, 2)
                              .join("")
                              .toUpperCase()}
                          </div>
                        </div>
                      </td>
                      <td className="px-3 py-2.5">
                        <span
                          className={`font-medium ${
                            isSelected
                              ? "text-[#c41e2a]"
                              : "text-accent hover:underline"
                          }`}
                        >
                          {u.official_name || "\u2014"}
                        </span>
                        {u.official_role && (
                          <span className="block text-xs text-muted capitalize">
                            {u.official_role}
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2.5 text-right text-muted">
                        {u.name}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-border text-xs text-muted">
          Part of the{" "}
          <span className="text-accent font-medium">CivicLens</span> project.
          Data from Census TIGER/Line, IL Comptroller, Cook County Clerk.
        </div>
      </div>

      {/* Right panel — map */}
      <div className="flex-1 relative min-h-[400px] lg:min-h-0">
        <CompareMap
          geojson={geojson}
          selectedId={selectedId}
          hoveredId={hoveredId}
          onSelect={handleMapSelect}
          onHover={handleMapHover}
        />

        {/* Selected unit info card */}
        {selectedUnit && (
          <div
            ref={infoCardRef}
            className="absolute top-3 right-3 bg-white border border-border rounded-lg shadow-lg px-4 py-3 z-[1000] max-w-[240px]"
          >
            <div className="flex items-center gap-3">
              {selectedUnit.official_photo && (
                <img
                  src={selectedUnit.official_photo}
                  alt={selectedUnit.official_name || ""}
                  className="w-10 h-10 rounded-md object-cover"
                />
              )}
              <div>
                <div className="text-xs text-muted font-medium mb-0.5">
                  {selectedUnit.name}
                </div>
                <div className="text-sm font-semibold">
                  {selectedUnit.official_name || "No official on file"}
                </div>
                {selectedUnit.official_role && (
                  <div className="text-xs text-muted capitalize">
                    {selectedUnit.official_role}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

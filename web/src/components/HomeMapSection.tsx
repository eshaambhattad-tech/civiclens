"use client";

import { useRef, useEffect, useState } from "react";
import dynamic from "next/dynamic";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

const CookCountyMap = dynamic(() => import("./CookCountyMap"), {
  ssr: false,
  loading: () => (
    <div className="h-[500px] rounded-xl border border-border bg-card flex items-center justify-center">
      <div className="w-8 h-8 border-2 border-accent border-t-transparent rounded-full animate-spin" />
    </div>
  ),
});

const TYPES = [
  { value: "", label: "All Units" },
  { value: "township", label: "Townships" },
  { value: "municipality", label: "Municipalities" },
  { value: "county", label: "County" },
  { value: "special_district", label: "Special Districts" },
];

const LEGEND = [
  { color: "#3b82f6", label: "Township" },
  { color: "#10b981", label: "Municipality" },
  { color: "#8b5cf6", label: "County" },
  { color: "#f59e0b", label: "Special District" },
];

export default function HomeMapSection() {
  const [filterType, setFilterType] = useState("");
  const sectionRef = useRef<HTMLDivElement>(null);
  const headingRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!headingRef.current) return;
    gsap.fromTo(
      headingRef.current,
      { y: 40, opacity: 0 },
      {
        y: 0,
        opacity: 1,
        duration: 0.7,
        ease: "power3.out",
        scrollTrigger: {
          trigger: headingRef.current,
          start: "top 85%",
          once: true,
        },
      }
    );
  }, []);

  return (
    <div ref={sectionRef} className="mt-4">
      <div ref={headingRef} style={{ opacity: 0 }}>
        <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 mb-5">
          <div>
            <h2 className="text-2xl font-bold">Explore Cook County</h2>
            <p className="text-muted text-sm mt-1">
              Click any boundary to view officials, finances, and meetings.
            </p>
          </div>

          {/* Type filter tabs */}
          <div className="flex gap-1 bg-card border border-border rounded-lg p-1">
            {TYPES.map((t) => (
              <button
                key={t.value}
                onClick={() => setFilterType(t.value)}
                className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all ${
                  filterType === t.value
                    ? "bg-accent text-white shadow-sm"
                    : "text-muted hover:text-foreground hover:bg-card-hover"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <CookCountyMap filterType={filterType || undefined} />

      {/* Legend */}
      <div className="flex items-center gap-5 mt-3 text-xs text-muted">
        {LEGEND.map((l) => (
          <div key={l.label} className="flex items-center gap-1.5">
            <div
              className="w-3 h-3 rounded-sm"
              style={{ backgroundColor: l.color, opacity: 0.6 }}
            />
            <span>{l.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

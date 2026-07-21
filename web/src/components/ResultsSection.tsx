"use client";

import { useRef, useEffect } from "react";
import gsap from "gsap";
import UnitCard from "./UnitCard";

interface Unit {
  id: string;
  name: string;
  type: string;
  officials_count?: number;
  latest_fy?: number;
  next_meeting?: string;
}

interface Props {
  matchedAddress: string;
  units: Unit[];
  provenance: { source_url: string; as_of: string; note?: string };
}

export default function ResultsSection({
  matchedAddress,
  units,
  provenance,
}: Props) {
  const headerRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const tl = gsap.timeline({ defaults: { ease: "power3.out" } });

    tl.fromTo(
      headerRef.current,
      { opacity: 0, y: 20, filter: "blur(4px)" },
      { opacity: 1, y: 0, filter: "blur(0px)", duration: 0.6 }
    );

    if (listRef.current?.children) {
      tl.fromTo(
        Array.from(listRef.current.children),
        { opacity: 0, y: 25, scale: 0.98 },
        {
          opacity: 1,
          y: 0,
          scale: 1,
          duration: 0.4,
          stagger: 0.08,
          ease: "power2.out",
        },
        "-=0.3"
      );
    }
  }, []);

  return (
    <div>
      <div ref={headerRef} style={{ opacity: 0 }}>
        <div className="bg-card border border-border rounded-xl p-4 mb-6">
          <p className="text-sm text-muted">
            Matched:{" "}
            <strong className="text-foreground">{matchedAddress}</strong>
          </p>
          <p className="text-sm font-medium mt-1">
            You live under{" "}
            <span className="text-accent font-bold">{units.length}</span> layer
            {units.length !== 1 ? "s" : ""} of local government:
          </p>
        </div>
      </div>
      <div ref={listRef} className="flex flex-col gap-3">
        {units.map((unit, i) => (
          <UnitCard key={unit.id} unit={unit} index={i} />
        ))}
      </div>
      <p className="text-xs text-muted mt-6">
        Source: Census TIGER/Line | As of: {provenance.as_of} |{" "}
        {provenance.note}
      </p>
    </div>
  );
}

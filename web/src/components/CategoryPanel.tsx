"use client";

import { useEffect } from "react";
import { lookupCategory } from "@/lib/glossary";

interface Props {
  name: string;
  kind: "expenditure" | "revenue";
  amount?: number | null;
  share?: string;
  onClose: () => void;
}

export default function CategoryPanel({ name, kind, amount, share, onClose }: Props) {
  const entry = lookupCategory(name, kind);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-[2000] flex items-end sm:items-center justify-center p-0 sm:p-6"
      style={{ background: "rgba(11,11,11,0.45)" }}
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={`About ${name}`}
    >
      <div
        className="bg-card border border-border w-full sm:max-w-lg max-h-[85vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div
          className="px-5 py-4 flex items-start justify-between gap-4"
          style={{ background: "var(--accent-darkest)", color: "#fff" }}
        >
          <div>
            <div className="label-gov mb-1" style={{ color: "rgba(255,255,255,0.7)" }}>
              {kind === "expenditure" ? "Expenditure category" : "Revenue category"}
            </div>
            <h3 className="text-lg font-bold tracking-tight">{name}</h3>
            {amount !== undefined && amount !== null && (
              <p className="text-sm mt-1 tabular-nums" style={{ color: "rgba(255,255,255,0.82)" }}>
                {amount.toLocaleString("en-US", {
                  style: "currency",
                  currency: "USD",
                  maximumFractionDigits: 0,
                })}
                {share ? ` · ${share} of the total` : ""}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="text-white/70 hover:text-white text-xl leading-none shrink-0"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        <div className="px-5 py-5">
          {entry ? (
            <>
              <p className="text-sm leading-relaxed mb-4">{entry.summary}</p>

              {entry.includes && (
                <>
                  <div className="label-gov mb-2">Typically includes</div>
                  <ul className="mb-4 space-y-1.5">
                    {entry.includes.map((item) => (
                      <li key={item} className="text-sm flex gap-2">
                        <span style={{ color: "var(--accent)" }}>·</span>
                        <span>{item}</span>
                      </li>
                    ))}
                  </ul>
                </>
              )}

              {entry.note && (
                <div
                  className="text-sm px-3 py-2.5 border-l-2"
                  style={{ background: "var(--background)", borderColor: "var(--accent)" }}
                >
                  {entry.note}
                </div>
              )}
            </>
          ) : (
            <p className="text-sm text-muted">
              No plain-language definition on file for this category yet.
            </p>
          )}

          <p className="text-xs text-muted mt-5 pt-4 border-t border-border">
            Categories follow the Illinois Comptroller&apos;s Annual Financial Report chart of
            accounts. Definitions are written by CivicLens to explain what each line covers, and
            are not themselves official Comptroller text.
          </p>
        </div>
      </div>
    </div>
  );
}

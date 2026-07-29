"use client";

import { useEffect, useState } from "react";

export default function ColdStartNotice() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 mb-3 text-xs text-muted">
        <span>
          Maps and tables can take up to a minute to appear on the first visit.
        </span>
        <button
          onClick={() => setOpen(true)}
          className="underline hover:text-accent font-semibold"
        >
          Learn more
        </button>
      </div>

      {open && (
        <div
          className="fixed inset-0 z-[1000] flex items-center justify-center p-4"
          style={{ background: "rgba(15, 23, 42, 0.55)" }}
          onClick={() => setOpen(false)}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="cold-start-title"
            className="bg-card border border-border rounded-xl max-w-lg w-full p-6 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-4 mb-3">
              <h2 id="cold-start-title" className="text-lg font-bold tracking-tight">
                Why the first load is slow
              </h2>
              <button
                onClick={() => setOpen(false)}
                aria-label="Close"
                className="text-muted hover:text-foreground text-xl leading-none -mt-1"
              >
                ×
              </button>
            </div>

            <div className="text-sm text-muted space-y-3">
              <p>
                CivicLens runs on free hosting. The server that answers data
                requests goes to sleep after about fifteen minutes without
                traffic, so if you are the first visitor in a while, it has to
                start up again before it can respond. That takes roughly thirty
                to sixty seconds.
              </p>
              <p>
                The county map also carries real geography — the boundary
                outlines for all 178 units of local government are several
                megabytes of coordinates, drawn in your browser rather than
                shipped as flat images, which is what lets you hover and click
                individual jurisdictions.
              </p>
              <p>
                Once the server is awake, every later page loads immediately.
                Nothing is broken; you are just early.
              </p>
            </div>

            <button
              onClick={() => setOpen(false)}
              className="mt-5 px-4 py-2 text-sm font-semibold rounded-sm text-white"
              style={{ background: "var(--accent-darkest)" }}
            >
              Got it
            </button>
          </div>
        </div>
      )}
    </>
  );
}

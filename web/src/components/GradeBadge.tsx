"use client";

const LETTER_STYLE: Record<string, { bg: string; fg: string }> = {
  A: { bg: "#0B5B33", fg: "#ffffff" },
  B: { bg: "#1B7A4A", fg: "#ffffff" },
  C: { bg: "#8A6D1B", fg: "#ffffff" },
  D: { bg: "#9A4A12", fg: "#ffffff" },
  F: { bg: "#8B1E1E", fg: "#ffffff" },
};

export function GradeBadge({
  letter,
  size = "md",
  title,
}: {
  letter: string | null | undefined;
  size?: "sm" | "md" | "lg";
  title?: string;
}) {
  if (!letter) {
    return (
      <span
        className="inline-flex items-center justify-center font-bold tabular-nums text-muted"
        style={{
          width: size === "lg" ? 48 : size === "sm" ? 22 : 32,
          height: size === "lg" ? 48 : size === "sm" ? 22 : 32,
          fontSize: size === "lg" ? 22 : size === "sm" ? 11 : 15,
          background: "var(--background)",
          border: "1px solid var(--border)",
        }}
        title={title || "Ungraded"}
      >
        —
      </span>
    );
  }
  const style = LETTER_STYLE[letter] || LETTER_STYLE.C;
  return (
    <span
      className="inline-flex items-center justify-center font-bold tabular-nums"
      style={{
        width: size === "lg" ? 48 : size === "sm" ? 22 : 32,
        height: size === "lg" ? 48 : size === "sm" ? 22 : 32,
        fontSize: size === "lg" ? 22 : size === "sm" ? 11 : 15,
        background: style.bg,
        color: style.fg,
      }}
      title={title || `Grade ${letter}`}
      aria-label={`Grade ${letter}`}
    >
      {letter}
    </span>
  );
}

const DIM_LABELS: Record<string, string> = {
  filing: "Filing",
  transparency: "Transparency",
  program_mix: "Program mix",
  reserves: "Reserves",
  cost_burden: "Cost burden",
};

export function GradeCard({
  grade,
}: {
  grade: {
    letter: string | null;
    score: number | null;
    rank?: number;
    peer_count?: number;
    fiscal_year?: number;
    dimensions?: Record<string, number>;
    flags?: string[];
    ungraded_reason?: string;
    methodology?: { summary?: string; limitations?: string[] };
    peer_median?: { score?: number | null };
  };
}) {
  if (!grade.letter || grade.score == null) {
    return (
      <section className="mb-12 border border-border bg-card px-5 py-5">
        <div className="flex items-start gap-4">
          <GradeBadge letter={null} size="lg" />
          <div>
            <h2 className="text-lg font-bold tracking-tight">Money management grade</h2>
            <p className="text-sm text-muted mt-1">
              {grade.ungraded_reason || "No grade available for this government."}
            </p>
          </div>
        </div>
      </section>
    );
  }

  const dims = grade.dimensions || {};

  return (
    <section className="mb-12 border border-border bg-card px-5 py-5">
      <div className="flex flex-wrap items-start justify-between gap-4 mb-5">
        <div className="flex items-start gap-4">
          <GradeBadge
            letter={grade.letter}
            size="lg"
            title={`Grade ${grade.letter} (${grade.score})`}
          />
          <div>
            <div className="label-gov mb-1">Money management grade</div>
            <h2 className="text-lg font-bold tracking-tight">
              {grade.letter} · {grade.score}
              {grade.fiscal_year ? (
                <span className="text-muted font-normal text-sm ml-2">FY{grade.fiscal_year}</span>
              ) : null}
            </h2>
            <p className="text-sm text-muted mt-1">
              Ranked {grade.rank} of {grade.peer_count} Cook County townships
              {grade.peer_median?.score != null
                ? ` · peer median score ${grade.peer_median.score}`
                : ""}
              . Letter is a peer-rank quintile from AFR filings — not an audit.
            </p>
          </div>
        </div>
      </div>

      <div className="grid gap-2.5 sm:grid-cols-2">
        {Object.entries(dims).map(([key, value]) => (
          <div key={key}>
            <div className="flex items-baseline justify-between gap-2 mb-1">
              <span className="text-xs font-semibold">{DIM_LABELS[key] || key}</span>
              <span className="text-xs tabular-nums text-muted">{value.toFixed(0)}</span>
            </div>
            <div className="h-1.5 w-full" style={{ background: "var(--viz-bar-soft)" }}>
              <div
                className="h-1.5"
                style={{
                  width: `${Math.min(100, Math.max(0, value))}%`,
                  background: "var(--viz-bar)",
                }}
              />
            </div>
          </div>
        ))}
      </div>

      {grade.flags && grade.flags.length > 0 && (
        <ul className="mt-4 space-y-1 text-xs text-muted">
          {grade.flags.map((f) => (
            <li key={f}>· {f}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

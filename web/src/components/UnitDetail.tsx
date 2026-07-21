"use client";

import { useRef, useEffect } from "react";
import Link from "next/link";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { motion } from "framer-motion";

gsap.registerPlugin(ScrollTrigger);

function dollars(n: number | null | undefined) {
  if (n == null) return "\u2014";
  return "$" + Number(n).toLocaleString("en-US", { maximumFractionDigits: 0 });
}

interface Official {
  role: string;
  name: string;
  email?: string;
  phone?: string;
  term_end?: string;
}

interface AFRYear {
  fiscal_year: number;
  total_revenues: number;
  total_expenditures: number;
  fund_balance?: number;
  per_capita_expenditures?: number;
  filed_on_time?: boolean;
  fund_detail?: {
    expenditures_by_category?: Record<string, number>;
    revenues_by_category?: Record<string, number>;
  };
}

interface Provenance {
  source_url: string;
  as_of: string;
  note?: string;
}

interface Props {
  unit: {
    id: string;
    name: string;
    type: string;
    population?: number;
    website?: string;
    has_spend_detail?: boolean;
    has_meetings?: boolean;
    officials_count?: number;
    latest_afr_year?: number;
  };
  officials: Official[];
  officialsProvenance?: Provenance;
  years: AFRYear[];
  financesProvenance?: Provenance;
}

const TYPE_COLORS: Record<string, string> = {
  county: "bg-purple-100 text-purple-800",
  township: "bg-blue-100 text-blue-800",
  municipality: "bg-green-100 text-green-800",
  special_district: "bg-orange-100 text-orange-800",
};

export default function UnitDetail({
  unit,
  officials,
  officialsProvenance,
  years,
  financesProvenance,
}: Props) {
  const headerRef = useRef<HTMLDivElement>(null);
  const officialsRef = useRef<HTMLElement>(null);
  const financesRef = useRef<HTMLElement>(null);
  const breakdownRef = useRef<HTMLElement>(null);
  const coverageRef = useRef<HTMLElement>(null);

  useEffect(() => {
    // Header entrance
    const tl = gsap.timeline({ defaults: { ease: "power3.out" } });
    tl.fromTo(
      headerRef.current,
      { y: 40, opacity: 0, filter: "blur(6px)" },
      { y: 0, opacity: 1, filter: "blur(0px)", duration: 0.8 }
    );

    // ScrollTrigger sections
    const sections = [officialsRef, financesRef, breakdownRef, coverageRef];
    sections.forEach((ref) => {
      if (!ref.current) return;
      gsap.fromTo(
        ref.current,
        { y: 40, opacity: 0 },
        {
          y: 0,
          opacity: 1,
          duration: 0.7,
          ease: "power2.out",
          scrollTrigger: {
            trigger: ref.current,
            start: "top 85%",
            once: true,
          },
        }
      );
    });
  }, []);

  return (
    <div className="max-w-4xl mx-auto px-6 py-10">
      <Link
        href="/"
        className="inline-flex items-center gap-1 text-sm text-muted hover:text-accent transition-colors"
      >
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
            d="M15 19l-7-7 7-7"
          />
        </svg>
        Back to search
      </Link>

      {/* Header */}
      <div ref={headerRef} className="mt-4 mb-10" style={{ opacity: 0 }}>
        <div className="flex items-start gap-3 mb-2">
          <h1 className="text-3xl sm:text-4xl font-bold">{unit.name}</h1>
          <span
            className={`text-xs px-2.5 py-1 rounded-full font-medium mt-2 capitalize ${TYPE_COLORS[unit.type] || "bg-gray-100 text-gray-800"}`}
          >
            {unit.type.replace("_", " ")}
          </span>
        </div>
        <div className="flex flex-wrap gap-4 text-sm text-muted">
          {unit.population && (
            <span className="flex items-center gap-1">
              <svg
                className="w-3.5 h-3.5"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z"
                />
              </svg>
              Pop. {unit.population.toLocaleString()}
            </span>
          )}
          {unit.website && (
            <a
              href={unit.website}
              target="_blank"
              className="flex items-center gap-1 text-accent hover:underline"
            >
              <svg
                className="w-3.5 h-3.5"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M13.5 6H5.25A2.25 2.25 0 003 8.25v10.5A2.25 2.25 0 005.25 21h10.5A2.25 2.25 0 0018 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25"
                />
              </svg>
              Website
            </a>
          )}
        </div>
      </div>

      {/* Officials */}
      <section ref={officialsRef} className="mb-12" style={{ opacity: 0 }}>
        <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
          <div className="w-1 h-6 bg-accent rounded-full" />
          Elected Officials
        </h2>
        {officials.length === 0 ? (
          <div className="bg-card border border-border rounded-xl p-6 text-center">
            <p className="text-muted text-sm">
              No officials data available for this unit.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {officials.map((o, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 15 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: 0.3 + i * 0.05 }}
                className="border border-border rounded-xl p-4 bg-card hover:shadow-md hover:border-accent/30 transition-all"
              >
                <div className="text-xs text-muted uppercase tracking-wider mb-1.5 font-medium">
                  {o.role}
                </div>
                <div className="font-semibold text-foreground">{o.name}</div>
                {o.email && (
                  <a
                    href={`mailto:${o.email}`}
                    className="text-sm text-accent hover:underline mt-1 block"
                  >
                    {o.email}
                  </a>
                )}
                {o.term_end && (
                  <div className="text-xs text-muted mt-2 flex items-center gap-1">
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
                        d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5"
                      />
                    </svg>
                    Term ends {o.term_end}
                  </div>
                )}
              </motion.div>
            ))}
          </div>
        )}
        {officialsProvenance && (
          <p className="text-xs text-muted mt-3">
            As of {officialsProvenance.as_of} | {officialsProvenance.note}
          </p>
        )}
      </section>

      {/* Finances */}
      <section ref={financesRef} className="mb-12" style={{ opacity: 0 }}>
        <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
          <div className="w-1 h-6 bg-green-500 rounded-full" />
          Finances
        </h2>
        {years.length === 0 ? (
          <div className="bg-card border border-border rounded-xl p-6 text-center">
            <p className="text-muted text-sm">
              No financial data available for this unit.
            </p>
          </div>
        ) : (
          <div className="bg-card border border-border rounded-xl overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-muted border-b border-border bg-card-hover">
                    <th className="py-3 px-4 font-medium">Fiscal Year</th>
                    <th className="py-3 px-4 font-medium">Revenues</th>
                    <th className="py-3 px-4 font-medium">Expenditures</th>
                    <th className="py-3 px-4 font-medium">Fund Balance</th>
                    <th className="py-3 px-4 font-medium">Per Capita Exp.</th>
                    <th className="py-3 px-4 font-medium">Filed on Time</th>
                  </tr>
                </thead>
                <tbody>
                  {years.map((y, i) => (
                    <motion.tr
                      key={y.fiscal_year}
                      initial={{ opacity: 0, x: -10 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: 0.1 + i * 0.05 }}
                      className="border-b border-border/50 hover:bg-card-hover transition-colors"
                    >
                      <td className="py-3 px-4 font-semibold">
                        FY{y.fiscal_year}
                      </td>
                      <td className="py-3 px-4 font-mono text-green-700">
                        {dollars(y.total_revenues)}
                      </td>
                      <td className="py-3 px-4 font-mono">
                        {dollars(y.total_expenditures)}
                      </td>
                      <td className="py-3 px-4 font-mono">
                        {dollars(y.fund_balance)}
                      </td>
                      <td className="py-3 px-4 font-mono">
                        {y.per_capita_expenditures
                          ? dollars(y.per_capita_expenditures)
                          : "\u2014"}
                      </td>
                      <td className="py-3 px-4">
                        {y.filed_on_time === true ? (
                          <span className="inline-flex items-center gap-1 text-green-700 text-xs font-medium bg-green-50 px-2 py-0.5 rounded-full">
                            Yes
                          </span>
                        ) : y.filed_on_time === false ? (
                          <span className="inline-flex items-center gap-1 text-red-700 text-xs font-medium bg-red-50 px-2 py-0.5 rounded-full">
                            No
                          </span>
                        ) : (
                          "\u2014"
                        )}
                      </td>
                    </motion.tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
        {financesProvenance && (
          <p className="text-xs text-muted mt-3">
            Source: {financesProvenance.source_url} | {financesProvenance.note}
          </p>
        )}
      </section>

      {/* Fund Detail Breakdown */}
      {years.length > 0 && years[0].fund_detail && (
        <section ref={breakdownRef} className="mb-12" style={{ opacity: 0 }}>
          <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
            <div className="w-1 h-6 bg-amber-500 rounded-full" />
            FY{years[0].fiscal_year} Breakdown
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
            {years[0].fund_detail.expenditures_by_category && (
              <div className="bg-card border border-border rounded-xl p-5">
                <h3 className="text-sm font-semibold text-muted mb-3 uppercase tracking-wide">
                  Expenditures by Category
                </h3>
                <div className="space-y-3">
                  {Object.entries(years[0].fund_detail.expenditures_by_category)
                    .sort(([, a], [, b]) => b - a)
                    .map(([cat, amt]) => {
                      const max = Math.max(
                        ...Object.values(
                          years[0].fund_detail!.expenditures_by_category!
                        )
                      );
                      return (
                        <div key={cat}>
                          <div className="flex justify-between text-sm mb-1">
                            <span className="truncate mr-2">{cat}</span>
                            <span className="font-mono font-medium text-foreground">
                              {dollars(amt)}
                            </span>
                          </div>
                          <div className="h-2 bg-accent/10 rounded-full overflow-hidden">
                            <motion.div
                              className="h-full rounded-full"
                              style={{
                                background:
                                  "linear-gradient(90deg, #3b82f6, #1d4ed8)",
                              }}
                              initial={{ width: 0 }}
                              animate={{
                                width: `${(amt / max) * 100}%`,
                              }}
                              transition={{
                                duration: 0.8,
                                delay: 0.3,
                                ease: "easeOut",
                              }}
                            />
                          </div>
                        </div>
                      );
                    })}
                </div>
              </div>
            )}
            {years[0].fund_detail.revenues_by_category && (
              <div className="bg-card border border-border rounded-xl p-5">
                <h3 className="text-sm font-semibold text-muted mb-3 uppercase tracking-wide">
                  Revenues by Category
                </h3>
                <div className="space-y-3">
                  {Object.entries(years[0].fund_detail.revenues_by_category)
                    .sort(([, a], [, b]) => b - a)
                    .map(([cat, amt]) => {
                      const max = Math.max(
                        ...Object.values(
                          years[0].fund_detail!.revenues_by_category!
                        )
                      );
                      return (
                        <div key={cat}>
                          <div className="flex justify-between text-sm mb-1">
                            <span className="truncate mr-2">{cat}</span>
                            <span className="font-mono font-medium text-foreground">
                              {dollars(amt)}
                            </span>
                          </div>
                          <div className="h-2 bg-green-100 rounded-full overflow-hidden">
                            <motion.div
                              className="h-full bg-green-500 rounded-full"
                              initial={{ width: 0 }}
                              animate={{
                                width: `${(amt / max) * 100}%`,
                              }}
                              transition={{
                                duration: 0.8,
                                delay: 0.3,
                                ease: "easeOut",
                              }}
                            />
                          </div>
                        </div>
                      );
                    })}
                </div>
              </div>
            )}
          </div>
        </section>
      )}

      {/* Data coverage */}
      <section ref={coverageRef} style={{ opacity: 0 }}>
        <div className="bg-card border border-border rounded-xl p-5">
          <h2 className="font-semibold text-foreground mb-3 flex items-center gap-2">
            <div className="w-1 h-6 bg-muted rounded-full" />
            Data Coverage
          </h2>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div className="text-center p-3 bg-background rounded-lg">
              <div className="text-lg font-bold text-foreground">
                {unit.has_spend_detail ? "Yes" : "No"}
              </div>
              <div className="text-xs text-muted">Spend Detail</div>
            </div>
            <div className="text-center p-3 bg-background rounded-lg">
              <div className="text-lg font-bold text-foreground">
                {unit.has_meetings ? "Yes" : "No"}
              </div>
              <div className="text-xs text-muted">Meetings</div>
            </div>
            <div className="text-center p-3 bg-background rounded-lg">
              <div className="text-lg font-bold text-foreground">
                {unit.officials_count || 0}
              </div>
              <div className="text-xs text-muted">Officials</div>
            </div>
            <div className="text-center p-3 bg-background rounded-lg">
              <div className="text-lg font-bold text-foreground">
                {unit.latest_afr_year ? `FY${unit.latest_afr_year}` : "None"}
              </div>
              <div className="text-xs text-muted">Latest AFR</div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

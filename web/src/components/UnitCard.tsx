"use client";

import Link from "next/link";
import { motion } from "framer-motion";

interface Props {
  unit: {
    id: string;
    name: string;
    type: string;
    officials_count?: number;
    latest_fy?: number;
    next_meeting?: string;
  };
  index: number;
}

const TYPE_LABELS: Record<string, string> = {
  county: "County",
  township: "Township",
  municipality: "Municipality",
  special_district: "Special District",
};

const TYPE_COLORS: Record<string, string> = {
  county: "bg-purple-100 text-purple-800",
  township: "bg-blue-100 text-blue-800",
  municipality: "bg-green-100 text-green-800",
  special_district: "bg-orange-100 text-orange-800",
};

export default function UnitCard({ unit }: Props) {
  return (
    <Link href={`/unit/${unit.id}`}>
      <motion.div
        whileHover={{
          scale: 1.01,
          boxShadow: "0 4px 20px rgba(0,0,0,0.08)",
          borderColor: "rgba(29, 78, 216, 0.3)",
        }}
        whileTap={{ scale: 0.99 }}
        className="border border-border rounded-xl p-5 bg-card cursor-pointer transition-colors"
      >
        <div className="flex items-start justify-between mb-2">
          <h3 className="text-lg font-semibold">{unit.name}</h3>
          <span
            className={`text-xs px-2.5 py-1 rounded-full font-medium ${TYPE_COLORS[unit.type] || "bg-gray-100 text-gray-800"}`}
          >
            {TYPE_LABELS[unit.type] || unit.type}
          </span>
        </div>
        <div className="flex flex-wrap gap-4 text-sm text-muted">
          {unit.officials_count ? (
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
              {unit.officials_count} officials
            </span>
          ) : null}
          {unit.latest_fy ? (
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
                  d="M2.25 18.75a60.07 60.07 0 0115.797 2.101c.727.198 1.453-.342 1.453-1.096V18.75M3.75 4.5v.75A.75.75 0 013 6h-.75m0 0v-.375c0-.621.504-1.125 1.125-1.125H20.25M2.25 6v9m18-10.5v.75c0 .414.336.75.75.75h.75m-1.5-1.5h.375c.621 0 1.125.504 1.125 1.125v9.75c0 .621-.504 1.125-1.125 1.125h-.375m1.5-1.5H21a.75.75 0 00-.75.75v.75m0 0H3.75m0 0h-.375a1.125 1.125 0 01-1.125-1.125V15m1.5 1.5v-.75A.75.75 0 003 15h-.75M15 10.5a3 3 0 11-6 0 3 3 0 016 0zm3 0h.008v.008H18V10.5zm-12 0h.008v.008H6V10.5z"
                />
              </svg>
              FY{unit.latest_fy}
            </span>
          ) : null}
          {unit.next_meeting ? (
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
                  d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5"
                />
              </svg>
              Next:{" "}
              {new Date(unit.next_meeting).toLocaleDateString("en-US", {
                month: "short",
                day: "numeric",
              })}
            </span>
          ) : null}
        </div>

        <div className="mt-3 flex items-center text-xs text-accent font-medium">
          View details
          <svg
            className="w-3.5 h-3.5 ml-1"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3"
            />
          </svg>
        </div>
      </motion.div>
    </Link>
  );
}

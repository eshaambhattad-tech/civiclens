"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useRef, useEffect } from "react";
import gsap from "gsap";

const LINKS = [
  { href: "/", label: "Lookup" },
  { href: "/spending", label: "Spending" },
  { href: "/compare", label: "Compare" },
];

export default function Nav() {
  const pathname = usePathname();
  const navRef = useRef<HTMLElement>(null);

  useEffect(() => {
    gsap.fromTo(
      navRef.current,
      { y: -10, opacity: 0 },
      { y: 0, opacity: 1, duration: 0.5, ease: "power2.out" }
    );
  }, []);

  return (
    <nav
      ref={navRef}
      className="sticky top-0 z-50 border-b border-border bg-card/90 backdrop-blur-md px-6 py-3 flex items-center justify-between"
      style={{ opacity: 0, borderTop: "3px solid var(--accent-darkest)" }}
    >
      <Link href="/" className="flex items-center gap-2">
        <div className="w-7 h-7 bg-accent-darkest rounded-sm flex items-center justify-center">
          <svg
            className="w-4 h-4 text-white"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2.5}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M15 10.5a3 3 0 11-6 0 3 3 0 016 0z"
            />
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M19.5 10.5c0 7.142-7.5 11.25-7.5 11.25S4.5 17.642 4.5 10.5a7.5 7.5 0 1115 0z"
            />
          </svg>
        </div>
        <span className="text-lg font-bold text-foreground tracking-tight">
          Civic<span className="text-accent">Lens</span>
        </span>
      </Link>

      <div className="flex items-center border border-border rounded-sm overflow-hidden">
        {LINKS.map((link) => {
          const isActive =
            link.href === "/"
              ? pathname === "/"
              : pathname.startsWith(link.href);
          return (
            <Link
              key={link.href}
              href={link.href}
              className={`px-4 py-1.5 text-sm font-semibold transition-colors ${
                isActive
                  ? "bg-accent-darkest text-white"
                  : "text-muted hover:text-foreground hover:bg-card-hover"
              }`}
            >
              {link.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}

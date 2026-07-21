"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useRef, useEffect } from "react";
import gsap from "gsap";

const LINKS = [
  { href: "/", label: "Lookup" },
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
      className="sticky top-0 z-50 border-b border-border bg-card/80 backdrop-blur-md px-6 py-3 flex items-center justify-between"
      style={{ opacity: 0 }}
    >
      <Link href="/" className="flex items-center gap-2">
        <div className="w-7 h-7 bg-accent rounded-lg flex items-center justify-center">
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
        <span className="text-lg font-bold text-foreground">
          Civic<span className="text-accent">Lens</span>
        </span>
      </Link>

      <div className="flex items-center gap-1 bg-background rounded-lg p-1">
        {LINKS.map((link) => {
          const isActive =
            link.href === "/"
              ? pathname === "/"
              : pathname.startsWith(link.href);
          return (
            <Link
              key={link.href}
              href={link.href}
              className={`px-4 py-1.5 text-sm font-medium rounded-md transition-all ${
                isActive
                  ? "bg-accent text-white shadow-sm"
                  : "text-muted hover:text-foreground"
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

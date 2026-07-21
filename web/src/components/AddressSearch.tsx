"use client";

import { useState, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";

export default function AddressSearch() {
  const [address, setAddress] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();
  const searchParams = useSearchParams();

  // Reset loading when the page finishes navigating (searchParams change)
  useEffect(() => {
    setLoading(false);
  }, [searchParams]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!address.trim()) return;
    setLoading(true);
    router.push(`/?address=${encodeURIComponent(address.trim())}`);
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex gap-2 w-full max-w-xl relative"
    >
      <div className="flex-1 relative">
        <svg
          className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted"
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
        <input
          type="text"
          value={address}
          onChange={(e) => setAddress(e.target.value)}
          placeholder="Enter a Cook County address, e.g. 1225 Waukegan Rd, Glenview, IL"
          className="w-full pl-10 pr-4 py-3.5 rounded-xl border border-border bg-card text-foreground placeholder:text-muted/70 focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent shadow-sm text-sm"
        />
      </div>
      <button
        type="submit"
        disabled={loading || !address.trim()}
        className="px-6 py-3.5 bg-accent text-white rounded-xl font-medium hover:bg-accent/90 disabled:opacity-40 disabled:cursor-not-allowed transition-all active:scale-[0.97] shadow-sm"
      >
        {loading ? (
          <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
        ) : (
          "Search"
        )}
      </button>
    </form>
  );
}

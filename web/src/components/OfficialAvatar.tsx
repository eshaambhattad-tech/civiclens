"use client";

import { useState } from "react";

/** Deterministic navy-family tint so the same person keeps the same swatch. */
const TINTS = ["#162e51", "#1a4480", "#005ea2", "#2a78d6", "#3d5b7a", "#0b4778"];

function initials(name: string) {
  const parts = name
    .replace(/["'']/g, "")
    .split(/\s+/)
    .filter((p) => p.length > 1 && !/^[A-Z]\.$/.test(p));
  const first = parts[0]?.[0] ?? name[0] ?? "?";
  const last = parts.length > 1 ? parts[parts.length - 1][0] : "";
  return (first + last).toUpperCase();
}

function tintFor(name: string) {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
  return TINTS[h % TINTS.length];
}

export default function OfficialAvatar({
  name,
  photoUrl,
  size = 48,
}: {
  name: string;
  photoUrl?: string | null;
  size?: number;
}) {
  const [broken, setBroken] = useState(false);
  const showPhoto = photoUrl && !broken;

  if (showPhoto) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={photoUrl}
        alt={name}
        width={size}
        height={size}
        onError={() => setBroken(true)}
        className="rounded-sm object-cover shrink-0 border border-border"
        style={{ width: size, height: size }}
      />
    );
  }

  return (
    <div
      className="rounded-sm shrink-0 flex items-center justify-center text-white font-bold select-none"
      style={{
        width: size,
        height: size,
        background: tintFor(name),
        fontSize: Math.round(size * 0.34),
      }}
      aria-hidden="true"
      title={name}
    >
      {initials(name)}
    </div>
  );
}

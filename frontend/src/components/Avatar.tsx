"use client";
/**
 * A person's profile picture, falling back to their initial on a coloured disc
 * when they haven't set one. Used wherever the app shows a user.
 */
import React from "react";

const GRADIENTS = [
  "from-indigo-500 to-violet-600",
  "from-cyan-500 to-blue-600",
  "from-emerald-500 to-teal-600",
  "from-amber-500 to-orange-600",
  "from-pink-500 to-rose-600",
];

/** Stable per-person colour, so the same user keeps the same disc everywhere. */
export function avatarGradient(seed: string) {
  let n = 0;
  for (const ch of seed || "?") n = (n + ch.charCodeAt(0)) % 997;
  return GRADIENTS[n % GRADIENTS.length];
}

export default function Avatar({
  name, url, size = 36, className = "", ring = "", textClass = "",
}: {
  name?: string;
  url?: string | null;
  /** Pixel diameter — kept off Tailwind so callers can pick any size. */
  size?: number;
  className?: string;
  ring?: string;
  textClass?: string;
}) {
  const label = (name || "?").trim();
  const initial = (label[0] || "?").toUpperCase();
  const box = { width: size, height: size };

  if (url) {
    return (
      <img
        src={url}
        alt={label}
        style={box}
        // object-cover keeps a non-square upload from squashing.
        className={`rounded-full object-cover flex-shrink-0 bg-slate-100 ${ring} ${className}`}
      />
    );
  }

  return (
    <div
      style={box}
      aria-label={label}
      className={`rounded-full bg-gradient-to-br ${avatarGradient(label)} flex items-center justify-center font-bold text-white flex-shrink-0 ${ring} ${className}`}
    >
      <span className={textClass || "text-xs"}>{initial}</span>
    </div>
  );
}

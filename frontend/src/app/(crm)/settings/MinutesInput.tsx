"use client";
/**
 * A length of time typed as a number and a unit — minutes, hours or days — and
 * kept in minutes, which is what the server stores. Opens on the largest unit
 * the value divides into evenly, so 1440 reads as 1 day rather than 1440
 * minutes.
 */
import React, { useState } from "react";

const UNITS = [
  { label: "minutes", size: 1 },
  { label: "hours", size: 60 },
  { label: "days", size: 24 * 60 },
] as const;

const unitFor = (minutes: number) =>
  [...UNITS].reverse().find(u => minutes > 0 && minutes % u.size === 0)?.size ?? 60;

export default function MinutesInput({ id, minutes, onChange, maxMinutes }: {
  id: string;
  minutes: number;
  onChange: (minutes: number) => void;
  maxMinutes: number;
}) {
  const [size, setSize] = useState(() => unitFor(minutes));
  const amount = Math.round(minutes / size);
  const field = "bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition";
  return (
    <div className="flex gap-2">
      <input id={id} type="number" min={0} max={Math.floor(maxMinutes / size)} value={amount}
        onChange={e => onChange(Math.min(Math.max(parseInt(e.target.value) || 0, 0) * size, maxMinutes))}
        className={`${field} w-full min-w-0`} />
      <select value={size} aria-label="Unit"
        onChange={e => {
          const next = Number(e.target.value);
          setSize(next);
          // The number stays as typed; the unit is what changed.
          onChange(Math.min(amount * next, maxMinutes));
        }}
        className={`${field} shrink-0`}>
        {UNITS.map(u => <option key={u.size} value={u.size}>{u.label}</option>)}
      </select>
    </div>
  );
}

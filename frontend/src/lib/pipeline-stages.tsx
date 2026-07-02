import React from "react";

// The fulfilment pipeline stage (module) a lead is currently in. Keys match the
// backend Lead.pipeline_stage values.
export const STAGE_META: Record<string, { label: string; bg: string; text: string }> = {
  tele_caller:   { label: "Tele Caller",      bg: "bg-slate-100",  text: "text-slate-600" },
  site_visit:    { label: "Site Visit",       bg: "bg-sky-50",     text: "text-sky-700" },
  documentation: { label: "Documentation S1", bg: "bg-violet-50",  text: "text-violet-700" },
  accounts:      { label: "Accounts",         bg: "bg-teal-50",    text: "text-teal-700" },
  purchase:      { label: "Purchase",         bg: "bg-orange-50",  text: "text-orange-700" },
  project:       { label: "Project",          bg: "bg-emerald-50", text: "text-emerald-700" },
};

// In pipeline order (earliest → latest) for filter dropdowns.
export const STAGE_OPTIONS = ["tele_caller", "site_visit", "documentation", "accounts", "purchase", "project"];

export function StageTag({ stage }: { stage?: string }) {
  const s = stage ? STAGE_META[stage] : null;
  if (!s) return null;
  return <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold ${s.bg} ${s.text}`}>{s.label}</span>;
}

import React from "react";

// The fulfilment pipeline stage (module) a lead is currently in. Keys match the
// backend Lead.pipeline_stage values.
export const STAGE_META: Record<string, { label: string; bg: string; text: string }> = {
  tele_caller:   { label: "Tele Caller",      bg: "bg-slate-100",  text: "text-slate-600" },
  site_visit:    { label: "Site Visit",       bg: "bg-sky-50",     text: "text-sky-700" },
  po_signed:     { label: "PO Signed",        bg: "bg-fuchsia-50", text: "text-fuchsia-700" },
  documentation: { label: "Documentation S1", bg: "bg-violet-50",  text: "text-violet-700" },
  accounts:      { label: "Accounts",         bg: "bg-teal-50",    text: "text-teal-700" },
  purchase:      { label: "Purchase",         bg: "bg-orange-50",  text: "text-orange-700" },
  project:       { label: "Project",          bg: "bg-emerald-50", text: "text-emerald-700" },
};

// In pipeline order (earliest → latest) for filter dropdowns.
export const STAGE_OPTIONS = ["tele_caller", "site_visit", "po_signed", "documentation", "accounts", "purchase", "project"];

export function StageTag({ stage }: { stage?: string }) {
  const s = stage ? STAGE_META[stage] : null;
  if (!s) return null;
  return <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold ${s.bg} ${s.text}`}>{s.label}</span>;
}

// What dates a lead's arrival in each stage, for the "stage reached" filter.
// Mirrors LeadViewSet._filter_stage_reached on the backend.
export const STAGE_REACHED_BASIS: Record<string, string> = {
  tele_caller:   "the day the lead came in",
  site_visit:    "the day it was handed to a BDE",
  po_signed:     "the PO signed date on the site visit",
  documentation: "the day it was pushed to Documentation S1",
  accounts:      "the day it was pushed to Accounts",
  purchase:      "the day it was pushed to Purchase",
  project:       "the day it was pushed to Project",
};

/** "06 Oct 2026". A plain date ("2026-10-06") is read as that calendar day —
 *  `new Date()` would take it as UTC midnight, which is the day before west of
 *  Greenwich. */
export function formatStageDay(at: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(at);
  const d = m ? new Date(+m[1], +m[2] - 1, +m[3]) : new Date(at);
  return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}

/** When a row reached the stage the list is filtered by. */
export function StageReachedTag({ stage, at }: { stage: string; at?: string | null }) {
  const s = STAGE_META[stage];
  if (!s || !at) return null;
  const day = formatStageDay(at);
  return (
    <span title={`Reached ${s.label} on ${day}`}
      className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold bg-emerald-50 text-emerald-700 whitespace-nowrap">
      {s.label} · {day}
    </span>
  );
}

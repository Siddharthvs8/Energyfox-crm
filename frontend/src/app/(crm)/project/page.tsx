"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase, formatCurrency } from "@/lib/mock-data";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import DeletedLeadCleanup, { DeletedLeadBadge } from "@/components/DeletedLeadCleanup";
import { asDate, deadlineNote, type DeadlineInfo } from "@/components/ProjectDeadline";
import { isSpectator } from "@/lib/spectator";
import BdeTag from "@/components/BdeTag";

// The row carries the whole deadline block, so the shared banner and dialog can
// read it without a second fetch.
type ProjectLead = DeadlineInfo & {
  /** Who did the site visit — shown as a tag on the row. */
  bde_name?: string | null;
  // Set when the lead behind this row has been deleted; the row is then
  // unopenable, and an admin gets a control to clear it out.
  lead_deleted?: boolean;
  can_cleanup?: boolean;
  id: number;
  first_name: string;
  last_name: string | null;
  phone: string | null;
  location: string | null;
  product_name: string | null;
  value: number;
  project_manager_name: string | null;
  // The project record itself; the list reads only when it was finished.
  project?: { completed_at: string | null } | null;
};

// Which finished jobs the Completed tab shows, by the day they were finished.
// All time by default: a job finished last month should not go missing behind
// a filter nobody set.
type Period = "all" | "today" | "this_week" | "this_month" | "custom";
const PERIODS: { key: Period; label: string }[] = [
  { key: "all", label: "All time" },
  { key: "today", label: "Today" },
  { key: "this_week", label: "This week" },
  { key: "this_month", label: "This month" },
  { key: "custom", label: "Custom" },
];

const DATE_INPUT = "bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all";

/** A day as yyyy-mm-dd in the viewer's own calendar — the one the row's
 * "Completed" date is printed in, so the filter and the row always agree. */
const isoDay = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

/** "09 Nov 2026" for a yyyy-mm-dd day, read as local midnight rather than UTC. */
const dayLabel = (iso: string) => asDate(`${iso}T00:00:00`);

/** The first and last day a period covers (inclusive; "" leaves that end open),
 * or null when it doesn't narrow the list at all. Weeks run Monday to Sunday,
 * as they do on the Leads filters. */
function periodRange(period: Period, from: string, to: string, now = new Date()): { start: string; end: string } | null {
  const y = now.getFullYear(), m = now.getMonth(), d = now.getDate();
  switch (period) {
    case "today":
      return { start: isoDay(now), end: isoDay(now) };
    case "this_week": {
      const monday = d - ((now.getDay() + 6) % 7);
      return { start: isoDay(new Date(y, m, monday)), end: isoDay(new Date(y, m, monday + 6)) };
    }
    case "this_month":
      return { start: isoDay(new Date(y, m, 1)), end: isoDay(new Date(y, m + 1, 0)) };
    case "custom":
      if (!from && !to) return null;
      // Picked the wrong way round, a range still means what was meant.
      return from && to && from > to ? { start: to, end: from } : { start: from, end: to };
    default:
      return null;
  }
}

/** How a period reads after "completed": "this week", "since 01 Nov 2026". */
function periodPhrase(period: Period, range: { start: string; end: string }) {
  if (period === "today") return "today";
  if (period === "this_week") return "this week";
  if (period === "this_month") return "this month";
  if (range.start && range.end) {
    return range.start === range.end ? `on ${dayLabel(range.start)}`
      : `between ${dayLabel(range.start)} and ${dayLabel(range.end)}`;
  }
  return range.start ? `since ${dayLabel(range.start)}` : `up to ${dayLabel(range.end)}`;
}

export default function ProjectPage() {
  const domain = APP_SLUG;
  const router = useRouter();
  const [authChecked, setAuthChecked] = useState(false);
  const [allowed, setAllowed] = useState(false);
  const [leads, setLeads] = useState<ProjectLead[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  // The list opens on the work still to be done; finished jobs are one tap away.
  // The ones that blew their deadline are not here at all — they move to the
  // Overdue Projects module, where a super admin can release them.
  const [tab, setTab] = useState<"pending" | "completed">("pending");
  const [period, setPeriod] = useState<Period>("all");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");

  const token = () => localStorage.getItem(`${domain}_access`);

  useEffect(() => {
    const t = token();
    if (!t) { router.push("/login"); return; }
    fetch(`${getApiBase(domain)}/api/users/me/`, { headers: { Authorization: `Bearer ${t}` } })
      .then(r => r.json())
      .then(d => {
        const ok = isSpectator(d) || d.role === "project_manager" || d.is_staff || d.is_general_manager;
        setAllowed(ok);
        setAuthChecked(true);
        if (!ok) router.replace("/");
      })
      .catch(() => setAuthChecked(true));
  }, [domain, router]);

  useEffect(() => {
    if (!allowed) return;
    fetch(`${getApiBase(domain)}/api/leads/project/`, { headers: { Authorization: `Bearer ${token()}` } })
      .then(r => (r.ok ? r.json() : []))
      .then(d => setLeads(Array.isArray(d) ? d : []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [allowed, domain]);

  if (!authChecked) return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="w-8 h-8 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
    </div>
  );
  if (!allowed) return null;

  const matchesSearch = (l: ProjectLead) => {
    const q = search.trim().toLowerCase();
    if (!q) return true;
    return (`${l.first_name} ${l.last_name || ""}`.toLowerCase().includes(q)
      || (l.phone || "").toLowerCase().includes(q)
      || (l.location || "").toLowerCase().includes(q));
  };

  // The Completed tab's dates. A finished job with no date on it can't be
  // placed in a range, so it shows only under All time.
  const range = periodRange(period, from, to);
  const completedOn = (l: ProjectLead) => (l.project?.completed_at ? isoDay(new Date(l.project.completed_at)) : null);
  const inPeriod = (l: ProjectLead) => {
    if (!range) return true;
    const on = completedOn(l);
    return !!on && (!range.start || on >= range.start) && (!range.end || on <= range.end);
  };

  // Counts are of what each tab would show — the search, and on Completed the
  // dates too — so the tabs show where the matches went rather than a total
  // that disagrees with the list underneath.
  // An overdue project leaves this module entirely for Overdue Projects — that is
  // the point of the escalation.
  const found = leads.filter(matchesSearch);
  const inTab = (l: ProjectLead, key: typeof tab) =>
    key === "completed" ? (l.project_complete && inPeriod(l)) : (!l.project_complete && !l.project_overdue);
  const counts = {
    pending: found.filter(l => inTab(l, "pending")).length,
    completed: found.filter(l => inTab(l, "completed")).length,
  };
  const overdueCount = found.filter(l => !l.project_complete && l.project_overdue).length;
  const filtered = found.filter(l => inTab(l, tab));
  // Finished jobs read in the order they were finished, latest first, rather
  // than the order they arrived in. The pending queue keeps the server's order.
  const completedAt = (l: ProjectLead) => (l.project?.completed_at ? Date.parse(l.project.completed_at) : 0);
  if (tab === "completed") filtered.sort((a, b) => completedAt(b) - completedAt(a));

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-[1200px]">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Project</h1>
        <p className="text-sm text-slate-500 mt-1">Installation projects (purchase &amp; logistics complete). Open one to track structure/electrical work and geotagged site photos.</p>
      </div>

      <div className="mb-5 flex flex-wrap items-center gap-3">
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search by name, phone or location…"
          className="w-full max-w-md bg-white border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all"
        />
        <div className="inline-flex rounded-xl bg-slate-100 p-1">
          {([["pending", "Pending"], ["completed", "Completed"]] as const).map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => setTab(key)}
              className={`px-4 py-1.5 rounded-lg text-xs font-bold transition-colors ${
                tab === key ? "bg-white text-indigo-600 shadow-sm" : "text-slate-500 hover:text-slate-700"
              }`}
            >
              {label}
              <span className={`ml-1.5 ${tab === key ? "text-indigo-400" : "text-slate-400"}`}>{counts[key]}</span>
            </button>
          ))}
        </div>
      </div>

      {/* When the finished jobs were finished — the date printed on each row.
          The same control Closed Deals carries for its periods. */}
      {tab === "completed" && (
        <div className="mb-5 -mt-1 bg-white border border-slate-200 rounded-2xl p-3 flex flex-wrap items-center gap-2">
          <div className="flex flex-wrap gap-1">
            {PERIODS.map(p => (
              <button key={p.key} type="button" onClick={() => setPeriod(p.key)} aria-pressed={period === p.key}
                className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                  period === p.key ? "bg-indigo-600 text-white" : "text-slate-600 hover:bg-slate-100"}`}>
                {p.label}
              </button>
            ))}
          </div>
          {/* On a phone the two pickers share the row rather than running off the card. */}
          {period === "custom" && (
            <div className="flex w-full sm:w-auto items-center gap-2">
              <input type="date" value={from} max={to || undefined} aria-label="Completed from"
                onChange={e => setFrom(e.target.value)} className={`${DATE_INPUT} min-w-0 flex-1 sm:flex-none`} />
              <span className="text-xs text-slate-400">to</span>
              <input type="date" value={to} min={from || undefined} aria-label="Completed to"
                onChange={e => setTo(e.target.value)} className={`${DATE_INPUT} min-w-0 flex-1 sm:flex-none`} />
            </div>
          )}
          <span className="ml-auto text-[11px] text-slate-400">
            {range ? (
              <>
                <b className="text-slate-600">{counts.completed}</b> completed {periodPhrase(period, range)}
                {/* The presets say which days they mean; a custom range already has. */}
                {period !== "custom" && (
                  <> · {range.start === range.end ? dayLabel(range.start) : `${dayLabel(range.start)} – ${dayLabel(range.end)}`}</>
                )}
              </>
            ) : period === "custom" ? (
              "Pick a from date, a to date, or both"
            ) : (
              <><b className="text-slate-600">{counts.completed}</b> completed · latest first</>
            )}
          </span>
        </div>
      )}

      {/* Where the missing rows went, so the queue does not just look short. */}
      {overdueCount > 0 && (
        <Link href="/project-overdue"
          className="mb-5 -mt-1 flex items-center justify-between gap-3 bg-rose-50 border border-rose-200 rounded-2xl px-5 py-3 hover:bg-rose-100/70 transition-colors">
          <p className="text-xs text-rose-700">
            <b>{overdueCount} {overdueCount === 1 ? "project has" : "projects have"}</b> passed the{" "}
            {leads[0]?.deadline_days ?? 20}-day deadline and moved to Overdue Projects, where only a
            super admin can act.
          </p>
          <span className="text-[11px] font-bold text-rose-700 whitespace-nowrap">Open →</span>
        </Link>
      )}

      {loading ? (
        <div className="py-16 text-center text-sm text-slate-400">Loading…</div>
      ) : filtered.length === 0 ? (
        <div className="bg-white border border-dashed border-slate-200 rounded-2xl p-12 text-center text-sm text-slate-400">
          {leads.length === 0
            ? "No installation projects yet."
            : found.length === 0
              ? "No projects match your search."
              : tab === "completed"
                ? (range
                  ? `No projects${search.trim() ? " matching your search" : ""} completed ${periodPhrase(period, range)}.`
                  : "No completed projects yet.")
                : "No pending projects — everything here is done."}
        </div>
      ) : (
        <div className="space-y-4">
          {filtered.map(l => (
            <Link key={l.id} href={`/project/${l.id}`} className="block bg-white border border-slate-200 rounded-2xl shadow-sm px-5 py-4 hover:bg-slate-50/60 hover:border-indigo-200 transition-colors">
              <div className="flex items-center justify-between gap-4">
                <div className="min-w-0">
                  {/* Four things on one line is a desktop row; on a phone it
                      wraps rather than crushing the badges into letter towers. */}
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <p className="text-sm font-bold text-slate-900 truncate">{l.first_name} {l.last_name}</p>
                    <BdeTag name={l.bde_name} />
                    {l.lead_deleted && <DeletedLeadBadge />}
                    {/* Nothing overdue reaches this list — it has moved to the
                        Overdue Projects module by then. */}
                    <span className={`text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full whitespace-nowrap flex-shrink-0 ${
                      l.project_complete ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>
                      {l.project_complete ? "Done" : "In Progress"}
                    </span>
                    {/* The deadline only matters while the work is still running. */}
                    {!l.project_complete && (
                      <span className={`text-[10px] font-semibold whitespace-nowrap flex-shrink-0 ${(l.days_to_deadline ?? 99) <= 3 ? "text-amber-600" : "text-slate-400"}`}>
                        {deadlineNote(l)}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-slate-500 mt-0.5 truncate">{l.phone || "—"} · {l.location || "No location"}{l.product_name ? ` · ${l.product_name}` : ""}</p>
                  {!l.project_complete && l.deadline_date && (
                    <p className="text-[11px] text-slate-400 mt-0.5">
                      Deadline {asDate(l.deadline_date)}
                      {l.extended_deadline ? " (extended)" : l.payment_started_on ? ` · paid ${asDate(l.payment_started_on)}` : ""}
                    </p>
                  )}
                  {/* What the completed list is ordered by, so the order reads. */}
                  {l.project_complete && l.project?.completed_at && (
                    <p className="text-[11px] text-slate-400 mt-0.5">Completed {asDate(l.project.completed_at)}</p>
                  )}
                </div>
                <div className="flex items-center gap-4 flex-shrink-0">
                  <div className="hidden sm:block text-right">
                    <p className="text-[10px] text-slate-400 uppercase tracking-wide">Deal Value</p>
                    <p className="text-xs font-semibold text-slate-700">{l.value ? `₹${formatCurrency(l.value)}` : "—"}</p>
                  </div>
                  <div className="hidden md:block text-right">
                    <p className="text-[10px] text-slate-400 uppercase tracking-wide">Project Manager</p>
                    <p className="text-xs font-semibold text-slate-600">{l.project_manager_name || "Unassigned"}</p>
                  </div>
                  {l.can_cleanup && (
                    <DeletedLeadCleanup leadId={l.id} module="project"
                      name={`${l.first_name} ${l.last_name || ""}`.trim()}
                      onRemoved={() => setLeads(prev => prev.filter(x => x.id !== l.id))} />
                  )}
                  <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" className="text-slate-300"><polyline points="9 18 15 12 9 6" /></svg>
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

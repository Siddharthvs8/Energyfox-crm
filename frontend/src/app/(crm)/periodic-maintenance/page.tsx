"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

type ScheduledRow = {
  id: number; first_name: string; last_name: string | null; phone: string | null; location: string | null;
  start_date: string; done_count: number; total_visits: number;
  next_due: string | null; next_sequence: number | null;
};
type EligibleRow = { id: number; first_name: string; last_name: string | null; phone: string | null; location: string | null };

/** Every visit still to be done, across all customers, soonest first. */
type UpcomingRow = {
  lead_id: number; visit_id: number;
  first_name: string; last_name: string | null; phone: string | null; location: string | null;
  sequence: number; due_date: string; days_to_due: number;
  is_overdue: boolean; is_due: boolean;
  is_rescheduled: boolean; original_due_date: string | null; reschedule_reason: string;
};

const today = () => new Date().toISOString().slice(0, 10);

/** How far off a visit is, in words. */
function dueNote(r: UpcomingRow) {
  const d = r.days_to_due;
  if (d < 0) return `${Math.abs(d)} day${Math.abs(d) === 1 ? "" : "s"} overdue`;
  if (d === 0) return "Due today";
  if (d === 1) return "Due tomorrow";
  return `in ${d} days`;
}

export default function PeriodicMaintenancePage() {
  const domain = APP_SLUG;
  const router = useRouter();
  const [authChecked, setAuthChecked] = useState(false);
  const [allowed, setAllowed] = useState(false);
  const [scheduled, setScheduled] = useState<ScheduledRow[]>([]);
  const [eligible, setEligible] = useState<EligibleRow[]>([]);
  const [upcoming, setUpcoming] = useState<UpcomingRow[]>([]);
  // The list runs five years ahead, so it opens on the near ones.
  const [showAllUpcoming, setShowAllUpcoming] = useState(false);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [startDates, setStartDates] = useState<Record<number, string>>({});
  const [schedulingId, setSchedulingId] = useState<number | null>(null);

  const token = () => localStorage.getItem(`${domain}_access`);

  useEffect(() => {
    const t = token();
    if (!t) { router.push("/login"); return; }
    fetch(`${getApiBase(domain)}/api/users/me/`, { headers: { Authorization: `Bearer ${t}` } })
      .then(r => r.json())
      .then(d => {
        const ok = d.role === "liasoning_officer" || d.is_staff || d.is_general_manager;
        setAllowed(ok); setAuthChecked(true);
        if (!ok) router.replace("/");
      })
      .catch(() => setAuthChecked(true));
  }, [domain, router]);

  const load = () => {
    fetch(`${getApiBase(domain)}/api/leads/periodic-maintenance/`, { headers: { Authorization: `Bearer ${token()}` } })
      .then(r => (r.ok ? r.json() : { scheduled: [], eligible: [], upcoming: [] }))
      .then(d => {
        setScheduled(d.scheduled || []);
        setEligible(d.eligible || []);
        setUpcoming(d.upcoming || []);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { if (allowed) load(); }, [allowed]); // eslint-disable-line react-hooks/exhaustive-deps

  const schedule = async (id: number) => {
    setSchedulingId(id);
    try {
      const r = await fetch(`${getApiBase(domain)}/api/leads/${id}/schedule-maintenance/`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token()}` },
        body: JSON.stringify({ start_date: startDates[id] || today() }),
      });
      if (r.ok) load();
      else { const e = await r.json().catch(() => ({})); alert(e.error || "Could not schedule."); }
    } catch { alert("Network error."); }
    finally { setSchedulingId(null); }
  };

  if (!authChecked) return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="w-8 h-8 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
    </div>
  );
  if (!allowed) return null;

  const q = search.trim().toLowerCase();
  const match = (r: { first_name: string; last_name: string | null; phone: string | null; location: string | null }) =>
    !q || `${r.first_name} ${r.last_name || ""}`.toLowerCase().includes(q)
    || (r.phone || "").toLowerCase().includes(q) || (r.location || "").toLowerCase().includes(q);
  const fScheduled = scheduled.filter(match);
  const fEligible = eligible.filter(match);
  const fUpcoming = upcoming.filter(match);
  // The ones already calling for attention — the same day-before line the sidebar
  // badge and the pop-up use.
  const dueNow = fUpcoming.filter(r => r.is_due).length;
  const UPCOMING_PREVIEW = 12;
  const shownUpcoming = showAllUpcoming ? fUpcoming : fUpcoming.slice(0, UPCOMING_PREVIEW);
  const isOverdue = (d: string | null) => !!d && new Date(d) < new Date(today());

  return (
    <div className="p-6 lg:p-8 max-w-[1200px]">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Periodic Maintenance</h1>
        <p className="text-sm text-slate-500 mt-1">Subsidy-redeemed / completed customers are scheduled for 5 years of maintenance with a tenure gap of 6 months.</p>
      </div>

      <div className="mb-5 flex items-center gap-3">
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search by name, phone or location…"
          className="w-full max-w-md bg-white border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all"
        />
      </div>

      {loading ? (
        <div className="py-16 text-center text-sm text-slate-400">Loading…</div>
      ) : (
        <>
          {/* Upcoming maintenance — every visit still to be done, soonest first.
              This is the working view: the officer reads down it in order. */}
          <div className="flex flex-wrap items-baseline gap-2 mb-3">
            <h2 className="text-sm font-bold text-slate-900">
              Upcoming Maintenance <span className="text-slate-400 font-medium">({fUpcoming.length})</span>
            </h2>
            {dueNow > 0 && (
              <span className="text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full bg-rose-50 text-rose-700">
                {dueNow} needing attention
              </span>
            )}
          </div>
          {fUpcoming.length === 0 ? (
            <div className="mb-8 bg-white border border-dashed border-slate-200 rounded-2xl p-10 text-center text-sm text-slate-400">
              {scheduled.length === 0
                ? "Nothing scheduled yet — schedule a customer below."
                : "Every scheduled visit is done."}
            </div>
          ) : (
            <div className="mb-8 bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-[10px] font-bold text-slate-400 uppercase tracking-wide border-b border-slate-100 bg-slate-50/60">
                    <th className="px-5 py-3">Customer</th>
                    <th className="px-5 py-3">Visit</th>
                    <th className="px-5 py-3">Due</th>
                    <th className="px-5 py-3">When</th>
                    <th className="px-5 py-3 text-right"></th>
                  </tr>
                </thead>
                <tbody>
                  {shownUpcoming.map(r => (
                    <tr key={r.visit_id}
                      className={`border-b border-slate-50 hover:bg-slate-50/60 ${r.is_overdue ? "bg-rose-50/40" : r.is_due ? "bg-amber-50/40" : ""}`}>
                      <td className="px-5 py-3">
                        <p className="font-semibold text-slate-800">{r.first_name} {r.last_name}</p>
                        <p className="text-[11px] text-slate-400">{r.phone || "—"}{r.location ? ` · ${r.location}` : ""}</p>
                      </td>
                      <td className="px-5 py-3 text-slate-600 whitespace-nowrap">#{r.sequence}</td>
                      <td className="px-5 py-3 whitespace-nowrap">
                        <span className="text-slate-700 font-medium">{new Date(r.due_date).toLocaleDateString("en-IN")}</span>
                        {/* A moved visit shows where it came from, rather than the
                            schedule quietly rewriting itself. */}
                        {r.is_rescheduled && r.original_due_date && (
                          <span className="block text-[11px] text-slate-400"
                            title={r.reschedule_reason || undefined}>
                            moved from {new Date(r.original_due_date).toLocaleDateString("en-IN")}
                          </span>
                        )}
                      </td>
                      <td className="px-5 py-3 whitespace-nowrap">
                        <span className={`text-xs font-bold ${r.is_overdue ? "text-rose-600" : r.is_due ? "text-amber-600" : "text-slate-500"}`}>
                          {dueNote(r)}
                        </span>
                      </td>
                      <td className="px-5 py-3 text-right">
                        <Link href={`/periodic-maintenance/${r.lead_id}`} className="text-[12px] font-semibold text-indigo-600 hover:text-indigo-800">Open →</Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {fUpcoming.length > UPCOMING_PREVIEW && (
                <button onClick={() => setShowAllUpcoming(v => !v)}
                  className="w-full py-3 text-[12px] font-semibold text-indigo-600 hover:bg-slate-50 transition border-t border-slate-100">
                  {showAllUpcoming
                    ? "Show fewer"
                    : `Show all ${fUpcoming.length} — the schedule runs five years out`}
                </button>
              )}
            </div>
          )}

          {/* Scheduled customer list */}
          <h2 className="text-sm font-bold text-slate-900 mb-3">Scheduled Customer List <span className="text-slate-400 font-medium">({fScheduled.length})</span></h2>
          {fScheduled.length === 0 ? (
            <div className="mb-8 bg-white border border-dashed border-slate-200 rounded-2xl p-10 text-center text-sm text-slate-400">
              No customers scheduled yet — schedule one from the list below.
            </div>
          ) : (
            <div className="mb-8 bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm min-w-[760px]">
                  <thead>
                    <tr className="text-left text-[10px] font-bold text-slate-400 uppercase tracking-wide border-b border-slate-100 bg-slate-50/60">
                      <th className="px-5 py-3">Customer</th>
                      <th className="px-5 py-3">Start Date</th>
                      <th className="px-5 py-3">Progress</th>
                      <th className="px-5 py-3">Next Visit Due</th>
                      <th className="px-5 py-3 text-right"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {fScheduled.map(r => (
                      <tr key={r.id} className="border-b border-slate-50 hover:bg-slate-50/60">
                        <td className="px-5 py-3">
                          <p className="font-semibold text-slate-800">{r.first_name} {r.last_name}</p>
                          <p className="text-[11px] text-slate-400">{r.phone || "—"}{r.location ? ` · ${r.location}` : ""}</p>
                        </td>
                        <td className="px-5 py-3 text-slate-600">{new Date(r.start_date).toLocaleDateString("en-IN")}</td>
                        <td className="px-5 py-3">
                          <span className={`text-xs font-bold ${r.done_count === r.total_visits ? "text-emerald-600" : "text-slate-600"}`}>
                            {r.done_count}/{r.total_visits} visits
                          </span>
                        </td>
                        <td className="px-5 py-3">
                          {r.next_due ? (
                            <span className={`text-xs font-semibold ${isOverdue(r.next_due) ? "text-rose-600" : "text-slate-600"}`}>
                              #{r.next_sequence} · {new Date(r.next_due).toLocaleDateString("en-IN")}{isOverdue(r.next_due) ? " · overdue" : ""}
                            </span>
                          ) : (
                            <span className="text-xs font-semibold text-emerald-600">All visits done</span>
                          )}
                        </td>
                        <td className="px-5 py-3 text-right">
                          <Link href={`/periodic-maintenance/${r.id}`} className="text-[12px] font-semibold text-indigo-600 hover:text-indigo-800">Open →</Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Eligible (not yet scheduled) */}
          <h2 className="text-sm font-bold text-slate-900 mb-3">Schedule a Customer <span className="text-slate-400 font-medium">({fEligible.length})</span></h2>
          {fEligible.length === 0 ? (
            <div className="bg-white border border-dashed border-slate-200 rounded-2xl p-10 text-center text-sm text-slate-400">
              Every installed customer is already scheduled.
            </div>
          ) : (
            <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
              <table className="w-full text-sm">
                <tbody>
                  {fEligible.map(r => (
                    <tr key={r.id} className="border-b border-slate-50 hover:bg-slate-50/60">
                      <td className="px-5 py-3">
                        <p className="font-semibold text-slate-800">{r.first_name} {r.last_name}</p>
                        <p className="text-[11px] text-slate-400">{r.phone || "—"}{r.location ? ` · ${r.location}` : ""}</p>
                      </td>
                      <td className="px-5 py-3">
                        <input type="date" value={startDates[r.id] || today()}
                          onChange={e => setStartDates(p => ({ ...p, [r.id]: e.target.value }))}
                          className="bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all" />
                      </td>
                      <td className="px-5 py-3 text-right">
                        <button onClick={() => schedule(r.id)} disabled={schedulingId === r.id}
                          title="10 visits, one every 6 months, from the start date"
                          className="px-4 py-2 bg-indigo-600 text-white rounded-xl text-xs font-semibold hover:bg-indigo-700 disabled:opacity-50 transition">
                          {schedulingId === r.id ? "Scheduling…" : "Schedule (5 yrs / 6 mo)"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}

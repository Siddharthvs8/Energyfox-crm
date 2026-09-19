"use client";
import { getApiBase } from "@/lib/mock-data";

import React, { useState } from "react";

/**
 * The 20-day installation deadline, shared by the project list and the project
 * detail page so both read the same rules from the same payload.
 *
 * The clock starts the day accounts first records money against the lead —
 * partial payment or full. Miss it and the project leaves the pending queue for
 * Overdue, where only a super admin can act: they release it back with a fresh
 * deadline, and the project team picks the work up again.
 */
export type DeadlineInfo = {
  payment_started_on: string | null;
  deadline_date: string | null;
  days_to_deadline: number | null;
  project_overdue: boolean;
  deadline_days: number;
  extended_deadline: string | null;
  released_at: string | null;
  released_by_name: string | null;
  release_reason: string;
  can_release_project: boolean;
  project_complete: boolean;
};

export const asDate = (d: string) =>
  new Date(d).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });

/** How the deadline reads on a project that is still running. */
export function deadlineNote(info: DeadlineInfo) {
  if (!info.deadline_date) return "Awaiting first payment";
  const left = info.days_to_deadline;
  if (left === null) return `Due ${asDate(info.deadline_date)}`;
  if (left < 0) return `${Math.abs(left)} day${Math.abs(left) === 1 ? "" : "s"} overdue`;
  if (left === 0) return "Due today";
  return `${left} day${left === 1 ? "" : "s"} left`;
}

const tomorrowISO = () => new Date(Date.now() + 86400000).toISOString().slice(0, 10);

/**
 * Super admin releases an overdue project back to the project team, granting a
 * fresh deadline — the default is another full run of the standard days.
 */
export function ReleaseDialog({ leadId, name, info, domain, onClose, onReleased }: {
  leadId: number; name: string; info: DeadlineInfo; domain: string;
  onClose: () => void;
  onReleased: (row: any) => void;
}) {
  const defaultDeadline = React.useMemo(() => {
    const d = new Date();
    d.setDate(d.getDate() + (info.deadline_days || 20));
    return d.toISOString().slice(0, 10);
  }, [info.deadline_days]);
  const [deadline, setDeadline] = useState(defaultDeadline);
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const tomorrow = tomorrowISO();

  const submit = async () => {
    setSaving(true); setError("");
    try {
      const r = await fetch(`${getApiBase(domain)}/api/leads/${leadId}/release-project/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem(`${domain}_access`)}`,
        },
        body: JSON.stringify({ deadline, reason }),
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) { setError(d.error || "Could not release this project."); return; }
      onReleased(d);
    } catch { setError("Network error."); }
    finally { setSaving(false); }
  };

  const inputCls = "w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="bg-white w-full max-w-md rounded-2xl shadow-2xl max-h-[calc(100dvh-2rem)] overflow-y-auto overscroll-contain" onClick={e => e.stopPropagation()}>
        <div className="px-6 py-4 border-b border-slate-100">
          <h2 className="text-base font-bold text-slate-900">Release to the project team</h2>
          <p className="text-xs text-slate-400 mt-0.5">
            {name}{info.deadline_date ? ` · missed ${asDate(info.deadline_date)}` : ""}
          </p>
        </div>
        <div className="px-6 py-5 space-y-4">
          <div>
            <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wide mb-1.5">New deadline</label>
            <input type="date" value={deadline} min={tomorrow} onChange={e => setDeadline(e.target.value)} className={inputCls} />
            <p className="text-[11px] text-slate-400 mt-1.5">
              Until this date the project team can edit it again. Miss it and the project comes back to Overdue.
            </p>
          </div>
          <div>
            <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wide mb-1.5">Reason (optional)</label>
            <input value={reason} onChange={e => setReason(e.target.value)} maxLength={255}
              placeholder="Why the deadline slipped" className={inputCls} />
          </div>
          {error && <p className="text-xs font-semibold text-rose-600">{error}</p>}
        </div>
        <div className="flex gap-3 px-6 pb-5">
          <button onClick={onClose}
            className="flex-1 px-4 py-2.5 text-slate-600 font-medium hover:bg-slate-50 rounded-xl transition-colors">
            Cancel
          </button>
          <button onClick={submit} disabled={saving || !deadline || deadline < tomorrow}
            className="flex-1 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-2.5 rounded-xl transition shadow-sm disabled:opacity-50 disabled:cursor-not-allowed">
            {saving ? "Releasing…" : "Release"}
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * The deadline as it appears on the project detail page: where the clock started,
 * what it is due, and — when the deadline has gone — that the record is locked
 * and who can lift it.
 */
export function DeadlineBanner({ leadId, name, info, domain, onReleased }: {
  leadId: number; name: string; info: DeadlineInfo; domain: string;
  onReleased: () => void;
}) {
  const [open, setOpen] = useState(false);

  // Finished work has no deadline left to keep, and a project with no payment
  // yet has no clock to show.
  if (info.project_complete || !info.deadline_date) return null;

  const overdue = info.project_overdue;
  const soon = !overdue && (info.days_to_deadline ?? 99) <= 3;
  const tone = overdue
    ? "bg-rose-50 border-rose-200"
    : soon ? "bg-amber-50 border-amber-200" : "bg-white border-slate-200";

  return (
    <>
      <div className={`mt-5 border rounded-2xl shadow-sm p-5 ${tone}`}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className={`text-sm font-bold ${overdue ? "text-rose-800" : "text-slate-900"}`}>
              {overdue ? "Overdue — locked" : "Installation deadline"}
            </h2>
            <p className={`text-xs mt-1 ${overdue ? "text-rose-700" : "text-slate-500"}`}>
              Due {asDate(info.deadline_date)} · {deadlineNote(info)}
              {info.payment_started_on
                ? ` · ${info.deadline_days} days from the first payment on ${asDate(info.payment_started_on)}`
                : ""}
            </p>
            {info.extended_deadline && info.released_at && (
              <p className="text-[11px] text-slate-500 mt-1">
                Released by {info.released_by_name || "a super admin"} on {asDate(info.released_at)}
                {info.release_reason ? ` — ${info.release_reason}` : ""}
              </p>
            )}
            {overdue && (
              <p className="text-[11px] text-rose-700 mt-2 max-w-xl">
                The project team can no longer edit this. A super admin has to release it with a
                fresh deadline before the work can continue.
              </p>
            )}
          </div>
          {overdue && info.can_release_project && (
            <button type="button" onClick={() => setOpen(true)}
              className="px-4 py-2 rounded-xl bg-rose-600 text-white text-xs font-bold hover:bg-rose-700 transition whitespace-nowrap">
              Release to project team
            </button>
          )}
        </div>
      </div>

      {open && (
        <ReleaseDialog
          leadId={leadId} name={name} info={info} domain={domain}
          onClose={() => setOpen(false)}
          onReleased={() => { setOpen(false); onReleased(); }}
        />
      )}
    </>
  );
}

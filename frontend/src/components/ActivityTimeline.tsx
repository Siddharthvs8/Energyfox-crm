"use client";
/**
 * Activity Timeline — the whole of a customer's history, in a modal.
 *
 * The downstream modules (documentation, accounts, purchase, project,
 * liasoning) each own one slice of a customer's journey. Whoever picks the file
 * up needs to see how it got to them, so every one of those screens carries this
 * button. Access is enforced server-side: a user who cannot open the lead cannot
 * read its history.
 */
import React, { useState } from "react";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";

type Entry = {
  id: number;
  type: string;
  description: string;
  actor: string | null;
  auto_generated: boolean;
  timestamp: string;
};

type Data = {
  lead: { id: number; name: string; phone: string; status: string; created_at: string | null };
  count: number;
  entries: Entry[];
};

/** A readable label per activity type, falling back to the raw key. */
const TYPE_LABELS: Record<string, string> = {
  lead_created: "Lead created",
  lead_status_change: "Status changed",
  note_added: "Note added",
  task_created: "Task created",
  task_stage_change: "Task stage changed",
  task_completed: "Task completed",
  meta_import: "Imported from Meta",
  call_logged: "Call logged",
  user_joined: "User joined",
};

/** Dot colour by kind, so a status change reads differently from a note. */
const TYPE_TONE: Record<string, string> = {
  lead_created: "bg-indigo-500",
  lead_status_change: "bg-emerald-500",
  note_added: "bg-amber-500",
  task_completed: "bg-emerald-500",
  call_logged: "bg-sky-500",
};

const fmt = (iso: string) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleString("en-IN", {
        day: "2-digit", month: "short", year: "numeric",
        hour: "2-digit", minute: "2-digit",
      });
};

export default function ActivityTimeline({ leadId, className }: {
  leadId: number | string;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<Data | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const load = async () => {
    setOpen(true);
    setLoading(true);
    setError("");
    try {
      const token = localStorage.getItem(`${APP_SLUG}_access`);
      const r = await fetch(`${getApiBase(APP_SLUG)}/api/leads/${leadId}/activity-timeline/`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!r.ok) {
        setError(r.status === 403 || r.status === 404
          ? "You don't have access to this customer's history."
          : "Could not load the activity timeline.");
        return;
      }
      setData(await r.json());
    } catch {
      setError("Network error while loading the timeline.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <button onClick={load} title="Everything that has happened to this customer"
        className={className ||
          "inline-flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-300 text-slate-700 rounded-lg text-xs font-semibold hover:bg-slate-50 transition"}>
        <svg width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
          <circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" />
        </svg>
        Activity Timeline
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
          onClick={() => setOpen(false)}>
          <div className="bg-white w-full max-w-2xl rounded-2xl shadow-2xl max-h-[85vh] overflow-hidden flex flex-col"
            onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 flex-shrink-0">
              <div>
                <h2 className="text-base font-bold text-slate-900">Activity Timeline</h2>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  {data?.lead?.name
                    ? `${data.lead.name}${data.lead.phone ? ` · ${data.lead.phone}` : ""}`
                    : "Everything recorded against this customer."}
                </p>
              </div>
              <button onClick={() => setOpen(false)}
                className="w-8 h-8 flex items-center justify-center rounded-xl bg-slate-100 text-slate-500 hover:bg-slate-200 transition text-sm">
                ✕
              </button>
            </div>

            <div className="overflow-y-auto flex-1 px-6 py-5">
              {loading ? (
                <div className="py-14 text-center text-sm text-slate-400">Loading…</div>
              ) : error ? (
                <div className="py-14 text-center text-sm text-rose-500">{error}</div>
              ) : !data?.entries?.length ? (
                <div className="py-14 text-center text-sm text-slate-400">
                  Nothing has been recorded against this customer yet.
                </div>
              ) : (
                <ol className="relative border-l border-slate-200 ml-2 space-y-5">
                  {data.entries.map(e => (
                    <li key={e.id} className="ml-5">
                      <span className={`absolute -left-[5px] w-2.5 h-2.5 rounded-full ring-4 ring-white ${
                        TYPE_TONE[e.type] || "bg-slate-300"}`} />
                      <div className="flex flex-wrap items-baseline gap-x-2">
                        <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                          {TYPE_LABELS[e.type] || e.type.replace(/_/g, " ")}
                        </span>
                        <span className="text-[11px] text-slate-400">{fmt(e.timestamp)}</span>
                      </div>
                      <p className="text-sm text-slate-700 mt-0.5 whitespace-pre-wrap break-words">
                        {e.description}
                      </p>
                      <p className="text-[11px] text-slate-400 mt-0.5">
                        {e.auto_generated ? "Auto generated" : e.actor || "—"}
                      </p>
                    </li>
                  ))}
                </ol>
              )}
            </div>

            {!loading && !error && !!data?.count && (
              <div className="px-6 py-3 border-t border-slate-100 text-[11px] text-slate-400 flex-shrink-0">
                {data.count} {data.count === 1 ? "entry" : "entries"}
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}

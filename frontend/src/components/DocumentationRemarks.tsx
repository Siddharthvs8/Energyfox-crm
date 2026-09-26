"use client";
/**
 * Remarks on a customer's documentation — usually why it is held up.
 *
 * A customer can sit in a documentation stage for days waiting on something
 * the desk does not control: an Aadhaar the customer has not sent, a bank that
 * has not answered, a portal that is down. The stage's own fields cannot say
 * that, so the reason lived in someone's head. A remark writes it down with
 * who noted it and when; the lists show the latest one, so a manager can see
 * why a customer is stuck without opening it.
 *
 * Stage 1 and Stage 2 keep separate logs. The server decides who may add
 * (`can_add`) and who may change each remark (`can_edit` — your own, or an
 * admin's override, the same rule as lead notes).
 */
import React, { useCallback, useEffect, useState } from "react";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";

export type RemarkStage = "stage1" | "stage2";

type Remark = {
  id: number;
  body: string;
  author_name: string | null;
  created_at: string;
  edited_at: string | null;
  can_edit: boolean;
};

/** The latest remark as the documentation lists carry it. */
export type RemarkSummaryData = { body: string; author_name: string | null; created_at: string } | null;

const MAX_LENGTH = 2000;
/** Remarks shown before "Show all". */
const SHOWN = 3;
/** Days in a stage after which a customer with no remark is flagged. */
export const STALE_DAYS = 3;

const DAY = 86_400_000;

/** "just now", "5 min ago", "3 h ago", "2 days ago" — then the date. */
export function timeAgo(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 60_000) return "just now";
  if (ms < 3_600_000) return `${Math.floor(ms / 60_000)} min ago`;
  if (ms < DAY) return `${Math.floor(ms / 3_600_000)} h ago`;
  const days = Math.floor(ms / DAY);
  if (days < 30) return `${days} day${days === 1 ? "" : "s"} ago`;
  return new Date(iso).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}

const fullDate = (iso: string) => new Date(iso).toLocaleString("en-IN",
  { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });

export default function DocumentationRemarks({ leadId, stage }: { leadId: number | string; stage: RemarkStage }) {
  const [remarks, setRemarks] = useState<Remark[]>([]);
  const [canAdd, setCanAdd] = useState(false);
  const [loading, setLoading] = useState(true);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState<number | null>(null);
  const [editDraft, setEditDraft] = useState("");
  const [showAll, setShowAll] = useState(false);

  const base = `${getApiBase(APP_SLUG)}/api/leads/${leadId}/documentation-remarks/`;
  const headers = () => ({
    "Content-Type": "application/json",
    Authorization: `Bearer ${localStorage.getItem(`${APP_SLUG}_access`)}`,
  });

  const load = useCallback(async () => {
    try {
      const r = await fetch(`${base}?stage=${stage}`, { headers: headers() });
      if (r.ok) {
        const d = await r.json();
        setRemarks(d.remarks || []);
        setCanAdd(!!d.can_add);
      }
    } catch { /* the card shows its empty state */ }
    finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [base, stage]);

  useEffect(() => { load(); }, [load]);

  const add = async () => {
    const body = draft.trim();
    if (!body) return;
    setSaving(true);
    try {
      const r = await fetch(base, { method: "POST", headers: headers(), body: JSON.stringify({ stage, body }) });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) { alert(d.error || "Could not add the remark."); return; }
      setRemarks(prev => [d, ...prev]);
      setDraft("");
    } catch { alert("Network error while adding the remark."); }
    finally { setSaving(false); }
  };

  const save = async (id: number) => {
    const body = editDraft.trim();
    if (!body) return;
    setSaving(true);
    try {
      const r = await fetch(`${base}${id}/`, { method: "PATCH", headers: headers(), body: JSON.stringify({ body }) });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) { alert(d.error || "Could not save the remark."); return; }
      setRemarks(prev => prev.map(x => (x.id === id ? d : x)));
      setEditing(null);
    } catch { alert("Network error while saving the remark."); }
    finally { setSaving(false); }
  };

  const remove = async (id: number) => {
    if (!window.confirm("Delete this remark?")) return;
    try {
      const r = await fetch(`${base}${id}/`, { method: "DELETE", headers: headers() });
      if (!r.ok) { const d = await r.json().catch(() => ({})); alert(d.error || "Could not delete the remark."); return; }
      setRemarks(prev => prev.filter(x => x.id !== id));
    } catch { alert("Network error while deleting the remark."); }
  };

  const visible = showAll ? remarks : remarks.slice(0, SHOWN);

  return (
    <div className="mt-5 bg-white border border-slate-200 rounded-2xl shadow-sm p-5">
      <div className="flex items-baseline justify-between gap-3 mb-1">
        <h2 className="text-sm font-bold text-slate-900">Remarks</h2>
        {remarks.length > 0 && (
          <span className="text-[11px] text-slate-400">{remarks.length} remark{remarks.length === 1 ? "" : "s"}</span>
        )}
      </div>
      <p className="text-xs text-slate-500 mb-4">
        Note why this customer is held up. The latest remark shows on the {stage === "stage1" ? "Stage 1" : "Stage 2"} list.
      </p>

      {canAdd && (
        <div className="mb-4">
          <textarea
            className="form-input"
            rows={2}
            maxLength={MAX_LENGTH}
            value={draft}
            onChange={e => setDraft(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); add(); } }}
            placeholder="e.g. Waiting for the customer's Aadhaar — they are travelling until the 30th"
          />
          <div className="mt-2 flex items-center justify-between gap-3">
            <span className="text-[11px] text-slate-400">Ctrl + Enter to add</span>
            <button className="btn btn-primary btn-sm" onClick={add} disabled={saving || !draft.trim()}>
              {saving && editing === null ? "Adding…" : "Add remark"}
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <p className="text-sm text-slate-400">Loading…</p>
      ) : remarks.length === 0 ? (
        <p className="text-sm text-slate-400">No remarks yet.</p>
      ) : (
        <div className="space-y-2.5">
          {visible.map((r, i) => (
            <div key={r.id}
              className={`rounded-xl border px-3.5 py-2.5 ${i === 0 ? "border-amber-200 bg-amber-50/50" : "border-slate-100 bg-slate-50/60"}`}>
              {editing === r.id ? (
                <>
                  <textarea className="form-input" rows={2} maxLength={MAX_LENGTH} value={editDraft} autoFocus
                    onChange={e => setEditDraft(e.target.value)} />
                  <div className="mt-2 flex items-center gap-2">
                    <button className="btn btn-primary btn-sm" onClick={() => save(r.id)}
                      disabled={saving || !editDraft.trim() || editDraft.trim() === r.body}>
                      {saving ? "Saving…" : "Save"}
                    </button>
                    <button className="btn btn-secondary btn-sm" onClick={() => setEditing(null)} disabled={saving}>
                      Cancel
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <p className="text-sm text-slate-700 leading-relaxed whitespace-pre-wrap break-words">{r.body}</p>
                  <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px] text-slate-400">
                    {i === 0 && (
                      <span className="font-bold uppercase tracking-wide text-amber-700">Latest</span>
                    )}
                    <span className="font-semibold text-slate-500">{r.author_name || "Unknown"}</span>
                    <span>·</span>
                    <span title={fullDate(r.created_at)}>{timeAgo(r.created_at)}</span>
                    {r.edited_at && <span className="italic" title={`Edited ${fullDate(r.edited_at)}`}>· edited</span>}
                    {r.can_edit && (
                      <span className="ml-auto flex items-center gap-2">
                        <button onClick={() => { setEditDraft(r.body); setEditing(r.id); }}
                          className="font-semibold text-indigo-600 hover:text-indigo-800">Edit</button>
                        <button onClick={() => remove(r.id)}
                          className="font-semibold text-rose-500 hover:text-rose-700">Delete</button>
                      </span>
                    )}
                  </div>
                </>
              )}
            </div>
          ))}
          {remarks.length > SHOWN && (
            <button onClick={() => setShowAll(v => !v)}
              className="text-xs font-semibold text-indigo-600 hover:text-indigo-800">
              {showAll ? "Show fewer" : `Show all ${remarks.length} remarks`}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * The remark line on a documentation list row: how long the customer has
 * been waiting, and the latest reason given. A customer waiting longer than
 * STALE_DAYS with nothing noted is called out, since that is the case the
 * remark exists for.
 */
export function RemarkSummary({ remark, since, pending }: {
  remark?: RemarkSummaryData;
  /** When the customer reached this stage. */
  since?: string | null;
  /** Still in progress — how long it has waited only matters then. */
  pending: boolean;
}) {
  const days = pending && since ? Math.max(0, Math.floor((Date.now() - new Date(since).getTime()) / DAY)) : null;
  const stale = days !== null && days >= STALE_DAYS;
  if (!remark && !stale) return null;

  return (
    <div className="mt-1.5 flex items-center gap-2 min-w-0 text-xs">
      {days !== null && (
        <span title={since ? `In this stage since ${fullDate(since)}` : undefined}
          className={`flex-shrink-0 text-[10px] font-bold px-1.5 py-0.5 rounded-full ${
            stale ? "bg-amber-50 text-amber-700" : "bg-slate-100 text-slate-500"}`}>
          {days === 0 ? "Today" : `${days} day${days === 1 ? "" : "s"}`}
        </span>
      )}
      {remark ? (
        <span className="min-w-0 truncate text-slate-600" title={remark.body}>
          <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"
            className="inline -mt-0.5 mr-1 text-slate-400" aria-hidden="true">
            <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
          </svg>
          {remark.body}
          <span className="text-slate-400"> — {remark.author_name || "Unknown"}, {timeAgo(remark.created_at)}</span>
        </span>
      ) : (
        <span className="text-amber-700">No remark yet</span>
      )}
    </div>
  );
}

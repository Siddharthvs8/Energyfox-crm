"use client";
/**
 * Duplicate Leads — the same customer, filed twice.
 *
 * Groups are built on the server from a shared phone or email, with phone
 * matched on its last ten digits so +919380077570 and 9380077570 are one
 * number. Pick the lead to keep, merge, and the rest go to Trash with their
 * history moved across.
 */
import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";

type Lead = {
  id: number; name: string; phone: string; email: string; status: string;
  source: string; district: string; created_at: string | null;
  owner: string | null; blockers: string[];
};
type Group = {
  match: "phone" | "email"; key: string; count: number;
  suggested_keep: number; leads: Lead[];
};

const shortDate = (iso: string | null) =>
  iso ? new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "numeric", year: "numeric" }) : "";

function PhoneIcon() {
  return (
    <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
      <path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6A19.79 19.79 0 012.12 4.2 2 2 0 014.11 2h3a2 2 0 012 1.72c.13.96.36 1.9.7 2.81a2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45c.9.34 1.85.57 2.81.7A2 2 0 0122 16.92z" />
    </svg>
  );
}

function MailIcon() {
  return (
    <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
      <rect x="2" y="4" width="20" height="16" rx="2" />
      <path d="m22 7-10 6L2 7" />
    </svg>
  );
}

export default function DuplicateLeadsPage() {
  const api = getApiBase(APP_SLUG);
  const [groups, setGroups] = useState<Group[]>([]);
  const [keep, setKeep] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [denied, setDenied] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [flash, setFlash] = useState<{ kind: "ok" | "bad"; text: string } | null>(null);

  const load = useCallback(async () => {
    const token = localStorage.getItem(`${APP_SLUG}_access`);
    if (!token) return;
    setLoading(true);
    try {
      const r = await fetch(`${api}/api/leads/duplicates/`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (r.status === 403) { setDenied(true); return; }
      if (!r.ok) return;
      const d = await r.json();
      setGroups(d.groups || []);
      setKeep(Object.fromEntries((d.groups || []).map((g: Group) => [g.key, g.suggested_keep])));
    } catch { /* the empty state covers it */ }
    finally { setLoading(false); }
  }, [api]);

  useEffect(() => { load(); }, [load]);

  const merge = async (g: Group) => {
    const keeper = keep[g.key] ?? g.suggested_keep;
    const others = g.leads.filter(l => l.id !== keeper);
    if (others.length === 0) return;
    if (!confirm(
      `Keep ${g.leads.find(l => l.id === keeper)?.name}, and merge ${others.length} other ` +
      `lead${others.length === 1 ? "" : "s"} into it?\n\n` +
      `Their history moves across and they go to Trash, so this can be undone.`
    )) return;

    setBusy(g.key);
    setFlash(null);
    try {
      const token = localStorage.getItem(`${APP_SLUG}_access`);
      const r = await fetch(`${api}/api/leads/merge-duplicates/`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ keep: keeper, merge: others.map(l => l.id) }),
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) { setFlash({ kind: "bad", text: d.error || "That merge could not be done." }); return; }
      setFlash({ kind: "ok", text: d.message || "Merged." });
      // Drop the group rather than refetching everything: the rest of the list
      // has not changed and reloading it would lose the user's place.
      setGroups(prev => prev.filter(x => x.key !== g.key));
    } catch {
      setFlash({ kind: "bad", text: "Network error — nothing was merged." });
    } finally { setBusy(null); }
  };

  if (denied) return (
    <div className="min-h-screen bg-[#f4f6fa] flex items-center justify-center px-6">
      <div className="bg-white rounded-2xl border border-slate-100 px-8 py-10 text-center max-w-sm">
        <p className="font-bold text-slate-800">Not available to you</p>
        <p className="text-sm text-slate-500 mt-2">
          The duplicate list manages the lead book, so it sits with the tele-calling side.
        </p>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-[#f4f6fa]">
      <div className="max-w-[1200px] mx-auto px-4 sm:px-6 py-8">

        <div className="flex items-start justify-between gap-4 mb-6">
          <div>
            <h1 className="text-2xl font-black text-slate-900">Duplicate Leads</h1>
            <p className="text-sm text-slate-500 mt-1">
              {loading ? "Checking the lead book…"
                : groups.length === 0 ? "Nothing is filed twice."
                : `${groups.length} group${groups.length === 1 ? "" : "s"} share a phone number or email. Choose which lead to keep, then merge.`}
            </p>
          </div>
          <Link href="/leads"
            className="flex-shrink-0 px-4 py-2.5 rounded-xl border border-slate-200 bg-white text-sm
                       font-semibold text-slate-600 hover:bg-slate-50 transition-all">
            ← Back to Leads
          </Link>
        </div>

        {flash && (
          <div className={`mb-5 rounded-xl px-4 py-3 text-sm font-medium border ${
            flash.kind === "ok"
              ? "bg-emerald-50 border-emerald-200 text-emerald-800"
              : "bg-rose-50 border-rose-200 text-rose-800"}`}>
            {flash.text}
          </div>
        )}

        {loading ? (
          <p className="py-24 text-center text-sm text-slate-400">Loading…</p>
        ) : groups.length === 0 ? (
          <div className="bg-white rounded-2xl border border-slate-100 py-20 text-center">
            <p className="font-bold text-slate-700">No duplicates</p>
            <p className="text-sm text-slate-400 mt-1">
              No two leads share a phone number or an email address.
            </p>
          </div>
        ) : (
          <div className="space-y-5">
            {groups.map(g => {
              const keeper = keep[g.key] ?? g.suggested_keep;
              return (
                <div key={`${g.match}-${g.key}`}
                  className="bg-white rounded-2xl border border-slate-100 shadow-[0_4px_20px_rgb(0,0,0,0.04)] overflow-hidden">
                  <div className="flex items-center justify-between gap-3 px-5 py-4 border-b border-slate-50">
                    <div className="flex items-center gap-2 text-sm min-w-0">
                      <span className="text-slate-400 flex-shrink-0">
                        {g.match === "phone" ? <PhoneIcon /> : <MailIcon />}
                      </span>
                      <span className="font-bold text-slate-700 flex-shrink-0">
                        Same {g.match}:
                      </span>
                      <span className="px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-700
                                       font-semibold text-[13px] truncate">{g.key}</span>
                      <span className="text-slate-400 text-[13px] flex-shrink-0">{g.count} leads</span>
                    </div>
                    <button onClick={() => merge(g)} disabled={busy === g.key}
                      className="flex-shrink-0 px-4 py-2 rounded-xl bg-indigo-600 text-white text-sm
                                 font-bold hover:bg-indigo-700 disabled:opacity-50
                                 disabled:cursor-not-allowed transition-all">
                      {busy === g.key ? "Merging…" : "Merge into selected"}
                    </button>
                  </div>

                  <div>
                    {g.leads.map(lead => {
                      const isKeeper = lead.id === keeper;
                      const stuck = !isKeeper && lead.blockers.length > 0;
                      return (
                        <label key={lead.id}
                          className={`flex items-start gap-3 px-5 py-3.5 border-t border-slate-50
                                      cursor-pointer transition-colors first:border-t-0
                                      ${isKeeper ? "bg-indigo-50/40" : "hover:bg-slate-50/60"}`}>
                          <input type="radio" name={`keep-${g.key}`} checked={isKeeper}
                            onChange={() => setKeep(k => ({ ...k, [g.key]: lead.id }))}
                            className="mt-1 w-4 h-4 accent-indigo-600 flex-shrink-0" />
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="font-bold text-slate-800">{lead.name}</span>
                              {isKeeper && (
                                <span className="px-1.5 py-0.5 rounded bg-indigo-100 text-indigo-700
                                                 text-[10px] font-black tracking-wide">KEEP</span>
                              )}
                            </div>
                            <p className="text-[12px] text-slate-500 mt-0.5 truncate">
                              {[lead.phone, lead.email, lead.status,
                                lead.owner || "unassigned"].filter(Boolean).join(" · ")}
                            </p>
                            {/* Said before the merge is attempted, not after it
                                fails: this row cannot be discarded, so the user
                                needs to keep it or sort the pair out by hand. */}
                            {stuck && (
                              <p className="text-[11px] text-amber-700 mt-1">
                                Has {lead.blockers.join(", ")} — keep this one, or sort the two out by hand.
                              </p>
                            )}
                          </div>
                          <span className="text-[12px] text-slate-400 flex-shrink-0">
                            {shortDate(lead.created_at)}
                          </span>
                        </label>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { isSpectator } from "@/lib/spectator";
import BdeTag from "@/components/BdeTag";

type Row = {
  /** Who did the site visit — shown as a tag on the row. */
  bde_name?: string | null;
  id: number;
  first_name: string;
  last_name: string | null;
  phone: string | null;
  location: string | null;
  installation_location: string | null;
  discom_approval: string;         // 'pending' | 'no'
  sent_to_liasoning: boolean;
  is_complete: boolean;
  pushed_at: string | null;
  days_pending: number | null;
};

export default function DiscomFollowupPage() {
  const domain = APP_SLUG;
  const router = useRouter();
  const [authChecked, setAuthChecked] = useState(false);
  const [allowed, setAllowed] = useState(false);
  // Only someone with documentation access can actually open Stage 2 from here.
  const [canOpenStage2, setCanOpenStage2] = useState(false);
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [savingId, setSavingId] = useState<number | null>(null);

  const token = () => localStorage.getItem(`${domain}_access`);

  useEffect(() => {
    const t = token();
    if (!t) { router.push("/login"); return; }
    fetch(`${getApiBase(domain)}/api/users/me/`, { headers: { Authorization: `Bearer ${t}` } })
      .then(r => r.json())
      .then(d => {
        const ok = isSpectator(d) || d.role === "liasoning_officer" || d.is_staff || d.is_general_manager;
        setAllowed(ok);
        setCanOpenStage2(["documentation_staff", "documentation_manager"].includes(d.role) || d.is_staff || d.is_general_manager);
        setAuthChecked(true);
        if (!ok) router.replace("/");
      })
      .catch(() => setAuthChecked(true));
  }, [domain, router]);

  const load = () => {
    fetch(`${getApiBase(domain)}/api/leads/discom-followup/`, { headers: { Authorization: `Bearer ${token()}` } })
      .then(r => (r.ok ? r.json() : []))
      .then(d => setRows(Array.isArray(d) ? d : []))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { if (allowed) load(); }, [allowed]); // eslint-disable-line react-hooks/exhaustive-deps

  const toggleSent = async (row: Row, value: boolean) => {
    setSavingId(row.id);
    try {
      const r = await fetch(`${getApiBase(domain)}/api/leads/${row.id}/discom-followup-sent/`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token()}` },
        body: JSON.stringify({ sent_to_liasoning: value }),
      });
      if (r.ok) {
        setRows(prev => prev.map(x => (x.id === row.id ? { ...x, sent_to_liasoning: value } : x)));
      } else {
        const e = await r.json().catch(() => ({}));
        alert(e.error || "Could not save.");
      }
    } catch { alert("Network error."); }
    finally { setSavingId(null); }
  };

  if (!authChecked) return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="w-8 h-8 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
    </div>
  );
  if (!allowed) return null;

  const filtered = rows.filter(l => {
    const q = search.trim().toLowerCase();
    if (!q) return true;
    return (`${l.first_name} ${l.last_name || ""}`.toLowerCase().includes(q)
      || (l.phone || "").toLowerCase().includes(q)
      || (l.location || "").toLowerCase().includes(q));
  });

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-[1200px]">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Discom Follow-up</h1>
        <p className="text-sm text-slate-500 mt-1">
          Customers whose discom approval is not approved, or still pending after 7 days — go to the concerned section and chase it.
          Once Documentation Stage 2 records the approval, the customer leaves this list.
        </p>
      </div>

      <div className="mb-5 flex items-center gap-3">
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search by name, phone or location…"
          className="w-full max-w-md bg-white border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all"
        />
        <span className="text-xs font-semibold text-slate-400">{filtered.length} customer{filtered.length === 1 ? "" : "s"}</span>
      </div>

      {loading ? (
        <div className="py-16 text-center text-sm text-slate-400">Loading…</div>
      ) : filtered.length === 0 ? (
        <div className="bg-white border border-dashed border-slate-200 rounded-2xl p-12 text-center text-sm text-slate-400">
          No customers awaiting discom approval — every approval has come through.
        </div>
      ) : (
        <div className="space-y-4">
          {filtered.map(l => {
            const notApproved = l.discom_approval === "no";
            return (
              <div key={l.id} className="bg-white border border-slate-200 rounded-2xl shadow-sm px-5 py-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-bold text-slate-900 truncate">{l.first_name} {l.last_name}</p>
                      <BdeTag name={l.bde_name} />
                      <span className={`text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full ${notApproved ? "bg-rose-50 text-rose-600" : "bg-amber-50 text-amber-700"}`}>
                        {notApproved ? "Not Approved" : `Pending${l.days_pending != null ? ` · ${l.days_pending}d` : ""}`}
                      </span>
                      {l.sent_to_liasoning && (
                        <span className="text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700">
                          Officer Sent
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-slate-500 mt-0.5 truncate">{l.phone || "—"} · {l.location || l.installation_location || "No location"}</p>
                  </div>
                  {canOpenStage2 && (
                    <Link href={`/documentation-stage2/${l.id}`} className="text-[12px] font-semibold text-indigo-600 hover:text-indigo-800 flex-shrink-0">
                      Open Stage 2 →
                    </Link>
                  )}
                </div>

                <div className={`mt-3 rounded-xl p-3 border ${notApproved ? "bg-amber-50/60 border-amber-100" : "bg-slate-50/70 border-slate-100"}`}>
                  <p className={`text-[11px] font-semibold mb-2 ${notApproved ? "text-amber-700" : "text-slate-500"}`}>
                    {notApproved
                      ? "Not approved — send the liasoning officer to the concerned section."
                      : "Approval pending — send the liasoning officer to the concerned section."}
                  </p>
                  {/* Recordable even after Stage 2 is signed off — the approval
                      can still be outstanding at that point. */}
                  <label className="inline-flex items-center gap-2 text-sm font-medium text-slate-700 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={l.sent_to_liasoning}
                      disabled={savingId === l.id}
                      onChange={e => toggleSent(l, e.target.checked)}
                      className="w-4 h-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500/30"
                    />
                    Liasoning officer sent to the concerned section
                    {savingId === l.id && <span className="text-[11px] text-slate-400">Saving…</span>}
                  </label>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

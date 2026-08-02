"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import DeletedLeadCleanup, { DeletedLeadBadge } from "@/components/DeletedLeadCleanup";
type LiasoningRecord = {
  feasibility_completed: boolean; feasibility_remark: string;
  annexure3_completed: boolean; annexure3_remark: string;
  discom_approval: string;
  is_complete: boolean;
};
type LiasoningLead = {
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
  is_complete: boolean;
  can_edit: boolean;
  pushed_at: string | null;
  record: LiasoningRecord | null;
};

const STAGES = [
  { key: "feasibility", label: "Feasibility" },
  { key: "annexure3", label: "Annexure 3 (completion doc submission)" },
] as const;

const DISCOM_OPTIONS = [
  { value: "pending", label: "Pending" },
  { value: "yes", label: "Approved" },
  { value: "no", label: "Not Approved" },
];

type RowDraft = {
  feasibility_completed: boolean; feasibility_remark: string;
  annexure3_completed: boolean; annexure3_remark: string;
  discom_approval: string;
};

const inputCls = "w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all disabled:opacity-70";

export default function LiasoningPage() {
  const domain = APP_SLUG;
  const router = useRouter();
  const [authChecked, setAuthChecked] = useState(false);
  const [allowed, setAllowed] = useState(false);
  const [leads, setLeads] = useState<LiasoningLead[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [stage, setStage] = useState<(typeof STAGES)[number]["key"]>("feasibility");
  const [rows, setRows] = useState<Record<number, RowDraft>>({});
  const [savingId, setSavingId] = useState<number | null>(null);

  const token = () => localStorage.getItem(`${domain}_access`);

  useEffect(() => {
    const t = token();
    if (!t) { router.push("/login"); return; }
    fetch(`${getApiBase(domain)}/api/users/me/`, { headers: { Authorization: `Bearer ${t}` } })
      .then(r => r.json())
      .then(d => {
        const ok = d.role === "liasoning_officer" || d.is_staff || d.is_general_manager;
        setAllowed(ok);
        setAuthChecked(true);
        if (!ok) router.replace("/");
      })
      .catch(() => setAuthChecked(true));
  }, [domain, router]);

  const seed = (list: LiasoningLead[]) => {
    const drafts: Record<number, RowDraft> = {};
    for (const l of list) {
      drafts[l.id] = {
        feasibility_completed: !!l.record?.feasibility_completed,
        feasibility_remark: l.record?.feasibility_remark || "",
        annexure3_completed: !!l.record?.annexure3_completed,
        annexure3_remark: l.record?.annexure3_remark || "",
        discom_approval: l.record?.discom_approval || "pending",
      };
    }
    setRows(drafts);
  };

  useEffect(() => {
    if (!allowed) return;
    fetch(`${getApiBase(domain)}/api/leads/liasoning/`, { headers: { Authorization: `Bearer ${token()}` } })
      .then(r => (r.ok ? r.json() : []))
      .then(d => { const list = Array.isArray(d) ? d : []; setLeads(list); seed(list); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [allowed, domain]); // eslint-disable-line react-hooks/exhaustive-deps

  const setRow = (id: number, patch: Partial<RowDraft>) =>
    setRows(p => ({ ...p, [id]: { ...p[id], ...patch } }));

  const saveRow = async (lead: LiasoningLead) => {
    const draft = rows[lead.id];
    if (!draft) return;
    const body = stage === "feasibility"
      ? { feasibility_completed: draft.feasibility_completed, feasibility_remark: draft.feasibility_remark }
      : { annexure3_completed: draft.annexure3_completed, annexure3_remark: draft.annexure3_remark, discom_approval: draft.discom_approval };
    setSavingId(lead.id);
    try {
      const r = await fetch(`${getApiBase(domain)}/api/leads/${lead.id}/liasoning-record/`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token()}` },
        body: JSON.stringify(body),
      });
      if (r.ok) {
        const d = await r.json();
        // Keep the saved record on the lead so the Annexure 3 gate reflects saved state.
        setLeads(prev => prev.map(x => (x.id === lead.id ? { ...x, record: { ...(x.record || {}), ...d } } : x)));
      } else { const e = await r.json().catch(() => ({})); alert(e.error || "Failed to save."); }
    } catch { alert("Network error while saving."); }
    finally { setSavingId(null); }
  };

  if (!authChecked) return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="w-8 h-8 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
    </div>
  );
  if (!allowed) return null;

  const filtered = leads.filter(l => {
    const q = search.trim().toLowerCase();
    if (!q) return true;
    return (`${l.first_name} ${l.last_name || ""}`.toLowerCase().includes(q)
      || (l.phone || "").toLowerCase().includes(q)
      || (l.location || "").toLowerCase().includes(q));
  });
  // Annexure 3 only opens once a customer's feasibility stage is completed (saved).
  const stageLeads = stage === "annexure3" ? filtered.filter(l => !!l.record?.feasibility_completed) : filtered;

  return (
    <div className="p-6 lg:p-8 max-w-[1200px]">
      <div className="mb-5">
        <h1 className="text-2xl font-bold text-slate-900">Liasoning</h1>
        <p className="text-sm text-slate-500 mt-1">Feasibility first — a customer moves to Annexure 3 (completion doc submission) once feasibility is completed.</p>
      </div>

      <>
          {/* Stage toggle */}
          <div className="mb-4 inline-flex items-center bg-slate-100 border border-slate-200 rounded-full p-1">
            {STAGES.map(s => (
              <button key={s.key} onClick={() => setStage(s.key)}
                className={`px-4 py-1.5 rounded-full text-xs font-semibold transition ${stage === s.key ? "bg-indigo-600 text-white shadow-sm" : "text-slate-500 hover:text-slate-700"}`}>
                {s.label}
              </button>
            ))}
          </div>
          {stage === "annexure3" && (
            <p className="mb-4 text-[11px] text-slate-400">Annexure 3 status &amp; discom approval entered here sync directly to the customer&apos;s MNRE Stage 2 (Documentation Stage 2).</p>
          )}

          <div className="mb-4 flex items-center gap-3">
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search by name, phone or location…"
              className="w-full max-w-md bg-white border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all"
            />
            <span className="text-xs font-semibold text-slate-400">{stageLeads.length} customer{stageLeads.length === 1 ? "" : "s"}</span>
          </div>

          {loading ? (
            <div className="py-16 text-center text-sm text-slate-400">Loading…</div>
          ) : stageLeads.length === 0 ? (
            <div className="bg-white border border-dashed border-slate-200 rounded-2xl p-12 text-center text-sm text-slate-400">
              {stage === "annexure3"
                ? "No customers yet — a customer appears here once their feasibility stage is completed."
                : "No customers in liasoning yet."}
            </div>
          ) : (
            <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm min-w-[760px]">
                  <thead>
                    <tr className="text-left text-[10px] font-bold text-slate-400 uppercase tracking-wide border-b border-slate-100 bg-slate-50/60">
                      <th className="px-5 py-3">Customer</th>
                      <th className="px-5 py-3">Completed</th>
                      <th className="px-5 py-3">Remarks</th>
                      {stage === "annexure3" && <th className="px-5 py-3">Discom Approval</th>}
                      <th className="px-5 py-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stageLeads.map(l => {
                      const d = rows[l.id];
                      if (!d) return null;
                      const locked = !l.can_edit || !!l.record?.is_complete;
                      const completed = stage === "feasibility" ? d.feasibility_completed : d.annexure3_completed;
                      const remark = stage === "feasibility" ? d.feasibility_remark : d.annexure3_remark;
                      return (
                        <tr key={l.id} className="border-b border-slate-50 hover:bg-slate-50/60 align-middle">
                          <td className="px-5 py-3">
                            <div className="flex items-center gap-2 flex-wrap">
                              <Link href={`/liasoning/${l.id}`} className="font-semibold text-slate-800 hover:text-indigo-600 transition">
                                {l.first_name} {l.last_name}
                              </Link>
                              {l.lead_deleted && <DeletedLeadBadge />}
                              {l.can_cleanup && (
                                <DeletedLeadCleanup leadId={l.id} module="liasoning"
                                  name={`${l.first_name} ${l.last_name || ""}`.trim()}
                                  onRemoved={() => setLeads(prev => prev.filter(x => x.id !== l.id))} />
                              )}
                            </div>
                            <p className="text-[11px] text-slate-400">{l.phone || "—"}{l.location ? ` · ${l.location}` : ""}</p>
                          </td>
                          <td className="px-5 py-3">
                            <label className="inline-flex items-center gap-2 cursor-pointer">
                              <input type="checkbox" checked={completed} disabled={locked}
                                onChange={e => setRow(l.id, stage === "feasibility"
                                  ? { feasibility_completed: e.target.checked }
                                  : { annexure3_completed: e.target.checked })}
                                className="w-4 h-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500/30" />
                              <span className={`text-xs font-semibold ${completed ? "text-emerald-600" : "text-slate-400"}`}>
                                {completed ? "Completed" : "Not completed"}
                              </span>
                            </label>
                          </td>
                          <td className="px-5 py-3 min-w-[220px]">
                            <input value={remark} disabled={locked} placeholder="Remarks"
                              onChange={e => setRow(l.id, stage === "feasibility"
                                ? { feasibility_remark: e.target.value }
                                : { annexure3_remark: e.target.value })}
                              className={inputCls} />
                          </td>
                          {stage === "annexure3" && (
                            <td className="px-5 py-3 min-w-[150px]">
                              <select value={d.discom_approval} disabled={locked}
                                onChange={e => setRow(l.id, { discom_approval: e.target.value })}
                                className={inputCls}>
                                {DISCOM_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                              </select>
                            </td>
                          )}
                          <td className="px-5 py-3 text-right">
                            {locked ? (
                              <span className="text-[11px] text-slate-400">Read-only</span>
                            ) : (
                              <button onClick={() => saveRow(l)} disabled={savingId === l.id}
                                className="px-4 py-2 bg-indigo-600 text-white rounded-xl text-xs font-semibold hover:bg-indigo-700 disabled:opacity-50 transition">
                                {savingId === l.id ? "Saving…" : "Save"}
                              </button>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
      </>
    </div>
  );
}

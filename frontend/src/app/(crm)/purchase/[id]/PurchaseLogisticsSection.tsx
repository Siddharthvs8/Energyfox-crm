"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";
import React, { useCallback, useEffect, useState } from "react";

const DELIVERY = [
  { value: "delivered", label: "Delivered" },
  { value: "not_delivered", label: "Not Delivered" },
];
const YES_NO = [
  { value: "yes", label: "Yes" },
  { value: "no", label: "No" },
];

const inputCls =
  "w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all disabled:opacity-70 disabled:cursor-not-allowed";
const labelCls = "block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5";

export default function PurchaseLogisticsSection({ leadId, canEdit, canReopen, onChanged }: {
  leadId: number | string; canEdit: boolean; canReopen?: boolean; onChanged?: () => void;
}) {
  const apiBase = getApiBase(APP_SLUG);
  const url = `${apiBase}/api/leads/${leadId}/purchase-logistics/`;
  const authHeader = () => ({ Authorization: `Bearer ${localStorage.getItem(`${APP_SLUG}_access`)}` });

  const [structureMaterial, setStructureMaterial] = useState("");
  const [bom, setBom] = useState("");
  const [pendingItem, setPendingItem] = useState("");
  const [remark, setRemark] = useState("");
  const [isComplete, setIsComplete] = useState(false);
  const [completedByName, setCompletedByName] = useState<string | null>(null);
  const [completedAt, setCompletedAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [completing, setCompleting] = useState(false);
  const [saved, setSaved] = useState(false);

  const load = useCallback((d: any) => {
    setStructureMaterial(d.structure_material || "");
    setBom(d.bom || "");
    setPendingItem(d.pending_item || "");
    setRemark(d.remark || "");
    setIsComplete(!!d.is_complete);
    setCompletedByName(d.completed_by_name ?? null);
    setCompletedAt(d.completed_at ?? null);
  }, []);

  useEffect(() => {
    if (!localStorage.getItem(`${APP_SLUG}_access`)) { setLoading(false); return; }
    fetch(url, { headers: authHeader() })
      .then(r => (r.ok ? r.json() : null))
      .then(d => { if (d) load(d); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [leadId]); // eslint-disable-line react-hooks/exhaustive-deps

  const readOnly = !canEdit || isComplete;
  const ready = !!structureMaterial && !!bom;
  const change = (setter: (v: string) => void) => (v: string) => { setter(v); setSaved(false); };

  const saveScalars = async (): Promise<any | null> => {
    const r = await fetch(url, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...authHeader() },
      body: JSON.stringify({ structure_material: structureMaterial, bom, pending_item: pendingItem, remark }),
    });
    if (!r.ok) { const e = await r.json().catch(() => ({})); alert(e.error || "Failed to save purchase & logistics."); return null; }
    return r.json();
  };

  const save = async () => {
    setSaving(true);
    try {
      const latest = await saveScalars();
      if (latest) { load(latest); setSaved(true); onChanged?.(); }
    } catch { alert("Network error while saving."); }
    finally { setSaving(false); }
  };

  const complete = async () => {
    if (!ready) { alert("Set the structure material and BOM delivery status first."); return; }
    setCompleting(true);
    try {
      const latest = await saveScalars();
      if (!latest) return;
      const r = await fetch(`${apiBase}/api/leads/${leadId}/complete-purchase-logistics/`, { method: "POST", headers: authHeader() });
      if (r.ok) {
        const d = await r.json();
        if (d.purchase_logistics) load(d.purchase_logistics);
        else { load(latest); setIsComplete(true); }
        onChanged?.();
        alert("Purchase & logistics completed.");
      } else {
        const d = await r.json().catch(() => ({}));
        alert(d.error || "Could not complete purchase & logistics.");
      }
    } catch { alert("Network error while completing."); }
    finally { setCompleting(false); }
  };

  const reopen = async () => {
    if (!window.confirm("Reopen this completed purchase & logistics for editing?")) return;
    try {
      const r = await fetch(`${apiBase}/api/leads/${leadId}/reopen-purchase-logistics/`, { method: "POST", headers: authHeader() });
      if (r.ok) {
        const d = await r.json();
        if (d.purchase_logistics) load(d.purchase_logistics);
        else setIsComplete(false);
        onChanged?.();
      } else {
        const d = await r.json().catch(() => ({}));
        alert(d.error || "Could not reopen.");
      }
    } catch { alert("Network error while reopening."); }
  };

  const cardCls = "bg-white border border-slate-200 rounded-2xl shadow-sm p-5";

  if (loading) {
    return <div className={`mt-5 ${cardCls} text-sm text-slate-400`}>Loading purchase & logistics…</div>;
  }

  return (
    <div className="mt-5 space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-bold text-slate-900">Purchase &amp; Logistics</h2>
          <p className="text-xs text-slate-400 mt-0.5">Filled by the assigned purchase staff.</p>
        </div>
        {isComplete ? (
          <div className="flex items-center gap-3">
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-emerald-50 border border-emerald-200 text-emerald-700 rounded-lg text-xs font-semibold">
              ✓ Completed{completedByName ? ` by ${completedByName}` : ""}{completedAt ? ` · ${new Date(completedAt).toLocaleDateString("en-IN")}` : ""}
            </span>
            {canReopen && (
              <button onClick={reopen} className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-300 text-slate-700 rounded-lg text-xs font-semibold hover:bg-slate-50 transition">
                Reopen for editing
              </button>
            )}
          </div>
        ) : !canEdit ? (
          <span className="text-xs text-slate-400">Read-only — not assigned to you.</span>
        ) : null}
      </div>

      <div className={cardCls}>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-4">
          <div>
            <label className={labelCls}>Structure Material</label>
            <select value={structureMaterial} disabled={readOnly} onChange={e => change(setStructureMaterial)(e.target.value)} className={inputCls}>
              <option value="">—</option>
              {DELIVERY.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>

          <div>
            <label className={labelCls}>BOM (Bill of Materials)</label>
            <select value={bom} disabled={readOnly} onChange={e => change(setBom)(e.target.value)} className={inputCls}>
              <option value="">—</option>
              {DELIVERY.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>

          <div>
            <label className={labelCls}>Pending Item</label>
            <select value={pendingItem} disabled={readOnly} onChange={e => change(setPendingItem)(e.target.value)} className={inputCls}>
              <option value="">—</option>
              {YES_NO.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>

          <div className="sm:col-span-2 lg:col-span-3">
            <label className={labelCls}>Remark</label>
            <textarea value={remark} disabled={readOnly} onChange={e => change(setRemark)(e.target.value)} rows={3}
              placeholder="Any notes on the procurement / delivery…" className={inputCls} />
          </div>
        </div>
      </div>

      {canEdit && !isComplete && (
        <div className="flex flex-wrap items-center gap-3">
          <button onClick={save} disabled={saving || completing}
            className="px-5 py-2.5 bg-slate-800 text-white rounded-xl text-sm font-semibold hover:bg-slate-900 disabled:opacity-50 transition">
            {saving ? "Saving…" : saved ? "Saved ✓" : "Save"}
          </button>
          <button onClick={complete} disabled={completing || saving || !ready} title={!ready ? "Set structure material and BOM status first" : ""}
            className="px-5 py-2.5 bg-emerald-600 text-white rounded-xl text-sm font-semibold hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed transition">
            {completing ? "Completing…" : "Mark Complete"}
          </button>
          {!ready && <span className="text-xs text-slate-400">Set structure material and BOM delivery status to complete.</span>}
        </div>
      )}
    </div>
  );
}

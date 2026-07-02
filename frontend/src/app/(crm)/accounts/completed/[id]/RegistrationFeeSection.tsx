"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";
import React, { useCallback, useEffect, useState } from "react";

const inputCls =
  "w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all disabled:opacity-70 disabled:cursor-not-allowed";
const labelCls = "block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5";

export default function RegistrationFeeSection({ leadId, canEdit, onChanged }: {
  leadId: number | string; canEdit: boolean; onChanged?: () => void;
}) {
  const apiBase = getApiBase(APP_SLUG);
  const url = `${apiBase}/api/leads/${leadId}/registration-fee/`;
  const authHeader = () => ({ Authorization: `Bearer ${localStorage.getItem(`${APP_SLUG}_access`)}` });

  const [poDate, setPoDate] = useState("");
  const [ksebDate, setKsebDate] = useState("");
  const [rfPushed, setRfPushed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [pushingRf, setPushingRf] = useState(false);
  const [saved, setSaved] = useState(false);

  const load = useCallback((d: any) => {
    setPoDate(d.po_date || "");
    setKsebDate(d.kseb_feasibility_date || "");
    setRfPushed(!!d.rf_pushed_to_service);
  }, []);

  useEffect(() => {
    if (!localStorage.getItem(`${APP_SLUG}_access`)) { setLoading(false); return; }
    fetch(url, { headers: authHeader() })
      .then(r => (r.ok ? r.json() : null))
      .then(d => { if (d) load(d); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [leadId]); // eslint-disable-line react-hooks/exhaustive-deps

  const readOnly = !canEdit || rfPushed;
  const change = (setter: (v: string) => void) => (v: string) => { setter(v); setSaved(false); };

  const saveScalars = async (): Promise<any | null> => {
    const r = await fetch(url, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...authHeader() },
      body: JSON.stringify({ po_date: poDate || null, kseb_feasibility_date: ksebDate || null }),
    });
    if (!r.ok) { const e = await r.json().catch(() => ({})); alert(e.error || "Failed to save registration fee."); return null; }
    return r.json();
  };

  const save = async () => {
    setSaving(true);
    try { const latest = await saveScalars(); if (latest) { load(latest); setSaved(true); onChanged?.(); } }
    catch { alert("Network error while saving."); }
    finally { setSaving(false); }
  };

  // RF is due 30 days from the KSEB feasibility date.
  const rfDue = (() => {
    if (!ksebDate) return "";
    const d = new Date(ksebDate);
    if (isNaN(d.getTime())) return "";
    d.setDate(d.getDate() + 30);
    return d.toLocaleDateString("en-IN");
  })();

  const pushRf = async () => {
    if (!ksebDate) { alert("Set the KSEB feasibility date first."); return; }
    if (!window.confirm("Push the RF remittance to the service department?")) return;
    setPushingRf(true);
    try {
      const latest = await saveScalars();  // persist po/feasibility dates first
      if (!latest) return;
      const r = await fetch(`${apiBase}/api/leads/${leadId}/push-rf-to-service/`, { method: "POST", headers: authHeader() });
      if (r.ok) {
        setRfPushed(true);
        onChanged?.();
        alert("RF pushed to the service department.");
      } else { const d = await r.json().catch(() => ({})); alert(d.error || "Could not push RF."); }
    } catch { alert("Network error while pushing RF."); }
    finally { setPushingRf(false); }
  };

  const cardCls = "bg-white border border-slate-200 rounded-2xl shadow-sm p-5";

  if (loading) {
    return <div className={`mt-5 ${cardCls} text-sm text-slate-400`}>Loading registration fee…</div>;
  }

  return (
    <div className="mt-5 space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-bold text-slate-900">PO &amp; Registration Fee (RF)</h2>
          <p className="text-xs text-slate-400 mt-0.5">Remit the registration fee at the KSEB section, then push it to the service department.</p>
        </div>
        {rfPushed ? (
          <span className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-emerald-50 border border-emerald-200 text-emerald-700 rounded-lg text-xs font-semibold">
            ✓ RF Pushed to Service
          </span>
        ) : !canEdit ? (
          <span className="text-xs text-slate-400">Read-only — not assigned to you.</span>
        ) : null}
      </div>

      <div className={cardCls}>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-4">
          <div>
            <label className={labelCls}>PO Date</label>
            <input type="date" value={poDate} disabled={readOnly} onChange={e => change(setPoDate)(e.target.value)} className={inputCls} />
          </div>
          <div>
            <label className={labelCls}>KSEB Feasibility Date</label>
            <input type="date" value={ksebDate} disabled={readOnly} onChange={e => change(setKsebDate)(e.target.value)} className={inputCls} />
          </div>
          <div>
            <label className={labelCls}>RF Due Date</label>
            <input value={rfDue || "—"} disabled className={`${inputCls} font-semibold text-amber-600`} />
            <p className="text-[10px] text-slate-400 mt-1">30 days from KSEB feasibility · reminder on day 29.</p>
          </div>
        </div>

        {rfPushed ? (
          <p className="mt-4 text-xs text-emerald-700 font-semibold">✓ RF remittance pushed to the service department (remit at KSEB section).</p>
        ) : canEdit ? (
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <button onClick={save} disabled={saving || pushingRf}
              className="px-5 py-2.5 bg-slate-800 text-white rounded-xl text-sm font-semibold hover:bg-slate-900 disabled:opacity-50 transition">
              {saving ? "Saving…" : saved ? "Saved ✓" : "Save"}
            </button>
            <button onClick={pushRf} disabled={pushingRf || saving || !ksebDate}
              title={!ksebDate ? "Set the KSEB feasibility date first" : ""}
              className="px-5 py-2.5 bg-amber-600 text-white rounded-xl text-sm font-semibold hover:bg-amber-700 disabled:opacity-50 disabled:cursor-not-allowed transition">
              {pushingRf ? "Pushing…" : "Push to Service Dept (remit RF at KSEB)"}
            </button>
            {!ksebDate && <span className="text-xs text-slate-400">Set the KSEB feasibility date to push RF.</span>}
          </div>
        ) : null}
      </div>
    </div>
  );
}

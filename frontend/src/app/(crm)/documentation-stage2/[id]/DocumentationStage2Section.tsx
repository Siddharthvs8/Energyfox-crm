"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";
import React, { useCallback, useEffect, useState } from "react";

const ANNEXURE_SLOT = "annexure3";
const DISCOM_OPTIONS = [
  { value: "pending", label: "Pending" },
  { value: "yes", label: "Approved" },
  { value: "no", label: "Not Approved" },
];

const inputCls =
  "w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all disabled:opacity-70 disabled:cursor-not-allowed";
const labelCls = "block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5";
const cardCls = "bg-white border border-slate-200 rounded-2xl shadow-sm p-5";
const sectionTitle = "text-xs font-bold text-indigo-600 uppercase tracking-wide mb-3";

type Doc = { id: number; doc_type: string; file: string };
type Form = {
  annexure3_completed: boolean; annexure3_remark: string;
  discom_approval: string; subsidy_requested: boolean; sent_to_liasoning: boolean; mnre_remark: string;
};

const BLANK: Form = {
  annexure3_completed: false, annexure3_remark: "",
  discom_approval: "pending", subsidy_requested: false, sent_to_liasoning: false, mnre_remark: "",
};

function Check({ checked, disabled, onChange, label }: { checked: boolean; disabled?: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <label className={`inline-flex items-center gap-2 text-sm font-medium ${disabled ? "text-slate-400" : "text-slate-700 cursor-pointer"}`}>
      <input type="checkbox" checked={checked} disabled={disabled} onChange={e => onChange(e.target.checked)}
        className="w-4 h-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500/30" />
      {label}
    </label>
  );
}

export default function DocumentationStage2Section({ leadId, canEdit, onChanged }: {
  leadId: number | string; canEdit: boolean; onChanged?: () => void;
}) {
  const apiBase = getApiBase(APP_SLUG);
  const url = `${apiBase}/api/leads/${leadId}/documentation-stage2-record/`;
  const docsUrl = `${apiBase}/api/leads/${leadId}/documentation-stage2/documents/`;
  const completeUrl = `${apiBase}/api/leads/${leadId}/complete-documentation-stage2/`;
  const authHeader = () => ({ Authorization: `Bearer ${localStorage.getItem(`${APP_SLUG}_access`)}` });

  const [f, setF] = useState<Form>({ ...BLANK });
  const [documents, setDocuments] = useState<Doc[]>([]);
  const [portalUrl, setPortalUrl] = useState("https://consumer.pmsuryaghar.gov.in/consumer/#/login");
  const [isComplete, setIsComplete] = useState(false);
  const [completedByName, setCompletedByName] = useState<string | null>(null);
  const [completedAt, setCompletedAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [completing, setCompleting] = useState(false);
  const [uploadingType, setUploadingType] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const load = useCallback((d: any) => {
    setF({
      annexure3_completed: !!d.annexure3_completed,
      annexure3_remark: d.annexure3_remark || "",
      discom_approval: d.discom_approval || "pending",
      subsidy_requested: !!d.subsidy_requested,
      sent_to_liasoning: !!d.sent_to_liasoning,
      mnre_remark: d.mnre_remark || "",
    });
    setDocuments(Array.isArray(d.documents) ? d.documents : []);
    if (d.mnre_portal_url) setPortalUrl(d.mnre_portal_url);
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
  const set = (k: keyof Form, v: any) => { setF(p => ({ ...p, [k]: v })); setSaved(false); };

  const saveScalars = async (): Promise<any | null> => {
    const r = await fetch(url, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...authHeader() },
      body: JSON.stringify(f),
    });
    if (!r.ok) { const e = await r.json().catch(() => ({})); alert(e.error || "Failed to save."); return null; }
    return r.json();
  };

  const save = async () => {
    setSaving(true);
    try { const latest = await saveScalars(); if (latest) { load(latest); setSaved(true); onChanged?.(); } }
    catch { alert("Network error while saving."); }
    finally { setSaving(false); }
  };

  const refetch = async () => {
    try { const r = await fetch(url, { headers: authHeader() }); if (r.ok) load(await r.json()); } catch {}
  };

  const addDocs = async (docType: string, fileList: File[]) => {
    if (!fileList.length) return;
    setUploadingType(docType);
    try {
      let any = false;
      for (const file of fileList) {
        const fd = new FormData();
        fd.append("doc_type", docType);
        fd.append("file", file);
        const r = await fetch(docsUrl, { method: "POST", headers: authHeader(), body: fd });
        if (r.ok) any = true;
        else { const e = await r.json().catch(() => ({})); alert(e.error || `Upload failed for ${file.name}.`); }
      }
      if (any) await refetch();
    } catch { alert("Network error while uploading."); }
    finally { setUploadingType(null); }
  };

  const deleteDoc = async (docId: number) => {
    if (!window.confirm("Delete this document?")) return;
    try {
      const r = await fetch(`${docsUrl}${docId}/`, { method: "DELETE", headers: authHeader() });
      if (r.ok || r.status === 204) await refetch();
      else { const e = await r.json().catch(() => ({})); alert(e.error || "Could not delete."); }
    } catch { alert("Network error while deleting."); }
  };

  const complete = async () => {
    if (!window.confirm("Mark Documentation Stage 2 complete? This locks it.")) return;
    setCompleting(true);
    try {
      const latest = await saveScalars();
      if (!latest) return;
      const r = await fetch(completeUrl, { method: "POST", headers: authHeader() });
      if (r.ok) { await refetch(); onChanged?.(); alert("Documentation Stage 2 marked complete."); }
      else { const e = await r.json().catch(() => ({})); alert(e.error || "Could not complete."); }
    } catch { alert("Network error while completing."); }
    finally { setCompleting(false); }
  };

  if (loading) return <div className={`mt-5 ${cardCls} text-sm text-slate-400`}>Loading Documentation Stage 2…</div>;

  const renderDocSlot = (slot: string) => {
    const mine = documents.filter(d => d.doc_type === slot);
    const busy = uploadingType === slot;
    return (
      <div>
        {mine.length > 0 && (
          <ul className="mb-2 space-y-1">
            {mine.map(d => {
              const href = d.file.startsWith("http") ? d.file : `${apiBase}${d.file}`;
              const name = decodeURIComponent(d.file.split("/").pop() || "file");
              return (
                <li key={d.id} className="flex items-center gap-2 text-[11px]">
                  <a href={href} target="_blank" rel="noreferrer" className="font-semibold text-emerald-600 hover:underline truncate max-w-[220px]" title={name}>{name}</a>
                  {!readOnly && <button type="button" onClick={() => deleteDoc(d.id)} title="Delete" className="font-bold text-rose-500 hover:text-rose-700">✕</button>}
                </li>
              );
            })}
          </ul>
        )}
        <label className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-semibold transition ${(readOnly || busy) ? "bg-slate-100 text-slate-400 cursor-not-allowed" : "bg-slate-100 text-slate-700 hover:bg-slate-200 cursor-pointer"}`}>
          {busy ? "Uploading…" : "+ Add document(s)"}
          <input type="file" accept="image/*,application/pdf" multiple disabled={readOnly || busy} className="hidden"
            onChange={e => { const fs = Array.from(e.target.files || []); e.currentTarget.value = ""; addDocs(slot, fs); }} />
        </label>
      </div>
    );
  };

  return (
    <div className="mt-5 space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-bold text-slate-900">Documentation Stage 2</h2>
          <p className="text-xs text-slate-400 mt-0.5">Completion docs (Annexure 3) &amp; MNRE Stage 2.</p>
        </div>
        {isComplete ? (
          <span className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-emerald-50 border border-emerald-200 text-emerald-700 rounded-lg text-xs font-semibold">
            ✓ Completed{completedByName ? ` by ${completedByName}` : ""}{completedAt ? ` · ${new Date(completedAt).toLocaleDateString("en-IN")}` : ""}
          </span>
        ) : !canEdit ? (
          <span className="text-xs text-slate-400">Read-only.</span>
        ) : null}
      </div>

      {/* 1. Completion docs / Annexure 3 */}
      <div className={cardCls}>
        <h3 className={sectionTitle}>Completion Docs — Annexure 3</h3>
        <p className="text-[11px] text-slate-400 mb-4">Set of documents given to KSEB, prepared right after the project uploads the installation photos.</p>

        <div className="mb-4">
          <label className={labelCls}>Annexure 3 Documents</label>
          {renderDocSlot(ANNEXURE_SLOT)}
        </div>

        <div className="grid sm:grid-cols-3 gap-4 items-start">
          <div className="pt-1"><Check checked={f.annexure3_completed} disabled={readOnly} onChange={v => set("annexure3_completed", v)} label="Task completed" /></div>
          <div className="sm:col-span-2"><label className={labelCls}>Remark</label><input value={f.annexure3_remark} disabled={readOnly} onChange={e => set("annexure3_remark", e.target.value)} placeholder="Remark" className={inputCls} /></div>
        </div>
      </div>

      {/* 2. MNRE Stage 2 */}
      <div className={cardCls}>
        <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
          <h3 className={sectionTitle}>MNRE Stage 2</h3>
          <a href={portalUrl} target="_blank" rel="noreferrer"
            className="inline-flex items-center gap-1.5 px-4 py-2 bg-indigo-600 text-white rounded-xl text-xs font-semibold hover:bg-indigo-700 transition shadow-sm">
            Open PM Surya Ghar portal
            <svg width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" /><polyline points="15 3 21 3 21 9" /><line x1="10" y1="14" x2="21" y2="3" /></svg>
          </a>
        </div>
        <div className="grid sm:grid-cols-3 gap-4 items-start">
          <div>
            <label className={labelCls}>Discom Approval</label>
            <select value={f.discom_approval} disabled={readOnly} onChange={e => set("discom_approval", e.target.value)} className={inputCls}>
              {DISCOM_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
          <div className="sm:col-span-2"><label className={labelCls}>Remark</label><input value={f.mnre_remark} disabled={readOnly} onChange={e => set("mnre_remark", e.target.value)} placeholder="Remark" className={inputCls} /></div>
        </div>

        {f.discom_approval === "yes" && (
          <div className="mt-4 bg-emerald-50/60 border border-emerald-100 rounded-xl p-3">
            <Check checked={f.subsidy_requested} disabled={readOnly} onChange={v => set("subsidy_requested", v)} label="Subsidy requested" />
          </div>
        )}
        {f.discom_approval === "no" && (
          <div className="mt-4 bg-amber-50/60 border border-amber-100 rounded-xl p-3">
            <p className="text-[11px] text-amber-700 font-semibold mb-2">Not approved — send the liasoning officer to the concerned section.</p>
            <Check checked={f.sent_to_liasoning} disabled={readOnly} onChange={v => set("sent_to_liasoning", v)} label="Liasoning officer sent to the concerned section" />
          </div>
        )}
      </div>

      {canEdit && !isComplete && (
        <div className="flex flex-wrap items-center gap-3">
          <button onClick={save} disabled={saving || completing || uploadingType !== null}
            className="px-5 py-2.5 bg-slate-800 text-white rounded-xl text-sm font-semibold hover:bg-slate-900 disabled:opacity-50 transition">
            {saving ? "Saving…" : saved ? "Saved ✓" : "Save"}
          </button>
          <button onClick={complete} disabled={completing || saving || uploadingType !== null}
            className="px-5 py-2.5 bg-emerald-600 text-white rounded-xl text-sm font-semibold hover:bg-emerald-700 disabled:opacity-50 transition">
            {completing ? "Completing…" : "Mark Complete"}
          </button>
        </div>
      )}
    </div>
  );
}

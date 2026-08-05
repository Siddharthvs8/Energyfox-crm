"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";
import React, { useCallback, useEffect, useState } from "react";

// Geotagged installation photo slots — mirror Project.PHOTO_SLOTS on the backend.
const PHOTO_SLOTS: [string, string][] = [
  ["panel_serial_numbers", "Panel Serial Numbers"],
  ["inverter_sn", "Inverter SN"],
  ["generation_meter", "Generation Meter"],
  ["plant_photo", "Plant Photo"],
  ["customer_with_inverter", "Customer with Inverter"],
  ["la", "LA (Lightning Arrestor)"],
];

const inputCls =
  "w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all disabled:opacity-70 disabled:cursor-not-allowed";
const labelCls = "block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5";

type ProjDoc = { id: number; doc_type: string; file: string };

export default function ProjectSection({ leadId, canEdit, canReopen, lockedReason, onChanged }: {
  // `lockedReason` says why editing is off when it isn't simply about assignment
  // — an overdue project is locked to everyone but a super admin.
  leadId: number | string; canEdit: boolean; canReopen?: boolean;
  lockedReason?: string; onChanged?: () => void;
}) {
  const apiBase = getApiBase(APP_SLUG);
  const url = `${apiBase}/api/leads/${leadId}/project-record/`;
  const docsUrl = `${apiBase}/api/leads/${leadId}/project-record/documents/`;
  const authHeader = () => ({ Authorization: `Bearer ${localStorage.getItem(`${APP_SLUG}_access`)}` });

  const [f, setF] = useState<Record<string, string>>({
    structure_work_start_date: "", structure_work_completed_date: "",
    electrical_work_start_date: "", electrical_work_completed_date: "",
  });
  const [documents, setDocuments] = useState<ProjDoc[]>([]);
  const [uploadingType, setUploadingType] = useState<string | null>(null);
  const [isComplete, setIsComplete] = useState(false);
  const [completedByName, setCompletedByName] = useState<string | null>(null);
  const [completedAt, setCompletedAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [completing, setCompleting] = useState(false);
  const [saved, setSaved] = useState(false);

  const load = useCallback((d: any) => {
    setF({
      structure_work_start_date: d.structure_work_start_date || "",
      structure_work_completed_date: d.structure_work_completed_date || "",
      electrical_work_start_date: d.electrical_work_start_date || "",
      electrical_work_completed_date: d.electrical_work_completed_date || "",
    });
    setDocuments(Array.isArray(d.documents) ? d.documents : []);
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
  const set = (k: string, v: string) => { setF(p => ({ ...p, [k]: v })); setSaved(false); };

  const saveScalars = async (): Promise<any | null> => {
    // Dates must be null (not "") for DRF DateField.
    const body: Record<string, any> = {};
    for (const k of ["structure_work_start_date", "structure_work_completed_date", "electrical_work_start_date", "electrical_work_completed_date"]) {
      body[k] = f[k] ? f[k] : null;
    }
    const r = await fetch(url, { method: "PATCH", headers: { "Content-Type": "application/json", ...authHeader() }, body: JSON.stringify(body) });
    if (!r.ok) { const e = await r.json().catch(() => ({})); alert(e.error || "Failed to save project."); return null; }
    return r.json();
  };

  const save = async () => {
    setSaving(true);
    try { const latest = await saveScalars(); if (latest) { load(latest); setSaved(true); onChanged?.(); } }
    catch { alert("Network error while saving."); }
    finally { setSaving(false); }
  };

  const refetchDocs = async () => {
    try { const r = await fetch(url, { headers: authHeader() }); if (r.ok) { const d = await r.json(); setDocuments(Array.isArray(d.documents) ? d.documents : []); } } catch {}
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
      if (any) await refetchDocs();
    } catch { alert("Network error while uploading."); }
    finally { setUploadingType(null); }
  };

  const deleteDoc = async (docId: number) => {
    if (!window.confirm("Delete this photo? This can't be undone.")) return;
    try {
      const r = await fetch(`${docsUrl}${docId}/`, { method: "DELETE", headers: authHeader() });
      if (r.ok || r.status === 204) await refetchDocs();
      else { const e = await r.json().catch(() => ({})); alert(e.error || "Could not delete the photo."); }
    } catch { alert("Network error while deleting."); }
  };

  const complete = async () => {
    setCompleting(true);
    try {
      const latest = await saveScalars();
      if (!latest) return;
      const r = await fetch(`${apiBase}/api/leads/${leadId}/complete-project/`, { method: "POST", headers: authHeader() });
      if (r.ok) {
        const d = await r.json();
        if (d.project) load(d.project); else { load(latest); setIsComplete(true); }
        onChanged?.();
        alert("Project marked complete.");
      } else { const d = await r.json().catch(() => ({})); alert(d.error || "Could not complete project."); }
    } catch { alert("Network error while completing."); }
    finally { setCompleting(false); }
  };

  const reopen = async () => {
    if (!window.confirm("Reopen this completed project for editing?")) return;
    try {
      const r = await fetch(`${apiBase}/api/leads/${leadId}/reopen-project/`, { method: "POST", headers: authHeader() });
      if (r.ok) { const d = await r.json(); if (d.project) load(d.project); else setIsComplete(false); onChanged?.(); }
      else { const d = await r.json().catch(() => ({})); alert(d.error || "Could not reopen."); }
    } catch { alert("Network error while reopening."); }
  };

  const cardCls = "bg-white border border-slate-200 rounded-2xl shadow-sm p-5";
  const sectionTitle = "text-xs font-bold text-indigo-600 uppercase tracking-wide mb-3";

  if (loading) return <div className={`mt-5 ${cardCls} text-sm text-slate-400`}>Loading project…</div>;

  return (
    <div className="mt-5 space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-bold text-slate-900">Project / Installation</h2>
          <p className="text-xs text-slate-400 mt-0.5">Filled by the assigned project manager.</p>
        </div>
        {isComplete ? (
          <div className="flex items-center gap-3">
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-emerald-50 border border-emerald-200 text-emerald-700 rounded-lg text-xs font-semibold">
              ✓ Completed{completedByName ? ` by ${completedByName}` : ""}{completedAt ? ` · ${new Date(completedAt).toLocaleDateString("en-IN")}` : ""}
            </span>
            {canReopen && (
              <button onClick={reopen} className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-300 text-slate-700 rounded-lg text-xs font-semibold hover:bg-slate-50 transition">Reopen for editing</button>
            )}
          </div>
        ) : !canEdit ? (
          <span className="text-xs text-slate-400">{lockedReason || "Read-only — not assigned to you."}</span>
        ) : null}
      </div>

      {/* Work dates */}
      <div className={cardCls}>
        <div className="grid sm:grid-cols-2 gap-6">
          <div>
            <h3 className={sectionTitle}>Structure Work</h3>
            <div className="grid grid-cols-2 gap-3">
              <div><label className={labelCls}>Start Date</label><input type="date" value={f.structure_work_start_date} disabled={readOnly} onChange={e => set("structure_work_start_date", e.target.value)} className={inputCls} /></div>
              <div><label className={labelCls}>Completed Date</label><input type="date" value={f.structure_work_completed_date} disabled={readOnly} onChange={e => set("structure_work_completed_date", e.target.value)} className={inputCls} /></div>
            </div>
          </div>
          <div>
            <h3 className={sectionTitle}>Electrical Work</h3>
            <div className="grid grid-cols-2 gap-3">
              <div><label className={labelCls}>Start Date</label><input type="date" value={f.electrical_work_start_date} disabled={readOnly} onChange={e => set("electrical_work_start_date", e.target.value)} className={inputCls} /></div>
              <div><label className={labelCls}>Completed Date</label><input type="date" value={f.electrical_work_completed_date} disabled={readOnly} onChange={e => set("electrical_work_completed_date", e.target.value)} className={inputCls} /></div>
            </div>
          </div>
        </div>
      </div>

      {/* Geotagged site photos */}
      <div className={cardCls}>
        <h3 className={sectionTitle}>Installation Images — Geotagged Site Photos</h3>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-4">
          {PHOTO_SLOTS.map(([key, label]) => {
            const mine = documents.filter(d => d.doc_type === key);
            const busy = uploadingType === key;
            return (
              <div key={key}>
                <label className={labelCls}>{label}</label>
                {mine.length > 0 && (
                  <ul className="mb-2 space-y-1">
                    {mine.map(d => {
                      const href = d.file.startsWith("http") ? d.file : `${apiBase}${d.file}`;
                      const name = decodeURIComponent(d.file.split("/").pop() || "file");
                      return (
                        <li key={d.id} className="flex items-center gap-2 text-[11px]">
                          <a href={href} target="_blank" rel="noreferrer" className="font-semibold text-emerald-600 hover:underline truncate max-w-[150px]" title={name}>{name}</a>
                          {!readOnly && <button type="button" onClick={() => deleteDoc(d.id)} title="Delete photo" className="font-bold text-rose-500 hover:text-rose-700">✕</button>}
                        </li>
                      );
                    })}
                  </ul>
                )}
                <label className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-semibold transition ${(readOnly || busy) ? "bg-slate-100 text-slate-400 cursor-not-allowed" : "bg-slate-100 text-slate-700 hover:bg-slate-200 cursor-pointer"}`}>
                  {busy ? "Uploading…" : "+ Add photo(s)"}
                  <input type="file" accept="image/*,application/pdf" multiple disabled={readOnly || busy} className="hidden"
                    onChange={e => { const fs = Array.from(e.target.files || []); e.currentTarget.value = ""; addDocs(key, fs); }} />
                </label>
              </div>
            );
          })}
        </div>
      </div>

      {canEdit && !isComplete && (
        <div className="flex flex-wrap items-center gap-3">
          <button onClick={save} disabled={saving || completing} className="px-5 py-2.5 bg-slate-800 text-white rounded-xl text-sm font-semibold hover:bg-slate-900 disabled:opacity-50 transition">
            {saving ? "Saving…" : saved ? "Saved ✓" : "Save"}
          </button>
          <button onClick={complete} disabled={completing || saving} className="px-5 py-2.5 bg-emerald-600 text-white rounded-xl text-sm font-semibold hover:bg-emerald-700 disabled:opacity-50 transition">
            {completing ? "Completing…" : "Mark Complete"}
          </button>
        </div>
      )}
    </div>
  );
}

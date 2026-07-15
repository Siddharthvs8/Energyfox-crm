"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";
import React, { useCallback, useEffect, useState } from "react";

const WARRANTY_SLOT = "warranty";
const inputCls =
  "w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all disabled:opacity-70 disabled:cursor-not-allowed";
const labelCls = "block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5";
const cardCls = "bg-white border border-slate-200 rounded-2xl shadow-sm p-5";

type Doc = { id: number; doc_type: string; file: string };

export default function WarrantySection({ leadId, canEdit, phone, email, customerName, onChanged }: {
  leadId: number | string; canEdit: boolean; phone?: string | null; email?: string | null; customerName?: string; onChanged?: () => void;
}) {
  const apiBase = getApiBase(APP_SLUG);
  const url = `${apiBase}/api/leads/${leadId}/warranty-record/`;
  const docsUrl = `${apiBase}/api/leads/${leadId}/warranty/documents/`;
  const completeUrl = `${apiBase}/api/leads/${leadId}/complete-warranty/`;
  const authHeader = () => ({ Authorization: `Bearer ${localStorage.getItem(`${APP_SLUG}_access`)}` });

  const [sent, setSent] = useState(false);
  const [remark, setRemark] = useState("");
  const [documents, setDocuments] = useState<Doc[]>([]);
  const [isComplete, setIsComplete] = useState(false);
  const [completedByName, setCompletedByName] = useState<string | null>(null);
  const [completedAt, setCompletedAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [completing, setCompleting] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [saved, setSaved] = useState(false);

  const load = useCallback((d: any) => {
    setSent(!!d.sent);
    setRemark(d.remark || "");
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

  // WhatsApp needs a full international number; assume India (+91) for 10-digit numbers.
  const waNumber = (() => {
    const d = (phone || "").replace(/\D/g, "");
    if (!d) return "";
    return d.length === 10 ? `91${d}` : d;
  })();

  const markSent = () => { if (!readOnly && !sent) { setSent(true); setSaved(false); } };

  const sendWhatsApp = () => {
    if (!waNumber) { alert("No phone number on file for this customer."); return; }
    const msg = encodeURIComponent(`Hello${customerName ? " " + customerName : ""}, please find your solar system warranty details.`);
    window.open(`https://wa.me/${waNumber}?text=${msg}`, "_blank", "noopener");
    markSent();
  };

  const sendEmail = () => {
    if (!email) { alert("No email on file for this customer."); return; }
    const subject = encodeURIComponent("Solar System Warranty");
    const body = encodeURIComponent(`Dear ${customerName || "Customer"},\n\nPlease find your solar system warranty details.\n\nRegards,\nEnergyFox`);
    window.location.href = `mailto:${email}?subject=${subject}&body=${body}`;
    markSent();
  };

  const saveScalars = async (): Promise<any | null> => {
    const r = await fetch(url, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...authHeader() },
      body: JSON.stringify({ sent, remark }),
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

  const addDocs = async (fileList: File[]) => {
    if (!fileList.length) return;
    setUploading(true);
    try {
      let any = false;
      for (const file of fileList) {
        const fd = new FormData();
        fd.append("doc_type", WARRANTY_SLOT);
        fd.append("file", file);
        const r = await fetch(docsUrl, { method: "POST", headers: authHeader(), body: fd });
        if (r.ok) any = true;
        else { const e = await r.json().catch(() => ({})); alert(e.error || `Upload failed for ${file.name}.`); }
      }
      if (any) await refetch();
    } catch { alert("Network error while uploading."); }
    finally { setUploading(false); }
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
    if (!window.confirm("Mark warranty complete? This locks it.")) return;
    setCompleting(true);
    try {
      const latest = await saveScalars();
      if (!latest) return;
      const r = await fetch(completeUrl, { method: "POST", headers: authHeader() });
      if (r.ok) { await refetch(); onChanged?.(); alert("Warranty marked complete."); }
      else { const e = await r.json().catch(() => ({})); alert(e.error || "Could not complete."); }
    } catch { alert("Network error while completing."); }
    finally { setCompleting(false); }
  };

  if (loading) return <div className={`mt-5 ${cardCls} text-sm text-slate-400`}>Loading warranty…</div>;

  const warrantyDocs = documents.filter(d => d.doc_type === WARRANTY_SLOT);

  return (
    <div className="mt-5 space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-bold text-slate-900">Warranty</h2>
          <p className="text-xs text-slate-400 mt-0.5">Send the warranty to the customer via WhatsApp or email, and attach the document.</p>
        </div>
        {isComplete ? (
          <span className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-emerald-50 border border-emerald-200 text-emerald-700 rounded-lg text-xs font-semibold">
            ✓ Completed{completedByName ? ` by ${completedByName}` : ""}{completedAt ? ` · ${new Date(completedAt).toLocaleDateString("en-IN")}` : ""}
          </span>
        ) : !canEdit ? (
          <span className="text-xs text-slate-400">Read-only.</span>
        ) : null}
      </div>

      <div className={cardCls}>
        {/* Send */}
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" onClick={sendWhatsApp} disabled={!waNumber}
            title={waNumber ? `WhatsApp ${phone}` : "No phone number on file"}
            className="inline-flex items-center gap-2 px-4 py-2.5 bg-emerald-600 text-white rounded-xl text-sm font-semibold hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed transition">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M17.47 14.38c-.29-.15-1.71-.84-1.97-.94-.26-.1-.46-.15-.65.14-.19.29-.75.94-.92 1.13-.17.19-.34.21-.63.07-.29-.15-1.22-.45-2.33-1.44-.86-.77-1.44-1.72-1.61-2.01-.17-.29-.02-.44.13-.59.13-.13.29-.34.44-.51.15-.17.19-.29.29-.48.1-.19.05-.36-.02-.51-.07-.15-.65-1.57-.89-2.15-.24-.56-.48-.49-.65-.5-.17-.01-.36-.01-.56-.01-.19 0-.51.07-.78.36-.27.29-1.02 1-1.02 2.42 0 1.43 1.04 2.81 1.19 3 .15.19 2.05 3.13 4.97 4.39.69.3 1.23.48 1.65.61.69.22 1.32.19 1.82.12.56-.08 1.71-.7 1.95-1.37.24-.67.24-1.25.17-1.37-.07-.12-.26-.19-.55-.34z"/><path d="M20.52 3.44A11.86 11.86 0 0012.05 0C5.5 0 .18 5.31.17 11.85c0 2.09.55 4.13 1.59 5.93L0 24l6.38-1.67a11.87 11.87 0 005.67 1.44h.01c6.55 0 11.87-5.31 11.87-11.85 0-3.17-1.23-6.15-3.41-8.48zM12.06 21.2h-.01a9.86 9.86 0 01-5.02-1.37l-.36-.21-3.79.99 1.01-3.69-.23-.38a9.82 9.82 0 01-1.51-5.24c0-5.44 4.43-9.86 9.9-9.86 2.64 0 5.13 1.03 7 2.9a9.82 9.82 0 012.9 6.97c0 5.44-4.43 9.86-9.89 9.86z"/></svg>
            WhatsApp
          </button>
          <button type="button" onClick={sendEmail} disabled={!email}
            title={email ? `Email ${email}` : "No email on file"}
            className="inline-flex items-center gap-2 px-4 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition">
            <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>
            Email
          </button>
          {sent && <span className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-600">✓ Marked sent</span>}
        </div>
        {(!waNumber || !email) && (
          <p className="text-[11px] text-amber-600 mt-2">
            {!waNumber && "No phone number on file. "}{!email && "No email on file."}
          </p>
        )}

        {/* Warranty document */}
        <div className="mt-5">
          <label className={labelCls}>Warranty Document</label>
          {warrantyDocs.length > 0 && (
            <ul className="mb-2 space-y-1">
              {warrantyDocs.map(d => {
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
          <label className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-semibold transition ${(readOnly || uploading) ? "bg-slate-100 text-slate-400 cursor-not-allowed" : "bg-slate-100 text-slate-700 hover:bg-slate-200 cursor-pointer"}`}>
            {uploading ? "Uploading…" : "+ Add document(s)"}
            <input type="file" accept="image/*,application/pdf" multiple disabled={readOnly || uploading} className="hidden"
              onChange={e => { const fs = Array.from(e.target.files || []); e.currentTarget.value = ""; addDocs(fs); }} />
          </label>
        </div>

        {/* Remark */}
        <div className="mt-5 max-w-xl">
          <label className={labelCls}>Remark</label>
          <input value={remark} disabled={readOnly} onChange={e => { setRemark(e.target.value); setSaved(false); }} placeholder="Remark" className={inputCls} />
        </div>
      </div>

      {canEdit && !isComplete && (
        <div className="flex flex-wrap items-center gap-3">
          <button onClick={save} disabled={saving || completing || uploading}
            className="px-5 py-2.5 bg-slate-800 text-white rounded-xl text-sm font-semibold hover:bg-slate-900 disabled:opacity-50 transition">
            {saving ? "Saving…" : saved ? "Saved ✓" : "Save"}
          </button>
          <button onClick={complete} disabled={completing || saving || uploading}
            className="px-5 py-2.5 bg-emerald-600 text-white rounded-xl text-sm font-semibold hover:bg-emerald-700 disabled:opacity-50 transition">
            {completing ? "Completing…" : "Mark Complete"}
          </button>
        </div>
      )}
    </div>
  );
}

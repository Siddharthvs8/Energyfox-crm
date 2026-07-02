"use client";
import { APP_SLUG, KSEB_PORTAL_URL } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";
import { kindForSlot } from "@/lib/docKinds";
import React, { useCallback, useContext, useEffect, useState, createContext } from "react";

/* ── Slot definitions (key = DocumentationStage1Document.doc_type) ── */
const NC_FILES = [
  ["nc_ownership", "Ownership"],
  ["nc_building_certificate", "Building Certificate"],
  ["nc_landtax", "Land Tax"],
  ["nc_customer_photo", "Customer Photo"],
  ["nc_aadhaar", "Aadhaar"],
  ["nc_kseb_bill", "KSEB Bill"],
] as const;

const LE_FILES = [["le_aadhaar", "Aadhaar"]] as const;
const LE_CHECKS = [
  ["le_test_cum_completion_report", "Test cum Completion Report"],
  ["le_sketch", "Sketch"],
] as const;

// KYC (Know Your Customer) = aadhaar + pan + passbook (grouped under one label).
const MNRE_KYC = [
  ["mnre_aadhaar", "Aadhaar"],
  ["mnre_pan", "PAN"],
  ["mnre_passbook", "Passbook"],
] as const;
const MNRE_FILES = [["mnre_kseb_bill", "KSEB Bill"]] as const;
const MNRE_PDF: readonly [string, string] = ["mnre_purchase_order", "Purchase Order"];

const LOAN_KYC = [
  ["loan_aadhaar", "Aadhaar"],
  ["loan_pan", "PAN"],
  ["loan_passbook", "Passbook"],
] as const;
const LOAN_FILES = [
  ["loan_land_tax", "Land Tax"],
  ["loan_passbook_copy", "Passbook Copy"],
] as const;
// ITR is only shown/required when "Loan above ₹2 lakh" is ticked.
const LOAN_ITR: readonly [string, string] = ["loan_itr", "ITR"];
const LOAN_PDF: readonly [string, string] = ["loan_agreement_purchase_order", "Agreement / Purchase Order"];

// Non-file inputs → saved via JSON PATCH.
const BOOL_KEYS = ["le_test_cum_completion_report", "le_sketch", "loan_above_2_lakh"] as const;
const TEXT_KEYS = ["mnre_plant_capacity"] as const;

// Mandatory MNRE doc_type slots (each needs ≥1 file) — mirrors the server.
const MNRE_REQUIRED_DOC_TYPES = [...MNRE_KYC.map(f => f[0]), ...MNRE_FILES.map(f => f[0]), MNRE_PDF[0]];

const inputCls =
  "w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all";
const labelCls = "block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5";
// Styled "add files" button (a label wrapping a hidden input) — avoids the native
// "No file chosen" text, which is misleading here since files upload immediately.
const addBtnCls = (disabled: boolean) =>
  `inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-semibold transition ${disabled ? "bg-slate-100 text-slate-400 cursor-not-allowed" : "bg-slate-100 text-slate-700 hover:bg-slate-200 cursor-pointer"}`;

// `shared` docs live in the lead-level pool (inherited across stages); they're
// deleted via a different endpoint and appear under every same-kind slot.
type DS1Doc = { id: number; doc_type: string; file: string; shared?: boolean; kind?: string };

const IMAGE_RE = /\.(jpe?g|png|webp|gif|bmp)$/i;
const isImage = (f: File) => f.type.startsWith("image/") || IMAGE_RE.test(f.name);

/* ── jsPDF: stitch dropped images into one PDF File ── */
async function generatePdfFromImages(images: File[], fileName: string): Promise<File> {
  const { jsPDF } = await import("jspdf");
  const doc = new jsPDF({ unit: "pt", format: "a4" });
  const pageW = doc.internal.pageSize.getWidth();
  const pageH = doc.internal.pageSize.getHeight();
  for (let i = 0; i < images.length; i++) {
    const dataUrl: string = await new Promise((res, rej) => {
      const fr = new FileReader();
      fr.onload = () => res(fr.result as string);
      fr.onerror = rej;
      fr.readAsDataURL(images[i]);
    });
    const dims: { w: number; h: number } = await new Promise((res, rej) => {
      const im = new Image();
      im.onload = () => res({ w: im.naturalWidth, h: im.naturalHeight });
      im.onerror = rej;
      im.src = dataUrl;
    });
    const ratio = Math.min(pageW / dims.w, pageH / dims.h);
    const w = dims.w * ratio;
    const h = dims.h * ratio;
    if (i > 0) doc.addPage();
    const fmt = dataUrl.startsWith("data:image/png") ? "PNG" : "JPEG";
    doc.addImage(dataUrl, fmt, (pageW - w) / 2, (pageH - h) / 2, w, h);
  }
  return new File([doc.output("blob")], fileName, { type: "application/pdf" });
}

/* ── Shared state for the slot renderers (module-level → stable identity) ── */
type DS1Ctx = {
  documents: DS1Doc[];
  disabled: boolean;
  apiBase: string;
  addDocs: (docType: string, files: File[]) => Promise<void>;
  deleteDoc: (doc: DS1Doc) => void;
  uploadingType: string | null;
};
const Ctx = createContext<DS1Ctx | null>(null);
const useDS1 = () => {
  const c = useContext(Ctx);
  if (!c) throw new Error("DS1 context not provided");
  return c;
};

function DocList({ docType }: { docType: string }) {
  const { documents, apiBase, disabled, deleteDoc } = useDS1();
  const mine = documents.filter(d => d.doc_type === docType);
  if (!mine.length) return null;
  return (
    <ul className="mb-2 space-y-1">
      {mine.map(d => {
        const href = d.file.startsWith("http") ? d.file : `${apiBase}${d.file}`;
        const name = decodeURIComponent(d.file.split("/").pop() || "file");
        return (
          <li key={d.id} className="flex items-center gap-2 text-[11px]">
            <a href={href} target="_blank" rel="noreferrer" className="font-semibold text-emerald-600 hover:underline truncate max-w-[150px]" title={name}>{name}</a>
            {!disabled && <button type="button" onClick={() => deleteDoc(d)} title="Delete file" className="font-bold text-rose-500 hover:text-rose-700">✕</button>}
          </li>
        );
      })}
    </ul>
  );
}

/* One slot — lists files (each deletable) + an input to add more (multiple). */
function MultiFileField({ docType, label }: { docType: string; label: string }) {
  const { disabled, addDocs, uploadingType } = useDS1();
  const busy = uploadingType === docType;
  return (
    <div>
      <label className={labelCls}>{label}</label>
      <DocList docType={docType} />
      <label className={addBtnCls(disabled || busy)}>
        {busy ? "Uploading…" : "+ Add file(s)"}
        <input type="file" accept="image/*,application/pdf" multiple disabled={disabled || busy} className="hidden"
          onChange={e => { const fs = Array.from(e.target.files || []); e.currentTarget.value = ""; addDocs(docType, fs); }} />
      </label>
    </div>
  );
}

function CheckRow({ label, checked, onChange, disabled }: {
  label: string; checked: boolean; disabled: boolean; onChange: (v: boolean) => void;
}) {
  return (
    <label className={`flex items-center gap-2 text-sm font-medium ${disabled ? "text-slate-400 cursor-default" : "text-slate-700 cursor-pointer"}`}>
      <input type="checkbox" checked={checked} disabled={disabled} onChange={e => onChange(e.target.checked)}
        className="w-4 h-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500/30 disabled:opacity-60" />
      {label}
    </label>
  );
}

/* PDF slot — multiple files; attach PDFs/images directly OR drop images → generate one PDF. */
function PdfMultiField({ docType, label }: { docType: string; label: string }) {
  const { disabled, addDocs, uploadingType } = useDS1();
  const busy = uploadingType === docType;
  const [images, setImages] = useState<File[]>([]);
  const [generating, setGenerating] = useState(false);
  const [dragActive, setDragActive] = useState(false);

  const addImages = (list: FileList | File[] | null) => {
    if (!list) return;
    const imgs = Array.from(list).filter(isImage);
    if (imgs.length) setImages(prev => [...prev, ...imgs]);
    else if (Array.from(list).length) alert("Please drop image files (JPG/PNG) here — use “Attach PDF / file(s)” for PDFs.");
  };
  const generate = async () => {
    if (!images.length) return;
    setGenerating(true);
    try {
      const pdf = await generatePdfFromImages(images, `${docType}.pdf`);
      await addDocs(docType, [pdf]);
      setImages([]);
    } catch { alert("Could not generate the PDF from those images."); }
    finally { setGenerating(false); }
  };

  return (
    <div className="sm:col-span-2 lg:col-span-3 border border-slate-200 rounded-xl p-4 bg-slate-50/60">
      <label className={labelCls}>{label}</label>
      <DocList docType={docType} />
      <div className="grid sm:grid-cols-2 gap-3">
        <div>
          <p className="text-[10px] text-slate-400 mb-1">Attach PDF / file(s)</p>
          <label className={addBtnCls(disabled || busy)}>
            {busy ? "Uploading…" : "+ Add file(s)"}
            <input type="file" accept="application/pdf,image/*" multiple disabled={disabled || busy} className="hidden"
              onChange={e => { const fs = Array.from(e.target.files || []); e.currentTarget.value = ""; addDocs(docType, fs); }} />
          </label>
        </div>
        <div>
          <p className="text-[10px] text-slate-400 mb-1">Or drop images → generate PDF</p>
          <div
            onDragEnter={e => { if (disabled) return; e.preventDefault(); e.stopPropagation(); setDragActive(true); }}
            onDragOver={e => { if (disabled) return; e.preventDefault(); e.stopPropagation(); e.dataTransfer.dropEffect = "copy"; setDragActive(true); }}
            onDragLeave={e => { if (disabled) return; e.preventDefault(); e.stopPropagation(); setDragActive(false); }}
            onDrop={e => { if (disabled) return; e.preventDefault(); e.stopPropagation(); setDragActive(false); addImages(e.dataTransfer.files); }}
            className={`rounded-lg border-2 border-dashed px-3 py-4 min-h-[180px] flex flex-col items-center justify-center text-center text-[11px] transition-colors ${disabled ? "border-slate-200 text-slate-300" : dragActive ? "border-indigo-400 bg-indigo-50 text-indigo-600" : "border-slate-300 text-slate-500"}`}
          >
            <label className={disabled ? "cursor-default" : "cursor-pointer text-indigo-600 font-semibold"}>
              Drag &amp; drop images or <span className="underline">browse</span>
              <input type="file" accept="image/*" multiple disabled={disabled} className="hidden"
                onChange={e => { addImages(e.target.files); e.currentTarget.value = ""; }} />
            </label>
            {images.length > 0 && <p className="mt-1 text-slate-600">{images.length} image(s) ready</p>}
          </div>
          {images.length > 0 && !disabled && (
            <button type="button" onClick={generate} disabled={generating || busy}
              className="mt-2 px-3 py-1.5 bg-indigo-600 text-white rounded-lg text-[11px] font-semibold hover:bg-indigo-700 disabled:opacity-50">
              {generating ? "Generating…" : `Generate PDF (${images.length})`}
            </button>
          )}
        </div>
      </div>
      {busy && <span className="text-[10px] font-semibold text-indigo-600">Uploading…</span>}
    </div>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <h3 className="text-xs font-bold text-indigo-600 uppercase tracking-wide mb-3">{children}</h3>;
}

/* KYC (Know Your Customer) = Aadhaar + PAN + Passbook, grouped under one label. */
function KycGroup({ fields }: { fields: readonly (readonly [string, string])[] }) {
  return (
    <div className="sm:col-span-2 lg:col-span-3 border border-slate-200 rounded-xl p-4 bg-slate-50/60">
      <label className={labelCls}>KYC — Know Your Customer</label>
      <p className="text-[10px] text-slate-400 mb-3">Aadhaar, PAN &amp; Passbook</p>
      <div className="grid sm:grid-cols-3 gap-4">
        {fields.map(([k, lbl]) => <MultiFileField key={k} docType={k} label={lbl} />)}
      </div>
    </div>
  );
}

function KsebButton() {
  return (
    <a href={KSEB_PORTAL_URL} target="_blank" rel="noreferrer"
      className="inline-flex items-center gap-1.5 px-3 py-1.5 mb-3 bg-amber-50 border border-amber-200 text-amber-700 rounded-lg text-xs font-semibold hover:bg-amber-100 transition">
      KSEB website
      <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6" /><path d="M15 3h6v6" /><path d="M10 14L21 3" /></svg>
    </a>
  );
}

/* ── Main component ── */
type SiteVisit = Record<string, any> | null;

export default function DocumentationStage1Section({ leadId, canEdit, canReopen, siteVisit, onChanged }: {
  leadId: number | string; canEdit: boolean; canReopen?: boolean; siteVisit: SiteVisit; onChanged?: () => void;
}) {
  const apiBase = getApiBase(APP_SLUG);
  const url = `${apiBase}/api/leads/${leadId}/documentation-stage1/`;
  const docsUrl = `${apiBase}/api/leads/${leadId}/documentation-stage1/documents/`;
  const authHeader = () => ({ Authorization: `Bearer ${localStorage.getItem(`${APP_SLUG}_access`)}` });

  const [bools, setBools] = useState<Record<string, boolean>>({});
  const [texts, setTexts] = useState<Record<string, string>>({});
  const [documents, setDocuments] = useState<DS1Doc[]>([]);
  const [uploadingType, setUploadingType] = useState<string | null>(null);
  const [isComplete, setIsComplete] = useState(false);
  const [completedByName, setCompletedByName] = useState<string | null>(null);
  const [completedAt, setCompletedAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [completing, setCompleting] = useState(false);
  const [saved, setSaved] = useState(false);

  const load = useCallback((d: any) => {
    setBools(Object.fromEntries(BOOL_KEYS.map(k => [k, !!d[k]])));
    setTexts(Object.fromEntries(TEXT_KEYS.map(k => [k, d[k] ?? ""])));
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

  // Stop the browser from opening/navigating to a file dropped outside a drop zone
  // (the zones themselves stopPropagation, so their drops still work).
  useEffect(() => {
    const prevent = (e: DragEvent) => e.preventDefault();
    window.addEventListener("dragover", prevent);
    window.addEventListener("drop", prevent);
    return () => {
      window.removeEventListener("dragover", prevent);
      window.removeEventListener("drop", prevent);
    };
  }, []);

  const readOnly = !canEdit || isComplete;
  const setBool = (k: string, v: boolean) => { setBools(p => ({ ...p, [k]: v })); setSaved(false); };
  const setText = (k: string, v: string) => { setTexts(p => ({ ...p, [k]: v })); setSaved(false); };

  // Re-pull just the document list so shared documents re-merge across every
  // same-kind slot — without clobbering unsaved checkbox / plant-capacity edits.
  const refetchDocs = async () => {
    try {
      const r = await fetch(url, { headers: authHeader() });
      if (r.ok) { const d = await r.json(); setDocuments(Array.isArray(d.documents) ? d.documents : []); onChanged?.(); }
    } catch { /* keep current state */ }
  };

  // Files upload/delete immediately (separate from the scalar "Save").
  // Shared customer documents (Aadhaar/PAN/…) go to the lead-level pool so they're
  // inherited across stages; stage-local slots (PDFs) use the Stage-1 endpoint.
  const addDocs = async (docType: string, fileList: File[]) => {
    if (!fileList.length) return;
    const kind = kindForSlot(docType);
    const endpoint = kind ? `${apiBase}/api/leads/${leadId}/shared-documents/` : docsUrl;
    setUploadingType(docType);
    try {
      let any = false;
      for (const file of fileList) {
        const fd = new FormData();
        if (kind) fd.append("kind", kind); else fd.append("doc_type", docType);
        fd.append("file", file);
        const r = await fetch(endpoint, { method: "POST", headers: authHeader(), body: fd });
        if (r.ok) any = true;
        else { const e = await r.json().catch(() => ({})); alert(e.error || `Upload failed for ${file.name}.`); }
      }
      if (any) await refetchDocs();
    } catch { alert("Network error while uploading."); }
    finally { setUploadingType(null); }
  };

  const deleteDoc = async (doc: DS1Doc) => {
    if (!window.confirm("Delete this file? This can't be undone.")) return;
    const endpoint = doc.shared
      ? `${apiBase}/api/leads/${leadId}/shared-documents/${doc.id}/`
      : `${docsUrl}${doc.id}/`;
    try {
      const r = await fetch(endpoint, { method: "DELETE", headers: authHeader() });
      if (r.ok || r.status === 204) await refetchDocs();
      else { const e = await r.json().catch(() => ({})); alert(e.error || "Could not delete the file."); }
    } catch { alert("Network error while deleting."); }
  };

  // Persist the non-file inputs (checkboxes + plant capacity).
  const saveScalars = async (): Promise<any | null> => {
    const r = await fetch(url, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...authHeader() },
      body: JSON.stringify({ ...bools, ...texts }),
    });
    if (!r.ok) { alert("Failed to save documentation details."); return null; }
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

  const hasDoc = (dt: string) => documents.some(d => d.doc_type === dt);
  const mnreReady = MNRE_REQUIRED_DOC_TYPES.every(hasDoc) && !!(texts["mnre_plant_capacity"] || "").trim();

  const complete = async () => {
    if (!mnreReady) { alert("Fill the mandatory For-MNRE section (all documents + plant capacity) before completing."); return; }
    setCompleting(true);
    try {
      const latest = await saveScalars(); // persist plant capacity / checkboxes first
      if (!latest) return;
      const r = await fetch(`${apiBase}/api/leads/${leadId}/complete-documentation-stage1/`, {
        method: "POST", headers: authHeader(),
      });
      if (r.ok) {
        const d = await r.json();
        if (d.documentation_stage1) load(d.documentation_stage1);
        else { load(latest); setIsComplete(true); }
        onChanged?.();
        alert("Documentation Stage 1 completed. A summary note was added to the lead history.");
      } else {
        const d = await r.json().catch(() => ({}));
        alert(d.error || "Could not complete Stage 1.");
      }
    } catch { alert("Network error while completing."); }
    finally { setCompleting(false); }
  };

  // Documentation manager re-opens a completed Stage 1 for further editing.
  const reopen = async () => {
    if (!window.confirm("Reopen this completed documentation for editing?")) return;
    try {
      const r = await fetch(`${apiBase}/api/leads/${leadId}/reopen-documentation-stage1/`, {
        method: "POST", headers: authHeader(),
      });
      if (r.ok) {
        const d = await r.json();
        if (d.documentation_stage1) load(d.documentation_stage1);
        else setIsComplete(false);
        onChanged?.();
      } else {
        const d = await r.json().catch(() => ({}));
        alert(d.error || "Could not reopen.");
      }
    } catch { alert("Network error while reopening."); }
  };

  const showNameChange = siteVisit?.name_change === "yes";
  const showLoadEnhancement = siteVisit?.load_enhancement === "yes";
  const showLoan = siteVisit?.loan === "yes";

  const cardCls = "bg-white border border-slate-200 rounded-2xl shadow-sm p-5";
  const gridCls = "grid sm:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-4";

  if (loading) {
    return <div className="mt-5 bg-white border border-slate-200 rounded-2xl shadow-sm p-5 text-sm text-slate-400">Loading documentation…</div>;
  }

  const ctx: DS1Ctx = { documents, disabled: readOnly, apiBase, addDocs, deleteDoc, uploadingType };

  return (
    <Ctx.Provider value={ctx}>
    <div className="mt-5 space-y-5">
      {/* Header / status */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-bold text-slate-900">Documentation Stage 1</h2>
          <p className="text-xs text-slate-400 mt-0.5">Filled by the assigned documentation staff. Each slot accepts multiple files.</p>
        </div>
        {isComplete ? (
          <div className="flex items-center gap-3">
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-emerald-50 border border-emerald-200 text-emerald-700 rounded-lg text-xs font-semibold">
              ✓ Completed{completedByName ? ` by ${completedByName}` : ""}{completedAt ? ` · ${new Date(completedAt).toLocaleDateString("en-IN")}` : ""}
            </span>
            {canReopen && (
              <button onClick={reopen}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-300 text-slate-700 rounded-lg text-xs font-semibold hover:bg-slate-50 transition">
                <svg width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><path d="M12 20h9" /><path d="M16.5 3.5a2.12 2.12 0 013 3L7 19l-4 1 1-4z" /></svg>
                Reopen for editing
              </button>
            )}
          </div>
        ) : !canEdit ? (
          <span className="text-xs text-slate-400">Read-only — not assigned to you.</span>
        ) : null}
      </div>

      {/* Name Change — only if site visit name_change == yes */}
      {showNameChange && (
        <div className={cardCls}>
          <SectionTitle>Name Change</SectionTitle>
          <KsebButton />
          <div className={gridCls}>
            {NC_FILES.map(([k, lbl]) => <MultiFileField key={k} docType={k} label={lbl} />)}
          </div>
        </div>
      )}

      {/* Load Enhancement — only if site visit load_enhancement == yes */}
      {showLoadEnhancement && (
        <div className={cardCls}>
          <SectionTitle>Load Enhancement</SectionTitle>
          <KsebButton />
          <div className={gridCls}>
            {LE_FILES.map(([k, lbl]) => <MultiFileField key={k} docType={k} label={lbl} />)}
            <div className="flex flex-col gap-3 justify-center">
              {LE_CHECKS.map(([k, lbl]) => (
                <CheckRow key={k} label={lbl} checked={!!bools[k]} disabled={readOnly} onChange={v => setBool(k, v)} />
              ))}
            </div>
          </div>
        </div>
      )}

      {/* For MNRE — always shown, mandatory */}
      <div className={cardCls}>
        <SectionTitle>For MNRE <span className="text-rose-500 normal-case">(mandatory)</span></SectionTitle>
        <div className={gridCls}>
          <KycGroup fields={MNRE_KYC} />
          {MNRE_FILES.map(([k, lbl]) => <MultiFileField key={k} docType={k} label={lbl} />)}
          <div>
            <label className={labelCls}>Plant Capacity</label>
            <input value={texts["mnre_plant_capacity"] || ""} disabled={readOnly} placeholder="e.g. 5 kW"
              onChange={e => setText("mnre_plant_capacity", e.target.value)}
              className={`${inputCls} disabled:opacity-70 disabled:cursor-not-allowed`} />
          </div>
          <PdfMultiField docType={MNRE_PDF[0]} label={MNRE_PDF[1]} />
        </div>
      </div>

      {/* For Loan — only if loan == yes */}
      {showLoan && (
        <div className={cardCls}>
          <SectionTitle>For Loan</SectionTitle>
          <div className={gridCls}>
            <KycGroup fields={LOAN_KYC} />
            {LOAN_FILES.map(([k, lbl]) => <MultiFileField key={k} docType={k} label={lbl} />)}
            <div className="sm:col-span-2 lg:col-span-3">
              <CheckRow label="Loan above ₹2 lakh" checked={!!bools["loan_above_2_lakh"]} disabled={readOnly} onChange={v => setBool("loan_above_2_lakh", v)} />
              {bools["loan_above_2_lakh"] && <p className="text-[10px] text-slate-400 mt-1">ITR is required for loans above ₹2 lakh.</p>}
            </div>
            {bools["loan_above_2_lakh"] && <MultiFileField docType={LOAN_ITR[0]} label={LOAN_ITR[1]} />}
            <PdfMultiField docType={LOAN_PDF[0]} label={LOAN_PDF[1]} />
          </div>
        </div>
      )}

      {/* Actions */}
      {canEdit && !isComplete && (
        <div className="flex flex-wrap items-center gap-3">
          <button onClick={save} disabled={saving || completing}
            className="px-5 py-2.5 bg-slate-800 text-white rounded-xl text-sm font-semibold hover:bg-slate-900 disabled:opacity-50 transition">
            {saving ? "Saving…" : saved ? "Saved ✓" : "Save"}
          </button>
          <button onClick={complete} disabled={completing || saving || !mnreReady} title={!mnreReady ? "Complete the mandatory For-MNRE section first" : ""}
            className="px-5 py-2.5 bg-emerald-600 text-white rounded-xl text-sm font-semibold hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed transition">
            {completing ? "Completing…" : "Documentation Stage 1 completed"}
          </button>
          {!mnreReady && <span className="text-xs text-slate-400">Add all For-MNRE documents + plant capacity to enable completion.</span>}
        </div>
      )}
    </div>
    </Ctx.Provider>
  );
}

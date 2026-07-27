"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";
import { kindForSlot } from "@/lib/docKinds";
import PdfDropField from "@/components/PdfDropField";
import Link from "next/link";
import React, { useEffect, useState, createContext, useContext } from "react";

// Scalar (text/choice) fields — saved via a JSON PATCH.
const TEXT_KEYS = [
  "roof_type", "connection_type", "connected_load", "consumer_number", "phase",
  "building_height", "panel_to_inverter_distance", "kseb_section",
  "feasible_capacity", "plant_capacity", "transformer_feasibility", "neutral_link", "roof_access",
  "parapet_height", "structure_type", "custom_structure_height", "cable_panel_to_dc_db",
  "cable_inverter_to_ac_db", "earthing_cable_length", "lightning_conductor_length",
  "earthing_surface", "anchoring_allowed",
  "name_change", "loan", "loan_amount", "load_enhancement", "email_linked_to_itr",
  "po_signed_date",
] as const;

// An ITR report is only required for loans above this amount.
const ITR_REQUIRED_ABOVE = 200000;

type TextKey = typeof TEXT_KEYS[number];
type Form = Record<TextKey, string> & { rcc_roof_types: string[] };

const EMPTY = {
  ...Object.fromEntries(TEXT_KEYS.map(k => [k, ""])),
  rcc_roof_types: [] as string[],
} as unknown as Form;

const RCC_SUBTYPES = [
  { value: "flat", label: "Flat" }, { value: "slope", label: "Slope" },
  { value: "tiled", label: "Tiled" }, { value: "non_linear", label: "Non linear" },
];

// Site-visit photo slots. Each `key` is a SiteVisitDocument.doc_type that can hold
// multiple uploaded files. (Customer-document slots are rendered explicitly below,
// some of them gated by the Name Change / Loan yes-no flags.)
const PHOTO_FIELDS = [
  { key: "photo_meterbox", label: "Meter Box" },
  { key: "photo_earthing_1", label: "Earthing 1" },
  { key: "photo_earthing_2", label: "Earthing 2" },
  { key: "photo_earthing_3", label: "Earthing 3" },
  { key: "photo_directional", label: "Directional" },
  { key: "photo_hand_sketch", label: "Hand Sketch" },
  { key: "photo_feasibility_report", label: "Site Feasibility Report" },
];
const inputCls =
  "w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all";
const labelCls = "block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5";

// Field renderers live at module scope (stable component identity) and read shared
// form state from context. Defining them inside the component instead would give them
// a new identity on every keystroke, so React would remount the whole form — stealing
// input focus and scrolling the page back to this section. See SiteVisitCtx.Provider below.
// `shared` docs live in the lead-level pool (inherited across stages); they're
// deleted via a different endpoint and appear under every same-kind slot.
type SVDoc = { id: number; doc_type: string; file: string; uploaded_at?: string; shared?: boolean; kind?: string };
type SVCtx = {
  form: Form;
  set: (k: TextKey, v: string) => void;
  canEdit: boolean;
  documents: SVDoc[];
  addDocs: (docType: string, files: File[]) => void;
  deleteDoc: (doc: SVDoc) => void;
  uploadingType: string | null;
  apiBase: string;
};
const SiteVisitCtx = createContext<SVCtx | null>(null);
const useSV = () => {
  const c = useContext(SiteVisitCtx);
  if (!c) throw new Error("SiteVisitCtx not provided");
  return c;
};

function Text({ k, label, placeholder }: { k: TextKey; label: string; placeholder?: string }) {
  const { form, set, canEdit } = useSV();
  return (
    <div>
      <label className={labelCls}>{label}</label>
      <input value={form[k]} onChange={e => set(k, e.target.value)} placeholder={placeholder} disabled={!canEdit} className={`${inputCls} disabled:opacity-70 disabled:cursor-not-allowed`} />
    </div>
  );
}

function Select({ k, label, options }: { k: TextKey; label: string; options: { value: string; label: string }[] }) {
  const { form, set, canEdit } = useSV();
  return (
    <div>
      <label className={labelCls}>{label}</label>
      <select value={form[k]} onChange={e => set(k, e.target.value)} disabled={!canEdit} className={`${inputCls} disabled:opacity-70 disabled:cursor-not-allowed`}>
        <option value="">—</option>
        {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </div>
  );
}

function YesNo({ k, label }: { k: TextKey; label: string }) {
  return <Select k={k} label={label} options={[{ value: "yes", label: "Yes" }, { value: "no", label: "No" }]} />;
}

// One document/photo slot — lists every file uploaded for this doc_type (each with a
// delete control) and lets the BDE add more (multiple files allowed). Uploads/deletes
// happen immediately via the SiteVisitDocument endpoints.
/* The uploaded-file list for a slot, shared by the plain and PDF slot renderers. */
function SVDocList({ docType }: { docType: string }) {
  const { documents, canEdit, apiBase, deleteDoc } = useSV();
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
            {canEdit && <button type="button" onClick={() => deleteDoc(d)} title="Delete file" className="font-bold text-rose-500 hover:text-rose-700">✕</button>}
          </li>
        );
      })}
    </ul>
  );
}

/* PDF slot — attach PDFs/files directly, or drop images to generate one PDF. */
function PdfMultiField({ docType, label }: { docType: string; label: string }) {
  const { canEdit, addDocs, uploadingType } = useSV();
  return (
    <PdfDropField docType={docType} label={label} disabled={!canEdit}
      busy={uploadingType === docType} addFiles={addDocs}>
      <SVDocList docType={docType} />
    </PdfDropField>
  );
}

function MultiFileField({ docType, label }: { docType: string; label: string }) {
  const { documents, canEdit, apiBase, addDocs, deleteDoc, uploadingType } = useSV();
  const mine = documents.filter(d => d.doc_type === docType);
  const busy = uploadingType === docType;
  return (
    <div>
      <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1.5">{label}</label>
      {mine.length > 0 && (
        <ul className="mb-2 space-y-1">
          {mine.map(d => {
            const href = d.file.startsWith("http") ? d.file : `${apiBase}${d.file}`;
            const name = decodeURIComponent(d.file.split("/").pop() || "file");
            return (
              <li key={d.id} className="flex items-center gap-2 text-[11px]">
                <a href={href} target="_blank" rel="noreferrer" className="font-semibold text-emerald-600 hover:underline truncate max-w-[150px]" title={name}>{name}</a>
                {canEdit && <button type="button" onClick={() => deleteDoc(d)} title="Delete file" className="font-bold text-rose-500 hover:text-rose-700">✕</button>}
              </li>
            );
          })}
        </ul>
      )}
      <label className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-semibold transition ${(!canEdit || busy) ? "bg-slate-100 text-slate-400 cursor-not-allowed" : "bg-slate-100 text-slate-700 hover:bg-slate-200 cursor-pointer"}`}>
        {busy ? "Uploading…" : "+ Add file(s)"}
        <input type="file" accept="image/*,application/pdf" multiple disabled={!canEdit || busy} className="hidden"
          onChange={e => { const fs = Array.from(e.target.files || []); e.currentTarget.value = ""; addDocs(docType, fs); }} />
      </label>
    </div>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <h3 className="text-xs font-bold text-indigo-600 uppercase tracking-wide mt-2 mb-1 sm:col-span-2 lg:col-span-3">{children}</h3>;
}

export default function SiteVisitSection({ leadId, canEdit = true, onSaved }: { leadId: string; canEdit?: boolean; onSaved?: () => void }) {
  const [form, setForm] = useState<Form>(EMPTY);
  const [siteVisitComplete, setSiteVisitComplete] = useState(false);
  const [dealValue, setDealValue] = useState("");  // lead.value — entered by the BDE here
  const [documents, setDocuments] = useState<SVDoc[]>([]);
  const [uploadingType, setUploadingType] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  // Set once the PO date has just been saved — sends the BDE to KSEB Feasibility.
  const [poPrompt, setPoPrompt] = useState(false);

  const apiBase = getApiBase(APP_SLUG);
  const url = `${apiBase}/api/leads/${leadId}/site-visit/`;
  const authHeader = () => ({ Authorization: `Bearer ${localStorage.getItem(`${APP_SLUG}_access`)}` });

  const load = (d: any) => {
    setForm({
      ...EMPTY,
      ...Object.fromEntries(TEXT_KEYS.map(k => [k, d[k] ?? ""])),
      rcc_roof_types: d.rcc_roof_types || [],
    } as Form);
    setSiteVisitComplete(!!d.site_visit_complete);
    setDealValue(d.deal_value != null ? String(d.deal_value) : "");
    setDocuments(Array.isArray(d.documents) ? d.documents : []);
  };

  useEffect(() => {
    if (!localStorage.getItem(`${APP_SLUG}_access`)) { setLoading(false); return; }
    fetch(url, { headers: authHeader() })
      .then(r => (r.ok ? r.json() : null))
      .then(d => { if (d) load(d); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [leadId]);

  // Arriving from the Leads list's "Site Visit" button (/leads/<id>#site-visit).
  // Next.js can't honour the hash itself — this section mounts empty and grows once
  // its data lands — so scroll here after loading, then again when the page above
  // has settled its own height.
  useEffect(() => {
    if (loading || typeof window === "undefined") return;
    if (window.location.hash !== "#site-visit") return;
    const scroll = () => document.getElementById("site-visit")
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
    const raf = requestAnimationFrame(scroll);
    const t = setTimeout(scroll, 600);
    return () => { cancelAnimationFrame(raf); clearTimeout(t); };
  }, [loading]);

  const set = (k: TextKey, v: string) => { setForm(p => ({ ...p, [k]: v })); setSaved(false); };
  const toggleRcc = (v: string) => {
    setForm(p => ({ ...p, rcc_roof_types: p.rcc_roof_types.includes(v) ? p.rcc_roof_types.filter(x => x !== v) : [...p.rcc_roof_types, v] }));
    setSaved(false);
  };
  // Re-pull just the document list so shared documents re-merge across every
  // same-kind slot — without clobbering unsaved text/choice edits in the form.
  const refetch = async () => {
    try {
      const r = await fetch(url, { headers: authHeader() });
      if (r.ok) { const d = await r.json(); setDocuments(Array.isArray(d.documents) ? d.documents : []); }
    } catch { /* keep current state */ }
  };

  // Documents upload/delete immediately (separate from the scalar "Save" below).
  // Shared customer documents (Aadhaar/PAN/…) go to the lead-level pool so they're
  // inherited by later stages; stage-local slots (photos) use the site-visit endpoint.
  const addDocs = async (docType: string, fileList: File[]) => {
    if (!fileList.length) return;
    const kind = kindForSlot(docType);
    const endpoint = kind
      ? `${apiBase}/api/leads/${leadId}/shared-documents/`
      : `${apiBase}/api/leads/${leadId}/site-visit/documents/`;
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
      if (any) await refetch();
    } catch { alert("Network error while uploading."); }
    finally { setUploadingType(null); }
  };

  const deleteDoc = async (doc: SVDoc) => {
    if (!window.confirm("Delete this file? This can't be undone.")) return;
    const endpoint = doc.shared
      ? `${apiBase}/api/leads/${leadId}/shared-documents/${doc.id}/`
      : `${apiBase}/api/leads/${leadId}/site-visit/documents/${doc.id}/`;
    try {
      const r = await fetch(endpoint, { method: "DELETE", headers: authHeader() });
      if (r.ok || r.status === 204) await refetch();
      else alert("Could not delete the file.");
    } catch { alert("Network error while deleting."); }
  };

  /** Scalars + rcc_roof_types as JSON. (Files upload separately, immediately.) */
  const scalarPayload = (f: Form) => ({
    ...Object.fromEntries(TEXT_KEYS.map(k => [k, f[k]])),
    // Every other key here is a CharField, where "" is a valid value. This one
    // is a date: an empty string is not, so a cleared date must go as null.
    po_signed_date: f.po_signed_date || null,
    rcc_roof_types: f.rcc_roof_types,
    site_visit_complete: siteVisitComplete,
    deal_value: dealValue === "" ? "0" : dealValue,
  });

  /** Pull something readable out of a DRF error body for the alert. */
  const reason = async (res: Response) => {
    try {
      const e = await res.json();
      const first = Object.entries(e)[0];
      if (!first) return "";
      const [field, msg] = first;
      return `

${field}: ${Array.isArray(msg) ? msg[0] : msg}`;
    } catch { return ""; }
  };

  const save = async () => {
    setSaving(true);
    try {
      const res1 = await fetch(url, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...authHeader() },
        body: JSON.stringify(scalarPayload(form)),
      });
      if (!res1.ok) { alert(`Failed to save site visit details.${await reason(res1)}`); return; }
      const data = await res1.json();
      load(data);
      setSaved(true);
      onSaved?.();
      // The server tells us when this save is the one that signed the PO — that's
      // the moment the lead lands on the KSEB feasibility queue.
      if (data.po_just_signed) setPoPrompt(true);
    } catch { alert("Network error while saving site visit."); }
    finally { setSaving(false); }
  };

  /** Picking a PO signed date saves straight away — the date is the trigger for
   *  the feasibility hand-off, so it shouldn't wait behind Save Site Visit. */
  const setPoSignedDate = (value: string) => {
    setForm(prev => {
      const next = { ...prev, po_signed_date: value };
      // save() reads `form`, which won't have updated yet, so patch from `next`.
      if (value) void savePoDate(next);
      return next;
    });
    setSaved(false);
  };

  const savePoDate = async (next: Form) => {
    setSaving(true);
    try {
      const res = await fetch(url, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...authHeader() },
        body: JSON.stringify(scalarPayload(next)),
      });
      if (!res.ok) { alert(`Failed to save the PO signed date.${await reason(res)}`); return; }
      const data = await res.json();
      load(data);
      setSaved(true);
      onSaved?.();
      if (data.po_just_signed) setPoPrompt(true);
    } catch { alert("Network error while saving the PO signed date."); }
    finally { setSaving(false); }
  };

  // Field state shared with the module-level renderers via context (see SVCtx above).
  const ctx: SVCtx = { form, set, canEdit, documents, addDocs, deleteDoc, uploadingType, apiBase };

  // ITR is only asked for above ₹2 lakh. Ignore any currency symbols/commas typed in.
  const loanAmountValue = parseFloat((form.loan_amount || "").replace(/[^0-9.]/g, ""));
  const loanNeedsItr = Number.isFinite(loanAmountValue) && loanAmountValue > ITR_REQUIRED_ABOVE;

  return (
    <div id="site-visit" className="mt-6 scroll-mt-6 bg-white rounded-2xl border border-slate-200/70 shadow-sm">
      <div className="px-6 py-4 border-b border-slate-100">
        <h2 className="font-semibold text-slate-900">Site Visit Details</h2>
        <p className="text-xs text-slate-400 mt-0.5">Filled by the BDE after the site visit.</p>
      </div>

      {loading ? (
        <div className="px-6 py-10 text-center text-sm text-slate-400">Loading…</div>
      ) : (
        <>
        <SiteVisitCtx.Provider value={ctx}>
        <div className="p-6 grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {/* Deal — value entered by the BDE (no longer by the tele caller) */}
          <SectionTitle>Deal</SectionTitle>
          <div>
            <label className={labelCls}>Deal Value (₹)</label>
            <input type="number" min="0" value={dealValue} disabled={!canEdit}
              onChange={e => { setDealValue(e.target.value); setSaved(false); }}
              placeholder="0"
              className={`${inputCls} font-mono disabled:opacity-70 disabled:cursor-not-allowed`} />
          </div>

          {/* Roof */}
          <SectionTitle>Roof</SectionTitle>
          <Select k="roof_type" label="Roof Type" options={[{ value: "rcc", label: "RCC" }, { value: "sheet", label: "Sheet" }, { value: "mixed", label: "Mixed" }]} />
          {form.roof_type === "rcc" && (
            <div className="sm:col-span-2">
              <label className={labelCls}>RCC Roof Type (select multiple)</label>
              <div className="flex flex-wrap gap-2 pt-1">
                {RCC_SUBTYPES.map(o => {
                  const active = form.rcc_roof_types.includes(o.value);
                  return (
                    <button type="button" key={o.value} onClick={() => toggleRcc(o.value)} disabled={!canEdit}
                      className={`px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all disabled:opacity-60 disabled:cursor-not-allowed ${active ? "bg-indigo-600 text-white border-indigo-600" : "bg-slate-50 text-slate-600 border-slate-200 hover:bg-slate-100"}`}>
                      {o.label}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Electrical & Supply */}
          <SectionTitle>Electrical &amp; Supply</SectionTitle>
          <Select k="connection_type" label="Connection Type" options={[{ value: "commercial", label: "Commercial" }, { value: "residential", label: "Residential" }]} />
          <Text k="connected_load" label="Connected Load" />
          <Text k="consumer_number" label="Consumer Number" />
          <Select k="phase" label="Phase" options={[{ value: "1ph", label: "1 Phase" }, { value: "3ph", label: "3 Phase" }]} />
          <Text k="building_height" label="Building Height" />
          <Text k="panel_to_inverter_distance" label="Solar Panel to Inverter Distance" />
          <Text k="kseb_section" label="KSEB Section" />
          <Text k="feasible_capacity" label="Feasible Capacity" />
          <Text k="plant_capacity" label="Plant Capacity" placeholder="e.g. 5 kW" />
          <YesNo k="transformer_feasibility" label="Transformer Feasibility" />
          <YesNo k="neutral_link" label="Neutral Link" />

          {/* Roof access / structure */}
          <SectionTitle>Roof Access &amp; Structure</SectionTitle>
          <Text k="roof_access" label="Access to the Roof" />
          <Text k="parapet_height" label="Parapet Height" />
          <Select k="structure_type" label="Structure Type" options={[{ value: "table_top", label: "Table top" }, { value: "custom", label: "Custom" }]} />
          {form.structure_type === "custom" && <Text k="custom_structure_height" label="Custom Structure Height" />}
          <YesNo k="anchoring_allowed" label="Anchoring in Roof Allowed?" />

          {/* Cabling */}
          <SectionTitle>Cabling Requirements (meters)</SectionTitle>
          <Text k="cable_panel_to_dc_db" label="Panel to DC DB" />
          <Text k="cable_inverter_to_ac_db" label="Inverter to AC DB" />
          <Text k="earthing_cable_length" label="Earthing Cable Length" />
          <Text k="lightning_conductor_length" label="Lightning Conductor Length" />

          {/* Earthing */}
          <SectionTitle>Earthing</SectionTitle>
          <Text k="earthing_surface" label="Earthing Surface" />

          {/* Customer details */}
          <SectionTitle>Customer Details</SectionTitle>
          <YesNo k="name_change" label="Name Change" />
          <YesNo k="loan" label="Loan" />
          <YesNo k="load_enhancement" label="Load Enhancement" />

          {/* General documents (always needed) */}
          <SectionTitle>Customer Documents</SectionTitle>
          <MultiFileField docType="kseb_bill_file" label="KSEB Bill" />
          <MultiFileField docType="aadhaar_card" label="Aadhaar Card" />
          <MultiFileField docType="pan_card" label="PAN Card" />
          <MultiFileField docType="passbook" label="Passbook" />

          {/* Name-change documents — only relevant (and shown) when Name Change = Yes */}
          {form.name_change === "yes" && (
            <>
              <SectionTitle>Name Change Documents</SectionTitle>
              <MultiFileField docType="land_tax" label="Land Tax Details" />
              <MultiFileField docType="ownership_certificate" label="Ownership Certificate" />
              <MultiFileField docType="customer_passport_photo" label="Customer Passport Photo" />
              <MultiFileField docType="building_certificate" label="Building Certificate" />
            </>
          )}

          {/* Loan documents — only relevant (and shown) when Loan = Yes */}
          {form.loan === "yes" && (
            <>
              <SectionTitle>Loan Documents</SectionTitle>
              <Text k="loan_amount" label="Required Loan Amount (₹)" placeholder="e.g. 250000" />
              <Text k="email_linked_to_itr" label="Email linked to Passbook" placeholder="email@example.com" />
              {/* Already captured above / in Electrical & Supply — shown here so the
                  loan paperwork is complete in one place. Same underlying data. */}
              <MultiFileField docType="kseb_bill_file" label="KSEB Bill" />
              <Text k="kseb_section" label="KSEB Section" />
              {loanNeedsItr ? (
                <MultiFileField docType="itr_report" label="ITR Report" />
              ) : (
                <div className="sm:col-span-2 lg:col-span-3">
                  <p className="text-[11px] text-slate-400">
                    An ITR report is required only for loans above ₹{ITR_REQUIRED_ABOVE.toLocaleString("en-IN")}.
                  </p>
                </div>
              )}
            </>
          )}

          {/* Purchase order — captured once here; Documentation Stage 1 inherits it
              into its For MNRE and For Loan slots. */}
          <SectionTitle>Purchase Order</SectionTitle>
          <div className="sm:col-span-2 lg:col-span-3">
            <p className="text-[11px] text-slate-400 -mt-2 mb-2">
              Uploaded once here — it appears automatically under Documentation Stage 1&apos;s For MNRE and For Loan sections.
            </p>
          </div>
          <PdfMultiField docType="purchase_order" label="Purchase Order" />

          {/* Signing the PO starts the KSEB feasibility clock (due 2 days later),
              so it saves on pick and hands the BDE straight over. */}
          <div>
            <label className={labelCls}>PO Signed Date</label>
            <input type="date" value={form.po_signed_date} disabled={!canEdit}
              onChange={e => setPoSignedDate(e.target.value)}
              className={`${inputCls} disabled:opacity-70 disabled:cursor-not-allowed`} />
            <p className="text-[10px] text-slate-400 mt-1">
              Saves immediately and adds this lead to KSEB Feasibility.
            </p>
          </div>

          {/* Site visit photos */}
          <SectionTitle>Site Visit Photos</SectionTitle>
          {PHOTO_FIELDS.map(f => <MultiFileField key={f.key} docType={f.key} label={f.label} />)}
        </div>
        </SiteVisitCtx.Provider>

        {/* PO signed → go and take the feasibility. */}
        {poPrompt && (
          <div className="popup-overlay">
            <div className="popup-backdrop" onClick={() => setPoPrompt(false)} />
            <div className="popup-card max-w-md w-full p-6 text-center">
              <div className="w-14 h-14 mx-auto rounded-2xl bg-amber-50 text-amber-600 flex items-center justify-center mb-4">
                <svg width="26" height="26" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><path d="M12 2v4" /><path d="M12 18v4" /><circle cx="12" cy="12" r="4" /><path d="M2 12h4" /><path d="M18 12h4" /></svg>
              </div>
              <h3 className="text-base font-bold text-slate-900">Purchase order signed</h3>
              <p className="text-sm text-slate-500 mt-2">
                Site visit saved. Go to the <span className="font-semibold text-slate-700">KSEB Feasibility</span> section
                and complete the feasibility requirements — it is due within 2 days of the PO date.
              </p>
              <div className="flex gap-3 mt-6">
                <button onClick={() => setPoPrompt(false)}
                  className="flex-1 py-2.5 border border-slate-200 rounded-xl text-sm font-semibold text-slate-600 hover:bg-slate-50 transition-all">
                  Later
                </button>
                <Link href={`/feasibility`}
                  className="flex-1 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 transition-all text-center">
                  Go to KSEB Feasibility
                </Link>
              </div>
            </div>
          </div>
        )}

        {/* Actions — placed at the bottom of the form. */}
        <div className="flex flex-wrap items-center justify-end gap-3 px-6 py-4 border-t border-slate-100">
          <label className={`flex items-center gap-2 text-xs font-semibold ${siteVisitComplete ? "text-emerald-600" : "text-slate-500"} ${canEdit ? "cursor-pointer" : "cursor-default"}`}>
            <input type="checkbox" checked={siteVisitComplete} disabled={!canEdit}
              onChange={e => { setSiteVisitComplete(e.target.checked); setSaved(false); }}
              className="w-4 h-4 rounded accent-emerald-600" />
            Site visit complete
          </label>
          {saved && <span className="text-xs font-semibold text-emerald-600">Saved ✓</span>}
          {canEdit ? (
            <button onClick={save} disabled={saving || loading} className="px-4 py-2 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 transition-all disabled:opacity-40">
              {saving ? "Saving…" : "Save Site Visit"}
            </button>
          ) : (
            <span className="text-[11px] font-semibold text-slate-400 bg-slate-100 px-3 py-1.5 rounded-lg">View only</span>
          )}
        </div>
        </>
      )}
    </div>
  );
}

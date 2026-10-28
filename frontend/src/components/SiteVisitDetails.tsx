"use client";
/**
 * "View site visit details" — the BDE's site visit, read-only, for the stages
 * after it (purchase & logistics, project).
 *
 * The page passes in the site visit it loaded with its own data, so whoever
 * can open the page can read it and nobody else. Sections, labels and the
 * fields shown follow the BDE's form (leads/[id]/SiteVisitSection), so what
 * the site team reads is what the BDE filled in.
 */
import React, { useEffect, useState } from "react";
import { APP_SLUG } from "@/lib/config";
import { getApiBase, formatCurrency } from "@/lib/mock-data";

export type SiteVisitData = Record<string, any> | null;
type Doc = { id: number; doc_type: string; file: string | null };
type Row = [label: string, value: string | null];

const CHOICES: Record<string, Record<string, string>> = {
  roof_type: { rcc: "RCC", sheet: "Sheet", mixed: "Mixed" },
  connection_type: { commercial: "Commercial", residential: "Residential" },
  phase: { "1ph": "1 Phase", "3ph": "3 Phase" },
  structure_type: { table_top: "Table top", custom: "Custom" },
  earthing_surface: { soil: "Soil", concrete: "Concrete", tile: "Tile", interlock: "Interlock" },
  yes_no: { yes: "Yes", no: "No" },
  rcc: { flat: "Flat", slope: "Slope", tiled: "Tiled", non_linear: "Non linear" },
};

const PHOTO_SLOTS: [string, string][] = [
  ["photo_site", "Site Photos"], ["photo_meterbox", "Meter Box"], ["photo_earthing", "Earthing"],
  ["photo_directional", "Directional"], ["photo_hand_sketch", "Hand Sketch"],
  ["photo_feasibility_report", "Site Feasibility Report"],
];
const DOCUMENT_SLOTS: [string, string][] = [
  ["kseb_bill_file", "KSEB Bill"], ["aadhaar_card", "Aadhaar Card"], ["pan_card", "PAN Card"],
  ["passbook", "Passbook"], ["land_tax", "Land Tax Details"], ["ownership_certificate", "Ownership Certificate"],
  ["customer_passport_photo", "Customer Passport Photo"], ["building_certificate", "Building Certificate"],
  ["loan_document", "Loan Document"], ["itr_report", "ITR Report"], ["purchase_order", "Purchase Order"],
  ["kseb_feasibility_receipt", "KSEB Feasibility Receipt"],
];

const filled = (v: unknown) => v !== null && v !== undefined && String(v).trim() !== "";
const text = (v: unknown) => (filled(v) ? String(v) : null);
const pick = (kind: string, v: unknown) => (filled(v) ? CHOICES[kind]?.[String(v)] || String(v) : null);
const money = (v: unknown) => (filled(v) ? `₹${formatCurrency(Number(v) || 0)}` : null);
/** Typed as free text on the form ("2,50,000", "₹250000"): shown as money when it reads as one. */
const looseMoney = (v: unknown) => {
  if (!filled(v)) return null;
  const n = parseFloat(String(v).replace(/[^0-9.]/g, ""));
  return Number.isFinite(n) && n > 0 ? `₹${formatCurrency(n)}` : String(v);
};
const date = (v: unknown) => (filled(v)
  ? new Date(`${v}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })
  : null);

/** A field the form no longer asks for: listed only on older visits that have it. */
const legacy = (label: string, v: unknown): Row[] => (filled(v) ? [[label, String(v)]] : []);

/** The form's sections, with its rules for what is asked when. */
function sections(sv: Record<string, any>, productName?: string | null): { title: string; rows: Row[] }[] {
  const sheet = sv.roof_type === "sheet";
  const price = Number(sv.product_price) || 0;
  const discount = Number(sv.discount) || 0;
  return [
    { title: "Deal", rows: [
      ["Product", text(sv.product_name || productName)],
      ["Product Price", money(sv.product_price)],
      ["Discount", money(sv.discount)],
      ["Deal Value", money(filled(sv.deal_value) ? sv.deal_value : Math.max(0, price - discount))],
    ] },
    { title: "Roof", rows: [
      ["Roof Type", pick("roof_type", sv.roof_type)],
      ...(sv.roof_type === "rcc"
        ? [["RCC Roof Type", (sv.rcc_roof_types || []).map((v: string) => CHOICES.rcc[v] || v).join(", ") || null] as Row]
        : []),
    ] },
    { title: "Electrical & Supply", rows: [
      ["Connection Type", pick("connection_type", sv.connection_type)],
      ["Connected Load", text(sv.connected_load)],
      ["Consumer Number", text(sv.consumer_number)],
      ...legacy("Current Bill", sv.current_bill),
      ...legacy("KSEB Bill", sv.kseb_bill),
      ["Phase", pick("phase", sv.phase)],
      ["Building Height", text(sv.building_height)],
      ["Solar Panel to Inverter Distance", text(sv.panel_to_inverter_distance)],
      ["KSEB Section", text(sv.kseb_section)],
      ["Feasible Capacity", text(sv.feasible_capacity)],
      ["Plant Capacity", text(sv.plant_capacity)],
      ["Transformer Feasibility", pick("yes_no", sv.transformer_feasibility)],
      ["Neutral Link", pick("yes_no", sv.neutral_link)],
    ] },
    // A sheet roof has no parapet and always takes a custom structure, so the
    // form asks only for its height.
    { title: "Roof Access & Structure", rows: sheet ? [
      ["Custom Structure Height", text(sv.custom_structure_height)],
    ] : [
      ["Access to the Roof", text(sv.roof_access)],
      ["Parapet Height", text(sv.parapet_height)],
      ["Structure Type", pick("structure_type", sv.structure_type)],
      ...(sv.structure_type === "custom" ? [["Custom Structure Height", text(sv.custom_structure_height)] as Row] : []),
      ["Anchoring in Roof Allowed?", pick("yes_no", sv.anchoring_allowed)],
    ] },
    { title: "Cabling Requirements (meters)", rows: [
      ["Panel to DC DB", text(sv.cable_panel_to_dc_db)],
      ["Inverter to AC DB", text(sv.cable_inverter_to_ac_db)],
      ["Earthing Cable Length", text(sv.earthing_cable_length)],
      ["Lightning Conductor Length", text(sv.lightning_conductor_length)],
    ] },
    { title: "Earthing", rows: [
      ["Earthing Surface", pick("earthing_surface", sv.earthing_surface)],
      ...legacy("Earthing", sv.earthing),
    ] },
    { title: "Customer Details", rows: [
      ["Name Change", pick("yes_no", sv.name_change)],
      ["Loan", pick("yes_no", sv.loan)],
      ["Load Enhancement", pick("yes_no", sv.load_enhancement)],
      ...(sv.loan === "yes" ? [
        ["Required Loan Amount", looseMoney(sv.loan_amount)] as Row,
        ["Email linked to Passbook", text(sv.email_linked_to_itr)] as Row,
      ] : []),
    ] },
    { title: "Purchase Order & KSEB Feasibility", rows: [
      ["PO Signed Date", date(sv.po_signed_date)],
      ["KSEB Feasibility Taken", pick("yes_no", sv.kseb_feasibility_taken)],
      ["KSEB Feasibility Date", date(sv.kseb_feasibility_date)],
    ] },
  ];
}

export default function SiteVisitDetails({ siteVisit, customer, phone, productName, bdeName }: {
  siteVisit: SiteVisitData; customer: string; phone?: string | null;
  productName?: string | null; bdeName?: string | null;
}) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const sv = siteVisit;
  const docs: Doc[] = Array.isArray(sv?.documents) ? sv!.documents.filter((d: Doc) => d.file) : [];
  const known = new Set([...PHOTO_SLOTS, ...DOCUMENT_SLOTS].map(([k]) => k));
  // Anything uploaded under a slot this list doesn't name still belongs to the visit.
  const other = docs.filter(d => !known.has(d.doc_type));

  return (
    <>
      <button type="button" onClick={() => setOpen(true)} title="The BDE's site visit, read-only"
        className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-300 text-slate-700 rounded-lg text-xs font-semibold hover:bg-slate-50 transition">
        <svg width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M3 10.5L12 3l9 7.5" /><path d="M5 9.5V21h14V9.5" /><path d="M9 21v-6h6v6" />
        </svg>
        View site visit details
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-3 sm:p-4"
          onClick={() => setOpen(false)}>
          <div className="bg-white w-full max-w-4xl rounded-2xl shadow-2xl max-h-[90vh] overflow-hidden flex flex-col"
            onClick={e => e.stopPropagation()} role="dialog" aria-modal="true" aria-label="Site visit details">
            <div className="flex items-start justify-between gap-3 px-5 sm:px-6 py-4 border-b border-slate-100 flex-shrink-0">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-base font-bold text-slate-900">Site Visit Details</h2>
                  {sv && (
                    <span className={`text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full ${
                      sv.site_visit_complete ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>
                      {sv.site_visit_complete ? "Signed off" : "Not signed off"}
                    </span>
                  )}
                </div>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  {[customer, phone, bdeName ? `filled by ${bdeName}` : null].filter(Boolean).join(" · ")}
                </p>
              </div>
              <button type="button" onClick={() => setOpen(false)} aria-label="Close"
                className="w-8 h-8 shrink-0 flex items-center justify-center rounded-xl bg-slate-100 text-slate-500 hover:bg-slate-200 transition text-sm">
                ✕
              </button>
            </div>

            <div className="overflow-y-auto flex-1 px-5 sm:px-6 py-5 space-y-6">
              {!sv ? (
                <p className="py-14 text-center text-sm text-slate-400">No site visit was recorded for this customer.</p>
              ) : (
                <>
                  {sections(sv, productName).map(s => (
                    <section key={s.title}>
                      <h3 className="text-xs font-bold text-indigo-600 uppercase tracking-wide mb-3">{s.title}</h3>
                      <dl className="grid grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-3">
                        {s.rows.map(([label, value]) => (
                          <div key={label} className="min-w-0">
                            <dt className="text-[10px] text-slate-400 uppercase tracking-wide">{label}</dt>
                            <dd className={`text-sm font-medium break-words ${value ? "text-slate-700" : "text-slate-300"}`}>{value || "—"}</dd>
                          </div>
                        ))}
                      </dl>
                    </section>
                  ))}
                  <Files title="Site Visit Photos" slots={PHOTO_SLOTS} docs={docs} empty="No photos were uploaded." />
                  <Files title="Customer Documents" slots={DOCUMENT_SLOTS} docs={docs} empty="No documents were uploaded." />
                  {other.length > 0 && (
                    <Files title="Other Files" docs={other} empty=""
                      slots={Array.from(new Set(other.map(d => d.doc_type))).map(t => [t, t.replace(/_/g, " ")] as [string, string])} />
                  )}
                </>
              )}
            </div>

            <div className="px-5 sm:px-6 py-3 border-t border-slate-100 text-[11px] text-slate-400 flex-shrink-0">
              Read-only. The BDE&apos;s site visit is changed on the lead itself.
            </div>
          </div>
        </div>
      )}
    </>
  );
}

const isImage = (url: string) => /\.(jpe?g|png|webp|gif|bmp)$/i.test(url.split("?")[0]);

/** A group of upload slots; only the slots that hold files are listed. */
function Files({ title, slots, docs, empty }: { title: string; slots: [string, string][]; docs: Doc[]; empty: string }) {
  const apiBase = getApiBase(APP_SLUG);
  const withFiles = slots
    .map(([key, label]) => ({ label, files: docs.filter(d => d.doc_type === key) }))
    .filter(s => s.files.length > 0);
  return (
    <section>
      <h3 className="text-xs font-bold text-indigo-600 uppercase tracking-wide mb-3">{title}</h3>
      {withFiles.length === 0 ? (
        <p className="text-sm text-slate-400">{empty}</p>
      ) : (
        <div className="space-y-4">
          {withFiles.map(s => (
            <div key={s.label}>
              <p className="text-[10px] text-slate-400 uppercase tracking-wide mb-1.5">{s.label} <span className="normal-case">({s.files.length})</span></p>
              <div className="flex flex-wrap gap-2">
                {s.files.map(d => {
                  const url = d.file!.startsWith("http") ? d.file! : `${apiBase}${d.file}`;
                  const name = decodeURIComponent(url.split("?")[0].split("/").pop() || "file");
                  return isImage(url) ? (
                    <a key={`${d.doc_type}-${d.id}`} href={url} target="_blank" rel="noreferrer" title={name}
                      className="block overflow-hidden rounded-xl ring-1 ring-slate-200 hover:ring-indigo-300 transition">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={url} alt={`${s.label}: ${name}`} loading="lazy" className="h-24 w-32 object-cover bg-slate-100" />
                    </a>
                  ) : (
                    <a key={`${d.doc_type}-${d.id}`} href={url} target="_blank" rel="noreferrer" title={name}
                      className="inline-flex max-w-[220px] items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-700 hover:border-indigo-300 hover:text-indigo-700 transition">
                      <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24" className="shrink-0 text-slate-400" aria-hidden="true">
                        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" /><path d="M14 2v6h6" />
                      </svg>
                      <span className="truncate">{name}</span>
                    </a>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

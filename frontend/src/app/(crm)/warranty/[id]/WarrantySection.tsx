"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";
import React, { useCallback, useEffect, useState } from "react";
import { loadEnergyfoxLogo } from "@/lib/pdf-logo";
import { toISODate, toDisplayDate } from "@/lib/date-fields";

const WARRANTY_SLOT = "warranty";
const inputCls =
  "w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all disabled:opacity-70 disabled:cursor-not-allowed";
const labelCls = "block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5";
const cardCls = "bg-white border border-slate-200 rounded-2xl shadow-sm p-5";

type Doc = { id: number; doc_type: string; file: string };

// Per-customer warranty certificate form. The fixed details (company name, CIN,
// GST, director, signature & seal) come from the Settings module, not from here.
type CertForm = {
  system_type: string; capacity_kw: string; customer_name: string;
  panel_make: string; inverter_make: string;
  panel_warranty_years: string; inverter_warranty_years: string;
  installation_date: string; site_address: string;
};
const BLANK_CERT: CertForm = {
  system_type: "OnGrid", capacity_kw: "", customer_name: "",
  panel_make: "", inverter_make: "",
  panel_warranty_years: "", inverter_warranty_years: "",
  installation_date: "", site_address: "",
};
type OrgInfo = {
  company_name: string; cin: string; gst: string;
  director_name: string; director_designation: string;
  panel_years: string; inverter_years: string; service_years: string;
  signature: string | null; seal: string | null;
};

const CERT_PREFIX = "Warranty_Certificate";

// Issuing the warranty (generating the certificate, or completing it without
// one) is what starts the customer's periodic maintenance. That happens in
// another module, so the confirmation says so.
const withSchedule = (message: string, from?: string | null) =>
  from
    ? `${message}\n\nPeriodic maintenance is scheduled from ${toDisplayDate(from)}: 10 visits, one every 6 months.`
    : message;

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
  const [cert, setCert] = useState<CertForm>({ ...BLANK_CERT });
  const [org, setOrg] = useState<OrgInfo | null>(null);
  const [generating, setGenerating] = useState(false);
  const [sending, setSending] = useState<"whatsapp" | "email" | null>(null);
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
    // Merge: saved form values win; blanks fall back to the customer's history
    // (prefill) and the Settings defaults for the warranty years.
    const fd = (d.form_data || {}) as Record<string, string>;
    const pf = (d.prefill || {}) as Record<string, string>;
    if (d.org) setOrg(d.org);
    const defaults: Record<string, string> = {
      ...pf,
      panel_warranty_years: d.org?.panel_years || "",
      inverter_warranty_years: d.org?.inverter_years || "",
    };
    setCert(prev => {
      const next = { ...BLANK_CERT } as Record<string, string>;
      for (const k of Object.keys(next)) {
        const saved = String(fd[k] ?? "").trim();
        next[k] = saved || defaults[k] || (prev as any)[k] || (BLANK_CERT as any)[k] || "";
      }
      return next as CertForm;
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

  // Both channels go out from the CRM's own accounts (Settings → Integrations),
  // so the customer hears from the company and every send lands in the outbox.
  const send = async (channel: "whatsapp" | "email") => {
    const label = channel === "email" ? "email" : "WhatsApp";
    if (!hasGenerated) { alert("Generate the warranty certificate first."); return; }
    const fallback = channel === "email" ? email : phone;
    const to = window.prompt(`Send the warranty by ${label} to:`, fallback || "");
    if (!to || !to.trim()) return;

    setSending(channel);
    try {
      const body = new FormData();
      body.append("channels", channel);
      body.append(channel === "email" ? "email" : "phone", to.trim());
      const r = await fetch(`${apiBase}/api/leads/${leadId}/send-warranty/`, {
        method: "POST", headers: authHeader(), body,
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) { alert(d.error || `Could not send the warranty by ${label}.`); return; }
      const warnings: string[] = d.warnings || [];
      alert(warnings.length ? ["Sent, with warnings:", ...warnings].join("\n")
                            : `Warranty sent by ${label}.`);
      await refetch();
      onChanged?.();
    } catch { alert(`Network error while sending the warranty by ${label}.`); }
    finally { setSending(null); }
  };

  const saveScalars = async (): Promise<any | null> => {
    const r = await fetch(url, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...authHeader() },
      body: JSON.stringify({ sent, remark, form_data: cert }),
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
      if (r.ok) {
        const d = await r.json().catch(() => ({}));
        await refetch(); onChanged?.();
        alert(withSchedule("Warranty marked complete.", d.maintenance_scheduled_from));
      }
      else { const e = await r.json().catch(() => ({})); alert(e.error || "Could not complete."); }
    } catch { alert("Network error while completing."); }
    finally { setCompleting(false); }
  };

  // A generated certificate already attached under Warranty Document (by filename prefix).
  const generatedDocs = documents.filter(d =>
    d.doc_type === WARRANTY_SLOT && decodeURIComponent(d.file.split("/").pop() || "").startsWith(CERT_PREFIX));
  const hasGenerated = generatedDocs.length > 0;

  const resetGenerated = async () => {
    if (!window.confirm("Reset the generated warranty certificate? It will be removed from the Warranty Document so you can edit the details and generate it again.")) return;
    try {
      for (const d of generatedDocs) {
        await fetch(`${docsUrl}${d.id}/`, { method: "DELETE", headers: authHeader() });
      }
      await refetch();
    } catch { alert("Network error while resetting."); }
  };

  // Fetch an image (signature / seal from Settings) as a data URL for jsPDF.
  const loadImg = async (u: string | null): Promise<{ dataUrl: string; fmt: "PNG" | "JPEG"; w: number; h: number } | null> => {
    if (!u) return null;
    try {
      const r = await fetch(u);
      if (!r.ok) return null;
      const b = await r.blob();
      const dataUrl: string = await new Promise((res, rej) => {
        const fr = new FileReader(); fr.onload = () => res(fr.result as string); fr.onerror = rej; fr.readAsDataURL(b);
      });
      const dims: { w: number; h: number } = await new Promise((res) => {
        const im = new Image(); im.onload = () => res({ w: im.width, h: im.height }); im.onerror = () => res({ w: 1, h: 1 }); im.src = dataUrl;
      });
      return { dataUrl, fmt: b.type.includes("png") ? "PNG" : "JPEG", w: dims.w, h: dims.h };
    } catch { return null; }
  };

  const generateCert = async () => {
    if (!cert.customer_name.trim()) { alert("Enter the customer name first."); return; }
    setGenerating(true);
    try {
      // Persist the form first so the certificate matches what is saved.
      if (!isComplete) { const latest = await saveScalars(); if (latest) load(latest); }

      const { jsPDF } = await import("jspdf");
      const doc = new jsPDF("p", "pt", "a4");
      const W = doc.internal.pageSize.getWidth();
      const H = doc.internal.pageSize.getHeight();
      const ORANGE: [number, number, number] = [247, 148, 29];
      const NAVY: [number, number, number] = [26, 35, 66];
      const SLATE: [number, number, number] = [51, 65, 85];

      const company = org?.company_name || "Energyfox Consultants Pvt. Ltd.";
      const brandFirst = company.split(" ")[0] || "Energyfox";
      const brandRest = company.slice(brandFirst.length).trim() || "Consultants Pvt Ltd";

      // ── Header (matches the other generated Energyfox documents) ──
      const logo = await loadEnergyfoxLogo();
      if (logo) {
        const lh = 42, lw = (logo.width / logo.height) * lh;
        doc.addImage(logo.dataUrl, "PNG", 40, 24, lw, lh);
      } else {
        // Fallback wordmark if the logo asset can't be loaded.
        doc.setFont("helvetica", "bold"); doc.setFontSize(24); doc.setTextColor(...ORANGE);
        doc.text(brandFirst, 40, 48);
        doc.setFont("helvetica", "normal"); doc.setFontSize(11); doc.setTextColor(148, 163, 184);
        doc.text(brandRest, 40, 64);
      }
      doc.setFont("helvetica", "bold"); doc.setFontSize(9); doc.setTextColor(...NAVY);
      [`CIN : ${org?.cin || ""}`, `GST : ${org?.gst || ""}`].forEach((ln, i) => doc.text(ln, W - 40, 38 + i * 13, { align: "right" }));
      doc.setFillColor(...NAVY); doc.rect(0, 80, W, 6, "F");
      doc.setFillColor(...ORANGE); doc.rect(0, 86, W, 3, "F");

      // Date (top right, like the template).
      const dateStr = toDisplayDate(cert.installation_date) || new Date().toLocaleDateString("en-IN");
      doc.setFont("helvetica", "normal"); doc.setFontSize(10.5); doc.setTextColor(...SLATE);
      doc.text(dateStr, W - 45, 120, { align: "right" });

      let y = 150;
      const para = (text: string, opts?: { bold?: boolean; gap?: number }) => {
        doc.setFont("helvetica", opts?.bold ? "bold" : "normal"); doc.setFontSize(10.5); doc.setTextColor(...SLATE);
        const lines = doc.splitTextToSize(text, W - 110);
        doc.text(lines, 55, y);
        y += lines.length * 15 + (opts?.gap ?? 14);
      };
      const bullet = (text: string) => {
        doc.setFont("helvetica", "normal"); doc.setFontSize(10.5); doc.setTextColor(...SLATE);
        doc.circle(70, y - 3.5, 1.6, "F");
        const lines = doc.splitTextToSize(text, W - 150);
        doc.text(lines, 82, y);
        y += lines.length * 15 + 4;
      };
      const heading = (text: string) => {
        doc.setFont("helvetica", "bold"); doc.setFontSize(11); doc.setTextColor(30, 41, 59);
        doc.text(text, 55, y);
        y += 20;
      };

      para(`This is to certify that ${company} has successfully installed a ${cert.capacity_kw || "____"} kW ${cert.system_type || "OnGrid"}-Connected Solar Power Plant at ${cert.customer_name}.`);
      heading("System Details");
      bullet(`Solar Plant Capacity: ${cert.capacity_kw ? `${cert.capacity_kw} kW` : "—"}`);
      bullet(`Solar Panel Make: ${cert.panel_make || "—"}`);
      bullet(`Inverter Make: ${cert.inverter_make || "—"}`);
      y += 10;
      heading("Warranty Details");
      bullet(`Solar Panels Warranty: ${cert.panel_warranty_years || org?.panel_years || "30"} Years (as per manufacturer terms)`);
      bullet(`Inverter Warranty: ${cert.inverter_warranty_years || org?.inverter_years || "12"} Years (as per manufacturer terms)`);
      bullet(`Service Warranty: ${org?.service_years || "5"} Years`);
      y += 10;
      para("During the service warranty period, free preventive maintenance service will be provided once every 6 months, subject to standard service terms and site accessibility.");
      para("The solar power system has been installed, tested, and commissioned as per applicable technical standards and is found to be functioning satisfactorily on the date of handover.");
      doc.setFont("helvetica", "bold");
      para(`Date of Installation / Commissioning: ${toDisplayDate(cert.installation_date) || "—"}`, { bold: true, gap: 0 });
      para(`Site Address: ${cert.site_address || "—"}`, { bold: true });

      // ── Signature block (fixed details from Settings) ──
      y += 6;
      doc.setFont("helvetica", "bold"); doc.setFontSize(10.5); doc.setTextColor(30, 41, 59);
      doc.text(company, 55, y); y += 16;
      doc.setFont("helvetica", "normal"); doc.setTextColor(...SLATE);
      doc.text(`Name & Designation: ${org?.director_name || ""}`, 55, y); y += 15;
      doc.text(`(${org?.director_designation || "Director"})`, 155, y); y += 12;

      const [sig, seal] = await Promise.all([loadImg(org?.signature || null), loadImg(org?.seal || null)]);
      const imgY = y + 12;
      if (sig) {
        const h = 55, w = Math.min(160, (sig.w / sig.h) * h);
        try { doc.addImage(sig.dataUrl, sig.fmt, 55, imgY, w, h); } catch {}
      }
      if (seal) {
        const h = 85, w = Math.min(160, (seal.w / seal.h) * h);
        try { doc.addImage(seal.dataUrl, seal.fmt, W - 45 - w, imgY - 20, w, h); } catch {}
      }
      // Leave room for the signature & seal — a generous blank band when no
      // images are set in Settings, so the certificate can be signed by hand.
      y = imgY + (sig || seal ? 80 : 78);
      doc.setFont("helvetica", "normal"); doc.setFontSize(10.5); doc.setTextColor(...SLATE);
      doc.text("Signature & Company Seal", 55, y);

      // Footer (same band as the other generated documents).
      doc.setFontSize(9); doc.setTextColor(...NAVY); doc.setFont("helvetica", "bold");
      doc.text("9526 396 823", 45, H - 50);
      doc.text("energyfox.in", W / 2, H - 50, { align: "center" });
      doc.text("info@energyfox.in", W - 45, H - 50, { align: "right" });
      doc.setFont("helvetica", "normal"); doc.setTextColor(...SLATE);
      doc.text("TC 15/4257/2 4th Floor Malankara Avenue pattom TVM - 695004", W / 2, H - 36, { align: "center" });

      const filename = `${CERT_PREFIX}_${cert.customer_name.replace(/[^\w\- ]+/g, "").trim().replace(/\s+/g, "_")}.pdf`;
      if (isComplete) {
        // Record is locked — nothing can be attached anymore; just download locally.
        doc.save(filename);
      } else {
        // Attach under the Warranty Document (preview / download / send from there).
        const blob = doc.output("blob");
        const fd = new FormData();
        fd.append("doc_type", WARRANTY_SLOT);
        fd.append("file", new File([blob], filename, { type: "application/pdf" }));
        const r = await fetch(docsUrl, { method: "POST", headers: authHeader(), body: fd });
        if (r.ok) {
          const d = await r.json().catch(() => ({}));
          await refetch();
          alert(withSchedule("Warranty certificate generated and attached under Warranty Document.",
            d.maintenance_scheduled_from));
        } else {
          const e = await r.json().catch(() => ({}));
          alert(e.error || "Generated, but could not attach — downloading instead.");
          doc.save(filename);
        }
      }
    } catch (e) {
      console.error(e);
      alert("Could not generate the warranty certificate.");
    } finally {
      setGenerating(false);
    }
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

      {/* Warranty certificate details (per-customer; fixed company details live in Settings) */}
      <div className={cardCls}>
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-4">
          <div>
            <h3 className="text-sm font-bold text-slate-900">Warranty Certificate</h3>
            <p className="text-[11px] text-slate-400 mt-0.5">
              Details already in the CRM are pre-filled. Company details, director sign-off, signature &amp; seal come from Settings.
            </p>
          </div>
          {hasGenerated && (
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-emerald-50 border border-emerald-200 text-emerald-700 rounded-lg text-[11px] font-semibold whitespace-nowrap">
              ✓ Certificate generated
            </span>
          )}
        </div>
        {(() => { const certLocked = readOnly || hasGenerated; const setC = (k: keyof CertForm, v: string) => { setCert(p => ({ ...p, [k]: v })); setSaved(false); }; return (
        <>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          <div>
            <label className={labelCls}>System Type</label>
            <select value={cert.system_type} disabled={certLocked} onChange={e => setC("system_type", e.target.value)} className={inputCls}>
              <option value="OnGrid">OnGrid</option>
              <option value="Hybrid">Hybrid</option>
            </select>
          </div>
          <div><label className={labelCls}>Solar Plant Capacity (kW)</label>
            <input value={cert.capacity_kw} disabled={certLocked} onChange={e => setC("capacity_kw", e.target.value)} placeholder="e.g. 5" className={inputCls} /></div>
          <div><label className={labelCls}>Customer Name</label>
            <input value={cert.customer_name} disabled={certLocked} onChange={e => setC("customer_name", e.target.value)} placeholder="Customer name" className={inputCls} /></div>
          <div><label className={labelCls}>Solar Panel Make</label>
            <input value={cert.panel_make} disabled={certLocked} onChange={e => setC("panel_make", e.target.value)} placeholder="Panel make" className={inputCls} /></div>
          <div><label className={labelCls}>Inverter Make</label>
            <input value={cert.inverter_make} disabled={certLocked} onChange={e => setC("inverter_make", e.target.value)} placeholder="Inverter make" className={inputCls} /></div>
          <div><label className={labelCls}>Date of Installation / Commissioning</label>
            <input type="date" value={toISODate(cert.installation_date)} disabled={certLocked}
              onChange={e => setC("installation_date", e.target.value)} className={inputCls} /></div>
          <div><label className={labelCls}>Solar Panels Warranty (Years)</label>
            <input value={cert.panel_warranty_years} disabled={certLocked} onChange={e => setC("panel_warranty_years", e.target.value)} placeholder={org?.panel_years || "30"} className={inputCls} /></div>
          <div><label className={labelCls}>Inverter Warranty (Years)</label>
            <input value={cert.inverter_warranty_years} disabled={certLocked} onChange={e => setC("inverter_warranty_years", e.target.value)} placeholder={org?.inverter_years || "12"} className={inputCls} /></div>
          <div><label className={labelCls}>Service Warranty</label>
            <input value={`${org?.service_years || "5"} Years`} disabled readOnly title="Set in Settings → Warranty Document" className={inputCls} /></div>
          <div className="sm:col-span-2 lg:col-span-3"><label className={labelCls}>Site Address</label>
            <input value={cert.site_address} disabled={certLocked} onChange={e => setC("site_address", e.target.value)} placeholder="Site address" className={inputCls} /></div>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          {!hasGenerated ? (
            <button type="button" onClick={generateCert} disabled={generating || (readOnly && !isComplete)}
              className="px-4 py-2.5 bg-orange-500 text-white rounded-xl text-sm font-semibold hover:bg-orange-600 disabled:opacity-50 transition">
              {generating ? "Generating…" : "Generate Warranty Certificate"}
            </button>
          ) : (
            !readOnly && (
              <button type="button" onClick={resetGenerated}
                className="px-4 py-2.5 bg-slate-100 text-slate-700 rounded-xl text-sm font-semibold hover:bg-slate-200 transition">
                Reset — edit &amp; generate again
              </button>
            )
          )}
          <span className="text-[11px] text-slate-400">
            {hasGenerated
              ? "The certificate is attached under Warranty Document below."
              : "Generates the certificate PDF and attaches it under Warranty Document."}
          </span>
        </div>
        </>
        ); })()}
      </div>

      <div className={cardCls}>
        {/* Send */}
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" onClick={() => send("whatsapp")} disabled={!phone || sending !== null || !hasGenerated}
            title={!hasGenerated ? "Generate the certificate first" : phone ? `WhatsApp ${phone}` : "No phone number on file"}
            className="inline-flex items-center gap-2 px-4 py-2.5 bg-emerald-600 text-white rounded-xl text-sm font-semibold hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed transition">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M17.47 14.38c-.29-.15-1.71-.84-1.97-.94-.26-.1-.46-.15-.65.14-.19.29-.75.94-.92 1.13-.17.19-.34.21-.63.07-.29-.15-1.22-.45-2.33-1.44-.86-.77-1.44-1.72-1.61-2.01-.17-.29-.02-.44.13-.59.13-.13.29-.34.44-.51.15-.17.19-.29.29-.48.1-.19.05-.36-.02-.51-.07-.15-.65-1.57-.89-2.15-.24-.56-.48-.49-.65-.5-.17-.01-.36-.01-.56-.01-.19 0-.51.07-.78.36-.27.29-1.02 1-1.02 2.42 0 1.43 1.04 2.81 1.19 3 .15.19 2.05 3.13 4.97 4.39.69.3 1.23.48 1.65.61.69.22 1.32.19 1.82.12.56-.08 1.71-.7 1.95-1.37.24-.67.24-1.25.17-1.37-.07-.12-.26-.19-.55-.34z"/><path d="M20.52 3.44A11.86 11.86 0 0012.05 0C5.5 0 .18 5.31.17 11.85c0 2.09.55 4.13 1.59 5.93L0 24l6.38-1.67a11.87 11.87 0 005.67 1.44h.01c6.55 0 11.87-5.31 11.87-11.85 0-3.17-1.23-6.15-3.41-8.48zM12.06 21.2h-.01a9.86 9.86 0 01-5.02-1.37l-.36-.21-3.79.99 1.01-3.69-.23-.38a9.82 9.82 0 01-1.51-5.24c0-5.44 4.43-9.86 9.9-9.86 2.64 0 5.13 1.03 7 2.9a9.82 9.82 0 012.9 6.97c0 5.44-4.43 9.86-9.89 9.86z"/></svg>
            {sending === "whatsapp" ? "Sending…" : "WhatsApp"}
          </button>
          <button type="button" onClick={() => send("email")} disabled={!email || sending !== null || !hasGenerated}
            title={!hasGenerated ? "Generate the certificate first" : email ? `Email ${email}` : "No email on file"}
            className="inline-flex items-center gap-2 px-4 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition">
            <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>
            {sending === "email" ? "Sending…" : "Email"}
          </button>
          {sent && <span className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-600">✓ Marked sent</span>}
        </div>
        <p className="text-[11px] text-slate-400 mt-2">
          Sent from the company&apos;s WhatsApp number and email account (Settings → Integrations), with the certificate attached.
        </p>
        {(!phone || !email || !hasGenerated) && (
          <p className="text-[11px] text-amber-600 mt-1">
            {!hasGenerated && "Generate the certificate before sending. "}
            {!phone && "No phone number on file. "}{!email && "No email on file."}
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

"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";
import React, { useCallback, useEffect, useState } from "react";
import { loadEnergyfoxLogo } from "@/lib/pdf-logo";
import { toISODate, toDisplayDate } from "@/lib/date-fields";

const ANNEXURE_SLOT = "annexure3";
const DISCOM_OPTIONS = [
  { value: "pending", label: "Pending" },
  { value: "yes", label: "Approved" },
  { value: "no", label: "Not Approved" },
];

// Completion-doc pop-up forms (each saved into a JSON field on the record).
// A field is [key, label] for free text, [key, label, options] for a dropdown,
// or [key, label, "date"] for a native date picker.
type FormField = [string, string] | [string, string, string[] | "date"];
const COMPLETION_FORMS: { key: string; label: string; fields: FormField[] }[] = [
  {
    key: "completion_letterhead",
    label: "Completion in Letterhead",
    fields: [
      ["name_of_consumer", "Name of Consumer"],
      ["consumer_number", "Consumer Number"],
      ["kseb_section", "KSEB Section"],
      ["capacity", "Capacity"],
      ["connection_type", "Connection Type"],
      ["date_of_completion", "Date of Completion", "date"],
    ],
  },
  {
    key: "customer_details",
    label: "Customer Details",
    fields: [
      ["electrical_division", "Name of Electrical Division & Sub Division"],
      ["electrical_section", "Name of Electrical Section"],
      ["consumer_no", "Consumer No"],
      ["tariff", "Tariff"],
      ["connected_load", "Connected Load"],
      ["solar_plant_owner", "Name of Solar Plant Owner"],
      ["address", "Address"],
      ["email", "Email ID"],
      ["contact_phone", "Contact Phone No. of Consumer"],
      ["alternate_contact", "Alternate Contact No"],
      ["bank_name", "Bank Name"],
      ["account_no_name", "Account No. & Name"],
      ["ifsc_code", "IFSC Code"],
      ["plant_type", "Type of Plant"],
      ["total_capacity", "Total Capacity of Solar Plant"],
      ["number_of_panels", "Number of Panels"],
      ["individual_capacity", "Individual Panel Capacity"],
      ["inverter_make_serial", "Make & Serial No. of Inverters"],
      ["inverter_phase", "Inverter Type (Single Phase / Three Phase)"],
      ["inverter_capacity", "Inverter Capacity"],
      ["dc_input_voltage", "DC Input Voltage"],
      ["voltage_phase", "Voltage and Number of Phase"],
      // Checklist rows 6–14 — standard answers pre-filled, editable per customer.
      ["hybrid_scheme_confirms", "6. Hybrid Inverter — Scheme Confirms to CE(REES)", ["NA", "Yes", "No"]],
      ["completion_certificate_submitted", "7. Completion Certificate Submitted in Ele. Section", ["Yes", "No"]],
      ["energization_approval_obtained", "8. Energization Approval Obtained from EI", ["Not Applicable", "Yes", "No"]],
      ["energization_approval_details", "9. Details of Energization Approval by EI"],
      ["dc_isolator_provided", "10. DC Isolator on Incoming Side of Inverter", ["Yes", "No"]],
      ["visual_isolator_provided", "11. Visual Isolator Before Connectivity Point", ["Yes", "No"]],
      ["wiring_completed", "12. All Wiring Connections as per Approved Scheme", ["Yes", "No"]],
      ["earthing_provided", "13. Earthing Provided as per Standards", ["Yes", "No"]],
      ["protection_functions_equipped", "14. Inverter Equipped with Protection Functions", ["Yes", "No"]],
    ],
  },
  {
    key: "inverter_panel_details",
    label: "Inverter & Panel Details",
    fields: [
      ["customer_name", "Customer Name"],
      ["customer_contact_no", "Customer Contact No"],
      ["customer_address", "Customer Address"],
      ["system_make", "System Make"],
      ["inverter_make", "Inverter Make"],
      ["inverter_model_no", "Inverter Model No"],
      ["inverter_capacity", "Inverter Capacity"],
      ["inverter_serial_number", "Inverter Serial Number"],
      ["panel_make", "Panel Make"],
      ["panel_capacity", "Panel Capacity"],
      ["panel_serial_numbers", "Panel Serial Numbers"],
    ],
  },
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
  const [canReopen, setCanReopen] = useState(false);
  const [reopening, setReopening] = useState(false);
  const [completedByName, setCompletedByName] = useState<string | null>(null);
  const [completedAt, setCompletedAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [completing, setCompleting] = useState(false);
  const [uploadingType, setUploadingType] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [forms, setForms] = useState<Record<string, Record<string, string>>>({
    completion_letterhead: {}, customer_details: {}, inverter_panel_details: {},
  });
  // Pre-fill values pulled from the customer's history (lead / site visit / stage 1 / project).
  const [prefill, setPrefill] = useState<Record<string, Record<string, string>>>({});
  // What the earlier stages photographed, shown here read-only.
  const [earlier, setEarlier] = useState<{
    stage1: (Doc & { label?: string })[]; installation: (Doc & { label?: string })[] }>(
    { stage1: [], installation: [] });
  const [openForm, setOpenForm] = useState<string | null>(null);
  const [formDraft, setFormDraft] = useState<Record<string, string>>({});
  // Panel serial numbers as a dynamic list of inputs (stored comma-joined in the JSON).
  const [serialDraft, setSerialDraft] = useState<string[]>([""]);
  const [formSaving, setFormSaving] = useState(false);

  const load = useCallback((d: any) => {
    setF({
      annexure3_completed: !!d.annexure3_completed,
      annexure3_remark: d.annexure3_remark || "",
      discom_approval: d.discom_approval || "pending",
      subsidy_requested: !!d.subsidy_requested,
      sent_to_liasoning: !!d.sent_to_liasoning,
      mnre_remark: d.mnre_remark || "",
    });
    setForms({
      completion_letterhead: d.completion_letterhead || {},
      customer_details: d.customer_details || {},
      inverter_panel_details: d.inverter_panel_details || {},
    });
    if (d.prefill) setPrefill(d.prefill);
    if (d.earlier_images) setEarlier({
      stage1: d.earlier_images.stage1 || [],
      installation: d.earlier_images.installation || [],
    });
    if (d.can_reopen !== undefined) setCanReopen(!!d.can_reopen);
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

  const openModal = (key: string) => {
    // Start from the customer's known history, then let previously saved values win.
    const merged: Record<string, string> = { ...(prefill[key] || {}) };
    if (key === "customer_details") {
      // Inherit details already entered in the other completion forms.
      const ip = forms.inverter_panel_details || {};
      const cl = forms.completion_letterhead || {};
      const serialCount = String(ip.panel_serial_numbers || "").split(/[\n,;]+/).map(s => s.trim()).filter(Boolean).length;
      const derived: Record<string, string> = {
        total_capacity: (cl.capacity as string) || "",
        inverter_make_serial: [ip.inverter_make, ip.inverter_serial_number].map(v => String(v || "").trim()).filter(Boolean).join(" / "),
        inverter_capacity: (ip.inverter_capacity as string) || "",
        individual_capacity: (ip.panel_capacity as string) || "",
        number_of_panels: serialCount ? String(serialCount) : "",
      };
      for (const [k, v] of Object.entries(derived)) {
        if (v.trim()) merged[k] = v;
      }
    }
    for (const [k, v] of Object.entries(forms[key] || {})) {
      if (String(v || "").trim()) merged[k] = v as string;
    }
    if (key === "inverter_panel_details") {
      const serials = String(merged.panel_serial_numbers || "").split(/[\n,;]+/).map(s => s.trim()).filter(Boolean);
      setSerialDraft(serials.length ? serials : [""]);
    }
    setFormDraft(merged);
    setOpenForm(key);
  };

  // ── Combined completion document (3 pages, styled after the Energyfox templates) ──
  const [generating, setGenerating] = useState(false);

  const generateDoc = async () => {
    const anyFilled = COMPLETION_FORMS.some(fm => Object.values(forms[fm.key] || {}).some(v => String(v || "").trim()));
    if (!anyFilled) { alert("Fill and submit at least one completion form first."); return; }
    setGenerating(true);
    try {
      const { jsPDF } = await import("jspdf");
      const autoTable = (await import("jspdf-autotable")).default;
      const doc = new jsPDF("p", "pt", "a4");
      const W = doc.internal.pageSize.getWidth();
      const H = doc.internal.pageSize.getHeight();
      const ORANGE: [number, number, number] = [247, 148, 29];
      const NAVY: [number, number, number] = [26, 35, 66];
      const SLATE: [number, number, number] = [51, 65, 85];

      const logo = await loadEnergyfoxLogo();
      // Date the document is generated — stamped on the pages we sign.
      const generatedOn = new Date().toLocaleDateString("en-IN", {
        day: "2-digit", month: "2-digit", year: "numeric",
      });

      const header = (rightLines: string[]) => {
        if (logo) {
          const h = 42, w = (logo.width / logo.height) * h;
          doc.addImage(logo.dataUrl, "PNG", 40, 24, w, h);
        } else {
          // Fallback wordmark if the logo asset can't be loaded.
          doc.setFont("helvetica", "bold"); doc.setFontSize(24); doc.setTextColor(...ORANGE);
          doc.text("Energyfox", 40, 48);
          doc.setFont("helvetica", "normal"); doc.setFontSize(11); doc.setTextColor(148, 163, 184);
          doc.text("Consultants Pvt Ltd", 40, 64);
        }
        doc.setFont("helvetica", "bold"); doc.setFontSize(9); doc.setTextColor(...NAVY);
        rightLines.forEach((ln, i) => doc.text(ln, W - 40, 38 + i * 13, { align: "right" }));
        doc.setFillColor(...NAVY); doc.rect(0, 80, W, 6, "F");
        doc.setFillColor(...ORANGE); doc.rect(0, 86, W, 3, "F");
      };
      const cinGst = ["CIN : U35105KL2023PTC084535", "GST : 32AAHCE8716F1ZR"];
      const centeredTitle = (title: string, y: number) => {
        doc.setFont("helvetica", "bold"); doc.setFontSize(14); doc.setTextColor(30, 41, 59);
        doc.text(title, W / 2, y, { align: "center" });
        const tw = doc.getTextWidth(title);
        doc.setDrawColor(30, 41, 59); doc.setLineWidth(1); doc.line(W / 2 - tw / 2, y + 4, W / 2 + tw / 2, y + 4);
      };
      const kvTable = (startY: number, rows: (string | number)[][], labelWidth = 220) => {
        autoTable(doc, {
          startY,
          body: rows as any,
          theme: "grid",
          styles: { fontSize: 10, cellPadding: 8, textColor: SLATE as any, lineColor: [30, 41, 59] as any, lineWidth: 0.7 },
          columnStyles: { 0: { cellWidth: labelWidth, fontStyle: "bold" } },
          margin: { left: 45, right: 45 },
        });
      };
      const g = (formKey: string, field: string) => String((forms[formKey] || {})[field] || "");

      // ── Page 1: Completion Certificate ──
      header(cinGst);
      centeredTitle("COMPLETION CERTIFICATE", 140);
      doc.setFont("helvetica", "normal"); doc.setFontSize(10.5); doc.setTextColor(...SLATE);
      const para = "Energyfox Consultants Pvt Ltd certify that the installation detailed below has been installed by us and tested to the best of our knowledge and belief, the installation complies with the provision of Central Electricity Authority Regulations and relevant codes of practice for electrical installations.";
      doc.text(doc.splitTextToSize(para, W - 90), 45, 175);
      kvTable(240, [
        ["Name of Consumer", g("completion_letterhead", "name_of_consumer")],
        ["Consumer Number", g("completion_letterhead", "consumer_number")],
        ["KSEB Section", g("completion_letterhead", "kseb_section")],
        ["Capacity", g("completion_letterhead", "capacity")],
        ["Connection Type", g("completion_letterhead", "connection_type")],
        ["Date of Completion", toDisplayDate(g("completion_letterhead", "date_of_completion"))],
      ]);
      doc.setFontSize(9); doc.setTextColor(...NAVY); doc.setFont("helvetica", "bold");
      doc.text("9526 396 823", 45, H - 50);
      doc.text("energyfox.in", W / 2, H - 50, { align: "center" });
      doc.text("info@energyfox.in", W - 45, H - 50, { align: "right" });
      doc.setFont("helvetica", "normal"); doc.setTextColor(...SLATE);
      doc.text("TC 15/4257/2 4th Floor Malankara Avenue pattom TVM - 695004", W / 2, H - 36, { align: "center" });

      // ── Pages 2–4: Details of Installation & Checklist (Customer Details) ──
      // Follows the KSEB template page-for-page: checklist + bank details,
      // plant details, protection functions & signature blocks.
      const cd = (field: string) => g("customer_details", field);
      const checklistStyles = {
        theme: "grid" as const,
        styles: { fontSize: 10, cellPadding: 8, textColor: SLATE as any, lineColor: [30, 41, 59] as any, lineWidth: 0.7 },
        columnStyles: { 0: { cellWidth: 34 }, 1: { cellWidth: 260, fontStyle: "bold" as const } },
        margin: { left: 45, right: 45 },
      };

      doc.addPage();
      header(["4th Floor TC 15/4257/2", "Malankara Avenue pattom", "Thiruvananthapuram Kerala - 695004", "9526396823"]);
      autoTable(doc, {
        startY: 115,
        body: [[{ content: "DETAILS OF INSTALLATION & CHECKLIST TO BE FURNISHED ALONG WITH THE REQUEST FOR TESTING SOLAR INVERTERS", styles: { fontStyle: "bold", fontSize: 10.5 } }]] as any,
        theme: "grid",
        styles: { cellPadding: 8, textColor: SLATE as any, lineColor: [30, 41, 59] as any, lineWidth: 0.7 },
        margin: { left: 45, right: 45 },
      });
      autoTable(doc, {
        ...checklistStyles,
        startY: (doc as any).lastAutoTable.finalY,
        body: [
          ["1", "Name of Electrical Division & Sub Division", cd("electrical_division")],
          ["2", "Name of Electrical Section", cd("electrical_section")],
          ["3", "Consumer No:", cd("consumer_no")],
          ["4", "Tariff", cd("tariff") || "LT-1"],
          ["5", "Connected load", cd("connected_load")],
          ["6", "Name of Solar plant Owner", cd("solar_plant_owner")],
          ["7", "Address", cd("address")],
          ["8", "Email I D", cd("email")],
          ["9", "Contact Phone no. of Consumer", cd("contact_phone")],
          ["10", "Alternate Contact no.", cd("alternate_contact")],
          ["11", { content: "Bank Details", colSpan: 2, styles: { fontStyle: "bold" } }],
          ["a", "Bank Name", cd("bank_name")],
          ["b", "Account No. & Name", cd("account_no_name")],
          ["c", "IFSC Code", cd("ifsc_code")],
          ["12", "Name & Address of Supplier /Installer", "Energyfox Consultants Pvt Ltd"],
          ["13", "Email I D", "energyfoxconsultants@gmail.com"],
          ["14", "Contact Phone no. of Installer", "8606885072"],
        ] as any,
      });

      // Plant details (template page 2 — plain table, no letterhead).
      doc.addPage();
      autoTable(doc, {
        ...checklistStyles,
        startY: 60,
        body: [
          [{ content: "Plant details", colSpan: 3, styles: { fontStyle: "bold" } }],
          ["1", "Type of plant", cd("plant_type")],
          ["2", "Total Capacity of solar plant", cd("total_capacity")],
          ["", "Number of panels", cd("number_of_panels")],
          ["", "Individual Capacity", cd("individual_capacity")],
          ["3", "make & Serial No. of Inverters", cd("inverter_make_serial")],
          ["", "Inverter type single phase/Three phase", cd("inverter_phase")],
          ["", "Inverter capacity", cd("inverter_capacity")],
          ["4", "DC input Voltage", cd("dc_input_voltage")],
          ["5", "Voltage and Number of phase", cd("voltage_phase")],
          ["6", "if the inverter is of hybrid type, whether the scheme confirms to the scheme approved by CE(REES)", cd("hybrid_scheme_confirms") || "NA"],
          ["7", "Whether Completion certificate submitted in Ele.Section", cd("completion_certificate_submitted") || "Yes"],
          ["8", "Whether Energization Approval obtained from Ele", cd("energization_approval_obtained") || "Not Applicable"],
          ["9", "Details of Energization Approval by El", cd("energization_approval_details")],
          ["10", "Whether Dc isolator provided on incoming side of Inverter", cd("dc_isolator_provided") || "Yes"],
          ["11", "Whether Visual Isolator provided before Connectivity point", cd("visual_isolator_provided") || "Yes"],
          ["12", "Whether all wiring connection as per the approved scheme are completed", cd("wiring_completed") || "Yes"],
          ["13", "Whether Earthing provided for Installation as per Standards. (Separate Earthing for AC DB, DC DB, Structure & Panels, LA & body of Invertor, Isolator etc.)", cd("earthing_provided") || "Yes"],
          ["14", "Whether the inverter is equipped with the following protection functions:", cd("protection_functions_equipped") || "Yes"],
        ] as any,
      });

      // Protection settings + signatures (template page 3).
      doc.addPage();
      autoTable(doc, {
        ...checklistStyles,
        startY: 60,
        body: [
          ["a", "Whether Over & Under voltage Trip function provided?", "Yes"],
          ["", "Details of Setting provided in the inverter:", "Over voltage setting: 264 V\nUnder Voltage setting: 192 V\nTrip time setting: 200ms"],
          ["b", "Whether Over & Under frequency Trip function", "Yes"],
          ["", "Details of Setting provided in the inverter:", "Over frequency setting: 50.5 Hz\nUnder frequency setting: 47.5 Hz\nTrip time setting: 200ms"],
          ["c", "Whether protection against unintentional islanding provided?", "Yes"],
          ["d", "Grid Failure Trip delay", "2m seconds"],
          ["e", "Whether Time-delay function for re-energisation after resuming stable grid supply provided?", "Yes"],
          ["", "Details of re-energisation time delay Setting", "60 seconds"],
          [{
            content: "The supplier /installer shall provide any of the following in proof of settings provided in the inverter for protection/function 14(a) & 14(b) listed above.\n(i) Actual setting provided in the inverter, as displayed in the HMI of the inverter or download in to laptop PC/ Mobile Phone which is connected to the device\n(ii) Factory Test certificate issued by the Original Equipment manufacturer or a NABL Accredited LAB showing the serial number of the Inverter & protection function setting provided\n(iii) Report On site, Testing carried out at site by an authorised testing agency with a calibrated test kit; witnessed by KSEB",
            colSpan: 3, styles: { fontSize: 8.5 },
          }],
        ] as any,
      });
      let sy = (doc as any).lastAutoTable.finalY + 34;
      const sline = (left: string, right: string | null, gap: number) => {
        doc.setFont("helvetica", "normal"); doc.setFontSize(10); doc.setTextColor(...SLATE);
        if (left) doc.text(doc.splitTextToSize(left, W - 110), 55, sy);
        if (right) doc.text(right, W - 55, sy, { align: "right" });
        sy += gap;
      };
      // Every date field carries the date the document was generated.
      sline("All the statements furnished above are true and correct", null, 38);
      sline(`Date: ${generatedOn}`, "Signature of Consumer/ installer", 38);
      sline("Remarks of Assistant Engineer:", null, 28);
      sline("Installation inspected and found to be in order. Recommended for pre-energisation testing.", null, 38);
      sline(`Date: ${generatedOn}`, "Signature of Assistant Engineer", 38);
      sline("Recommended for pre-energisation testing.", null, 28);
      sline("", "Signature of Assistant Executive Engineer", 38);
      sline(`Date: ${generatedOn}`, null, 28);
      sline("Pre-energisation testing may be scheduled.", null, 28);
      sline("", "Signature of Executive Engineer", 0);

      // ── Final page: Inverter and Panel Details ──
      doc.addPage();
      header(cinGst);
      centeredTitle("INVERTER AND PANEL DETAILS", 130);
      kvTable(155, [
        ["CUSTOMER NAME", g("inverter_panel_details", "customer_name")],
        ["CUSTOMER CONTACT NO", g("inverter_panel_details", "customer_contact_no")],
        ["CUSTOMER ADDRESS", g("inverter_panel_details", "customer_address")],
        ["SYSTEM MAKE", g("inverter_panel_details", "system_make")],
        ["INVERTER MAKE", g("inverter_panel_details", "inverter_make")],
        ["INVERTER MODEL NO", g("inverter_panel_details", "inverter_model_no")],
        ["INVERTER CAPACITY", g("inverter_panel_details", "inverter_capacity")],
        ["INVERTER SERIAL NUMBER", g("inverter_panel_details", "inverter_serial_number")],
        ["PANEL MAKE", g("inverter_panel_details", "panel_make")],
        ["PANEL CAPACITY", g("inverter_panel_details", "panel_capacity")],
      ], 200);
      const serials = g("inverter_panel_details", "panel_serial_numbers").split(/[\n,;]+/).map(s => s.trim()).filter(Boolean);
      autoTable(doc, {
        startY: (doc as any).lastAutoTable.finalY,
        body: [
          [{ content: "PANEL SERIAL NUMBERS", colSpan: 2, styles: { fontStyle: "bold" } }],
          ...Array.from({ length: 10 }, (_, i) => [{ content: String(i + 1), styles: { halign: "center" } }, serials[i] || ""]),
        ] as any,
        theme: "grid",
        styles: { fontSize: 10, cellPadding: 7, textColor: SLATE as any, lineColor: [30, 41, 59] as any, lineWidth: 0.7 },
        columnStyles: { 0: { cellWidth: 120 } },
        margin: { left: 45, right: 45 },
      });

      const custName = g("completion_letterhead", "name_of_consumer") || g("inverter_panel_details", "customer_name") || `lead-${leadId}`;
      const filename = `Completion_Documents_${custName.replace(/[^\w\- ]+/g, "").trim().replace(/\s+/g, "_")}.pdf`;
      if (isComplete) {
        // Record is locked — nothing can be attached anymore; just download locally.
        doc.save(filename);
      } else {
        // Attach the generated PDF under Annexure 3 Documents (preview/download from there).
        const blob = doc.output("blob");
        const fd = new FormData();
        fd.append("doc_type", ANNEXURE_SLOT);
        fd.append("file", new File([blob], filename, { type: "application/pdf" }));
        const r = await fetch(docsUrl, { method: "POST", headers: authHeader(), body: fd });
        if (r.ok) {
          await refetch();
          alert("Document generated and attached under Annexure 3 Documents.");
        } else {
          const e = await r.json().catch(() => ({}));
          alert(e.error || "Generated, but could not attach — downloading instead.");
          doc.save(filename);
        }
      }
    } catch (e) {
      console.error(e);
      alert("Could not generate the document.");
    } finally {
      setGenerating(false);
    }
  };

  // A generated completion document already attached under Annexure 3 (by filename prefix).
  const generatedDocs = documents.filter(d =>
    d.doc_type === ANNEXURE_SLOT && decodeURIComponent(d.file.split("/").pop() || "").startsWith("Completion_Documents"));
  const hasGenerated = generatedDocs.length > 0;

  const resetGenerated = async () => {
    if (!window.confirm("Reset the generated document? It will be removed from Annexure 3 Documents so you can edit and submit the forms again.")) return;
    try {
      for (const d of generatedDocs) {
        await fetch(`${docsUrl}${d.id}/`, { method: "DELETE", headers: authHeader() });
      }
      await refetch();
    } catch { alert("Network error while resetting."); }
  };

  const submitForm = async () => {
    if (!openForm) return;
    const payload: Record<string, string> = { ...formDraft };
    if (openForm === "inverter_panel_details") {
      payload.panel_serial_numbers = serialDraft.map(s => s.trim()).filter(Boolean).join(", ");
    }
    setFormSaving(true);
    try {
      const r = await fetch(url, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...authHeader() },
        body: JSON.stringify({ [openForm]: payload }),
      });
      if (r.ok) {
        const d = await r.json();
        setForms(prev => ({ ...prev, [openForm]: d[openForm] || payload }));
        setOpenForm(null);
        onChanged?.();
      } else { const e = await r.json().catch(() => ({})); alert(e.error || "Failed to save the form."); }
    } catch { alert("Network error while saving the form."); }
    finally { setFormSaving(false); }
  };

  const saveScalars = async (): Promise<any | null> => {
    // Stage 2 owns discom_approval; the server writes it through to Liasoning.
    // Once signed off, it and the subsidy claim that follows it are the only
    // fields still accepted — KSEB answers late, and the claim can only be filed
    // after it does — so those two go alone.
    const payload = isComplete
      ? { discom_approval: f.discom_approval, subsidy_requested: f.subsidy_requested }
      : f;
    const r = await fetch(url, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...authHeader() },
      body: JSON.stringify(payload),
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

  // Documentation managers / admins can unlock a completed stage for editing.
  const reopen = async () => {
    if (!window.confirm("Unlock Documentation Stage 2 for editing? It can be marked complete again afterwards.")) return;
    setReopening(true);
    try {
      const r = await fetch(`${apiBase}/api/leads/${leadId}/reopen-documentation-stage2/`, {
        method: "POST", headers: authHeader(),
      });
      if (r.ok) { await refetch(); onChanged?.(); }
      else { const e = await r.json().catch(() => ({})); alert(e.error || "Could not unlock this stage."); }
    } catch { alert("Network error while unlocking."); }
    finally { setReopening(false); }
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
                <li key={d.id} className="flex items-center gap-2 text-[11px] bg-slate-50 border border-slate-100 rounded-xl px-3 py-2">
                  <a href={href} target="_blank" rel="noreferrer" className="font-semibold text-emerald-600 hover:underline truncate flex-1 min-w-0" title={name}>{name}</a>
                  <a href={href} target="_blank" rel="noreferrer" title="Open this document"
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-white border border-slate-200 text-slate-600 font-semibold hover:bg-slate-100 hover:text-indigo-600 transition flex-shrink-0">
                    <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" /></svg>
                    Preview
                  </a>
                  {!readOnly && (
                    <button type="button" onClick={() => deleteDoc(d.id)} title="Delete this document"
                      className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-white border border-rose-100 text-rose-600 font-semibold hover:bg-rose-50 transition flex-shrink-0">
                      <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6" /><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" /><path d="M10 11v6M14 11v6" /><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" /></svg>
                      Delete
                    </button>
                  )}
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

  /** The earlier stages' pictures, read-only.
   *
   * A thumbnail where the file is an image and a named chip where it is not —
   * a PDF has no preview to show, and dropping it from the list would quietly
   * hide a document somebody uploaded. Both open the file itself.
   */
  const renderGallery = (rows: (Doc & { label?: string })[], empty: string) => {
    if (rows.length === 0) return <p className="text-[11px] text-slate-400">{empty}</p>;
    return (
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
        {rows.map(d => {
          const href = d.file.startsWith("http") ? d.file : `${apiBase}${d.file}`;
          const name = decodeURIComponent(d.file.split("/").pop() || "file");
          // Named by the server, from the same lists the modules that collected
          // these files label them with — so the two pages cannot drift apart.
          const label = d.label || d.doc_type;
          const isImage = /\.(jpe?g|png|gif|webp|bmp|heic|avif)$/i.test(name);
          return (
            <a key={d.id} href={href} target="_blank" rel="noreferrer" title={`${label} — ${name}`}
              className="group block border border-slate-200 rounded-xl overflow-hidden bg-white hover:border-indigo-300 hover:shadow-sm transition">
              <div className="aspect-[4/3] bg-slate-50 flex items-center justify-center overflow-hidden">
                {isImage ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={href} alt={label} loading="lazy"
                    className="w-full h-full object-cover group-hover:scale-[1.03] transition-transform" />
                ) : (
                  <div className="flex flex-col items-center gap-1 text-slate-400">
                    <svg width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8"
                      strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                      <polyline points="14 2 14 8 20 8" />
                    </svg>
                    <span className="text-[10px] font-semibold uppercase tracking-wide">
                      {(name.split(".").pop() || "file").slice(0, 5)}
                    </span>
                  </div>
                )}
              </div>
              <p className="px-2.5 py-1.5 text-[10px] font-semibold text-slate-600 truncate">{label}</p>
            </a>
          );
        })}
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
          <div className="flex items-center gap-2 flex-wrap">
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-emerald-50 border border-emerald-200 text-emerald-700 rounded-lg text-xs font-semibold">
              ✓ Completed{completedByName ? ` by ${completedByName}` : ""}{completedAt ? ` · ${new Date(completedAt).toLocaleDateString("en-IN")}` : ""}
            </span>
            {canReopen && (
              <button type="button" onClick={reopen} disabled={reopening}
                title="Unlock this stage so it can be edited again"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-200 text-slate-600 rounded-lg text-xs font-semibold hover:bg-slate-50 hover:text-indigo-600 disabled:opacity-50 transition">
                <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><rect x="3" y="11" width="18" height="11" rx="2" /><path d="M7 11V7a5 5 0 0 1 9.9-1" /></svg>
                {reopening ? "Unlocking…" : "Unlock to edit"}
              </button>
            )}
          </div>
        ) : !canEdit ? (
          <span className="text-xs text-slate-400">Read-only.</span>
        ) : null}
      </div>

      {/* The earlier stages' evidence, read-only. Placed above the completion
          docs because that is the order the work happens in: these are what
          Annexure 3 is written from. */}
      <div className={cardCls}>
        <h3 className={sectionTitle}>Documentation Stage 1 Images</h3>
        <p className="text-[11px] text-slate-400 mb-4">
          The site visit&rsquo;s own files, as Documentation Stage 1 shows them.
          Here so the completion documents can be written from them without
          leaving this page.
        </p>
        {renderGallery(earlier.stage1,
          "No site visit files were uploaded for this customer.")}
      </div>

      <div className={cardCls}>
        <h3 className={sectionTitle}>Project Installation Images</h3>
        <p className="text-[11px] text-slate-400 mb-4">
          The geotagged photos taken on site — serial numbers, meter and plant.
        </p>
        {renderGallery(earlier.installation,
          "The installation photos have not been uploaded yet.")}
      </div>

      {/* 1. Completion docs / Annexure 3 */}
      <div className={cardCls}>
        <h3 className={sectionTitle}>Completion Docs — Annexure 3</h3>
        <p className="text-[11px] text-slate-400 mb-4">Set of documents given to KSEB, prepared right after the project uploads the installation photos.</p>

        <div className="mb-4">
          <label className={labelCls}>Annexure 3 Documents</label>
          {renderDocSlot(ANNEXURE_SLOT)}
        </div>

        <div className="mb-4">
          <label className={labelCls}>Completion Forms</label>
          <div className="flex flex-wrap items-center gap-2">
            {COMPLETION_FORMS.map(form => {
              const filled = Object.values(forms[form.key] || {}).some(v => String(v || "").trim());
              return (
                <button key={form.key} type="button" onClick={() => openModal(form.key)}
                  className="inline-flex items-center gap-1.5 px-4 py-2 bg-indigo-50 text-indigo-700 border border-indigo-100 rounded-xl text-xs font-semibold hover:bg-indigo-100 transition">
                  {form.label}
                  {filled && <span className="text-emerald-600">✓</span>}
                </button>
              );
            })}
            {!hasGenerated ? (
              <button type="button" onClick={generateDoc} disabled={generating}
                title="Generate the combined completion document (3 pages) and attach it under Annexure 3 Documents"
                className="inline-flex items-center gap-1.5 px-4 py-2 bg-slate-800 text-white rounded-xl text-xs font-semibold hover:bg-slate-900 disabled:opacity-50 transition shadow-sm">
                <svg width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line x1="12" y1="15" x2="12" y2="3" /></svg>
                {generating ? "Generating…" : "Generate Document"}
              </button>
            ) : (
              <>
                <span className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-600">✓ Document generated — see Annexure 3 Documents above</span>
                {!readOnly && (
                  <button type="button" onClick={resetGenerated}
                    title="Remove the generated document so the forms can be edited and submitted again"
                    className="inline-flex items-center gap-1.5 px-4 py-2 bg-rose-50 text-rose-700 border border-rose-100 rounded-xl text-xs font-semibold hover:bg-rose-100 transition">
                    Reset
                  </button>
                )}
              </>
            )}
          </div>
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
            {/* Recorded here even after Stage 2 is signed off — KSEB answers on
                its own schedule — and it reflects into Liasoning. */}
            <select value={f.discom_approval} disabled={!canEdit}
              onChange={e => set("discom_approval", e.target.value)} className={inputCls}>
              {DISCOM_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
            <p className="text-[10px] text-slate-400 mt-1.5">Reflects into Liasoning for the liasoning officer.</p>
            {/* The page's Save button is gone once Stage 2 is signed off, but the
                approval can still land after that — so it gets its own. */}
            {canEdit && isComplete && (
              <button onClick={save} disabled={saving}
                className="mt-2 px-4 py-2 bg-slate-800 text-white rounded-xl text-xs font-semibold hover:bg-slate-900 disabled:opacity-50 transition">
                {saving ? "Saving…" : saved ? "Saved ✓" : "Save approval"}
              </button>
            )}
          </div>
          <div className="sm:col-span-2"><label className={labelCls}>Remark</label><input value={f.mnre_remark} disabled={readOnly} onChange={e => set("mnre_remark", e.target.value)} placeholder="Remark" className={inputCls} /></div>
        </div>

        {f.discom_approval === "yes" && (
          <div className="mt-4 bg-emerald-50/60 border border-emerald-100 rounded-xl p-3 flex flex-col items-start gap-3">
            {/* Like the approval above it, this survives the sign-off: the claim
                can only go in once KSEB has answered, which is often after Stage
                2 is closed. The customer's tracking link shows this step.

                Laid out as a column with a gap rather than a margin on the
                button: the button is an inline-block, so a margin-top alone
                left it on the same line as the label, touching it. */}
            <Check checked={f.subsidy_requested} disabled={!canEdit} onChange={v => set("subsidy_requested", v)} label="Subsidy requested" />
            {canEdit && isComplete && (
              <button onClick={save} disabled={saving}
                className="px-4 py-2 bg-slate-800 text-white rounded-xl text-xs font-semibold hover:bg-slate-900 disabled:opacity-50 transition">
                {saving ? "Saving…" : saved ? "Saved ✓" : "Save subsidy status"}
              </button>
            )}
          </div>
        )}
        {f.discom_approval !== "yes" && (
          <div className="mt-4 bg-amber-50/60 border border-amber-100 rounded-xl p-3">
            <p className="text-[11px] text-amber-700 font-semibold">
              {/* Discom Follow-up belongs to Liasoning now, so this is a status
                  line rather than a link the documentation team can follow. */}
              {f.discom_approval === "no"
                ? "Not approved — this customer is on the liasoning officer's Discom Follow-up list"
                : "Approval pending — this customer joins the liasoning officer's Discom Follow-up list if still pending after 7 days"}
              {f.sent_to_liasoning ? " (officer sent to the concerned section)." : "."}
            </p>
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

      {/* Completion-doc form modal */}
      {openForm && (() => {
        const form = COMPLETION_FORMS.find(x => x.key === openForm);
        if (!form) return null;
        // Forms lock once the combined document is generated — Reset to edit again.
        const modalReadOnly = readOnly || hasGenerated;
        const gridFields = form.fields.filter(([k]) => k !== "panel_serial_numbers");
        const hasSerials = form.key === "inverter_panel_details";
        return (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
            <div className="bg-white w-full max-w-2xl rounded-2xl shadow-2xl max-h-[90vh] overflow-hidden flex flex-col" onClick={e => e.stopPropagation()}>
              <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 flex-shrink-0">
                <h2 className="text-base font-bold text-slate-900">{form.label}</h2>
                <button onClick={() => setOpenForm(null)} className="w-8 h-8 flex items-center justify-center rounded-xl bg-slate-100 text-slate-500 hover:bg-slate-200 transition text-sm">✕</button>
              </div>
              <div className="overflow-y-auto flex-1 px-6 py-5">
                {hasGenerated && !readOnly && (
                  <p className="mb-4 text-[11px] font-semibold text-amber-700 bg-amber-50 border border-amber-100 rounded-xl px-3 py-2">
                    Document already generated — click Reset (next to Generate Document) to edit and submit again.
                  </p>
                )}
                <div className="grid sm:grid-cols-2 gap-4">
                  {gridFields.map(([k, lbl, options]) => (
                    <div key={k}>
                      <label className={labelCls}>{lbl}</label>
                      {options === "date" ? (
                        <input type="date" value={toISODate(formDraft[k])} disabled={modalReadOnly}
                          onChange={e => setFormDraft(p => ({ ...p, [k]: e.target.value }))}
                          className={inputCls} />
                      ) : options ? (
                        <select value={formDraft[k] || options[0]} disabled={modalReadOnly}
                          onChange={e => setFormDraft(p => ({ ...p, [k]: e.target.value }))}
                          className={inputCls}>
                          {options.map(o => <option key={o} value={o}>{o}</option>)}
                        </select>
                      ) : (
                        <input value={formDraft[k] || ""} disabled={modalReadOnly}
                          onChange={e => setFormDraft(p => ({ ...p, [k]: e.target.value }))}
                          placeholder={lbl} className={inputCls} />
                      )}
                    </div>
                  ))}
                </div>
                {hasSerials && (
                  <div className="mt-5">
                    <label className={labelCls}>Panel Serial Numbers</label>
                    <div className="space-y-2">
                      {serialDraft.map((s, i) => (
                        <div key={i} className="flex items-center gap-2">
                          <span className="w-6 text-right text-[11px] font-bold text-slate-400 flex-shrink-0">{i + 1}.</span>
                          <input value={s} disabled={modalReadOnly}
                            onChange={e => setSerialDraft(p => p.map((v, j) => (j === i ? e.target.value : v)))}
                            placeholder={`Panel serial number ${i + 1}`} className={inputCls} />
                          {!modalReadOnly && serialDraft.length > 1 && (
                            <button type="button" title="Remove"
                              onClick={() => setSerialDraft(p => p.filter((_, j) => j !== i))}
                              className="w-8 h-8 flex-shrink-0 flex items-center justify-center rounded-lg text-rose-500 hover:bg-rose-50 font-bold transition">✕</button>
                          )}
                        </div>
                      ))}
                    </div>
                    {!modalReadOnly && (
                      <button type="button" onClick={() => setSerialDraft(p => [...p, ""])}
                        className="mt-2 inline-flex items-center gap-1.5 px-3 py-1.5 bg-slate-100 text-slate-700 rounded-lg text-[11px] font-semibold hover:bg-slate-200 transition">
                        + Add Serial Number
                      </button>
                    )}
                  </div>
                )}
              </div>
              <div className="px-6 py-4 border-t border-slate-100 flex justify-end gap-3 flex-shrink-0">
                <button onClick={() => setOpenForm(null)} className="px-4 py-2.5 border border-slate-200 rounded-xl text-sm font-semibold text-slate-600 hover:bg-slate-50 transition">Cancel</button>
                {!modalReadOnly && (
                  <button onClick={submitForm} disabled={formSaving}
                    className="px-5 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 disabled:opacity-50 transition">
                    {formSaving ? "Submitting…" : "Submit"}
                  </button>
                )}
              </div>
            </div>
          </div>
        );
      })()}
    </div>
  );
}

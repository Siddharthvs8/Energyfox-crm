"use client";
/**
 * The quotations raised for one customer, on that customer's own page.
 *
 * A BDE sitting with a lead needs to put a number in front of them without
 * leaving the record — so a quotation can be raised, sent and downloaded from
 * here. It is the same document the Quotation module lists; this is a second
 * door onto it, not a second copy of it.
 *
 * The form it opens is the same one the module opens — imported, not copied —
 * with this customer already fixed. A quotation raised from a lead is not a
 * lesser document than one raised from the module, and a BDE sitting with a
 * customer should not have to finish it somewhere else.
 */
import { useCallback, useEffect, useState } from "react";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";
import { buildProformaPdf, proformaFileName } from "@/lib/proformaPdf";
import QuotationFormModal, { VARIANTS, money }
  from "@/components/QuotationFormModal";
import QuotationPreviewModal from "@/components/QuotationPreviewModal";

type Quotation = {
  id: number; number: string; status: string; project_name: string | null;
  price_variant: string; grand_total: string; discount_amount: string;
  pdf: string | null; converted_quote: number | null; quotation_date: string | null;
};

const STATUS_STYLE: Record<string, string> = {
  draft: "bg-slate-100 text-slate-600",
  sent: "bg-blue-50 text-blue-700",
  accepted: "bg-emerald-50 text-emerald-700",
  declined: "bg-rose-50 text-rose-700",
  converted: "bg-indigo-50 text-indigo-700",
};

export default function LeadQuotationsPanel({ leadId, customerEmail }: {
  leadId: number | string;
  customerEmail?: string | null;
}) {
  const api = getApiBase(APP_SLUG);
  const token = () => localStorage.getItem(`${APP_SLUG}_access`);
  const headers = useCallback(() => ({
    "Content-Type": "application/json", Authorization: `Bearer ${token()}`,
  }), []);

  const [rows, setRows] = useState<Quotation[]>([]);
  const [open, setOpen] = useState(false);
  const [preview, setPreview] = useState<Quotation | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await fetch(`${api}/api/quotations/?lead=${leadId}`, { headers: headers() });
      if (r.ok) {
        const d = await r.json();
        setRows(Array.isArray(d) ? d : (d.results || []));
      }
    } catch { /* the panel simply offers to create one */ }
  }, [api, leadId, headers]);

  useEffect(() => { load(); }, [load]);

  const pdfFor = async (q: Quotation) => {
    const r = await fetch(`${api}/api/quotations/${q.id}/document/`, { headers: headers() });
    if (!r.ok) throw new Error("document");
    return buildProformaPdf(await r.json());
  };

  const download = async (q: Quotation) => {
    setBusy(q.id); setNote(null);
    try {
      const doc = await pdfFor(q);
      doc.save(`${proformaFileName(q.number, null)}.pdf`);
    } catch { setNote({ ok: false, text: "Could not build the PDF." }); }
    finally { setBusy(null); }
  };

  const send = async (q: Quotation) => {
    setBusy(q.id); setNote(null);
    try {
      const doc = await pdfFor(q);
      const fd = new FormData();
      fd.append("pdf", doc.output("blob"), `${proformaFileName(q.number, null)}.pdf`);
      fd.append("channels", "email");
      const r = await fetch(`${api}/api/quotations/${q.id}/send/`, {
        method: "POST", headers: { Authorization: `Bearer ${token()}` }, body: fd });
      const d = await r.json().catch(() => ({}));
      setNote(d.sent
        ? { ok: true, text: `${q.number} sent to ${d.sent_to || customerEmail || "the customer"}.` }
        : { ok: false, text: d.error || (d.failures || []).join(" ") || "Could not send it." });
      await load();
    } catch { setNote({ ok: false, text: "Could not send this quotation." }); }
    finally { setBusy(null); }
  };

  return (
    <div className="bg-white rounded-2xl border border-slate-100 p-6">
      <div className="flex flex-wrap justify-between items-center gap-3 mb-4">
        <div>
          <h2 className="font-semibold text-slate-900">Quotations</h2>
          <p className="text-[11px] text-slate-400 mt-0.5">
            Raised for this customer — also listed in Inventory → Quotation.
          </p>
        </div>
        <button onClick={() => setOpen(true)}
          className="text-xs font-semibold text-indigo-600 hover:text-indigo-800 transition">
          + New quotation
        </button>
      </div>

      {rows.length === 0 ? (
        <p className="text-sm text-slate-400">No quotations for this customer yet.</p>
      ) : (
        <div className="space-y-2">
          {rows.map(q => (
            <div key={q.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 border border-slate-100 rounded-xl px-4 py-3">
              <div className="min-w-0">
                <button onClick={() => setPreview(q)}
                  className="text-sm font-semibold text-slate-900 hover:text-indigo-600 transition">
                  {q.number}
                </button>
                <p className="text-[11px] text-slate-400 truncate">
                  {q.project_name || "No project"}
                  {" · "}{VARIANTS.find(([k]) => k === q.price_variant)?.[1]}
                  {Number(q.discount_amount) > 0 && ` · ₹${money(q.discount_amount)} off`}
                </p>
              </div>
              <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wide ${
                STATUS_STYLE[q.status] || "bg-slate-100 text-slate-600"}`}>{q.status}</span>
              <span className="text-sm font-bold text-slate-900 ml-auto">₹{money(q.grand_total)}</span>
              <div className="flex items-center gap-3 text-xs font-bold">
                <button onClick={() => download(q)} disabled={busy === q.id}
                  className="text-slate-500 hover:text-slate-800 disabled:opacity-40">Download</button>
                <button onClick={() => send(q)} disabled={busy === q.id}
                  title={customerEmail ? `Email ${customerEmail}` : "This customer has no email on file"}
                  className="text-slate-500 hover:text-slate-800 disabled:opacity-40">Send</button>
                <button onClick={() => setPreview(q)}
                  className="text-indigo-600 hover:text-indigo-800">Open</button>
              </div>
            </div>
          ))}
        </div>
      )}

      {note && (
        <p className={`mt-3 text-[12px] font-medium ${note.ok ? "text-emerald-600" : "text-rose-600"}`}>
          {note.text}
        </p>
      )}

      <QuotationPreviewModal quotation={preview}
        onClose={() => setPreview(null)} onSent={load} />

      {/* The module's own form, with this customer fixed — see the header note. */}
      <QuotationFormModal
        open={open} editing={null} lockedLeadId={leadId}
        onClose={() => setOpen(false)}
        onSaved={() => { setNote({ ok: true, text: "Quotation saved." }); load(); }} />
    </div>
  );
}

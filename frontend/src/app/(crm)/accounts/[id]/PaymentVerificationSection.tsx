"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase, formatCurrency } from "@/lib/mock-data";
import { downloadLeadReceipt, sendLeadReceipt } from "@/lib/receipt-pdf";
import React, { useCallback, useEffect, useState } from "react";

const PAYMENT_MODES = [
  { value: "cash", label: "Cash" },
  { value: "cheque", label: "Cheque" },
  { value: "card", label: "Card" },
  { value: "upi", label: "UPI" },
  { value: "loan", label: "Loan" },
];
// Modes that need a UTR / transaction reference. Cash has none, and a loan
// disbursement is evidenced by the sanction rather than a transaction id.
const UTR_MODES = ["cheque", "card", "upi"];

const inputCls =
  "w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all disabled:opacity-70 disabled:cursor-not-allowed";
const labelCls = "block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5";

const toNum = (v: any) => {
  const n = parseFloat(v);
  return Number.isFinite(n) ? n : 0;
};

export default function PaymentVerificationSection({ leadId, canEdit, canReopen, dealValue,
                                                     customerEmail, customerPhone, onChanged }: {
  leadId: number | string; canEdit: boolean; canReopen?: boolean; dealValue: number;
  customerEmail?: string | null; customerPhone?: string | null; onChanged?: () => void;
}) {
  const apiBase = getApiBase(APP_SLUG);
  const url = `${apiBase}/api/leads/${leadId}/payment-verification/`;
  const authHeader = () => ({ Authorization: `Bearer ${localStorage.getItem(`${APP_SLUG}_access`)}` });

  const [amountReceived, setAmountReceived] = useState("");
  const [discountValue, setDiscountValue] = useState("");
  const [paymentMode, setPaymentMode] = useState("");
  const [utrDetails, setUtrDetails] = useState("");
  const [onAccountOf, setOnAccountOf] = useState("");
  const [discountGivenBy, setDiscountGivenBy] = useState("");
  const [remarks, setRemarks] = useState("");
  const [isComplete, setIsComplete] = useState(false);
  const [completedByName, setCompletedByName] = useState<string | null>(null);
  const [completedAt, setCompletedAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [completing, setCompleting] = useState(false);
  const [saved, setSaved] = useState(false);
  const [sending, setSending] = useState(false);

  const load = useCallback((d: any) => {
    setAmountReceived(d.amount_received != null ? String(d.amount_received) : "");
    setDiscountValue(d.discount_value != null ? String(d.discount_value) : "");
    setPaymentMode(d.payment_mode || "");
    setUtrDetails(d.utr_details || "");
    setOnAccountOf(d.on_account_of || "");
    setDiscountGivenBy(d.discount_given_by || "");
    setRemarks(d.remarks || "");
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
  const needsUtr = UTR_MODES.includes(paymentMode);
  const balance = toNum(dealValue) - toNum(amountReceived) - toNum(discountValue);
  const ready = !!paymentMode && (!needsUtr || !!utrDetails.trim());

  const change = (setter: (v: string) => void) => (v: string) => { setter(v); setSaved(false); };

  const saveScalars = async (): Promise<any | null> => {
    const r = await fetch(url, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...authHeader() },
      body: JSON.stringify({
        amount_received: toNum(amountReceived),
        discount_value: toNum(discountValue),
        payment_mode: paymentMode,
        utr_details: needsUtr ? utrDetails : "",
        on_account_of: onAccountOf,
        discount_given_by: discountGivenBy,
        remarks,
      }),
    });
    if (!r.ok) { const e = await r.json().catch(() => ({})); alert(e.error || "Failed to save payment verification."); return null; }
    return r.json();
  };

  const save = async () => {
    // Payment mode is mandatory, so a record can't be saved without it.
    if (!paymentMode) { alert("Select a payment mode — it is required."); return; }
    if (needsUtr && !utrDetails.trim()) { alert(`Enter the UTR / transaction details for ${paymentMode} payments.`); return; }
    setSaving(true);
    try {
      const latest = await saveScalars();
      if (latest) { load(latest); setSaved(true); onChanged?.(); }
    } catch { alert("Network error while saving."); }
    finally { setSaving(false); }
  };

  const complete = async () => {
    if (!ready) { alert("Select a payment mode (and UTR details for non-cash payments) first."); return; }
    setCompleting(true);
    try {
      const latest = await saveScalars();
      if (!latest) return;
      const r = await fetch(`${apiBase}/api/leads/${leadId}/complete-payment-verification/`, { method: "POST", headers: authHeader() });
      if (r.ok) {
        const d = await r.json();
        if (d.payment_verification) load(d.payment_verification);
        else { load(latest); setIsComplete(true); }
        onChanged?.();
        alert("Payment verification completed.");
      } else {
        const d = await r.json().catch(() => ({}));
        alert(d.error || "Could not complete payment verification.");
      }
    } catch { alert("Network error while completing."); }
    finally { setCompleting(false); }
  };

  const reopen = async () => {
    if (!window.confirm("Reopen this completed payment verification for editing?")) return;
    try {
      const r = await fetch(`${apiBase}/api/leads/${leadId}/reopen-payment-verification/`, { method: "POST", headers: authHeader() });
      if (r.ok) {
        const d = await r.json();
        if (d.payment_verification) load(d.payment_verification);
        else setIsComplete(false);
        onChanged?.();
      } else {
        const d = await r.json().catch(() => ({}));
        alert(d.error || "Could not reopen.");
      }
    } catch { alert("Network error while reopening."); }
  };

  /** Ask where it should go, then render and hand it to the server. */
  const askAndSend = async (channel: "email" | "whatsapp") => {
    const label = channel === "email" ? "email address" : "WhatsApp number";
    // Pre-filled from the customer's own record — still editable, because a
    // receipt sometimes goes to a spouse or an accountant instead.
    const known = (channel === "email" ? customerEmail : customerPhone) || "";
    const to = window.prompt(`Send the receipt to which ${label}?`, known);
    if (!to) return;
    setSending(true);
    try {
      await sendLeadReceipt(leadId, channel, to, { initial: true });
    } catch {
      alert("Network error while sending the receipt.");
    } finally {
      setSending(false);
    }
  };

  const cardCls = "bg-white border border-slate-200 rounded-2xl shadow-sm p-5";

  if (loading) {
    return <div className={`mt-5 ${cardCls} text-sm text-slate-400`}>Loading payment verification…</div>;
  }

  return (
    <div className="mt-5 space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-bold text-slate-900">Payment Verification</h2>
          <p className="text-xs text-slate-400 mt-0.5">Filled by the assigned accounts staff.</p>
        </div>
        {isComplete ? (
          <div className="flex items-center gap-3 flex-wrap">
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-emerald-50 border border-emerald-200 text-emerald-700 rounded-lg text-xs font-semibold">
              ✓ Verified{completedByName ? ` by ${completedByName}` : ""}{completedAt ? ` · ${new Date(completedAt).toLocaleDateString("en-IN")}` : ""}
            </span>
            <button onClick={() => downloadLeadReceipt(leadId, { initial: true })}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 text-white rounded-lg text-xs font-semibold hover:bg-indigo-700 transition">
              <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line x1="12" y1="15" x2="12" y2="3" /></svg>
              Download Receipt
            </button>
            <button onClick={() => askAndSend("email")} disabled={sending}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-300 text-slate-700 rounded-lg text-xs font-semibold hover:bg-slate-50 transition disabled:opacity-40">
              {sending ? "Sending…" : "Email Receipt"}
            </button>
            <button onClick={() => askAndSend("whatsapp")} disabled={sending}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 text-white rounded-lg text-xs font-semibold hover:bg-emerald-700 transition disabled:opacity-40">
              {sending ? "Sending…" : "WhatsApp Receipt"}
            </button>
            {canReopen && (
              <button onClick={reopen} className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-300 text-slate-700 rounded-lg text-xs font-semibold hover:bg-slate-50 transition">
                Reopen for editing
              </button>
            )}
          </div>
        ) : !canEdit ? (
          <span className="text-xs text-slate-400">Read-only — not assigned to you.</span>
        ) : null}
      </div>

      <div className={cardCls}>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-4">
          {/* Deal value — fetched from BDE/sales info, read-only */}
          <div>
            <label className={labelCls}>Deal Value</label>
            <input value={dealValue ? `₹${formatCurrency(dealValue)}` : "—"} disabled className={inputCls} />
            <p className="text-[10px] text-slate-400 mt-1">From the lead&apos;s deal value.</p>
          </div>

          <div>
            <label className={labelCls}>Amount Received</label>
            <input type="number" min="0" step="0.01" value={amountReceived} disabled={readOnly}
              onChange={e => change(setAmountReceived)(e.target.value)} placeholder="0.00" className={inputCls} />
          </div>

          <div>
            <label className={labelCls}>Discount Value</label>
            <input type="number" min="0" step="0.01" value={discountValue} disabled={readOnly}
              onChange={e => change(setDiscountValue)(e.target.value)} placeholder="0.00" className={inputCls} />
          </div>

          <div>
            <label className={labelCls}>Payment Mode <span className="text-rose-500 normal-case">*</span></label>
            <select value={paymentMode} disabled={readOnly}
              onChange={e => change(setPaymentMode)(e.target.value)}
              className={`${inputCls} ${!paymentMode && !readOnly ? "border-rose-300 bg-rose-50/40" : ""}`}>
              <option value="">—</option>
              {PAYMENT_MODES.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
            </select>
            {!paymentMode && !readOnly && <p className="text-[11px] text-rose-500 mt-1">Required.</p>}
          </div>

          {/* UTR / transaction reference — only for non-cash modes */}
          {needsUtr && (
            <div>
              <label className={labelCls}>UTR / Transaction Details <span className="text-rose-500 normal-case">*</span></label>
              <input value={utrDetails} disabled={readOnly} onChange={e => change(setUtrDetails)(e.target.value)}
                placeholder="Transaction / reference no."
                className={`${inputCls} ${!utrDetails.trim() && !readOnly ? "border-rose-300 bg-rose-50/40" : ""}`} />
              {!utrDetails.trim() && !readOnly && <p className="text-[11px] text-rose-500 mt-1">Required for {paymentMode} payments.</p>}
            </div>
          )}

          <div>
            <label className={labelCls}>On Account of</label>
            <input value={onAccountOf} disabled={readOnly} onChange={e => change(setOnAccountOf)(e.target.value)}
              placeholder="e.g. 10 kW Margin Money" className={inputCls} />
            <p className="text-[10px] text-slate-400 mt-1">Printed on the receipt.</p>
          </div>

          <div>
            <label className={labelCls}>Discount Given By</label>
            <input value={discountGivenBy} disabled={readOnly} onChange={e => change(setDiscountGivenBy)(e.target.value)}
              placeholder="Name of authorised personnel" className={inputCls} />
          </div>

          <div className="sm:col-span-2 lg:col-span-3">
            <label className={labelCls}>Remarks</label>
            <textarea value={remarks} disabled={readOnly} rows={2}
              onChange={e => change(setRemarks)(e.target.value)}
              placeholder="Anything worth recording about this payment"
              className={inputCls} />
          </div>

          {/* Balance — derived: deal value − amount received − discount */}
          <div>
            <label className={labelCls}>Balance to be Received</label>
            <input value={`₹${formatCurrency(balance)}`} disabled
              className={`${inputCls} font-semibold ${balance > 0 ? "text-amber-600" : "text-emerald-600"}`} />
            <p className="text-[10px] text-slate-400 mt-1">Deal value − amount received − discount.</p>
          </div>
        </div>
      </div>

      {canEdit && !isComplete && (
        <div className="flex flex-wrap items-center gap-3">
          <button onClick={save} disabled={saving || completing || !ready}
            title={!ready ? "Select a payment mode (and UTR for non-cash) first" : ""}
            className="px-5 py-2.5 bg-slate-800 text-white rounded-xl text-sm font-semibold hover:bg-slate-900 disabled:opacity-50 disabled:cursor-not-allowed transition">
            {saving ? "Saving…" : saved ? "Saved ✓" : "Save"}
          </button>
          <button onClick={complete} disabled={completing || saving || !ready} title={!ready ? "Select a payment mode (and UTR for non-cash) first" : ""}
            className="px-5 py-2.5 bg-emerald-600 text-white rounded-xl text-sm font-semibold hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed transition">
            {completing ? "Completing…" : "Payment Verified"}
          </button>
          {!ready && <span className="text-xs text-slate-400">Select a payment mode (and UTR for non-cash) to verify.</span>}
        </div>
      )}
    </div>
  );
}

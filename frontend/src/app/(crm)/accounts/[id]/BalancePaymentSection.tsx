"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase, formatCurrency } from "@/lib/mock-data";
import React, { useCallback, useEffect, useState } from "react";

const PAYMENT_MODES = [
  { value: "", label: "—" },
  { value: "cash", label: "Cash" },
  { value: "cheque", label: "Cheque" },
  { value: "card", label: "Card" },
  { value: "upi", label: "UPI" },
];
const UTR_MODES = ["cheque", "card", "upi"];

const inputCls =
  "w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all disabled:opacity-70";
const labelCls = "block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5";

type BP = { id: number; amount: string; payment_mode: string; utr_details: string; note: string; recorded_by_name: string | null; created_at: string };
type Summary = { deal_value: string; amount_received: string; discount_value: string; balance_amount: string; fully_paid: boolean; can_collect: boolean; payments: BP[] };

const num = (v: any) => { const n = parseFloat(v); return Number.isFinite(n) ? n : 0; };

export default function BalancePaymentSection({ leadId, canEdit, onChanged }: {
  leadId: number | string; canEdit: boolean; onChanged?: () => void;
}) {
  const apiBase = getApiBase(APP_SLUG);
  const url = `${apiBase}/api/leads/${leadId}/balance-payments/`;
  const authHeader = () => ({ Authorization: `Bearer ${localStorage.getItem(`${APP_SLUG}_access`)}` });

  const [summary, setSummary] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(true);
  const [amount, setAmount] = useState("");
  const [mode, setMode] = useState("");
  const [utr, setUtr] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback((d: Summary) => setSummary(d), []);

  useEffect(() => {
    if (!localStorage.getItem(`${APP_SLUG}_access`)) { setLoading(false); return; }
    fetch(url, { headers: authHeader() })
      .then(r => (r.ok ? r.json() : null))
      .then(d => { if (d) load(d); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [leadId]); // eslint-disable-line react-hooks/exhaustive-deps

  const needsUtr = UTR_MODES.includes(mode);

  const addPayment = async () => {
    const amt = num(amount);
    if (amt <= 0) { alert("Enter a valid payment amount greater than zero."); return; }
    if (needsUtr && !utr.trim()) { alert("Enter the UTR / transaction reference for non-cash payments."); return; }
    setSaving(true);
    try {
      const r = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeader() },
        body: JSON.stringify({ amount: amt, payment_mode: mode, utr_details: needsUtr ? utr : "", note }),
      });
      if (r.ok) {
        const d = await r.json();
        load(d);
        setAmount(""); setMode(""); setUtr(""); setNote("");
        onChanged?.();
      } else { const e = await r.json().catch(() => ({})); alert(e.error || "Could not record the balance payment."); }
    } catch { alert("Network error while recording the payment."); }
    finally { setSaving(false); }
  };

  const cardCls = "bg-white border border-slate-200 rounded-2xl shadow-sm p-5";
  if (loading) return <div className={`mt-5 ${cardCls} text-sm text-slate-400`}>Loading balance…</div>;
  if (!summary) return null;

  const balance = num(summary.balance_amount);
  const fully = summary.fully_paid;
  const canCollect = canEdit && summary.can_collect && !fully;

  const Tile = ({ label, value, tone }: { label: string; value: string; tone?: string }) => (
    <div className="bg-slate-50 border border-slate-100 rounded-xl p-4">
      <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">{label}</p>
      <p className={`text-lg font-black ${tone || "text-slate-800"}`}>{value}</p>
    </div>
  );

  return (
    <div className="mt-5 space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-bold text-slate-900">Balance Payments</h2>
          <p className="text-xs text-slate-400 mt-0.5">Record balance / installment payments until the deal value is fully received.</p>
        </div>
        <span className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border ${fully ? "bg-emerald-50 border-emerald-200 text-emerald-700" : "bg-amber-50 border-amber-200 text-amber-700"}`}>
          {fully ? "✓ Fully Paid" : "⏳ Partially Paid"}
        </span>
      </div>

      <div className={cardCls}>
        <div className="grid sm:grid-cols-3 gap-4">
          <Tile label="Deal Value" value={`₹${formatCurrency(num(summary.deal_value))}`} />
          <Tile label="Received" value={`₹${formatCurrency(num(summary.amount_received))}`} tone="text-emerald-600" />
          <Tile label="Balance Due" value={`₹${formatCurrency(balance)}`} tone={balance > 0 ? "text-amber-600" : "text-emerald-600"} />
        </div>

        {canCollect && (
          <div className="mt-5 border-t border-slate-100 pt-5">
            <h3 className="text-xs font-bold text-indigo-600 uppercase tracking-wide mb-3">Add Balance Payment</h3>
            <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-x-6 gap-y-4">
              <div>
                <label className={labelCls}>Amount</label>
                <input type="number" min="0" step="0.01" value={amount} onChange={e => setAmount(e.target.value)} placeholder="0.00" className={inputCls} />
                <p className="text-[10px] text-slate-400 mt-1">Balance due: ₹{formatCurrency(balance)}</p>
              </div>
              <div>
                <label className={labelCls}>Payment Mode</label>
                <select value={mode} onChange={e => setMode(e.target.value)} className={inputCls}>
                  {PAYMENT_MODES.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
                </select>
              </div>
              {needsUtr && (
                <div>
                  <label className={labelCls}>UTR / Transaction Details</label>
                  <input value={utr} onChange={e => setUtr(e.target.value)} placeholder="Transaction / reference no." className={inputCls} />
                </div>
              )}
              <div>
                <label className={labelCls}>Note</label>
                <input value={note} onChange={e => setNote(e.target.value)} placeholder="Optional note" className={inputCls} />
              </div>
            </div>
            <button onClick={addPayment} disabled={saving || num(amount) <= 0}
              className="mt-4 px-5 py-2.5 bg-emerald-600 text-white rounded-xl text-sm font-semibold hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed transition">
              {saving ? "Recording…" : "Record Payment"}
            </button>
          </div>
        )}

        {fully && (
          <p className="mt-4 text-xs text-emerald-700 font-semibold">✓ Full payment received — no balance due.</p>
        )}

        {/* Payment history */}
        {summary.payments.length > 0 && (
          <div className="mt-5 border-t border-slate-100 pt-4">
            <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wide mb-2">Payment History</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-[10px] font-bold text-slate-400 uppercase tracking-wide border-b border-slate-100">
                    <th className="py-2 pr-4">Date</th>
                    <th className="py-2 pr-4">Amount</th>
                    <th className="py-2 pr-4">Mode</th>
                    <th className="py-2 pr-4">Note</th>
                    <th className="py-2 pr-4">Recorded By</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.payments.map(p => (
                    <tr key={p.id} className="border-b border-slate-50">
                      <td className="py-2 pr-4 text-slate-600">{new Date(p.created_at).toLocaleDateString("en-IN")}</td>
                      <td className="py-2 pr-4 font-semibold text-emerald-700">₹{formatCurrency(num(p.amount))}</td>
                      <td className="py-2 pr-4 text-slate-600 capitalize">{p.payment_mode || "—"}{p.utr_details ? ` · ${p.utr_details}` : ""}</td>
                      <td className="py-2 pr-4 text-slate-600">{p.note || "—"}</td>
                      <td className="py-2 pr-4 text-slate-600">{p.recorded_by_name || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

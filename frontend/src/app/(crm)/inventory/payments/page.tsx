"use client";
/**
 * Inventory → Payments (wholesale).
 *
 * Every document money has been verified against, in three sections that do not
 * overlap — so a document appears once and the tab counts add up:
 *
 *   Fully paid     — settled, in real money.
 *   Partially paid — some received, a balance still owing.
 *   Credit         — released on terms. Credit settles an invoice, so without a
 *                    section of its own it would sit under "fully paid" and hide
 *                    the fact that no money came in.
 *
 * Deliveries and proformas both appear. A proforma takes its instalments before
 * it becomes a delivery, and leaving those out would hide part-paid business
 * exactly while it is part-paid.
 */
import React, { useState } from "react";
import Link from "next/link";
import { rupee, useStock, StockPage, Empty, I } from "../shared";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";

type PaymentRow = {
  id: number; amount_received: string; mode: string; mode_label: string;
  reference: string; paid_on: string | null; notes: string;
  verified_by: string | null; verified_at: string | null;
};

type Row = {
  number: string; kind: "invoice" | "proforma"; customer: string | null;
  date: string | null; invoice_total: string; received: string; balance: string;
  modes: string[]; payment_count: number; last_paid_on: string | null;
  status: string; status_label: string; payments: PaymentRow[];
};

type Totals = { count: number; invoice_total: string; received: string; balance: string };
type Section = { rows: Row[]; totals: Totals };
type SectionKey = "fully_paid" | "partially_paid" | "credit";

const SECTIONS: { key: SectionKey; label: string; blurb: string }[] = [
  { key: "fully_paid", label: "Fully Paid", blurb: "Settled in real money." },
  { key: "partially_paid", label: "Partially Paid", blurb: "Some received, a balance still owing." },
  { key: "credit", label: "Credit", blurb: "Released on agreed terms rather than paid." },
];

const EMPTY_TEXT: Record<SectionKey, string> = {
  fully_paid: "Nothing settled in full yet.",
  partially_paid: "Nothing part-paid — every document here is either settled or on terms.",
  credit: "Nothing on credit — every document here was paid for.",
};

const MODE_LABEL: Record<string, string> = {
  cash: "Cash", upi: "UPI", bank: "Bank", cheque: "Cheque", card: "Card", credit: "Credit",
};

const BLANK: Section = {
  rows: [], totals: { count: 0, invoice_total: "0", received: "0", balance: "0" },
};

export default function StockPaymentsPage() {
  const { payments, loading, denied, isSuperadmin, reload } = useStock(["payments"], "dispatch");
  const d = payments || null;

  const [tab, setTab] = useState<SectionKey>("fully_paid");
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const [removing, setRemoving] = useState<number | null>(null);

  /** Undo a payment that should never have been recorded.
   *
   *  Says what it will and will not do before doing it: the money record goes,
   *  a delivery already released stays gone, and the confirm has to name both
   *  or a super admin is deleting on a guess. */
  const removePayment = async (row: Row, p: PaymentRow) => {
    const released = row.status === "released";
    if (!confirm(
      `Delete the ${rupee(p.amount_received)} ${p.mode_label} payment on ${row.number}?\n\n` +
      `${row.number} will be short by that amount and may stop counting as settled.` +
      (released ? "\n\nThe goods have already gone out — this does not bring them back." : "") +
      `\n\nThis cannot be undone.`
    )) return;

    setRemoving(p.id);
    try {
      const token = localStorage.getItem(`${APP_SLUG}_access`);
      const r = await fetch(`${getApiBase(APP_SLUG)}/api/stock-payments/${p.id}/`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) { alert(body.error || "That payment could not be deleted."); return; }
      if (body.note) alert(body.note);
      reload();
    } catch {
      alert("Network error — nothing was deleted.");
    } finally { setRemoving(null); }
  };

  const section = (key: SectionKey): Section => (d?.sections?.[key] as Section) || BLANK;

  const active = section(tab);
  const term = search.trim().toLowerCase();
  const rows = !term ? active.rows : active.rows.filter(r =>
    `${r.number} ${r.customer || ""}`.toLowerCase().includes(term));

  return (
    <StockPage title="Payments" loading={loading} denied={denied}
      subtitle="Every delivery and proforma money has been verified against.">

      {!d ? <Empty text="No payments verified yet." /> : (
        <>
          {/* One section at a time. The three are disjoint — a document appears
              in exactly one — so the tab counts add up to the whole board. */}
          <div className="flex gap-1 mb-5 border-b border-slate-200 overflow-x-auto no-scrollbar">
            {SECTIONS.map(s => (
              <button key={s.key} onClick={() => { setTab(s.key); setOpen(null); }}
                className={`flex items-center gap-2 px-4 py-2.5 text-sm font-semibold whitespace-nowrap border-b-2 -mb-px transition-colors ${
                  tab === s.key ? "border-indigo-600 text-indigo-600" : "border-transparent text-slate-500 hover:text-slate-800"}`}>
                {s.label}
                <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full ${
                  tab === s.key ? "bg-indigo-50 text-indigo-700" : "bg-slate-100 text-slate-500"}`}>
                  {section(s.key).totals.count}
                </span>
              </button>
            ))}
          </div>

          <div className="mb-4 flex flex-wrap items-center gap-3">
            <input value={search} onChange={e => setSearch(e.target.value)}
              placeholder="Search by document or customer…"
              className="w-full max-w-md bg-white border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all" />
            <span className="text-xs font-semibold text-slate-400">
              {rows.length} document{rows.length === 1 ? "" : "s"}
            </span>
            {/* The money in this section, beside the list it describes. */}
            <span className="ml-auto text-xs text-slate-400">
              Received <b className="text-emerald-600 tabular-nums">{rupee(active.totals.received)}</b>
              {Number(active.totals.balance) > 0 && (
                <> · Owing <b className="text-amber-600 tabular-nums">{rupee(active.totals.balance)}</b></>
              )}
            </span>
          </div>

          <p className="text-[11px] text-slate-400 mb-3">
            {SECTIONS.find(s => s.key === tab)?.blurb}
          </p>

          <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
            {rows.length === 0 ? (
              <p className="px-6 py-14 text-center text-sm text-slate-400">
                {term ? "Nothing matches that search." : EMPTY_TEXT[tab]}
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[860px] text-left border-collapse">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-200 text-[10px] uppercase tracking-wider text-slate-500 font-semibold">
                      <th className="py-3 px-3">Document</th>
                      <th className="py-3 px-3">Customer</th>
                      <th className="py-3 px-3">Modes</th>
                      <th className="py-3 px-3 text-right">Invoice</th>
                      <th className="py-3 px-3 text-right">Received</th>
                      <th className="py-3 px-3 text-right">Balance</th>
                      <th className="py-3 px-3">Last paid</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {rows.map(r => (
                      <React.Fragment key={`${r.kind}-${r.number}`}>
                        <tr onClick={() => setOpen(open === r.number ? null : r.number)}
                          title="Show the payments on this document"
                          className="hover:bg-slate-50/60 transition-colors cursor-pointer text-sm text-slate-700">
                          <td className="py-3 px-3">
                            <span className="font-mono text-xs font-semibold text-slate-900">{r.number}</span>
                            <span className="block text-[10px] text-slate-400">
                              {r.kind === "proforma" ? "Proforma" : r.status_label}
                            </span>
                          </td>
                          <td className="py-3 px-3">{r.customer || "—"}</td>
                          <td className="py-3 px-3">
                            <span className="flex flex-wrap gap-1">
                              {r.modes.map(m => (
                                <span key={m}
                                  className={`text-[9px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded ${
                                    m === "credit" ? "bg-violet-50 text-violet-700" : "bg-slate-100 text-slate-600"}`}>
                                  {MODE_LABEL[m] || m}
                                </span>
                              ))}
                            </span>
                          </td>
                          <td className="py-3 px-3 text-right tabular-nums">{rupee(r.invoice_total)}</td>
                          <td className="py-3 px-3 text-right tabular-nums font-semibold text-emerald-600">
                            {rupee(r.received)}
                          </td>
                          <td className={`py-3 px-3 text-right tabular-nums font-semibold ${
                            Number(r.balance) > 0 ? "text-amber-600" : "text-slate-300"}`}>
                            {Number(r.balance) > 0 ? rupee(r.balance) : "—"}
                          </td>
                          <td className="py-3 px-3 text-[12px] text-slate-500 whitespace-nowrap">
                            {r.last_paid_on || "—"}
                          </td>
                        </tr>
                        {open === r.number && (
                          <tr className="bg-slate-50/60">
                            <td colSpan={7} className="px-3 pb-3 pt-0">
                              <div className="rounded-xl border border-slate-200 bg-white divide-y divide-slate-100">
                                {r.payments.map(p => (
                                  <div key={p.id} className="flex items-center justify-between gap-3 px-3 py-2 text-xs">
                                    <div className="min-w-0">
                                      <span className="font-semibold text-slate-700">{p.mode_label}</span>
                                      {p.reference && (
                                        <span className="ml-1.5 font-mono text-slate-400">{p.reference}</span>
                                      )}
                                      <span className="block text-[10px] text-slate-400">
                                        {p.paid_on || "—"}{p.verified_by ? ` · verified by ${p.verified_by}` : ""}
                                      </span>
                                    </div>
                                    <span className="flex items-center gap-2 flex-shrink-0">
                                      <span className="font-bold tabular-nums text-slate-800">
                                        {rupee(p.amount_received)}
                                      </span>
                                      {/* Undoing a verified payment sits above the
                                          admin tier — see StockPaymentView. */}
                                      {isSuperadmin && (
                                        <button onClick={e => { e.stopPropagation(); removePayment(r, p); }}
                                          disabled={removing === p.id}
                                          title="Delete this payment" aria-label="Delete this payment"
                                          className="w-7 h-7 inline-flex items-center justify-center rounded-lg
                                                     text-rose-500 hover:text-rose-700 hover:bg-rose-50
                                                     disabled:opacity-40 transition-colors">
                                          <I.Trash />
                                        </button>
                                      )}
                                    </span>
                                  </div>
                                ))}
                              </div>
                              <p className="mt-2 text-[11px]">
                                <Link href={r.kind === "proforma" ? "/inventory/quotes" : "/inventory/dispatch"}
                                  className="font-semibold text-indigo-600 hover:text-indigo-800">
                                  Open {r.kind === "proforma" ? "Proforma Invoice" : "Sales / Dispatches"} →
                                </Link>
                              </p>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <p className="flex items-start gap-2 text-[11px] text-slate-400 mt-4">
            <I.Check />
            Credit settles an invoice so the goods can go out on terms — it is counted as
            received, and kept in its own section so it is never mistaken for money in.
          </p>
        </>
      )}
    </StockPage>
  );
}

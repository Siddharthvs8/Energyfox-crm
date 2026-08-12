"use client";
/**
 * Inventory → Payments (wholesale).
 *
 * Every document money has been verified against, in three sections that do not
 * overlap — so a document appears once and the counts add up:
 *
 *   Credit         — released on terms. Credit settles an invoice, so without a
 *                    section of its own it would sit under "fully paid" and hide
 *                    the fact that no money came in.
 *   Fully paid     — settled, in real money.
 *   Partially paid — some received, a balance still owing.
 *
 * Deliveries and proformas both appear. A proforma takes its instalments before
 * it becomes a delivery, and leaving those out would hide part-paid business
 * exactly while it is part-paid.
 */
import React, { useState } from "react";
import Link from "next/link";
import { rupee, useStock, StockPage, Empty, I } from "../shared";

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

type Section = { rows: Row[]; totals: { count: number; invoice_total: string; received: string; balance: string } };

const SECTIONS: { key: "fully_paid" | "partially_paid" | "credit"; label: string; blurb: string; tone: string }[] = [
  { key: "fully_paid", label: "Fully Paid", tone: "emerald",
    blurb: "Settled in real money." },
  { key: "partially_paid", label: "Partially Paid", tone: "amber",
    blurb: "Some received, a balance still owing." },
  { key: "credit", label: "Credit", tone: "violet",
    blurb: "Released on agreed terms rather than paid." },
];

const TONE: Record<string, { chip: string; bar: string; text: string }> = {
  emerald: { chip: "bg-emerald-50 text-emerald-700", bar: "border-t-emerald-500", text: "text-emerald-600" },
  amber: { chip: "bg-amber-50 text-amber-700", bar: "border-t-amber-500", text: "text-amber-600" },
  violet: { chip: "bg-violet-50 text-violet-700", bar: "border-t-violet-500", text: "text-violet-600" },
};

const MODE_LABEL: Record<string, string> = {
  cash: "Cash", upi: "UPI", bank: "Bank", cheque: "Cheque", card: "Card", credit: "Credit",
};

export default function StockPaymentsPage() {
  const { payments, loading, denied } = useStock(["payments"], "dispatch");
  const d = payments || null;
  const [open, setOpen] = useState<string | null>(null);

  const section = (key: string): Section =>
    (d?.sections?.[key] as Section) || { rows: [], totals: { count: 0, invoice_total: "0", received: "0", balance: "0" } };

  return (
    <StockPage title="Payments" loading={loading} denied={denied}
      subtitle="Every delivery and proforma money has been verified against.">

      {!d ? <Empty text="No payments verified yet." /> : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6">
            {SECTIONS.map(s => {
              const t = section(s.key).totals;
              return (
                <div key={s.key}
                  className={`bg-white border border-slate-200 rounded-2xl p-4 border-t-4 ${TONE[s.tone].bar}`}>
                  <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">{s.label}</p>
                  <p className="text-xl font-bold mt-1.5 tabular-nums text-slate-900">{rupee(t.received)}</p>
                  <p className="text-[11px] text-slate-400 mt-0.5">
                    {t.count} document{t.count === 1 ? "" : "s"}
                    {Number(t.balance) > 0 && (
                      <span className={`ml-1.5 font-semibold ${TONE[s.tone].text}`}>
                        · {rupee(t.balance)} owing
                      </span>
                    )}
                  </p>
                </div>
              );
            })}
          </div>

          {SECTIONS.map(s => {
            const sec = section(s.key);
            return (
              <div key={s.key} className="mb-6">
                <div className="flex items-baseline gap-2.5 mb-2.5">
                  <h2 className="text-sm font-bold text-slate-900">{s.label}</h2>
                  <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ${TONE[s.tone].chip}`}>
                    {sec.totals.count}
                  </span>
                  <span className="text-[11px] text-slate-400">{s.blurb}</span>
                </div>

                <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
                  {sec.rows.length === 0 ? (
                    <p className="px-6 py-8 text-center text-sm text-slate-400">Nothing here.</p>
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
                          {sec.rows.map(r => (
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
                                          <span className="font-bold tabular-nums text-slate-800 flex-shrink-0">
                                            {rupee(p.amount_received)}
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
              </div>
            );
          })}

          <p className="flex items-start gap-2 text-[11px] text-slate-400">
            <I.Check />
            Credit settles an invoice so the goods can go out on terms — it is counted as
            received, and kept in its own section so it is never mistaken for money in.
          </p>
        </>
      )}
    </StockPage>
  );
}

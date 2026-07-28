"use client";
/**
 * Inventory → Quotes (wholesale).
 *
 * A quotation over stock items. Accepting one is recorded by converting it: that
 * writes a dispatch row per line, which is what takes the goods out of stock — so
 * a converted quote is locked from then on.
 */
import React, { useState } from "react";
import {
  FIELD, I, rupee, num, todayISO, useStock, StockPage, Table, Field, DeleteBtn, Empty,
} from "../shared";

type Line = { item: string; description: string; quantity: string; unit_price: string };

const blankLine = (): Line => ({ item: "", description: "", quantity: "1", unit_price: "" });
const blankForm = () => ({
  customer: "", quote_date: todayISO(), expiry_date: "", site: "",
  discount_percent: "", tax_percent: "", notes: "", status: "draft",
  items: [blankLine()],
});

const STATUS_STYLE: Record<string, string> = {
  draft: "bg-slate-100 text-slate-600",
  sent: "bg-sky-50 text-sky-700",
  accepted: "bg-emerald-50 text-emerald-700",
  declined: "bg-rose-50 text-rose-700",
  converted: "bg-indigo-50 text-indigo-700",
};

export default function StockQuotesPage() {
  const { quotes, items, customers, loading, denied, create, remove, act } =
    useStock(["quotes", "items", "customers"]);
  // useStock starts with an empty bag, and StockPage's children are evaluated
  // before it swaps in the spinner — so default everything here.
  const itemList: any[] = items || [];
  const customerList: any[] = customers || [];
  const quoteList: any[] = quotes || [];
  const [form, setForm] = useState(blankForm());
  const [saving, setSaving] = useState(false);
  const [open, setOpen] = useState<number | null>(null);

  const lines = form.items;
  const setLine = (i: number, patch: Partial<Line>) =>
    setForm(f => ({ ...f, items: f.items.map((l, n) => (n === i ? { ...l, ...patch } : l)) }));

  // Live totals, mirroring the server: subtotal → discount → tax.
  const subtotal = lines.reduce((s, l) => s + (Number(l.quantity) || 0) * (Number(l.unit_price) || 0), 0);
  const discount = subtotal * (Number(form.discount_percent) || 0) / 100;
  const tax = (subtotal - discount) * (Number(form.tax_percent) || 0) / 100;
  const total = subtotal - discount + tax;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const valid = lines.filter(l => l.item && Number(l.quantity) > 0);
    if (!valid.length) { alert("Add at least one line with an item and a quantity."); return; }
    setSaving(true);
    const ok = await create("quotes", {
      ...form,
      customer: form.customer || null,
      expiry_date: form.expiry_date || null,
      discount_percent: form.discount_percent || 0,
      tax_percent: form.tax_percent || 0,
      items: valid.map(l => ({
        item: l.item, description: l.description,
        quantity: l.quantity, unit_price: l.unit_price || 0,
      })),
    });
    setSaving(false);
    if (ok) setForm(blankForm());
  };

  const convert = async (q: any) => {
    if (!confirm(`Dispatch ${q.number}? This takes ${q.items.length} line(s) out of stock.`)) return;
    const d = await act(`stock-quotes/${q.id}/convert`);
    if (d) alert(`${q.number} dispatched — ${d.dispatched_lines} line(s) recorded.`);
  };

  if (itemList.length === 0 && !loading && !denied) {
    return (
      <StockPage title="Quotes" subtitle="Quote your wholesale customers from stock.">
        <Empty text="Add an item in Item Master first — a quote is priced off stock items." />
      </StockPage>
    );
  }

  return (
    <StockPage title="Quotes" loading={loading} denied={denied}
      subtitle="Quote your wholesale customers from stock; converting one dispatches it.">

      <form onSubmit={submit} className="bg-white border border-slate-200 rounded-2xl p-5 mb-5 space-y-4">
        <h2 className="text-sm font-bold text-slate-900">New quote</h2>

        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
          <Field label="Customer">
            <select value={form.customer} onChange={e => setForm({ ...form, customer: e.target.value })} className={FIELD}>
              <option value="">—</option>
              {customerList.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </Field>
          <Field label="Date">
            <input type="date" required value={form.quote_date}
              onChange={e => setForm({ ...form, quote_date: e.target.value })} className={FIELD} />
          </Field>
          <Field label="Valid until">
            <input type="date" value={form.expiry_date}
              onChange={e => setForm({ ...form, expiry_date: e.target.value })} className={FIELD} />
          </Field>
          <Field label="Discount %">
            <input type="number" step="any" min="0" max="100" value={form.discount_percent}
              onChange={e => setForm({ ...form, discount_percent: e.target.value })} className={FIELD} />
          </Field>
          <Field label="Tax %">
            <input type="number" step="any" min="0" max="100" value={form.tax_percent}
              onChange={e => setForm({ ...form, tax_percent: e.target.value })} className={FIELD} />
          </Field>
          <Field label="Site address">
            <input value={form.site} onChange={e => setForm({ ...form, site: e.target.value })} className={FIELD} />
          </Field>
        </div>

        <div>
          <p className="text-[11px] font-semibold text-slate-500 mb-1.5">Lines</p>
          <div className="space-y-2">
            {lines.map((l, i) => (
              <div key={i} className="grid grid-cols-[2fr_1.5fr_90px_120px_36px] gap-2 items-center">
                <select value={l.item} onChange={e => setLine(i, { item: e.target.value })} className={FIELD}>
                  <option value="">Select item…</option>
                  {itemList.map((it: any) => (
                    <option key={it.id} value={it.id}>{it.code} — {`${it.brand} ${it.model_name}`.trim()}</option>
                  ))}
                </select>
                <input placeholder="Description" value={l.description}
                  onChange={e => setLine(i, { description: e.target.value })} className={FIELD} />
                <input type="number" step="any" min="0" placeholder="Qty" value={l.quantity}
                  onChange={e => setLine(i, { quantity: e.target.value })} className={FIELD} />
                <input type="number" step="any" min="0" placeholder="Rate ₹" value={l.unit_price}
                  onChange={e => setLine(i, { unit_price: e.target.value })} className={FIELD} />
                {lines.length > 1 ? (
                  <DeleteBtn onClick={() => setForm(f => ({ ...f, items: f.items.filter((_, n) => n !== i) }))} />
                ) : <span />}
              </div>
            ))}
          </div>
          <button type="button" onClick={() => setForm(f => ({ ...f, items: [...f.items, blankLine()] }))}
            className="mt-2 text-[11px] font-semibold text-indigo-600 hover:text-indigo-800">
            + Add line
          </button>
        </div>

        <div className="flex flex-wrap items-center justify-end gap-4 pt-3 border-t border-slate-100">
          <span className="text-xs text-slate-400 mr-auto tabular-nums">
            Subtotal {rupee(subtotal)} · Discount −{rupee(discount)} · Tax {rupee(tax)}
          </span>
          <span className="text-sm font-bold text-slate-900 tabular-nums">Total {rupee(total)}</span>
          <button type="submit" disabled={saving}
            className="flex items-center gap-1.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white rounded-xl px-4 h-[38px] text-sm font-semibold transition-colors">
            <I.Plus /> {saving ? "Saving…" : "Create quote"}
          </button>
        </div>
      </form>

      <Table columns={["Quote", "Date", "Customer", "Lines", "Total", "Status", "Raised by", ""]}
        rows={quoteList.map((q: any) => [
          <button onClick={() => setOpen(open === q.id ? null : q.id)}
            className="font-mono font-semibold text-indigo-600 hover:text-indigo-800">{q.number}</button>,
          <span className="font-mono text-slate-500">{q.quote_date || "—"}</span>,
          q.customer_name || "—",
          <span className="tabular-nums">{q.items.length}</span>,
          <span className="tabular-nums font-semibold">{rupee(q.total)}</span>,
          <span className={`inline-flex text-[10px] font-bold uppercase tracking-wider px-2 py-1 rounded-full ${STATUS_STYLE[q.status] || "bg-slate-100 text-slate-600"}`}>
            {q.status}
          </span>,
          <span className="text-slate-400 text-xs">{q.created_by_name || "—"}</span>,
          <div className="flex items-center gap-2 justify-end">
            {q.status !== "converted" && (
              <button onClick={() => convert(q)}
                className="px-2.5 py-1 rounded-lg bg-emerald-50 text-emerald-700 text-[11px] font-bold hover:bg-emerald-100 transition-colors whitespace-nowrap">
                Dispatch
              </button>
            )}
            {q.status !== "converted" && <DeleteBtn onClick={() => remove("quotes", q.id, "quote")} />}
          </div>,
        ])} />

      {/* Line detail for the quote whose number was clicked. */}
      {open !== null && (() => {
        const q = quoteList.find((x: any) => x.id === open);
        if (!q) return null;
        return (
          <div className="bg-white border border-slate-200 rounded-2xl p-5 mt-4">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-bold text-slate-900">{q.number} · lines</h2>
              <button onClick={() => setOpen(null)} className="text-xs font-semibold text-slate-400 hover:text-slate-600">Close</button>
            </div>
            <Table columns={["Item", "Description", "Qty", "Rate", "Amount"]}
              rows={q.items.map((l: any) => [
                <span><span className="font-mono">{l.item_code}</span> <span className="text-slate-400">— {l.item_label}</span></span>,
                l.description || "—",
                <span className="tabular-nums">{num(l.quantity)}</span>,
                <span className="tabular-nums">{rupee(l.unit_price)}</span>,
                <span className="tabular-nums font-semibold">{rupee(l.line_total)}</span>,
              ])} />
            <p className="text-xs text-slate-500 mt-3 text-right tabular-nums">
              Subtotal {rupee(q.subtotal)} · Discount −{rupee(q.discount_amount)} · Tax {rupee(q.tax_amount)} ·{" "}
              <b className="text-slate-800">Total {rupee(q.total)}</b>
            </p>
          </div>
        );
      })()}
    </StockPage>
  );
}

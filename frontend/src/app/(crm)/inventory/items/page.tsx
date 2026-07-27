"use client";
import React, { useState } from "react";
import {
  I, CATS, FIELD, rupee, num, useStock, StockPage, FormPanel, Field, Table, StatusPill, DeleteBtn,
} from "../shared";

const blankItem = {
  code: "", category: CATS[0], brand: "", model_name: "", unit: "Nos",
  opening_stock: "", unit_cost: "", reorder_level: "", location: "",
};

export default function ItemMasterPage() {
  const { items, loading, denied, create, remove } = useStock(["items"]);
  const [form, setForm] = useState<any>(blankItem);
  const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState("");

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.code.trim()) return;
    setSaving(true);
    const ok = await create("items", {
      ...form,
      opening_stock: form.opening_stock || 0,
      unit_cost: form.unit_cost || 0,
      reorder_level: form.reorder_level || 0,
    });
    setSaving(false);
    if (ok) setForm(blankItem);
  };

  const filtered = (items || []).filter((r: any) =>
    !search || `${r.code} ${r.category} ${r.brand} ${r.model_name}`.toLowerCase().includes(search.toLowerCase()));

  return (
    <StockPage title="Item Master" loading={loading} denied={denied}
      subtitle="Your SKU catalog — panels, inverters, batteries, structures, cables.">
      <FormPanel title="Add item" onSubmit={submit} saving={saving} action="Add item">
        <Field label="Item code *"><input required value={form.code} onChange={e => setForm({ ...form, code: e.target.value })} className={`${FIELD} font-mono`} placeholder="SOL-PNL-540" /></Field>
        <Field label="Category">
          <select value={form.category} onChange={e => setForm({ ...form, category: e.target.value })} className={FIELD}>
            {CATS.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </Field>
        <Field label="Brand"><input value={form.brand} onChange={e => setForm({ ...form, brand: e.target.value })} className={FIELD} placeholder="Waaree" /></Field>
        <Field label="Model / spec"><input value={form.model_name} onChange={e => setForm({ ...form, model_name: e.target.value })} className={FIELD} placeholder="540W Mono PERC" /></Field>
        <Field label="Unit"><input value={form.unit} onChange={e => setForm({ ...form, unit: e.target.value })} className={FIELD} placeholder="Nos" /></Field>
        <Field label="Opening stock"><input type="number" step="any" value={form.opening_stock} onChange={e => setForm({ ...form, opening_stock: e.target.value })} className={FIELD} /></Field>
        <Field label="Unit cost (₹)"><input type="number" step="any" value={form.unit_cost} onChange={e => setForm({ ...form, unit_cost: e.target.value })} className={FIELD} /></Field>
        <Field label="Reorder level"><input type="number" step="any" value={form.reorder_level} onChange={e => setForm({ ...form, reorder_level: e.target.value })} className={FIELD} /></Field>
        <Field label="Warehouse location"><input value={form.location} onChange={e => setForm({ ...form, location: e.target.value })} className={FIELD} placeholder="Warehouse A - Rack 1" /></Field>
      </FormPanel>

      <div className="relative max-w-xs mb-3">
        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"><I.Search /></span>
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search items…"
          className="w-full bg-white border border-slate-200 rounded-xl pl-9 pr-3 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition" />
      </div>

      <Table columns={["Code", "Category", "Brand / Model", "Opening", "In", "Out", "Closing", "Unit Cost", "Stock Value", "Location", "Status", ""]}
        rows={filtered.map((r: any) => [
          <span className="font-mono font-semibold text-slate-800">{r.code}</span>,
          r.category,
          `${r.brand} ${r.model_name}`.trim() || "—",
          <span className="tabular-nums text-slate-500">{num(r.opening_stock)}</span>,
          <span className="tabular-nums text-emerald-600">+{num(r.received)}</span>,
          <span className="tabular-nums text-rose-600">−{num(r.dispatched)}</span>,
          <span className="tabular-nums font-semibold">{num(r.closing_stock)} {r.unit}</span>,
          <span className="tabular-nums">{rupee(r.unit_cost)}</span>,
          <span className="tabular-nums font-semibold">{rupee(r.stock_value)}</span>,
          <span className="text-slate-500">{r.location || "—"}</span>,
          <StatusPill status={r.status} />,
          <DeleteBtn onClick={() => remove("items", r.id, "item")} />,
        ])} />
    </StockPage>
  );
}

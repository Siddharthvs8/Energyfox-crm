"use client";
/**
 * Inventory → Item Master (wholesale).
 *
 * Laid out like /products, with one honest difference: closing stock isn't an
 * editable number here. It is opening + received − dispatched, so the table shows
 * the movement columns that produce it and the modal only edits the opening
 * figure.
 */
import React, { useState } from "react";
import {
  CATS, FIELD, rupee, num, useStock, StockPage, AddButton, SearchBar,
  DataTable, Modal, Fld, Row, RowActions, StatusPill,
} from "../shared";

const blankItem = {
  code: "", category: CATS[0], brand: "", model_name: "", unit: "Nos",
  opening_stock: "", unit_cost: "", reorder_level: "", location: "",
};

export default function StockItemMasterPage() {
  const { items, loading, denied, save, remove } = useStock(["items"]);
  const list: any[] = items || [];

  const [form, setForm] = useState<any>(blankItem);
  const [editing, setEditing] = useState<any>(null);
  const [show, setShow] = useState(false);
  const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState("");

  const openCreate = () => { setEditing(null); setForm(blankItem); setShow(true); };
  const openEdit = (r: any) => {
    setEditing(r);
    setForm({
      code: r.code, category: r.category, brand: r.brand || "", model_name: r.model_name || "",
      unit: r.unit || "Nos", opening_stock: r.opening_stock ?? "", unit_cost: r.unit_cost ?? "",
      reorder_level: r.reorder_level ?? "", location: r.location || "",
    });
    setShow(true);
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.code.trim()) return;
    setSaving(true);
    const ok = await save("items", {
      ...form,
      opening_stock: form.opening_stock || 0,
      unit_cost: form.unit_cost || 0,
      reorder_level: form.reorder_level || 0,
    }, editing?.id);
    setSaving(false);
    if (ok) { setShow(false); setEditing(null); setForm(blankItem); }
  };

  const term = search.trim().toLowerCase();
  const filtered = !term ? list : list.filter(r =>
    `${r.code} ${r.category} ${r.brand} ${r.model_name} ${r.location}`.toLowerCase().includes(term));
  const lowCount = list.filter(r => r.status === "REORDER").length;

  return (
    <StockPage
      title="Item Master" loading={loading} denied={denied}
      subtitle={<>
        Your wholesale SKUs — closing stock is derived from movements.
        {lowCount > 0 && <span className="ml-2 text-rose-600 font-medium">{lowCount} low on stock</span>}
      </>}
      action={<AddButton label="Add Item" onClick={openCreate} />}>

      <SearchBar value={search} onChange={setSearch} placeholder="Search items..." />

      <DataTable
        minWidth={1040}
        columns={[
          "Code", "Category", "Brand / Model",
          { label: "Opening", align: "right" }, { label: "In", align: "right" }, { label: "Out", align: "right" },
          { label: "Closing", align: "center" }, { label: "Unit Cost", align: "right" },
          { label: "Stock Value", align: "right" }, "Location", { label: "Actions", align: "right" },
        ]}
        empty={{ title: "No items found", hint: "Add your first stock item to get started." }}
        rows={filtered.map(r => [
          <span className="font-mono text-xs font-semibold text-slate-900">{r.code}</span>,
          r.category,
          <span>{`${r.brand} ${r.model_name}`.trim() || "—"}</span>,
          <span className="tabular-nums text-slate-500">{num(r.opening_stock)}</span>,
          <span className="tabular-nums text-emerald-600">+{num(r.received)}</span>,
          <span className="tabular-nums text-rose-600">−{num(r.dispatched)}</span>,
          <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold ${
            r.status === "REORDER" ? "bg-rose-50 text-rose-600" : "bg-emerald-50 text-emerald-600"}`}>
            {r.status === "REORDER" && <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />}
            {num(r.closing_stock)} {r.unit}
          </span>,
          <span className="tabular-nums text-slate-400">{rupee(r.unit_cost)}</span>,
          <span className="tabular-nums font-semibold">{rupee(r.stock_value)}</span>,
          <span className="text-slate-500">{r.location || "—"}</span>,
          <RowActions onEdit={() => openEdit(r)} onDelete={() => remove("items", r.id, "item")} />,
        ])} />

      <Modal show={show} title={editing ? "Edit Item" : "Add Item"} onClose={() => setShow(false)}
        onSubmit={submit} saving={saving} submitLabel="Save Item">
        <Row>
          <Fld label="Item Code *">
            <input required value={form.code} onChange={e => setForm({ ...form, code: e.target.value })}
              className={`${FIELD} font-mono`} placeholder="e.g. SOL-PNL-540" />
          </Fld>
          <Fld label="Category">
            <select value={form.category} onChange={e => setForm({ ...form, category: e.target.value })} className={FIELD}>
              {CATS.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </Fld>
        </Row>
        <Row>
          <Fld label="Brand">
            <input value={form.brand} onChange={e => setForm({ ...form, brand: e.target.value })}
              className={FIELD} placeholder="e.g. Waaree" />
          </Fld>
          <Fld label="Model / Spec">
            <input value={form.model_name} onChange={e => setForm({ ...form, model_name: e.target.value })}
              className={FIELD} placeholder="e.g. 540W Mono PERC" />
          </Fld>
        </Row>
        <Row cols={3}>
          <Fld label="Opening Stock">
            <input type="number" step="any" min="0" value={form.opening_stock}
              onChange={e => setForm({ ...form, opening_stock: e.target.value })} className={FIELD} />
          </Fld>
          <Fld label="Unit Cost (₹)">
            <input type="number" step="any" min="0" value={form.unit_cost}
              onChange={e => setForm({ ...form, unit_cost: e.target.value })} className={FIELD} />
          </Fld>
          <Fld label="Reorder Level">
            <input type="number" step="any" min="0" value={form.reorder_level}
              onChange={e => setForm({ ...form, reorder_level: e.target.value })} className={FIELD} />
          </Fld>
        </Row>
        <Row>
          <Fld label="Unit">
            <input value={form.unit} onChange={e => setForm({ ...form, unit: e.target.value })}
              className={FIELD} placeholder="Nos" />
          </Fld>
          <Fld label="Warehouse Location">
            <input value={form.location} onChange={e => setForm({ ...form, location: e.target.value })}
              className={FIELD} placeholder="e.g. Warehouse A - Rack 1" />
          </Fld>
        </Row>
        {editing && (
          <p className="text-xs text-slate-400">
            Closing stock stays derived from receipts and dispatches — edit those to correct it.
          </p>
        )}
      </Modal>
    </StockPage>
  );
}

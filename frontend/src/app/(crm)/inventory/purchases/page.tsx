"use client";
/**
 * Inventory → Purchases (wholesale).
 *
 * A receipt is stored as one row per item — that is what the stock ledger
 * values — so a delivery of several products from a supplier is several rows
 * sharing one GRN number. This screen writes that whole set in one save.
 */
import React, { useState } from "react";
import {
  FIELD, rupee, num, todayISO, useStock, StockPage, AddButton, SearchBar,
  DataTable, Modal, Fld, Row, RowActions, I,
} from "../shared";

type Line = { item: string; quantity: string; rate: string };

const blankLine = (): Line => ({ item: "", quantity: "", rate: "" });
const blankForm = () => ({
  grn_no: "", date: todayISO(), supplier: "", notes: "", lines: [blankLine()],
});

export default function StockPurchasesPage() {
  const { receipts, items, suppliers, loading, denied, save, remove } =
    useStock(["receipts", "items", "suppliers"]);
  const itemList: any[] = items || [];
  const supplierList: any[] = suppliers || [];
  const list: any[] = receipts || [];

  const [form, setForm] = useState<any>(blankForm());
  const [editing, setEditing] = useState<any>(null);
  const [show, setShow] = useState(false);
  const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState("");

  const lines: Line[] = form.lines;
  const setLine = (i: number, patch: Partial<Line>) =>
    setForm((f: any) => ({ ...f, lines: f.lines.map((l: Line, n: number) => (n === i ? { ...l, ...patch } : l)) }));

  // Live total, mirroring the server. Receipts carry no tax.
  const goods = lines.reduce((s, l) => s + (Number(l.quantity) || 0) * (Number(l.rate) || 0), 0);

  const openCreate = () => { setEditing(null); setForm(blankForm()); setShow(true); };

  /** Editing touches the one row that was clicked, not the whole GRN. */
  const openEdit = (r: any) => {
    setEditing(r);
    setForm({
      grn_no: r.grn_no || "", date: r.date || todayISO(),
      supplier: r.supplier || "", notes: r.notes || "",
      lines: [{ item: String(r.item || ""), quantity: String(r.quantity ?? ""), rate: String(r.rate ?? "") }],
    });
    setShow(true);
  };

  /** Default the rate to the item's unit cost, but never overwrite a typed one. */
  const pickItem = (i: number, itemId: string) => {
    const it = itemList.find(x => String(x.id) === String(itemId));
    setLine(i, { item: itemId, rate: lines[i].rate || String(it?.unit_cost ?? "") });
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const valid = lines.filter(l => l.item && Number(l.quantity) > 0);
    if (!valid.length) { alert("Add at least one item with a quantity."); return; }
    setSaving(true);
    // One row per item, all carrying the same header so they group under one GRN.
    const header = {
      grn_no: form.grn_no, date: form.date,
      supplier: form.supplier || null, notes: form.notes,
    };
    let ok = true;
    for (const l of valid) {
      ok = (await save("receipts", { ...header, item: l.item, quantity: l.quantity, rate: l.rate || 0 },
                       editing?.id)) && ok;
      if (editing) break;                      // an edit is one row, not a set
    }
    setSaving(false);
    if (ok) { setShow(false); setEditing(null); setForm(blankForm()); }
  };

  const term = search.trim().toLowerCase();
  const filtered = !term ? list : list.filter(r =>
    `${r.grn_no || ""} ${r.item_code || ""} ${r.item_label || ""} ${r.supplier_name || ""}`
      .toLowerCase().includes(term));

  return (
    <StockPage
      title="Purchases"
      subtitle="Every stock receipt from a supplier (GRN)."
      loading={loading} denied={denied}
      action={itemList.length > 0 ? <AddButton label="New Receipt" onClick={openCreate} /> : undefined}>

      {itemList.length === 0 ? (
        <DataTable columns={["Item"]} rows={[]}
          empty={{ title: "No items yet", hint: "Add an item in Item Master first — every movement is logged against one." }} />
      ) : (
        <>
          <SearchBar value={search} onChange={setSearch} placeholder="Search receipts..." />

          <DataTable
            columns={[
              "GRN", "Date", "Supplier", "Item",
              { label: "Qty", align: "right" }, { label: "Rate", align: "right" },
              { label: "Amount", align: "right" },
              "Logged by", { label: "Actions", align: "right" },
            ]}
            minWidth={980}
            empty={{ title: "No receipts yet", hint: "Record your first receipt." }}
            rows={filtered.map(r => [
              <span className="font-mono font-semibold text-slate-900">{r.grn_no || "—"}</span>,
              <span className="font-mono text-xs text-slate-500">{r.date}</span>,
              r.supplier_name || "—",
              <span><span className="font-mono text-xs">{r.item_code}</span> <span className="text-slate-400">— {r.item_label}</span></span>,
              <span className="tabular-nums font-semibold">{num(r.quantity)}</span>,
              <span className="tabular-nums">{rupee(r.rate)}</span>,
              <span className="tabular-nums">{rupee(r.amount)}</span>,
              <span className="text-xs text-slate-400">{r.created_by_name || "—"}</span>,
              <RowActions onEdit={() => openEdit(r)} onDelete={() => remove("receipts", r.id, "receipt")} />,
            ])} />
        </>
      )}

      <Modal show={show} title={`${editing ? "Edit" : "New"} Receipt`} onClose={() => setShow(false)}
        onSubmit={submit} saving={saving} submitLabel="Save Receipt">
        <Row>
          <Fld label="GRN No.">
            <input value={form.grn_no} onChange={e => setForm({ ...form, grn_no: e.target.value })}
              className={`${FIELD} font-mono`} placeholder="GRN-0001" />
          </Fld>
          <Fld label="Date *">
            <input type="date" required value={form.date}
              onChange={e => setForm({ ...form, date: e.target.value })} className={FIELD} />
          </Fld>
        </Row>
        <Fld label="Supplier">
          <select value={form.supplier} onChange={e => setForm({ ...form, supplier: e.target.value })} className={FIELD}>
            <option value="">—</option>
            {supplierList.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </Fld>

        <div>
          <label className="block text-sm font-semibold text-slate-700 mb-1.5">Items</label>
          <div className="space-y-2">
            {lines.map((l, i) => (
              <div key={i} className="grid grid-cols-[2.4fr_90px_120px_32px] gap-2 items-center">
                <select value={l.item} onChange={e => pickItem(i, e.target.value)} className={FIELD}>
                  <option value="">Select item…</option>
                  {itemList.map(it => (
                    <option key={it.id} value={it.id}>{it.code} — {`${it.brand} ${it.model_name}`.trim()}</option>
                  ))}
                </select>
                <input type="number" step="any" min="0" placeholder="Qty" value={l.quantity}
                  onChange={e => setLine(i, { quantity: e.target.value })} className={FIELD} />
                <input type="number" step="any" min="0" placeholder="Rate ₹" value={l.rate}
                  onChange={e => setLine(i, { rate: e.target.value })} className={FIELD} />
                {lines.length > 1 && !editing ? (
                  <button type="button" aria-label="Remove item"
                    onClick={() => setForm((f: any) => ({ ...f, lines: f.lines.filter((_: Line, n: number) => n !== i) }))}
                    className="w-8 h-8 flex items-center justify-center rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-all">
                    <I.Trash />
                  </button>
                ) : <span />}
              </div>
            ))}
          </div>
          {editing ? (
            <p className="mt-2 text-xs text-slate-400">
              A receipt is stored per item, so editing changes this row only.
              Add another item as a new receipt on the same GRN number.
            </p>
          ) : (
            <button type="button"
              onClick={() => setForm((f: any) => ({ ...f, lines: [...f.lines, blankLine()] }))}
              className="mt-2 text-xs font-semibold text-indigo-600 hover:text-indigo-800">
              + Add item
            </button>
          )}
        </div>

        <Fld label="Notes">
          <textarea rows={2} value={form.notes}
            onChange={e => setForm({ ...form, notes: e.target.value })} className={FIELD} />
        </Fld>

        <div className="flex items-center justify-end gap-4 pt-3 border-t border-slate-100 text-sm">
          <span className="font-bold text-slate-900 tabular-nums">Total {rupee(goods)}</span>
        </div>
      </Modal>
    </StockPage>
  );
}

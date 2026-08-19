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
  DataTable, Modal, Fld, Row, RowActions, StatusPill, I,
} from "../shared";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";

const blankItem = {
  code: "", category: CATS[0], brand: "", model_name: "", unit: "Nos", hsn: "",
  opening_stock: "", unit_cost: "", reorder_level: "", location: "", is_active: true,
};


/**
 * Where an item's stock came from.
 *
 * Goods receipts have no screen of their own anywhere else, so an item's IN
 * column is otherwise a total with nothing behind it. This is that behind:
 * every quantity ever added, newest first, with the opening stock as its own
 * entry so the lines add up to the total.
 */
function StockHistoryModal({ show, itemId, onClose }: {
  show: boolean; itemId: number | null; onClose: () => void;
}) {
  const [data, setData] = React.useState<any>(null);
  const [loading, setLoading] = React.useState(false);

  React.useEffect(() => {
    if (!show || !itemId) { setData(null); return; }
    let live = true;
    setLoading(true);
    (async () => {
      try {
        const token = localStorage.getItem(`${APP_SLUG}_access`);
        const r = await fetch(`${getApiBase(APP_SLUG)}/api/stock-items/${itemId}/history/`,
          { headers: { Authorization: `Bearer ${token}` } });
        if (live && r.ok) setData(await r.json());
      } catch { /* the empty state covers it */ }
      finally { if (live) setLoading(false); }
    })();
    return () => { live = false; };
  }, [show, itemId]);

  if (!show) return null;
  const entries: any[] = data?.entries || [];
  const s = data?.summary;

  return (
    <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[92vh] overflow-y-auto">
        <div className="px-6 py-4 border-b border-slate-100 flex items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-bold text-slate-900">Stock added</h2>
            <p className="text-[12px] text-slate-500 mt-0.5">
              {data ? `${data.item.code} · ${data.item.name}` : "Loading…"}
            </p>
          </div>
          <button onClick={onClose} aria-label="Close"
            className="text-slate-400 hover:text-slate-700 transition"><I.X /></button>
        </div>

        <div className="p-6 space-y-4">
          {s && (
            <div className="rounded-xl bg-slate-50 border border-slate-200 px-4 py-3">
              <div className="grid grid-cols-3 gap-3 text-[12px]">
                <div>
                  <p className="text-slate-400">Opening</p>
                  <p className="font-bold text-slate-800 tabular-nums">{num(s.opening_stock)}</p>
                </div>
                <div>
                  <p className="text-slate-400">Added since</p>
                  <p className="font-bold text-emerald-600 tabular-nums">+{num(s.total_added)}</p>
                </div>
                <div>
                  <p className="text-slate-400">Total in</p>
                  <p className="font-bold text-slate-800 tabular-nums">{num(s.total_in)}</p>
                </div>
              </div>
              {/* The rest of the item's position, so this modal cannot appear to
                  contradict the row it was opened from. */}
              <p className="text-[11px] text-slate-400 mt-2.5 pt-2.5 border-t border-slate-200">
                {num(s.dispatched)} dispatched · {num(s.reserved)} reserved on proforma invoices ·{" "}
                <b className="text-slate-600">{num(s.closing_stock)} closing</b>
              </p>
            </div>
          )}

          {loading ? (
            <p className="py-10 text-center text-sm text-slate-400">Loading…</p>
          ) : entries.length === 0 ? (
            <p className="py-10 text-center text-sm text-slate-400">
              No stock has been added to this item yet.
            </p>
          ) : (
            <div className="space-y-2">
              {entries.map((e, i) => (
                <div key={e.id ?? `opening-${i}`}
                  className="flex items-start justify-between gap-4 rounded-xl border border-slate-100 px-4 py-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-bold text-slate-800 text-[13px]">
                        {e.kind === "opening" ? "Opening stock" : `+${num(e.quantity)}`}
                      </span>
                      {e.reference && (
                        <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">
                          {e.reference}
                        </span>
                      )}
                      {e.supplier && <span className="text-[12px] text-slate-500">{e.supplier}</span>}
                    </div>
                    <p className="text-[11px] text-slate-400 mt-0.5">
                      {[e.date, e.added_by, e.notes].filter(Boolean).join(" · ")}
                    </p>
                  </div>
                  <div className="text-right flex-shrink-0">
                    <p className="font-bold text-slate-800 tabular-nums text-[13px]">
                      {e.kind === "opening" ? num(e.quantity) : `+${num(e.quantity)}`}
                    </p>
                    {/* Stock added so far, not a stock balance: netting off
                        dispatches here would be wrong on every line. */}
                    <p className="text-[11px] text-slate-400 tabular-nums">
                      {num(e.running_total)} in total
                    </p>
                    {/* Two figures side by side say nothing about which is
                        which; "each" is the whole difference. */}
                    {Number(e.rate) > 0 && (
                      <p className="text-[11px] text-slate-400 tabular-nums">
                        {rupee(e.rate)} each · {rupee(e.amount)}
                      </p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function StockItemMasterPage() {
  const { items, loading, denied, readOnly, save, remove } = useStock(["items"], "items");
  const [historyFor, setHistoryFor] = useState<number | null>(null);
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
      unit: r.unit || "Nos", hsn: r.hsn || "", opening_stock: r.opening_stock ?? "", unit_cost: r.unit_cost ?? "",
      reorder_level: r.reorder_level ?? "", location: r.location || "", is_active: r.is_active !== false,
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
    `${r.code} ${r.category} ${r.brand} ${r.model_name} ${r.hsn} ${r.location}`.toLowerCase().includes(term));
  const lowCount = list.filter(r => r.status === "REORDER").length;

  return (
    <StockPage
      title="Item Master" loading={loading} denied={denied}
      subtitle={<>
        Your wholesale SKUs — closing stock is derived from movements, less
        anything a proforma invoice has already reserved.
        {lowCount > 0 && <span className="ml-2 text-rose-600 font-medium">{lowCount} low on stock</span>}
      </>}
      action={readOnly ? undefined : <AddButton label="Add Item" onClick={openCreate} />}>

      <SearchBar value={search} onChange={setSearch} placeholder="Search items..." />

      <DataTable
        minWidth={1060} compact
        columns={[
          "Code", "Category", "Brand / Model", "HSN / SAC",
          { label: "Opening", align: "right" }, { label: "In", align: "right" }, { label: "Out", align: "right" },
          { label: "Reserved", align: "right" },
          { label: "Closing", align: "center" }, { label: "Unit Cost", align: "right" },
          { label: "Stock Value", align: "right" }, "Location", { label: "Actions", align: "right" },
        ]}
        empty={{ title: "No items found", hint: "Add your first stock item to get started." }}
        rows={filtered.map(r => [
          <span className="whitespace-nowrap">
            <span className={`font-mono text-xs font-semibold ${r.is_active === false ? "text-slate-400 line-through" : "text-slate-900"}`}>{r.code}</span>
            {r.is_active === false && (
              <span className="ml-1.5 text-[9px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded bg-slate-100 text-slate-500">Retired</span>
            )}
          </span>,
          r.category,
          <span>{`${r.brand} ${r.model_name}`.trim() || "—"}</span>,
          <span className="font-mono text-xs text-slate-500">{r.hsn || "—"}</span>,
          <span className="tabular-nums text-slate-500">{num(r.opening_stock)}</span>,
          <span className="tabular-nums text-emerald-600">+{num(r.received)}</span>,
          <span className="tabular-nums text-rose-600">−{num(r.dispatched)}</span>,
          // Held by proforma invoices that have not been dispatched. Still on
          // the shelf, so Closing is what is left to sell, not what is there.
          Number(r.reserved) > 0 ? (
            <span title={`${num(r.reserved)} ${r.unit} promised on proforma invoices — ${num(r.physical_stock)} physically in stock`}
              className="tabular-nums font-semibold text-amber-600">{num(r.reserved)}</span>
          ) : (
            <span className="tabular-nums text-slate-300">—</span>
          ),
          <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold whitespace-nowrap ${
            r.status === "REORDER" ? "bg-rose-50 text-rose-600" : "bg-emerald-50 text-emerald-600"}`}
            title={Number(r.reserved) > 0
              ? `${num(r.physical_stock)} in stock − ${num(r.reserved)} reserved`
              : undefined}>
            {r.status === "REORDER" && <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />}
            {num(r.closing_stock)} {r.unit}
          </span>,
          <span className="tabular-nums text-slate-400">{rupee(r.unit_cost)}</span>,
          <span className="tabular-nums font-semibold">{rupee(r.stock_value)}</span>,
          <span className="text-slate-500">{r.location || "—"}</span>,
          // A spectator may read where the stock came from; only the edit and
          // delete actions are withheld.
          readOnly
            ? <RowActions onHistory={() => setHistoryFor(r.id)} />
            : <RowActions onHistory={() => setHistoryFor(r.id)} onEdit={() => openEdit(r)}
                onDelete={() => remove("items", r.id, "item")} />,
        ])} />

      <StockHistoryModal show={historyFor !== null} itemId={historyFor}
        onClose={() => setHistoryFor(null)} />

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
        <Row cols={3}>
          <Fld label="Unit">
            <input value={form.unit} onChange={e => setForm({ ...form, unit: e.target.value })}
              className={FIELD} placeholder="Nos" />
          </Fld>
          <Fld label="HSN / SAC">
            <input value={form.hsn} onChange={e => setForm({ ...form, hsn: e.target.value })}
              className={`${FIELD} font-mono`} placeholder="e.g. 85414300" />
          </Fld>
          <Fld label="Warehouse Location">
            <input value={form.location} onChange={e => setForm({ ...form, location: e.target.value })}
              className={FIELD} placeholder="e.g. Warehouse A - Rack 1" />
          </Fld>
        </Row>
        {editing && (
          <>
            {/* The way to retire an SKU that has stock history behind it and so
                cannot simply be deleted. */}
            <label className="inline-flex items-center gap-2 text-sm font-medium text-slate-700 cursor-pointer">
              <input type="checkbox" checked={form.is_active !== false}
                onChange={e => setForm({ ...form, is_active: e.target.checked })}
                className="w-4 h-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500/30" />
              Active
            </label>
            <p className="text-xs text-slate-400">
              Untick to retire an item you no longer stock but whose movement history has to stay.
              Closing stock is derived from receipts and dispatches — edit those to correct it.
            </p>
          </>
        )}
      </Modal>
    </StockPage>
  );
}

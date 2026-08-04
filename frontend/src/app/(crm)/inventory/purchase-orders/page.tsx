"use client";
/**
 * Inventory → Purchase Order (wholesale).
 *
 * The order raised on a supplier before the goods arrive — the outbound
 * counterpart of the GRN, which receives against it. The printed form is the
 * company's own purchase-order template; its figures are assembled server-side
 * so the document and the stored order can never disagree.
 */
import React, { useState } from "react";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";
import { buildPurchaseOrderPdf, purchaseOrderFileName } from "@/lib/purchaseOrderPdf";
import {
  FIELD, rupee, num, todayISO, useStock, StockPage, AddButton, SearchBar,
  DataTable, Modal, Fld, Row, DocActions, DocumentPreview, I,
} from "../shared";

type Line = {
  item: string; type_of_spare: string; description: string;
  part_code: string; unit_price: string; quantity: string;
};

const blankLine = (): Line =>
  ({ item: "", type_of_spare: "", description: "", part_code: "", unit_price: "", quantity: "" });

const blankForm = () => ({
  po_date: todayISO(), supplier: "", ship_to_address: "", ship_to_phone: "",
  transportation: "", tax_label: "IGST", tax_percent: "18",
  terms_taxes: "As Mentioned", terms_delivery: "Immediately", notes: "",
  lines: [blankLine()],
});

// One grid for the header row and every line, so the columns stay in step.
const LINE_GRID = "grid grid-cols-[24px_1.5fr_1.1fr_1.9fr_1fr_100px_90px_110px_32px]";

const STATUS_TONE: Record<string, string> = {
  draft: "bg-slate-100 text-slate-600",
  sent: "bg-indigo-50 text-indigo-700",
  received: "bg-emerald-50 text-emerald-700",
  cancelled: "bg-rose-50 text-rose-600",
};

export default function StockPurchaseOrderPage() {
  const { purchaseOrders, items, suppliers, loading, denied, save, remove, reload } =
    useStock(["purchaseOrders", "items", "suppliers"]);
  const itemList: any[] = items || [];
  const supplierList: any[] = suppliers || [];
  const list: any[] = purchaseOrders || [];

  const [form, setForm] = useState<any>(blankForm());
  const [editing, setEditing] = useState<any>(null);
  const [show, setShow] = useState(false);
  const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState<number | null>(null);
  const [preview, setPreview] = useState<any>(null);

  const api = getApiBase(APP_SLUG);
  const authHeader = () => ({ Authorization: `Bearer ${localStorage.getItem(`${APP_SLUG}_access`)}` });

  const lines: Line[] = form.lines;
  const setLine = (i: number, patch: Partial<Line>) =>
    setForm((f: any) => ({ ...f, lines: f.lines.map((l: Line, n: number) => (n === i ? { ...l, ...patch } : l)) }));

  // Live totals, mirroring the server: goods + freight, then tax on both.
  const goods = lines.reduce((s, l) => s + (Number(l.quantity) || 0) * (Number(l.unit_price) || 0), 0);
  const taxable = goods + (Number(form.transportation) || 0);
  const taxValue = taxable * (Number(form.tax_percent) || 0) / 100;
  const grand = taxable + taxValue;

  const openCreate = () => { setEditing(null); setForm(blankForm()); setShow(true); };

  const openEdit = (r: any) => {
    setEditing(r);
    setForm({
      po_date: r.po_date || todayISO(), supplier: String(r.supplier || ""),
      ship_to_address: r.ship_to_address || "", ship_to_phone: r.ship_to_phone || "",
      transportation: r.transportation ?? "", tax_label: r.tax_label || "IGST",
      tax_percent: r.tax_percent ?? "18",
      terms_taxes: r.terms_taxes || "", terms_delivery: r.terms_delivery || "",
      notes: r.notes || "",
      lines: (r.items || []).length
        ? r.items.map((li: any) => ({
            item: String(li.item || ""), type_of_spare: li.type_of_spare || "",
            description: li.description || "", part_code: li.part_code || "",
            unit_price: String(li.unit_price ?? ""), quantity: String(li.quantity ?? ""),
          }))
        : [blankLine()],
    });
    setShow(true);
  };

  /** Picking a catalogued item fills the description, part code and rate. */
  const pickItem = (i: number, itemId: string) => {
    const it = itemList.find(x => String(x.id) === String(itemId));
    setLine(i, {
      item: itemId,
      description: lines[i].description || (it ? `${it.brand} ${it.model_name}`.trim() || it.code : ""),
      part_code: lines[i].part_code || (it?.code ?? ""),
      unit_price: lines[i].unit_price || String(it?.unit_cost ?? ""),
      type_of_spare: lines[i].type_of_spare || (it?.category ?? ""),
    });
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.supplier) { alert("Select the supplier this order is raised on."); return; }
    const valid = lines.filter(l => (l.description.trim() || l.item) && Number(l.quantity) > 0);
    if (!valid.length) { alert("Add at least one item with a quantity."); return; }
    setSaving(true);
    const ok = await save("purchaseOrders", {
      po_date: form.po_date, supplier: form.supplier,
      ship_to_address: form.ship_to_address, ship_to_phone: form.ship_to_phone,
      transportation: form.transportation || 0,
      tax_label: form.tax_label, tax_percent: form.tax_percent || 0,
      terms_taxes: form.terms_taxes, terms_delivery: form.terms_delivery, notes: form.notes,
      items: valid.map(l => ({
        item: l.item || null, type_of_spare: l.type_of_spare, description: l.description,
        part_code: l.part_code, unit_price: l.unit_price || 0, quantity: l.quantity,
      })),
    }, editing?.id);
    setSaving(false);
    if (ok) { setShow(false); setEditing(null); setForm(blankForm()); }
  };

  const docName = (r: any) =>
    purchaseOrderFileName({ number: r.number, supplier: r.supplier_name });

  /** Pull the printed figures from the server and render the order. */
  const render = async (r: any) => {
    const res = await fetch(`${api}/api/stock-purchase-orders/${r.id}/document/`, { headers: authHeader() });
    if (!res.ok) { alert("Could not build the purchase order."); return null; }
    return buildPurchaseOrderPdf(await res.json());
  };

  const download = async (r: any) => {
    setBusy(r.id);
    try { const pdf = await render(r); if (pdf) pdf.save(docName(r)); }
    finally { setBusy(null); }
  };

  /** Render, hand the file to the server, and let it email / WhatsApp it. */
  const sendTo = async (r: any, channel: "email" | "whatsapp") => {
    const sup = supplierList.find(s => s.id === r.supplier);
    const label = channel === "email" ? "email address" : "WhatsApp number";
    const fallback = channel === "email" ? (sup?.email || "") : (sup?.phone || "");
    const to = window.prompt(`Send purchase order ${r.number} to which ${label}?`, fallback);
    if (!to) return;

    setBusy(r.id);
    try {
      const pdf = await render(r);
      if (!pdf) return;
      const body = new FormData();
      body.append("pdf", new File([pdf.output("blob")], docName(r), { type: "application/pdf" }));
      body.append("channels", channel);
      body.append(channel === "email" ? "email" : "phone", to);
      const res = await fetch(`${api}/api/stock-purchase-orders/${r.id}/send/`, {
        method: "POST", headers: authHeader(), body,
      });
      const d = await res.json().catch(() => ({}));
      if (!res.ok) { alert(d.error || "Could not send the purchase order."); return; }
      alert((d.warnings || []).length
        ? `Sent, with warnings:\n${d.warnings.join("\n")}`
        : `Purchase order sent by ${channel === "email" ? "email" : "WhatsApp"}.`);
      reload();
    } catch { alert("Network error while sending."); }
    finally { setBusy(null); }
  };

  const term = search.trim().toLowerCase();
  const filtered = !term ? list : list.filter(r =>
    `${r.number || ""} ${r.fy || ""} ${r.supplier_name || ""}`.toLowerCase().includes(term));

  return (
    <StockPage
      title="Purchases" loading={loading} denied={denied}
      subtitle="Purchase orders raised on suppliers — print the order and send it."
      action={<AddButton label="New Purchase Order" onClick={openCreate} />}>

      <SearchBar value={search} onChange={setSearch} placeholder="Search purchase orders..." />

      <DataTable
        minWidth={820} compact
        columns={[
          "PO No.", "Date", "Supplier", { label: "Items", align: "right" },
          { label: "Total", align: "right" }, "Status", { label: "Actions", align: "right" },
        ]}
        empty={{ title: "No purchase orders yet", hint: "Raise your first order on a supplier." }}
        onRowClick={i => setPreview(filtered[i])}
        rowTitle="Open the purchase order"
        rows={filtered.map(r => [
          <span className="font-mono text-xs font-semibold text-slate-900 whitespace-nowrap">{r.number || "—"}</span>,
          <span className="font-mono text-xs text-slate-500 whitespace-nowrap">{r.po_date || "—"}</span>,
          r.supplier_name || "—",
          <span className="tabular-nums">{(r.items || []).length}</span>,
          <span className="tabular-nums font-semibold">{rupee(r.total)}</span>,
          <span className={`text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full ${STATUS_TONE[r.status] || STATUS_TONE.draft}`}>
            {r.status}
          </span>,
          <DocActions busy={busy === r.id}
            onDownload={() => download(r)}
            onEmail={() => sendTo(r, "email")}
            onWhatsApp={() => sendTo(r, "whatsapp")}
            onEdit={() => openEdit(r)}
            onDelete={() => remove("purchaseOrders", r.id, "purchase order")} />,
        ])} />

      <DocumentPreview
        open={!!preview}
        title={preview ? `Purchase Order ${preview.number}` : ""}
        fileName={preview ? docName(preview) : ""}
        render={() => render(preview)}
        onClose={() => setPreview(null)}
        actions={preview && (
          <>
            <button onClick={() => download(preview)}
              className="px-3 py-1.5 bg-indigo-600 text-white rounded-lg text-xs font-semibold hover:bg-indigo-700">Download</button>
            <button onClick={() => sendTo(preview, "email")}
              className="text-xs font-semibold text-slate-500 hover:text-slate-800">Email</button>
            <button onClick={() => sendTo(preview, "whatsapp")}
              className="text-xs font-semibold text-emerald-600 hover:text-emerald-800">WhatsApp</button>
          </>
        )} />

      <Modal show={show} xl title={`${editing ? `Edit Purchase Order ${editing.number}` : "New Purchase Order"}`}
        onClose={() => setShow(false)} onSubmit={submit} saving={saving} submitLabel="Save Purchase Order">
        <Row>
          <Fld label="Supplier *">
            <select required value={form.supplier}
              onChange={e => setForm({ ...form, supplier: e.target.value })} className={FIELD}>
              <option value="">Select supplier…</option>
              {supplierList.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </Fld>
          <Fld label="PO Date *">
            <input type="date" required value={form.po_date}
              onChange={e => setForm({ ...form, po_date: e.target.value })} className={FIELD} />
          </Fld>
        </Row>
        <p className="-mt-2 text-xs text-slate-400">
          The PO number is issued from this financial year&apos;s series when the order is saved (REN2627-PO001).
          The supplier&apos;s PAN, IEC and GST print from their Suppliers record.
        </p>

        {/* The delivery address is the longest thing on the form, so it gets the
            width rather than sharing a row. */}
        <div className="grid grid-cols-1 sm:grid-cols-[3fr_1fr] gap-4">
          <Fld label="Ship to — Address">
            <input value={form.ship_to_address} placeholder="Blank uses the company address"
              onChange={e => setForm({ ...form, ship_to_address: e.target.value })} className={FIELD} />
          </Fld>
          <Fld label="Ship to — Phone">
            <input value={form.ship_to_phone}
              onChange={e => setForm({ ...form, ship_to_phone: e.target.value })} className={FIELD} />
          </Fld>
        </div>

        <div>
          <label className="block text-sm font-semibold text-slate-700 mb-1.5">Items</label>
          {/* The columns the printed form carries, in its order, so what is
              typed here reads the way it will print. On a narrow screen the
              table scrolls sideways rather than crushing its fields. */}
          <div className="overflow-x-auto -mx-1 px-1">
          <div className="min-w-[860px]">
            <div className={`${LINE_GRID} gap-2 px-1 pb-1`}>
              {["SL", "Item", "Type of Spare", "Description", "Part Code", "Unit Price", "Quantity", "Base Amount", ""]
                .map((h, n) => (
                  <span key={n} className={`text-[10px] font-bold uppercase tracking-wider text-slate-400 ${n >= 5 && n <= 7 ? "text-right" : ""}`}>
                    {h}
                  </span>
                ))}
            </div>
            <div className="space-y-2">
              {lines.map((l, i) => (
                <div key={i} className={`${LINE_GRID} gap-2 items-center`}>
                  <span className="text-xs font-semibold text-slate-400 tabular-nums pl-1">{i + 1}</span>
                  <select value={l.item} onChange={e => pickItem(i, e.target.value)} className={FIELD}>
                    <option value="">— none —</option>
                    {itemList.map(it => (
                      <option key={it.id} value={it.id}>{it.code} — {`${it.brand} ${it.model_name}`.trim()}</option>
                    ))}
                  </select>
                  <input value={l.type_of_spare}
                    onChange={e => setLine(i, { type_of_spare: e.target.value })} className={FIELD} />
                  <input value={l.description} placeholder="e.g. R-KEM-II-300"
                    onChange={e => setLine(i, { description: e.target.value })} className={FIELD} />
                  <input value={l.part_code}
                    onChange={e => setLine(i, { part_code: e.target.value })} className={FIELD} />
                  <input type="number" step="any" min="0" value={l.unit_price}
                    onChange={e => setLine(i, { unit_price: e.target.value })} className={`${FIELD} text-right`} />
                  <input type="number" step="any" min="0" value={l.quantity}
                    onChange={e => setLine(i, { quantity: e.target.value })} className={`${FIELD} text-right`} />
                  <span className="text-sm font-semibold text-slate-700 tabular-nums text-right pr-1">
                    {rupee((Number(l.quantity) || 0) * (Number(l.unit_price) || 0))}
                  </span>
                  {lines.length > 1 ? (
                    <button type="button" aria-label="Remove item"
                      onClick={() => setForm((f: any) => ({ ...f, lines: f.lines.filter((_: Line, n: number) => n !== i) }))}
                      className="w-8 h-8 flex items-center justify-center rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-all">
                      <I.Trash />
                    </button>
                  ) : <span />}
                </div>
              ))}
            </div>
          </div>
          </div>
          <button type="button"
            onClick={() => setForm((f: any) => ({ ...f, lines: [...f.lines, blankLine()] }))}
            className="mt-2 text-xs font-semibold text-indigo-600 hover:text-indigo-800">
            + Add item
          </button>
          <p className="mt-1 text-xs text-slate-400">
            Item is optional — pick one to fill the rest from the catalogue, or type a one-off spare.
          </p>
        </div>

        <Row>
          <Fld label="Transportation (₹)">
            <input type="number" step="any" min="0" value={form.transportation}
              onChange={e => setForm({ ...form, transportation: e.target.value })}
              className={FIELD} placeholder="e.g. 800" />
          </Fld>
          <Fld label="Tax">
            <div className="flex gap-2">
              <select value={form.tax_label} onChange={e => setForm({ ...form, tax_label: e.target.value })}
                className={FIELD}>
                <option value="IGST">IGST</option>
                <option value="GST">GST</option>
                <option value="CGST+SGST">CGST+SGST</option>
              </select>
              <input type="number" step="any" min="0" max="100" value={form.tax_percent}
                onChange={e => setForm({ ...form, tax_percent: e.target.value })}
                className={FIELD} placeholder="18" />
            </div>
          </Fld>
        </Row>

        <Row>
          <Fld label="Terms — Taxes">
            <input value={form.terms_taxes}
              onChange={e => setForm({ ...form, terms_taxes: e.target.value })} className={FIELD} />
          </Fld>
          <Fld label="Terms — Delivery">
            <input value={form.terms_delivery}
              onChange={e => setForm({ ...form, terms_delivery: e.target.value })} className={FIELD} />
          </Fld>
        </Row>

        <Fld label="Notes">
          <textarea rows={2} value={form.notes}
            onChange={e => setForm({ ...form, notes: e.target.value })} className={FIELD} />
        </Fld>

        <div className="flex items-center justify-between gap-4 pt-3 border-t border-slate-100 text-sm">
          <span className="text-xs text-slate-400 tabular-nums">
            Goods {rupee(goods)} · Freight {rupee(Number(form.transportation) || 0)} · {form.tax_label} {rupee(taxValue)}
          </span>
          <span className="font-bold text-slate-900 tabular-nums">Total {rupee(grand)}</span>
        </div>
      </Modal>
    </StockPage>
  );
}

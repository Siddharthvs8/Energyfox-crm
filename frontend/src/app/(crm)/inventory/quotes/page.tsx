"use client";
/**
 * Inventory → Quotes (wholesale).
 *
 * Laid out like /quotes: header button, modal with line items, card table.
 * Converting a quote writes a dispatch row per line — that is what takes the
 * goods out of stock — so a converted quote is locked from then on.
 */
import React, { useState } from "react";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";
import { buildProformaPdf, proformaFileName } from "@/lib/proformaPdf";
import { STATES, HOME_STATE } from "@/lib/states";
import {
  FIELD, rupee, num, todayISO, useStock, StockPage, AddButton, SearchBar,
  DataTable, Modal, Fld, Row, DocActions, DocumentPreview, I,
} from "../shared";

type Line = { item: string; description: string; quantity: string; unit_price: string };

const blankLine = (): Line => ({ item: "", description: "", quantity: "1", unit_price: "" });
const blankForm = () => ({
  customer: "", quote_date: todayISO(), expiry_date: "", site: "", status: "draft",
  ship_to_state: HOME_STATE, ship_to_gstin: "",
  efc_ref_no: "", discount_percent: "", tax_percent: "", notes: "",
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
  const { quotes, items, customers, loading, denied, save, remove, act, reload } =
    useStock(["quotes", "items", "customers"]);
  // StockPage's children are evaluated before it swaps in the spinner, so every
  // collection has to be safe on the first render.
  const itemList: any[] = items || [];
  const customerList: any[] = customers || [];
  const quoteList: any[] = quotes || [];

  const [form, setForm] = useState(blankForm());
  const [editing, setEditing] = useState<any>(null);
  const [show, setShow] = useState(false);
  const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState<number | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [preview, setPreview] = useState<any>(null);

  const lines = form.items;
  const setLine = (i: number, patch: Partial<Line>) =>
    setForm(f => ({ ...f, items: f.items.map((l, n) => (n === i ? { ...l, ...patch } : l)) }));

  // Live totals, mirroring the server: subtotal → discount → tax.
  const subtotal = lines.reduce((s, l) => s + (Number(l.quantity) || 0) * (Number(l.unit_price) || 0), 0);
  const discount = subtotal * (Number(form.discount_percent) || 0) / 100;
  const tax = (subtotal - discount) * (Number(form.tax_percent) || 0) / 100;
  const total = subtotal - discount + tax;

  const openCreate = () => { setEditing(null); setForm(blankForm()); setShow(true); };
  const openEdit = (q: any) => {
    setEditing(q);
    setForm({
      customer: q.customer || "", quote_date: q.quote_date || todayISO(),
      expiry_date: q.expiry_date || "", site: q.site || "", status: q.status,
      ship_to_state: q.ship_to_state || HOME_STATE, ship_to_gstin: q.ship_to_gstin || "",
      efc_ref_no: q.efc_ref_no || "",
      discount_percent: q.discount_percent ?? "", tax_percent: q.tax_percent ?? "",
      notes: q.notes || "",
      items: (q.items || []).map((l: any) => ({
        item: String(l.item), description: l.description || "",
        quantity: String(l.quantity), unit_price: String(l.unit_price),
      })) || [blankLine()],
    });
    setShow(true);
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const valid = lines.filter(l => l.item && Number(l.quantity) > 0);
    if (!valid.length) { alert("Add at least one line with an item and a quantity."); return; }
    setSaving(true);
    const ok = await save("quotes", {
      ...form,
      customer: form.customer || null,
      expiry_date: form.expiry_date || null,
      discount_percent: form.discount_percent || 0,
      tax_percent: form.tax_percent || 0,
      items: valid.map(l => ({
        item: l.item, description: l.description,
        quantity: l.quantity, unit_price: l.unit_price || 0,
      })),
    }, editing?.id);
    setSaving(false);
    if (ok) { setShow(false); setEditing(null); setForm(blankForm()); }
  };

  /** Selecting a customer pulls their delivery details across. */
  const pickCustomer = (id: string) => {
    const c = customerList.find(x => String(x.id) === String(id));
    setForm((f: any) => ({
      ...f,
      customer: id,
      // Only fill what has not been typed over, so a deliberate override stands.
      ship_to_state: f.ship_to_state && f.ship_to_state !== HOME_STATE
        ? f.ship_to_state : (c?.state || HOME_STATE),
      ship_to_gstin: f.ship_to_gstin || c?.gstin || "",
      site: f.site || c?.site_address || "",
    }));
  };

  const api = getApiBase(APP_SLUG);
  const authHeader = () => ({ Authorization: `Bearer ${localStorage.getItem(`${APP_SLUG}_access`)}` });

  /** Pull the printed figures from the server and render the template. */
  const render = async (q: any) => {
    const r = await fetch(`${api}/api/stock-quotes/${q.id}/proforma/`, { headers: authHeader() });
    if (!r.ok) { alert("Could not build the document."); return null; }
    return buildProformaPdf(await r.json());
  };

  const download = async (q: any) => {
    setBusy(q.id);
    try {
      const pdf = await render(q);
      if (pdf) pdf.save(proformaFileName(q.number));
    } finally { setBusy(null); }
  };

  /** Render, hand the file to the server, and let it email / WhatsApp it. */
  const sendTo = async (q: any, channel: "email" | "whatsapp") => {
    const cust = customerList.find(c => c.id === q.customer);
    const label = channel === "email" ? "email address" : "WhatsApp number";
    const fallback = channel === "email" ? "" : (cust?.contact_number || cust?.phone || "");
    const to = window.prompt(`Send ${q.number} to which ${label}?`, fallback);
    if (!to) return;

    setBusy(q.id);
    try {
      const pdf = await render(q);
      if (!pdf) return;
      const body = new FormData();
      body.append("pdf", new File([pdf.output("blob")], proformaFileName(q.number),
                                  { type: "application/pdf" }));
      body.append("channels", channel);
      body.append(channel === "email" ? "email" : "phone", to);
      const r = await fetch(`${api}/api/stock-quotes/${q.id}/send/`, {
        method: "POST", headers: authHeader(), body,
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) { alert(d.error || "Could not send the document."); return; }
      alert((d.warnings || []).length
        ? `Sent, with warnings:\n${d.warnings.join("\n")}`
        : `${q.number} sent by ${channel === "email" ? "email" : "WhatsApp"}.`);
      reload();
    } catch { alert("Network error while sending."); }
    finally { setBusy(null); }
  };

  const convert = async (q: any) => {
    if (!confirm(`Dispatch ${q.number}? This takes ${q.items.length} line(s) out of stock.`)) return;
    const d = await act(`stock-quotes/${q.id}/convert`);
    if (d) alert(`${q.number} dispatched — ${d.dispatched_lines} line(s) recorded.`);
  };

  const term = search.trim().toLowerCase();
  const filtered = !term ? quoteList : quoteList.filter(q =>
    `${q.number} ${q.customer_name || ""} ${q.status}`.toLowerCase().includes(term));

  return (
    <StockPage
      title="Proforma Invoice" loading={loading} denied={denied}
      subtitle="Raise a proforma invoice from stock — download it, send it, and dispatch when accepted."
      action={itemList.length > 0 ? <AddButton label="New Proforma Invoice" onClick={openCreate} /> : undefined}>

      {itemList.length === 0 ? (
        <DataTable columns={["Quote"]} rows={[]}
          empty={{ title: "No items yet", hint: "Add an item in Item Master first — a proforma invoice is priced off stock items." }} />
      ) : (
        <>
          <SearchBar value={search} onChange={setSearch} placeholder="Search proforma invoices..." />

          <DataTable
            minWidth={800} compact
            columns={[
              "Invoice No.", "Customer", "Date", { label: "Status", align: "center" },
              { label: "Total", align: "right" }, { label: "Actions", align: "right" },
            ]}
            empty={{ title: "No proforma invoices yet", hint: "Raise your first proforma invoice." }}
            onRowClick={i => setPreview(filtered[i])}
            rowTitle="Open the proforma invoice"
            rows={filtered.map(q => [
              <button onClick={e => { e.stopPropagation(); setOpen(open === q.id ? null : q.id); }}
                className="font-mono text-xs font-semibold text-indigo-600 hover:text-indigo-900"
                title="Show the lines on this invoice">{q.number}</button>,
              q.customer_name || "—",
              <span className="font-mono text-xs text-slate-500 whitespace-nowrap">{q.quote_date || "—"}</span>,
              <span className={`inline-flex text-[10px] font-bold uppercase tracking-wider px-2 py-1 rounded-full ${STATUS_STYLE[q.status] || "bg-slate-100 text-slate-600"}`}>
                {q.status}
              </span>,
              <span className="tabular-nums font-semibold">{rupee(q.total)}</span>,
              // A converted invoice can no longer be dispatched or edited — its
              // stock has already gone out — but it can still be deleted.
              <DocActions busy={busy === q.id}
                onDownload={() => download(q)}
                onEmail={() => sendTo(q, "email")}
                onWhatsApp={() => sendTo(q, "whatsapp")}
                onDispatch={q.status === "converted" ? undefined : () => convert(q)}
                onEdit={q.status === "converted" ? undefined : () => openEdit(q)}
                onDelete={() => remove("quotes", q.id, "proforma invoice",
                  q.status === "converted"
                    ? `${q.number} has already been dispatched. Deleting it removes the proforma invoice only — the dispatch, its invoice and the stock movement stay. Delete it?`
                    : `Delete ${q.number}?`)} />,
            ])} />
        </>
      )}

      {/* Line detail for the quote whose number was clicked. */}
      {open !== null && (() => {
        const q = quoteList.find(x => x.id === open);
        if (!q) return null;
        return (
          <div className="bg-white rounded-2xl shadow-sm border border-slate-200 mt-4 overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
              <h2 className="font-bold text-slate-900">{q.number} · lines</h2>
              <button onClick={() => setOpen(null)} className="text-slate-400 hover:text-slate-600"><I.X /></button>
            </div>
            <DataTable minWidth={620}
              columns={["Item", "Description", { label: "Qty", align: "right" },
                        { label: "Rate", align: "right" }, { label: "Amount", align: "right" }]}
              rows={q.items.map((l: any) => [
                <span><span className="font-mono text-xs">{l.item_code}</span> <span className="text-slate-400">— {l.item_label}</span></span>,
                l.description || "—",
                <span className="tabular-nums">{num(l.quantity)}</span>,
                <span className="tabular-nums">{rupee(l.unit_price)}</span>,
                <span className="tabular-nums font-semibold">{rupee(l.line_total)}</span>,
              ])} />
            <p className="text-xs text-slate-500 px-6 py-4 text-right tabular-nums">
              Subtotal {rupee(q.subtotal)} · Discount −{rupee(q.discount_amount)} · Tax {rupee(q.tax_amount)} ·{" "}
              <b className="text-slate-800">Total {rupee(q.total)}</b>
            </p>
          </div>
        );
      })()}

      <DocumentPreview
        open={!!preview}
        title={preview ? `Proforma Invoice ${preview.number}` : ""}
        fileName={preview ? proformaFileName(preview.number) : ""}
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

      <Modal show={show} wide title={editing ? `Edit ${editing.number}` : "New Proforma Invoice"}
        onClose={() => setShow(false)} onSubmit={submit} saving={saving} submitLabel="Save Proforma Invoice">
        <Row>
          <Fld label="Customer">
            <select value={form.customer} onChange={e => pickCustomer(e.target.value)} className={FIELD}>
              <option value="">—</option>
              {customerList.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </Fld>
          <Fld label="Status">
            <select value={form.status} onChange={e => setForm({ ...form, status: e.target.value })} className={FIELD}>
              <option value="draft">Draft</option>
              <option value="sent">Sent</option>
              <option value="accepted">Accepted</option>
              <option value="declined">Declined</option>
            </select>
          </Fld>
        </Row>
        <Row>
          <Fld label="Invoice Date *">
            <input type="date" required value={form.quote_date}
              onChange={e => setForm({ ...form, quote_date: e.target.value })} className={FIELD} />
          </Fld>
          <Fld label="Expiry Date">
            <input type="date" value={form.expiry_date}
              onChange={e => setForm({ ...form, expiry_date: e.target.value })} className={FIELD} />
          </Fld>
        </Row>
        <Row cols={3}>
          <Fld label="EFC Ref No.">
            <input value={form.efc_ref_no} onChange={e => setForm({ ...form, efc_ref_no: e.target.value })}
              className={FIELD} placeholder="Printed on the invoice" />
          </Fld>
          <Fld label="State (shipped to)">
            <select value={form.ship_to_state} onChange={e => setForm({ ...form, ship_to_state: e.target.value })}
              className={FIELD}>
              {STATES.map(st => <option key={st} value={st}>{st}</option>)}
            </select>
          </Fld>
          <Fld label="GST No. (shipped to)">
            <input value={form.ship_to_gstin} onChange={e => setForm({ ...form, ship_to_gstin: e.target.value })}
              className={`${FIELD} font-mono`} placeholder="Auto-filled from the customer" />
          </Fld>
        </Row>
        <Fld label="Site Address">
          <input value={form.site} onChange={e => setForm({ ...form, site: e.target.value })} className={FIELD} />
        </Fld>

        <div>
          <label className="block text-sm font-semibold text-slate-700 mb-1.5">Items</label>
          <div className="space-y-2">
            {lines.map((l, i) => (
              <div key={i} className="grid grid-cols-[2fr_1.4fr_80px_110px_32px] gap-2 items-center">
                <select value={l.item} onChange={e => setLine(i, { item: e.target.value })} className={FIELD}>
                  <option value="">Select item…</option>
                  {itemList.map(it => (
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
                  <button type="button" aria-label="Remove line"
                    onClick={() => setForm(f => ({ ...f, items: f.items.filter((_, n) => n !== i) }))}
                    className="w-8 h-8 flex items-center justify-center rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-all">
                    <I.Trash />
                  </button>
                ) : <span />}
              </div>
            ))}
          </div>
          <button type="button" onClick={() => setForm(f => ({ ...f, items: [...f.items, blankLine()] }))}
            className="mt-2 text-xs font-semibold text-indigo-600 hover:text-indigo-800">
            + Add item
          </button>
        </div>

        <Row>
          <Fld label="Discount %">
            <input type="number" step="any" min="0" max="100" value={form.discount_percent}
              onChange={e => setForm({ ...form, discount_percent: e.target.value })} className={FIELD} />
          </Fld>
          <Fld label="Tax %">
            <input type="number" step="any" min="0" max="100" value={form.tax_percent}
              onChange={e => setForm({ ...form, tax_percent: e.target.value })} className={FIELD} />
          </Fld>
        </Row>

        <div className="flex items-center justify-between gap-4 pt-3 border-t border-slate-100 text-sm">
          <span className="text-xs text-slate-400 tabular-nums">
            Subtotal {rupee(subtotal)} · Discount −{rupee(discount)} · Tax {rupee(tax)}
          </span>
          <span className="font-bold text-slate-900 tabular-nums">Total {rupee(total)}</span>
        </div>
      </Modal>
    </StockPage>
  );
}

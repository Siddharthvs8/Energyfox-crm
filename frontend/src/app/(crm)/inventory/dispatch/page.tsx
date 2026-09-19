"use client";
/**
 * Inventory → Sales / Dispatches (wholesale).
 *
 * A dispatch is stored as one row per item — that is what the stock ledger
 * values — so a delivery of several products is several rows sharing one
 * invoice number. This screen writes that whole set in one save and prints the
 * invoice for it, using the same template the proforma does with the wording
 * changed, because a dispatch is the sale rather than the offer.
 */
import React, { useState } from "react";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";
import { buildProformaPdf, proformaFileName } from "@/lib/proformaPdf";
import {
  FIELD, rupee, num, todayISO, useStock, StockPage, AddButton, SearchBar,
  DataTable, Modal, Fld, Row, DocActions, DocumentPreview, I,
  PaymentVerificationModal, VerifiedPayment, PaymentRow,
} from "../shared";

type Line = { item: string; serial_numbers: string; quantity: string; rate: string };

const blankLine = (): Line => ({ item: "", serial_numbers: "", quantity: "", rate: "" });
const blankForm = () => ({
  invoice_no: "", date: todayISO(), customer: "", tax_percent: "", site: "", notes: "",
  lines: [blankLine()],
});

export default function StockDispatchPage() {
  const { dispatches, items, customers, loading, denied, readOnly, save, act, remove, reload } =
    useStock(["dispatches", "items", "customers"], "dispatch");
  const itemList: any[] = items || [];
  const customerList: any[] = customers || [];
  const list: any[] = dispatches || [];

  const [form, setForm] = useState<any>(blankForm());
  const [editing, setEditing] = useState<any>(null);
  const [show, setShow] = useState(false);
  const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState<number | null>(null);
  const [preview, setPreview] = useState<any>(null);
  // Save Dispatch does not write anything: it hands the delivery to the payment
  // gate, and the gate is what posts it. Nothing exists until the invoice has
  // been settled.
  const [pendingLines, setPendingLines] = useState<Line[] | null>(null);
  // A delivery already on the books, open at its payment screen.
  const [settling, setSettling] = useState<any>(null);
  const [position, setPosition] = useState<{ total: number; received: number;
                                            exact: number | null; balance: number | null;
                                            settled: boolean | null; payments: PaymentRow[] }>(
    { total: 0, received: 0, exact: null, balance: null, settled: null, payments: [] });
  const [working, setWorking] = useState(false);

  const lines: Line[] = form.lines;
  const setLine = (i: number, patch: Partial<Line>) =>
    setForm((f: any) => ({ ...f, lines: f.lines.map((l: Line, n: number) => (n === i ? { ...l, ...patch } : l)) }));

  // Live totals, mirroring the server: goods value, then tax on top.
  const totalOf = (rows: Line[]) => {
    const goodsValue = rows.reduce((s, l) => s + (Number(l.quantity) || 0) * (Number(l.rate) || 0), 0);
    return goodsValue + goodsValue * (Number(form.tax_percent) || 0) / 100;
  };
  const goods = lines.reduce((s, l) => s + (Number(l.quantity) || 0) * (Number(l.rate) || 0), 0);
  const taxValue = goods * (Number(form.tax_percent) || 0) / 100;
  const grand = goods + taxValue;

  const openCreate = () => { setEditing(null); setForm(blankForm()); setShow(true); };

  /** Editing touches the one row that was clicked, not the whole delivery. */
  const openEdit = (r: any) => {
    setEditing(r);
    setForm({
      invoice_no: r.invoice_no || "", date: r.date || todayISO(),
      customer: r.customer || "", tax_percent: r.tax_percent ?? "",
      site: r.site || "", notes: r.notes || "",
      lines: [{
        item: String(r.item || ""), serial_numbers: r.serial_numbers || "",
        quantity: String(r.quantity ?? ""), rate: String(r.rate ?? ""),
      }],
    });
    setShow(true);
  };

  const pickItem = (i: number, itemId: string) => {
    const it = itemList.find(x => String(x.id) === String(itemId));
    setLine(i, { item: itemId, rate: lines[i].rate || String(it?.unit_cost ?? "") });
  };

  const header = () => ({
    date: form.date, customer: form.customer || null,
    tax_percent: form.tax_percent || 0, site: form.site, notes: form.notes,
  });

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const valid = lines.filter(l => l.item && Number(l.quantity) > 0);
    if (!valid.length) { alert("Add at least one product with a quantity."); return; }

    // Editing touches a row that has already gone out; it is a correction to
    // paperwork, not a fresh release of goods, so it does not re-verify.
    if (editing) {
      setSaving(true);
      const l = valid[0];
      const saved = await save("dispatches", {
        ...header(), invoice_no: form.invoice_no, item: l.item,
        serial_numbers: l.serial_numbers, quantity: l.quantity, rate: l.rate || 0,
      }, editing.id);
      setSaving(false);
      if (saved) { setShow(false); setEditing(null); setForm(blankForm()); }
      return;
    }

    // A new delivery: raise it, then settle it. Nothing ships yet.
    setPendingLines(valid);
  };

  /** Write the delivery. Every line in one request, so a half-written delivery
   *  is not a state that can exist — but *pending*: its goods stay on the shelf,
   *  reserved, until the invoice is settled and it is released. */
  const raiseDispatch = async (payment?: VerifiedPayment) => {
    if (!pendingLines) return;
    setSaving(true);
    const d = await act("stock-dispatches/dispatch", {
      ...header(),
      invoice_no: form.invoice_no || undefined,
      lines: pendingLines.map(l => ({
        item: l.item, serial_numbers: l.serial_numbers,
        quantity: l.quantity, rate: l.rate || 0,
      })),
      ...(payment ? { payment } : {}),
    });
    setSaving(false);
    if (!d) return;                            // refused; stay put
    setPendingLines(null);
    setShow(false);
    setEditing(null);
    setForm(blankForm());
    // Straight on to its payment screen: raising it is only half the job.
    openPayments({ invoice_no: d.invoice_no });
  };

  /** Open a delivery's payment screen, showing what it has taken so far. */
  const openPayments = async (r: any) => {
    setPosition({ total: 0, received: 0, exact: null, balance: null, settled: null, payments: [] });
    setSettling(r);
    try {
      const res = await fetch(`${api}/api/stock-dispatches/verify-payment/?invoice_no=${encodeURIComponent(r.invoice_no)}`,
        { headers: authHeader() });
      if (res.ok) {
        const d = await res.json();
        setPosition({ total: Number(d.invoice_total || 0), received: Number(d.amount_received || 0),
                      exact: d.exact_total != null ? Number(d.exact_total) : null,
                      balance: d.balance != null ? Number(d.balance) : null,
                      settled: d.fully_paid ?? null, payments: d.payments || [] });
      }
    } catch { /* the modal still opens */ }
  };

  const verifyPayment = async (payment: VerifiedPayment) => {
    if (!settling) return;
    setWorking(true);
    const d = await act("stock-dispatches/verify-payment", { invoice_no: settling.invoice_no, payment });
    setWorking(false);
    if (!d) return;
    setPosition({ total: Number(d.invoice_total || 0), received: Number(d.amount_received || 0),
                  exact: d.exact_total != null ? Number(d.exact_total) : null,
                  balance: d.balance != null ? Number(d.balance) : null,
                  settled: d.fully_paid ?? null, payments: d.payments || [] });
  };

  const releaseNow = async () => {
    if (!settling) return;
    setWorking(true);
    const d = await act("stock-dispatches/release", { invoice_no: settling.invoice_no });
    setWorking(false);
    if (!d) return;
    setSettling(null);
    alert(`${settling.invoice_no} dispatched — the stock has moved.`);
  };

  const api = getApiBase(APP_SLUG);
  const authHeader = () => ({ Authorization: `Bearer ${localStorage.getItem(`${APP_SLUG}_access`)}` });

  const docName = (r: any) => proformaFileName(r.invoice_no || `DSP-${r.id}`);

  /** The serials on a row, as entered — comma or newline separated. */
  const serialsOf = (r: any): string[] =>
    String(r.serial_numbers || "").split(/[\r\n,]+/).map(t => t.trim()).filter(Boolean);

  /** Pull the printed figures from the server and render the invoice. */
  const render = async (r: any) => {
    const res = await fetch(`${api}/api/stock-dispatches/${r.id}/invoice/`, { headers: authHeader() });
    if (!res.ok) { alert("Could not build the invoice."); return null; }
    return buildProformaPdf(await res.json());
  };

  const download = async (r: any) => {
    setBusy(r.id);
    try {
      const pdf = await render(r);
      if (pdf) pdf.save(docName(r));
    } finally { setBusy(null); }
  };

  /** Render, hand the file to the server, and let it email / WhatsApp it. */
  const sendTo = async (r: any, channel: "email" | "whatsapp") => {
    const cust = customerList.find(c => c.id === r.customer);
    const label = channel === "email" ? "email address" : "WhatsApp number";
    const fallback = channel === "email" ? "" : (cust?.contact_number || cust?.phone || "");
    const to = window.prompt(`Send invoice ${r.invoice_no || `DSP-${r.id}`} to which ${label}?`, fallback);
    if (!to) return;

    setBusy(r.id);
    try {
      const pdf = await render(r);
      if (!pdf) return;
      const body = new FormData();
      body.append("pdf", new File([pdf.output("blob")], docName(r), { type: "application/pdf" }));
      body.append("channels", channel);
      body.append(channel === "email" ? "email" : "phone", to);
      const res = await fetch(`${api}/api/stock-dispatches/${r.id}/send/`, {
        method: "POST", headers: authHeader(), body,
      });
      const d = await res.json().catch(() => ({}));
      if (!res.ok) { alert(d.error || "Could not send the invoice."); return; }
      alert((d.warnings || []).length
        ? `Sent, with warnings:\n${d.warnings.join("\n")}`
        : `Invoice sent by ${channel === "email" ? "email" : "WhatsApp"}.`);
      reload();
    } catch { alert("Network error while sending."); }
    finally { setBusy(null); }
  };

  const term = search.trim().toLowerCase();
  const filtered = !term ? list : list.filter(r =>
    `${r.invoice_no || ""} ${r.item_code || ""} ${r.item_label || ""} ${r.customer_name || ""} ${r.serial_numbers || ""}`
      .toLowerCase().includes(term));

  return (
    <StockPage
      title="Sales / Dispatches" loading={loading} denied={denied}
      subtitle="Goods going out to customers — raise the invoice, send it, and the stock ledger follows."
      action={readOnly ? undefined : <AddButton label="New Dispatch" onClick={openCreate} />}>

      <SearchBar value={search} onChange={setSearch} placeholder="Search dispatches..." />

      {/* A pending delivery is stock held, not stock gone — worth saying once at
          the top rather than leaving it to be inferred from the badges. */}
      {list.some(r => r.status === "pending") && (
        <p className="mb-3 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-xl px-4 py-2.5">
          Deliveries marked <b>not yet shipped</b> are recorded and their stock is held, but the
          goods have not left. Settle the invoice, then dispatch.
        </p>
      )}

      <DataTable
        minWidth={880} compact
        columns={[
          "Invoice No.", "Customer", "Date", "Item", "Serial No.",
          { label: "Qty", align: "right" }, { label: "Total", align: "right" },
          { label: "Payment", align: "center" },
          { label: "Actions", align: "right" },
        ]}
        empty={{ title: "No dispatches yet", hint: "Record your first dispatch to a customer." }}
        onRowClick={i => setPreview(filtered[i])}
        rowTitle="Open the invoice"
        rows={filtered.map(r => [
          <span className="font-mono text-xs font-semibold text-slate-900 whitespace-nowrap">
            {r.invoice_no || "—"}
            {r.status === "pending" && (
              <span className="block text-[9px] font-bold uppercase tracking-wider text-amber-600">
                not yet shipped
              </span>
            )}
          </span>,
          r.customer_name || "—",
          <span className="font-mono text-xs text-slate-500 whitespace-nowrap">{r.date || "—"}</span>,
          <div className="min-w-[120px]">
            <span className="font-mono text-xs whitespace-nowrap">{r.item_code}</span>
            <span className="block text-[11px] text-slate-400">{r.item_label}</span>
          </div>,
          (() => {
            const serials = serialsOf(r);
            if (!serials.length) return <span className="text-slate-300">—</span>;
            // Wrapped rather than run out sideways, so the row grows downward
            // instead of the table growing past the page. Joined with ", " —
            // the stored form has no spaces, which leaves the browser nothing to
            // wrap on, and that is what was stretching the column. break-words
            // rather than break-all so a serial is never split down the middle.
            return (
              <div className="max-w-[180px]">
                <span className="font-mono text-[10px] leading-relaxed text-slate-500 break-words">
                  {serials.join(", ")}
                </span>
                {serials.length > 1 && (
                  <span className="block text-[9px] font-semibold uppercase tracking-wider text-slate-300 mt-0.5">
                    {serials.length} serials
                  </span>
                )}
              </div>
            );
          })(),
          <span className="tabular-nums">{num(r.quantity)}</span>,
          <span className="tabular-nums font-semibold">{rupee(r.total)}</span>,
          r.status === "pending" ? (
            <button onClick={e => { e.stopPropagation(); openPayments(r); }}
              title={`${rupee(r.amount_received)} received · ${rupee(r.balance)} owing`}
              className={`inline-flex text-[10px] font-bold uppercase tracking-wider px-2 py-1 rounded-full transition-colors ${
                r.fully_paid
                  ? "bg-emerald-50 text-emerald-700 hover:bg-emerald-100"
                  : "bg-amber-50 text-amber-700 hover:bg-amber-100"}`}>
              {r.fully_paid ? "Settled · dispatch" : `Owing ${rupee(r.balance)}`}
            </button>
          ) : (
            <span title={`Released${r.released_at ? ` on ${new Date(r.released_at).toLocaleDateString("en-IN")}` : ""}`}
              className="inline-flex text-[10px] font-bold uppercase tracking-wider px-2 py-1 rounded-full bg-slate-100 text-slate-600">
              Dispatched
            </span>
          ),
          <DocActions busy={busy === r.id}
            onDownload={() => download(r)}
            onEmail={() => sendTo(r, "email")}
            onWhatsApp={() => sendTo(r, "whatsapp")}
            onEdit={readOnly ? undefined : () => openEdit(r)}
            onDelete={readOnly ? undefined : () => remove("dispatches", r.id, "dispatch")} />,
        ])} />

      <DocumentPreview
        open={!!preview}
        title={preview ? `Invoice ${preview.invoice_no || `DSP-${preview.id}`}` : ""}
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

      <Modal show={show} wide title={editing ? "Edit Dispatch" : "New Dispatch"}
        onClose={() => setShow(false)} onSubmit={submit} saving={saving} submitLabel="Save Dispatch">
        <Row>
          <Fld label="Invoice No.">
            {/* Issued from this year's series on save; typing one overrides it. */}
            <input value={form.invoice_no} onChange={e => setForm({ ...form, invoice_no: e.target.value })}
              className={`${FIELD} font-mono`} placeholder="Auto — REN2627-IN001" />
          </Fld>
          <Fld label="Date *">
            <input type="date" required value={form.date}
              onChange={e => setForm({ ...form, date: e.target.value })} className={FIELD} />
          </Fld>
        </Row>
        <Row>
          <Fld label="Customer">
            <select value={form.customer} onChange={e => setForm({ ...form, customer: e.target.value })} className={FIELD}>
              <option value="">—</option>
              {customerList.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </Fld>
          <Fld label="Tax %">
            <input type="number" step="any" min="0" max="100" value={form.tax_percent}
              onChange={e => setForm({ ...form, tax_percent: e.target.value })} className={FIELD} placeholder="e.g. 18" />
          </Fld>
        </Row>

        <div>
          <label className="block text-sm font-semibold text-slate-700 mb-1.5">Products</label>
          <div className="space-y-2">
            {lines.map((l, i) => (
              <div key={i} className="grid grid-cols-[1.8fr_1.4fr_80px_110px_32px] gap-2 items-center">
                <select value={l.item} onChange={e => pickItem(i, e.target.value)} className={FIELD}>
                  <option value="">Select item…</option>
                  {itemList.map(it => (
                    <option key={it.id} value={it.id}>{it.code} — {`${it.brand} ${it.model_name}`.trim()}</option>
                  ))}
                </select>
                <input placeholder="Serial no(s)" value={l.serial_numbers}
                  onChange={e => setLine(i, { serial_numbers: e.target.value })} className={FIELD} />
                <input type="number" step="any" min="0" placeholder="Qty" value={l.quantity}
                  onChange={e => setLine(i, { quantity: e.target.value })} className={FIELD} />
                <input type="number" step="any" min="0" placeholder="Rate ₹" value={l.rate}
                  onChange={e => setLine(i, { rate: e.target.value })} className={FIELD} />
                {lines.length > 1 && !editing ? (
                  <button type="button" aria-label="Remove product"
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
              A dispatch is stored per product, so editing changes this row only.
              Add another product as a new dispatch on the same invoice number.
            </p>
          ) : (
            <button type="button"
              onClick={() => setForm((f: any) => ({ ...f, lines: [...f.lines, blankLine()] }))}
              className="mt-2 text-xs font-semibold text-indigo-600 hover:text-indigo-800">
              + Add product
            </button>
          )}
        </div>

        <Fld label="Site Address">
          <input value={form.site} onChange={e => setForm({ ...form, site: e.target.value })} className={FIELD} />
        </Fld>
        <Fld label="Notes">
          <textarea rows={2} value={form.notes}
            onChange={e => setForm({ ...form, notes: e.target.value })} className={FIELD} />
        </Fld>

        <div className="flex items-center justify-between gap-4 pt-3 border-t border-slate-100 text-sm">
          <span className="text-xs text-slate-400 tabular-nums">
            Goods {rupee(goods)} · Tax {rupee(taxValue)}
          </span>
          <span className="font-bold text-slate-900 tabular-nums">Total {rupee(grand)}</span>
        </div>
      </Modal>

      {/* Nothing has been written yet — this is what releases the delivery. */}
      {/* Raising a delivery is its own step now — it asks whether to take an
          opening payment with it, and neither answer ships anything. */}
      {pendingLines !== null && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md max-h-[calc(100dvh-2rem)] overflow-y-auto overscroll-contain">
            <div className="px-6 py-4 border-b border-slate-100">
              <h2 className="text-lg font-bold text-slate-900">Raise this delivery?</h2>
              <p className="text-xs text-slate-400 mt-0.5">
                It is recorded and its stock held, but nothing ships until the invoice is
                settled and you dispatch it.
              </p>
            </div>
            <div className="p-6">
              <div className="flex items-center justify-between rounded-xl bg-slate-50 border border-slate-200 px-4 py-3">
                <span className="text-sm font-semibold text-slate-600">Invoice total</span>
                <span className="text-lg font-bold text-slate-900 tabular-nums">
                  {rupee(totalOf(pendingLines || []))}
                </span>
              </div>
            </div>
            <div className="px-6 py-4 border-t border-slate-100 flex gap-3">
              <button onClick={() => setPendingLines(null)} disabled={saving}
                className="flex-1 px-4 py-2.5 text-slate-600 font-medium hover:bg-slate-50 rounded-xl transition">
                Cancel
              </button>
              <button onClick={() => raiseDispatch()} disabled={saving}
                className="flex-1 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-2.5 rounded-xl transition disabled:opacity-50">
                {saving ? "Saving…" : "Raise & take payment"}
              </button>
            </div>
          </div>
        </div>
      )}

      <PaymentVerificationModal
        show={!!settling}
        invoiceTotal={position.total}
        alreadyReceived={position.received}
        exactTotal={position.exact}
        serverBalance={position.balance}
        serverSettled={position.settled}
        payments={position.payments}
        title={settling ? `Payment Verification · ${settling.invoice_no}` : "Payment Verification"}
        defaultDate={form.date}
        saving={working}
        onCancel={() => setSettling(null)}
        onVerify={verifyPayment}
        onDispatch={releaseNow} />
    </StockPage>
  );
}

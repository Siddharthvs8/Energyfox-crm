"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { buildProformaPdf, proformaFileName } from "@/lib/proformaPdf";
import { STATES, HOME_STATE } from "@/lib/states";

type Item = { product: string; quantity: string; unit_price: string };
const blankItem: Item = { product: "", quantity: "1", unit_price: "0" };


const STATUS: Record<string, { label: string; cls: string }> = {
  draft:     { label: "Draft",     cls: "bg-slate-100 text-slate-600" },
  sent:      { label: "Sent",      cls: "bg-blue-50 text-blue-600" },
  accepted:  { label: "Accepted",  cls: "bg-emerald-50 text-emerald-600" },
  declined:  { label: "Declined",  cls: "bg-rose-50 text-rose-600" },
  converted: { label: "Converted", cls: "bg-violet-50 text-violet-600" },
};

// The same system, built with Indian-made modules or imported ones — a
// different price, not a different product. The invoice records which it is
// written for, so "why is this one ₹20,000 more" has an answer on the paper.
const PRICE_VARIANTS: [string, string][] = [["dcr", "DCR"], ["non_dcr", "Non-DCR"]];

export default function QuotesPage({ params: paramsPromise }: { params: Promise<{ domain: string }> }) {
  const params = React.use(paramsPromise);
  const domain = APP_SLUG;
  const router = useRouter();

  const [quotes, setQuotes] = useState<any[]>([]);
  const [leads, setLeads] = useState<any[]>([]);
  const [products, setProducts] = useState<any[]>([]);
  const [projects, setProjects] = useState<any[]>([]);
  // The specification on THIS proforma — a copy of the chosen project's sheet,
  // editable here without touching the project every other quote is built from.
  const [specLines, setSpecLines] = useState<any[]>([]);
  const [specOpen, setSpecOpen] = useState(false);
  const [specTouched, setSpecTouched] = useState(false);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editQuote, setEditQuote] = useState<any>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [form, setForm] = useState({ lead: "", project: "", price_variant: "dcr", status: "draft", quote_date: "", expiry_date: "", site: "", ship_to_state: HOME_STATE, ship_to_gstin: "", efc_ref_no: "", discount_percent: "0", tax_percent: "0", notes: "" });
  const [items, setItems] = useState<Item[]>([{ ...blankItem }]);

  const token = () => localStorage.getItem(`${domain}_access`);
  const headers = () => ({ Authorization: `Bearer ${token()}`, "Content-Type": "application/json" });

  useEffect(() => {
    if (!token()) { router.push(`/login`); return; }
    fetchAll();
  }, [domain]);

  const fetchAll = async () => {
    try {
      const [q, l, p, pr] = await Promise.all([
        fetch(`${getApiBase(domain)}/api/quotes/`, { headers: headers() }),
        fetch(`${getApiBase(domain)}/api/leads/?all=true`, { headers: headers() }),
        fetch(`${getApiBase(domain)}/api/products/`, { headers: headers() }),
        fetch(`${getApiBase(domain)}/api/projects/`, { headers: headers() }),
      ]);
      const qd = await q.json(); setQuotes(Array.isArray(qd) ? qd : qd.results || []);
      const ld = await l.json(); setLeads(Array.isArray(ld) ? ld : ld.results || []);
      const pd = await p.json(); setProducts(Array.isArray(pd) ? pd : pd.results || []);
      const prd = await pr.json(); setProjects(Array.isArray(prd) ? prd : prd.results || []);
    } catch {} finally { setLoading(false); }
  };

  const openCreate = () => {
    setEditQuote(null);
    setSpecLines([]); setSpecTouched(false); setSpecOpen(false);
    setForm({ lead: "", project: "", price_variant: "dcr", status: "draft", quote_date: new Date().toISOString().slice(0, 10), expiry_date: "", site: "", ship_to_state: HOME_STATE, ship_to_gstin: "", efc_ref_no: "", discount_percent: "0", tax_percent: "0", notes: "" });
    setItems([{ ...blankItem }]);
    setShowModal(true);
  };
  const openEdit = (q: any) => {
    setEditQuote(q);
    setSpecLines((q.spec_lines || []).map((l: any) => ({ ...l })));
    setSpecTouched(false); setSpecOpen(false);
    setForm({ lead: q.lead || "", project: q.project ? String(q.project) : "", price_variant: q.price_variant || "dcr", status: q.status, quote_date: q.quote_date || "", expiry_date: q.expiry_date || "", site: q.site || "", ship_to_state: q.ship_to_state || HOME_STATE, ship_to_gstin: q.ship_to_gstin || "", efc_ref_no: q.efc_ref_no || "", discount_percent: String(q.discount_percent ?? 0), tax_percent: String(q.tax_percent ?? 0), notes: q.notes || "" });
    const its = (q.items || []).map((it: any) => ({ product: String(it.product || ""), quantity: String(it.quantity), unit_price: String(it.unit_price) }));
    setItems(its.length ? its : [{ ...blankItem }]);
    setShowModal(true);
  };

  const setItem = (idx: number, patch: Partial<Item>) => setItems(prev => prev.map((it, i) => i === idx ? { ...it, ...patch } : it));
  const onProductChange = (idx: number, productId: string) => {
    const p = products.find(pp => String(pp.id) === productId);
    setItem(idx, { product: productId, unit_price: p ? String(p.default_price || 0) : items[idx].unit_price });
  };
  const addRow = () => setItems(prev => [...prev, { ...blankItem }]);
  const removeRow = (idx: number) => setItems(prev => prev.length > 1 ? prev.filter((_, i) => i !== idx) : prev);

  const subtotal = items.reduce((s, it) => s + (parseFloat(it.quantity) || 0) * (parseFloat(it.unit_price) || 0), 0);
  const discountAmt = subtotal * (parseFloat(form.discount_percent) || 0) / 100;
  const taxable = subtotal - discountAmt;
  const taxAmt = taxable * (parseFloat(form.tax_percent) || 0) / 100;
  const total = taxable + taxAmt;

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    const payload = {
      lead: form.lead || null, project: form.project ? parseInt(form.project) : null,
      price_variant: form.price_variant,
      status: form.status, quote_date: form.quote_date || null, expiry_date: form.expiry_date || null,
      site: form.site, ship_to_state: form.ship_to_state, ship_to_gstin: form.ship_to_gstin,
      efc_ref_no: form.efc_ref_no,
      discount_percent: form.discount_percent || 0, tax_percent: form.tax_percent || 0, notes: form.notes,
      items: items.filter(it => it.product).map(it => ({ product: parseInt(it.product), quantity: it.quantity || 0, unit_price: it.unit_price || 0 })),
      // Sent only when the sheet has been opened and edited. Left out, the
      // server copies the chosen project's sheet across — which is what picking
      // one from the dropdown is for.
      ...(specTouched ? { spec_lines: specLines.filter(l => (l.item_name || "").trim()) } : {}),
    };
    const url = editQuote ? `${getApiBase(domain)}/api/quotes/${editQuote.id}/` : `${getApiBase(domain)}/api/quotes/`;
    try {
      const res = await fetch(url, { method: editQuote ? "PATCH" : "POST", headers: headers(), body: JSON.stringify(payload) });
      if (res.ok) { setShowModal(false); fetchAll(); } else alert("Failed to save quote.");
    } catch { alert("Network error."); } finally { setSaving(false); }
  };

  /** Pull the printed figures from the server and render the template. */
  const render = async (q: any) => {
    const r = await fetch(`${getApiBase(domain)}/api/quotes/${q.id}/proforma/`, { headers: headers() });
    if (!r.ok) { alert("Could not build the document."); return null; }
    return buildProformaPdf(await r.json());
  };

  /** "<Customer> - <NUMBER>.pdf" — the number alone says nothing about whose
   *  document it is, and the customer is what people search their downloads for. */
  const docName = (q: any) => proformaFileName(q.number, q.lead_name);

  const download = async (q: any) => {
    setBusy(q.id);
    try {
      const pdf = await render(q);
      if (pdf) pdf.save(docName(q));
    } finally { setBusy(null); }
  };

  /** Render, hand the file to the server, and let it email / WhatsApp it. */
  const sendTo = async (q: any, channel: "email" | "whatsapp") => {
    const lead = leads.find(l => l.id === q.lead);
    const label = channel === "email" ? "email address" : "WhatsApp number";
    const to = window.prompt(`Send ${q.number} to which ${label}?`,
      channel === "email" ? (lead?.email || "") : (lead?.phone || ""));
    if (!to) return;

    setBusy(q.id);
    try {
      const pdf = await render(q);
      if (!pdf) return;
      const body = new FormData();
      body.append("pdf", new File([pdf.output("blob")], docName(q), { type: "application/pdf" }));
      body.append("channels", channel);
      body.append(channel === "email" ? "email" : "phone", to);
      const res = await fetch(`${getApiBase(domain)}/api/quotes/${q.id}/send/`, {
        method: "POST", headers: { Authorization: `Bearer ${token()}` }, body,
      });
      const d = await res.json().catch(() => ({}));
      if (!res.ok) { alert(d.error || "Could not send the document."); return; }
      alert((d.warnings || []).length
        ? `Sent, with warnings:\n${d.warnings.join("\n")}`
        : `${q.number} sent by ${channel === "email" ? "email" : "WhatsApp"}.`);
      fetchAll();
    } catch { alert("Network error while sending."); }
    finally { setBusy(null); }
  };

  const convert = async (q: any) => {
    if (!confirm(`Convert ${q.number} into a Sales Order?`)) return;
    try {
      const res = await fetch(`${getApiBase(domain)}/api/quotes/${q.id}/convert/`, { method: "POST", headers: headers() });
      if (res.ok) { fetchAll(); router.push(`/sales-orders`); } else alert("Failed to convert.");
    } catch { alert("Network error."); }
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Delete this proforma invoice?")) return;
    try {
      const res = await fetch(`${getApiBase(domain)}/api/quotes/${id}/`, { method: "DELETE", headers: headers() });
      if (res.ok) fetchAll(); else alert("Failed to delete.");
    } catch { alert("Network error."); }
  };

  const field = "w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none transition";
  const itemField = field.replace("w-full ", ""); // row inputs size via flex/fixed widths, not w-full

  if (loading) return <div className="p-8 flex items-center justify-center h-full"><div className="w-8 h-8 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" /></div>;

  return (
    <div className="max-w-6xl mx-auto p-4 sm:p-6 lg:p-8">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Proforma Invoice</h1>
          <p className="text-sm text-slate-500 mt-1">Raise a proforma invoice for a lead — download it, send it, and convert it to a sales order.</p>
        </div>
        <button onClick={openCreate} className="bg-indigo-600 hover:bg-indigo-700 text-white px-5 py-2.5 rounded-xl text-sm font-semibold transition-colors flex items-center gap-2 shadow-sm">
          <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14" /></svg>
          New Proforma Invoice
        </button>
      </div>

      <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse min-w-[1080px]">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200 text-xs uppercase tracking-wider text-slate-500 font-semibold">
                <th className="py-4 px-6">Invoice No.</th><th className="py-4 px-6">Customer</th><th className="py-4 px-6">Date</th>
                <th className="py-4 px-6 text-center">Status</th><th className="py-4 px-6 text-right">Total</th><th className="py-4 px-6 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {quotes.length === 0 ? (
                <tr><td colSpan={6} className="py-12 text-center text-slate-500"><p className="font-medium text-slate-900">No proforma invoices yet</p><p className="text-sm mt-1">Raise a proforma invoice for a lead.</p></td></tr>
              ) : quotes.map(q => {
                const st = STATUS[q.status] || STATUS.draft;
                return (
                  <tr key={q.id} className="hover:bg-slate-50/50 transition-colors">
                    <td className="py-4 px-6 font-semibold text-slate-900">{q.number}</td>
                    <td className="py-4 px-6 text-slate-600">{q.lead_name || "—"}</td>
                    <td className="py-4 px-6 text-slate-500 text-sm">{q.quote_date || "—"}</td>
                    <td className="py-4 px-6 text-center"><span className={`inline-flex px-2.5 py-1 rounded-full text-xs font-semibold ${st.cls}`}>{st.label}</span></td>
                    <td className="py-4 px-6 text-right font-semibold text-slate-700">₹{parseFloat(q.total || 0).toLocaleString("en-IN")}</td>
                    <td className="py-4 px-6 text-right whitespace-nowrap">
                      <button onClick={() => download(q)} disabled={busy === q.id} className="text-slate-600 hover:text-slate-900 text-sm font-medium mr-3 disabled:opacity-40">{busy === q.id ? "…" : "PDF"}</button>
                      <button onClick={() => sendTo(q, "email")} disabled={busy === q.id} className="text-indigo-600 hover:text-indigo-900 text-sm font-medium mr-3 disabled:opacity-40">Email</button>
                      <button onClick={() => sendTo(q, "whatsapp")} disabled={busy === q.id} className="text-emerald-600 hover:text-emerald-800 text-sm font-medium mr-3 disabled:opacity-40">WhatsApp</button>
                      {q.status !== "converted" && <button onClick={() => convert(q)} className="text-violet-600 hover:text-violet-800 text-sm font-medium mr-4">Convert</button>}
                      <button onClick={() => openEdit(q)} className="text-indigo-600 hover:text-indigo-900 text-sm font-medium mr-4">Edit</button>
                      <button onClick={() => handleDelete(q.id)} className="text-rose-600 hover:text-rose-900 text-sm font-medium">Delete</button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center px-4 py-8">
          <div className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm" />
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-2xl relative z-10 max-h-[90vh] overflow-hidden flex flex-col">
            <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between flex-shrink-0">
              <h3 className="font-bold text-lg text-slate-900">{editQuote ? `Edit ${editQuote.number}` : "New Proforma Invoice"}</h3>
              <button onClick={() => setShowModal(false)} className="text-slate-400 hover:text-slate-600"><svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12" /></svg></button>
            </div>
            <form onSubmit={handleSave} className="p-6 overflow-y-auto flex-1">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-5">
                <div>
                  <label className="block text-sm font-semibold text-slate-700 mb-1.5">Customer (Lead)</label>
                  <select value={form.lead} onChange={e => setForm({ ...form, lead: e.target.value })} className={field}>
                    <option value="">No lead</option>
                    {leads.map(l => <option key={l.id} value={l.id}>{`${l.first_name || ""} ${l.last_name || ""}`.trim() || l.email}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-semibold text-slate-700 mb-1.5">Status</label>
                  <select value={form.status} onChange={e => setForm({ ...form, status: e.target.value })} className={field}>
                    {Object.entries(STATUS).filter(([k]) => k !== "converted").map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
                  </select>
                </div>
                <div><label className="block text-sm font-semibold text-slate-700 mb-1.5">Invoice Date</label><input type="date" value={form.quote_date} onChange={e => setForm({ ...form, quote_date: e.target.value })} className={field} /></div>
                <div><label className="block text-sm font-semibold text-slate-700 mb-1.5">Expiry Date</label><input type="date" value={form.expiry_date} onChange={e => setForm({ ...form, expiry_date: e.target.value })} className={field} /></div>
                <div><label className="block text-sm font-semibold text-slate-700 mb-1.5">EFC Ref No.</label><input value={form.efc_ref_no} onChange={e => setForm({ ...form, efc_ref_no: e.target.value })} className={field} placeholder="Printed on the invoice" /></div>
                <div><label className="block text-sm font-semibold text-slate-700 mb-1.5">Site address</label><input value={form.site} onChange={e => setForm({ ...form, site: e.target.value })} className={field} placeholder="Shipped-to, if different" /></div>
                <div><label className="block text-sm font-semibold text-slate-700 mb-1.5">State (shipped to)</label>
                  <select value={form.ship_to_state} onChange={e => setForm({ ...form, ship_to_state: e.target.value })} className={field}>
                    {STATES.map(st => <option key={st} value={st}>{st}</option>)}
                  </select>
                </div>
                <div><label className="block text-sm font-semibold text-slate-700 mb-1.5">GST No. (shipped to)</label><input value={form.ship_to_gstin} onChange={e => setForm({ ...form, ship_to_gstin: e.target.value })} className={field} placeholder="e.g. 32AAWFD1840P1ZZ" /></div>
              </div>

              {/* ── The project: what the customer is getting ── */}
              <div className="mb-6 border border-slate-200 rounded-xl overflow-hidden">
                <div className="flex flex-wrap items-end gap-3 px-4 py-3 bg-slate-50 border-b border-slate-200">
                  <div className="flex-1 min-w-[220px]">
                    <label className="block text-sm font-semibold text-slate-700 mb-1.5">Project</label>
                    <select value={form.project}
                      onChange={e => {
                        // Choosing a project replaces the sheet with that
                        // project's, which is what the dropdown is for — so the
                        // local copy is cleared and the server does the copying.
                        setForm({ ...form, project: e.target.value });
                        setSpecLines([]); setSpecTouched(false); setSpecOpen(false);
                      }} className={field}>
                      <option value="">No project</option>
                      {projects.map(p => (
                        <option key={p.id} value={p.id}>
                          {p.name}{p.capacity ? ` · ${p.capacity}` : ""}
                        </option>
                      ))}
                    </select>
                  </div>
                  {form.project && (
                    <div>
                      <label className="block text-sm font-semibold text-slate-700 mb-1.5">Price</label>
                      {/* Switching reprices the invoice; the specification is
                          the same system either way and is left alone. */}
                      <div className="flex rounded-xl border border-slate-200 overflow-hidden bg-white">
                        {PRICE_VARIANTS.map(([key, label]) => {
                          const chosen = form.price_variant === key;
                          const p = projects.find(pr => String(pr.id) === form.project);
                          const amount = p?.pricing?.[key]?.total;
                          return (
                            <button key={key} type="button"
                              onClick={() => setForm({ ...form, price_variant: key })}
                              className={`px-4 py-2 text-xs font-bold transition ${
                                chosen ? "bg-indigo-600 text-white" : "text-slate-500 hover:bg-slate-50"}`}>
                              {label}
                              {Number(amount) > 0 && (
                                <span className={`block text-[10px] font-semibold ${
                                  chosen ? "text-indigo-100" : "text-slate-400"}`}>
                                  ₹{Number(amount).toLocaleString("en-IN")}
                                </span>
                              )}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  )}
                  {form.project && (
                    <button type="button" onClick={() => setSpecOpen(!specOpen)}
                      className="px-4 py-2.5 rounded-xl border border-slate-200 bg-white text-xs font-bold text-slate-600 hover:bg-slate-50 transition">
                      {specOpen ? "Done editing" : "Edit products"}
                    </button>
                  )}
                </div>

                {!form.project ? (
                  <p className="px-4 py-3 text-[12px] text-slate-400">
                    Pick a project and its specification and price are put on this invoice,
                    replacing the line items below — editable here without changing the project.
                  </p>
                ) : !specOpen ? (
                  <p className="px-4 py-3 text-[12px] text-slate-500">
                    {specLines.length > 0
                      ? `${specLines.length} item${specLines.length === 1 ? "" : "s"} on this invoice${specTouched ? " · edited" : ""}.`
                      : "Its specification is copied across when you save."}
                  </p>
                ) : (
                  <div className="px-4 py-3 space-y-3">
                    {specLines.length === 0 && (
                      <p className="text-[12px] text-slate-400">
                        Save first — the project&rsquo;s items are copied across, then they can be edited here.
                      </p>
                    )}
                    {specLines.length > 0 && (
                      <div>
                        <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">
                          Specifications
                        </p>
                        <div className="space-y-1.5">
                          {specLines.map((row, idx) => {
                            const set = (patch: any) => {
                              setSpecTouched(true);
                              setSpecLines(specLines.map((l, n) => (n === idx ? { ...l, ...patch } : l)));
                            };
                            return (
                              <div key={idx} className="grid gap-2 items-center sm:grid-cols-[1fr_1fr_140px_28px]">
                                <input value={row.item_name} onChange={e => set({ item_name: e.target.value })}
                                  placeholder="Item" className={field} />
                                <input value={row.brand || ""} onChange={e => set({ brand: e.target.value })}
                                  placeholder="Brand" className={field} />
                                <input value={row.quantity || ""} onChange={e => set({ quantity: e.target.value })}
                                  placeholder="Qty" className={field} />
                                <button type="button" title="Remove this line"
                                  onClick={() => { setSpecTouched(true); setSpecLines(specLines.filter((_, n) => n !== idx)); }}
                                  className="justify-self-center text-slate-300 hover:text-rose-500 transition">
                                  <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2"
                                    strokeLinecap="round" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12" /></svg>
                                </button>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}
                    {specLines.length > 0 && (
                      <p className="text-[11px] text-slate-400">
                        Edits stay on this invoice. The project itself is unchanged.
                      </p>
                    )}
                  </div>
                )}
              </div>

              <label className="block text-sm font-semibold text-slate-700 mb-2">Items</label>
              <div className="space-y-2 mb-3">
                <div className="hidden sm:flex gap-2 items-center px-1 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                  <span className="flex-1">Product</span>
                  <span className="w-16 text-center">Qty</span>
                  <span className="w-24 text-center">Unit Price</span>
                  <span className="w-20 text-right">Amount</span>
                  <span className="w-6" />
                </div>
                {items.map((it, idx) => (
                  <div key={idx} className="flex gap-2 items-center">
                    <select value={it.product} onChange={e => onProductChange(idx, e.target.value)} className={`${itemField} flex-1 min-w-0`}>
                      <option value="">Select product...</option>
                      {products.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                    </select>
                    <input type="number" min="0" step="0.01" value={it.quantity} onChange={e => setItem(idx, { quantity: e.target.value })} className={`${itemField} w-16`} placeholder="Qty" />
                    <input type="number" min="0" step="0.01" value={it.unit_price} onChange={e => setItem(idx, { unit_price: e.target.value })} className={`${itemField} w-24`} placeholder="Price" />
                    <span className="w-20 text-right text-sm font-medium text-slate-600">₹{((parseFloat(it.quantity) || 0) * (parseFloat(it.unit_price) || 0)).toLocaleString("en-IN")}</span>
                    <button type="button" onClick={() => removeRow(idx)} className="text-slate-300 hover:text-rose-500 p-1"><svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12" /></svg></button>
                  </div>
                ))}
              </div>
              <button type="button" onClick={addRow} className="text-indigo-600 hover:text-indigo-800 text-sm font-semibold mb-5">+ Add item</button>

              <div className="grid grid-cols-2 gap-4 mb-4">
                <div><label className="block text-sm font-semibold text-slate-700 mb-1.5">Discount %</label><input type="number" min="0" step="0.01" value={form.discount_percent} onChange={e => setForm({ ...form, discount_percent: e.target.value })} className={field} /></div>
                <div><label className="block text-sm font-semibold text-slate-700 mb-1.5">Tax %</label><input type="number" min="0" step="0.01" value={form.tax_percent} onChange={e => setForm({ ...form, tax_percent: e.target.value })} className={field} /></div>
              </div>

              <div className="bg-slate-50 rounded-xl p-4 mb-4 space-y-1.5 text-sm">
                <div className="flex justify-between text-slate-500"><span>Subtotal</span><span>₹{subtotal.toLocaleString("en-IN")}</span></div>
                <div className="flex justify-between text-slate-500"><span>Discount</span><span>− ₹{discountAmt.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</span></div>
                <div className="flex justify-between text-slate-500"><span>Tax</span><span>+ ₹{taxAmt.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</span></div>
                <div className="flex justify-between font-bold text-slate-900 text-base pt-1.5 border-t border-slate-200"><span>Total</span><span>₹{total.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</span></div>
              </div>

              <div className="mb-6"><label className="block text-sm font-semibold text-slate-700 mb-1.5">Notes</label><textarea value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} rows={2} className={field} /></div>

              <div className="flex gap-3">
                <button type="button" onClick={() => setShowModal(false)} className="flex-1 px-4 py-2.5 text-slate-600 font-medium hover:bg-slate-50 rounded-xl transition-colors">Cancel</button>
                <button type="submit" disabled={saving} className="flex-1 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-2.5 rounded-xl transition shadow-sm disabled:opacity-50">{saving ? "Saving..." : "Save Proforma Invoice"}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

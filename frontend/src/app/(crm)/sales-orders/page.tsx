"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";

type Item = { product: string; quantity: string; unit_price: string };
const blankItem: Item = { product: "", quantity: "1", unit_price: "0" };

const STATUS: Record<string, { label: string; cls: string }> = {
  draft:     { label: "Draft",     cls: "bg-slate-100 text-slate-600" },
  confirmed: { label: "Confirmed", cls: "bg-blue-50 text-blue-600" },
  shipped:   { label: "Shipped",   cls: "bg-violet-50 text-violet-600" },
  delivered: { label: "Delivered", cls: "bg-emerald-50 text-emerald-600" },
  cancelled: { label: "Cancelled", cls: "bg-rose-50 text-rose-600" },
};

export default function SalesOrdersPage({ params: paramsPromise }: { params: Promise<{ domain: string }> }) {
  const params = React.use(paramsPromise);
  const domain = APP_SLUG;
  const router = useRouter();

  const [orders, setOrders] = useState<any[]>([]);
  const [leads, setLeads] = useState<any[]>([]);
  const [products, setProducts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editOrder, setEditOrder] = useState<any>(null);
  const [form, setForm] = useState({ lead: "", status: "draft", order_date: "", discount_percent: "0", tax_percent: "0", notes: "" });
  const [items, setItems] = useState<Item[]>([{ ...blankItem }]);

  const token = () => localStorage.getItem(`${domain}_access`);
  const headers = () => ({ Authorization: `Bearer ${token()}`, "Content-Type": "application/json" });

  useEffect(() => {
    if (!token()) { router.push(`/login`); return; }
    fetchAll();
  }, [domain]);

  const fetchAll = async () => {
    try {
      const [o, l, p] = await Promise.all([
        fetch(`${getApiBase(domain)}/api/sales-orders/`, { headers: headers() }),
        fetch(`${getApiBase(domain)}/api/leads/?all=true`, { headers: headers() }),
        fetch(`${getApiBase(domain)}/api/products/`, { headers: headers() }),
      ]);
      const od = await o.json(); setOrders(Array.isArray(od) ? od : od.results || []);
      const ld = await l.json(); setLeads(Array.isArray(ld) ? ld : ld.results || []);
      const pd = await p.json(); setProducts(Array.isArray(pd) ? pd : pd.results || []);
    } catch {} finally { setLoading(false); }
  };

  const openCreate = () => {
    setEditOrder(null);
    setForm({ lead: "", status: "draft", order_date: new Date().toISOString().slice(0, 10), discount_percent: "0", tax_percent: "0", notes: "" });
    setItems([{ ...blankItem }]);
    setShowModal(true);
  };
  const openEdit = (o: any) => {
    setEditOrder(o);
    setForm({ lead: o.lead || "", status: o.status, order_date: o.order_date || "", discount_percent: String(o.discount_percent ?? 0), tax_percent: String(o.tax_percent ?? 0), notes: o.notes || "" });
    const its = (o.items || []).map((it: any) => ({ product: String(it.product || ""), quantity: String(it.quantity), unit_price: String(it.unit_price) }));
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
      lead: form.lead || null, status: form.status, order_date: form.order_date || null,
      discount_percent: form.discount_percent || 0, tax_percent: form.tax_percent || 0, notes: form.notes,
      items: items.filter(it => it.product).map(it => ({ product: parseInt(it.product), quantity: it.quantity || 0, unit_price: it.unit_price || 0 })),
    };
    const url = editOrder ? `${getApiBase(domain)}/api/sales-orders/${editOrder.id}/` : `${getApiBase(domain)}/api/sales-orders/`;
    try {
      const res = await fetch(url, { method: editOrder ? "PATCH" : "POST", headers: headers(), body: JSON.stringify(payload) });
      if (res.ok) { setShowModal(false); fetchAll(); } else alert("Failed to save sales order.");
    } catch { alert("Network error."); } finally { setSaving(false); }
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Delete this sales order?")) return;
    try {
      const res = await fetch(`${getApiBase(domain)}/api/sales-orders/${id}/`, { method: "DELETE", headers: headers() });
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
          <h1 className="text-2xl font-bold text-slate-900">Sales / Dispatches</h1>
          <p className="text-sm text-slate-500 mt-1">Confirmed customer orders. Confirming an order reduces product stock.</p>
        </div>
        <button onClick={openCreate} className="bg-indigo-600 hover:bg-indigo-700 text-white px-5 py-2.5 rounded-xl text-sm font-semibold transition-colors flex items-center gap-2 shadow-sm">
          <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14" /></svg>
          New Dispatch
        </button>
      </div>

      <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse min-w-[760px]">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200 text-xs uppercase tracking-wider text-slate-500 font-semibold">
                <th className="py-4 px-6">SO #</th><th className="py-4 px-6">Customer</th><th className="py-4 px-6">Date</th>
                <th className="py-4 px-6 text-center">Status</th><th className="py-4 px-6 text-right">Total</th><th className="py-4 px-6 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {orders.length === 0 ? (
                <tr><td colSpan={6} className="py-12 text-center text-slate-500"><p className="font-medium text-slate-900">No sales orders</p><p className="text-sm mt-1">Create one or convert a quote.</p></td></tr>
              ) : orders.map(o => {
                const st = STATUS[o.status] || STATUS.draft;
                return (
                  <tr key={o.id} className="hover:bg-slate-50/50 transition-colors">
                    <td className="py-4 px-6 font-semibold text-slate-900">
                      {o.number}
                      {o.source_quote && <span className="ml-2 text-[10px] font-bold text-violet-500">from quote</span>}
                    </td>
                    <td className="py-4 px-6 text-slate-600">{o.lead_name || "—"}</td>
                    <td className="py-4 px-6 text-slate-500 text-sm">{o.order_date || "—"}</td>
                    <td className="py-4 px-6 text-center"><span className={`inline-flex px-2.5 py-1 rounded-full text-xs font-semibold ${st.cls}`}>{st.label}</span></td>
                    <td className="py-4 px-6 text-right font-semibold text-slate-700">₹{parseFloat(o.total || 0).toLocaleString("en-IN")}</td>
                    <td className="py-4 px-6 text-right whitespace-nowrap">
                      <button onClick={() => openEdit(o)} className="text-indigo-600 hover:text-indigo-900 text-sm font-medium mr-4">Edit</button>
                      <button onClick={() => handleDelete(o.id)} className="text-rose-600 hover:text-rose-900 text-sm font-medium">Delete</button>
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
          <div className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm" onClick={() => setShowModal(false)} />
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-2xl relative z-10 max-h-[90vh] overflow-hidden flex flex-col">
            <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between flex-shrink-0">
              <h3 className="font-bold text-lg text-slate-900">{editOrder ? `Edit ${editOrder.number}` : "New Dispatch"}</h3>
              <button onClick={() => setShowModal(false)} className="text-slate-400 hover:text-slate-600"><svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12" /></svg></button>
            </div>
            <form onSubmit={handleSave} className="p-6 overflow-y-auto flex-1">
              {editOrder && form.status === "draft" && (
                <p className="text-xs text-amber-600 bg-amber-50 border border-amber-100 rounded-lg px-3 py-2 mb-4">Setting status to Confirmed/Shipped/Delivered will deduct the ordered quantities from product stock.</p>
              )}
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
                    {Object.entries(STATUS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
                  </select>
                </div>
                <div><label className="block text-sm font-semibold text-slate-700 mb-1.5">Order Date</label><input type="date" value={form.order_date} onChange={e => setForm({ ...form, order_date: e.target.value })} className={field} /></div>
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
                      {products.map(p => <option key={p.id} value={p.id}>{p.name}{typeof p.stock_quantity === "number" ? ` (${p.stock_quantity} in stock)` : ""}</option>)}
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
                <button type="submit" disabled={saving} className="flex-1 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-2.5 rounded-xl transition shadow-sm disabled:opacity-50">{saving ? "Saving..." : "Save Dispatch"}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

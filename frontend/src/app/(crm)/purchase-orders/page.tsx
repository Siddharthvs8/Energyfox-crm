"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { jsPDF } from "jspdf";
import autoTable from "jspdf-autotable";

type Item = { product: string; quantity: string; unit_price: string };
const blankItem: Item = { product: "", quantity: "1", unit_price: "0" };

const STATUS: Record<string, { label: string; cls: string }> = {
  draft:     { label: "Draft",     cls: "bg-slate-100 text-slate-600" },
  ordered:   { label: "Ordered",   cls: "bg-blue-50 text-blue-600" },
  received:  { label: "Received",  cls: "bg-emerald-50 text-emerald-600" },
  cancelled: { label: "Cancelled", cls: "bg-rose-50 text-rose-600" },
};

export default function PurchaseOrdersPage({ params: paramsPromise }: { params: Promise<{ domain: string }> }) {
  const params = React.use(paramsPromise);
  const domain = APP_SLUG;
  const router = useRouter();

  const [orders, setOrders] = useState<any[]>([]);
  const [vendors, setVendors] = useState<any[]>([]);
  const [products, setProducts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editOrder, setEditOrder] = useState<any>(null);
  const [form, setForm] = useState({ vendor: "", status: "draft", order_date: "", expected_date: "", notes: "" });
  const [items, setItems] = useState<Item[]>([{ ...blankItem }]);
  const [orgName, setOrgName] = useState("EnergyFox");
  const [busyId, setBusyId] = useState<number | null>(null);

  const token = () => localStorage.getItem(`${domain}_access`);
  const headers = () => ({ Authorization: `Bearer ${token()}`, "Content-Type": "application/json" });

  useEffect(() => {
    if (!token()) { router.push(`/login`); return; }
    fetchAll();
  }, [domain]);

  const fetchAll = async () => {
    try {
      const [o, v, p] = await Promise.all([
        fetch(`${getApiBase(domain)}/api/purchase-orders/`, { headers: headers() }),
        fetch(`${getApiBase(domain)}/api/vendors/`, { headers: headers() }),
        fetch(`${getApiBase(domain)}/api/products/`, { headers: headers() }),
      ]);
      const od = await o.json(); setOrders(Array.isArray(od) ? od : od.results || []);
      const vd = await v.json(); setVendors(Array.isArray(vd) ? vd : vd.results || []);
      const pd = await p.json(); setProducts(Array.isArray(pd) ? pd : pd.results || []);
    } catch {} finally { setLoading(false); }
    try {
      const r = await fetch(`${getApiBase(domain)}/api/subscription/`, { headers: headers() });
      if (r.ok) { const d = await r.json(); if (d.name) setOrgName(d.name); }
    } catch {}
  };

  // ── PDF generation (used for both Print and Email) ──
  const fmt = (n: any) => Number(n || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  const buildPdf = (o: any): jsPDF => {
    const doc = new jsPDF("p", "pt", "a4");
    const W = doc.internal.pageSize.getWidth();
    const vendor = vendors.find(v => String(v.id) === String(o.vendor));

    doc.setFontSize(20); doc.setTextColor(30, 41, 59);
    doc.text("PURCHASE ORDER", 40, 52);
    doc.setFontSize(12); doc.setTextColor(99, 102, 241);
    doc.text(orgName, 40, 72);

    doc.setFontSize(10); doc.setTextColor(100, 116, 139);
    doc.text(`PO #: ${o.number || "-"}`, W - 40, 46, { align: "right" });
    doc.text(`Order Date: ${o.order_date || "-"}`, W - 40, 60, { align: "right" });
    doc.text(`Expected: ${o.expected_date || "-"}`, W - 40, 74, { align: "right" });
    doc.text(`Status: ${(STATUS[o.status]?.label || o.status || "").toString()}`, W - 40, 88, { align: "right" });

    let y = 116;
    doc.setFontSize(11); doc.setTextColor(30, 41, 59); doc.text("Vendor", 40, y);
    doc.setFontSize(10); doc.setTextColor(71, 85, 105);
    const vlines = [
      vendor?.name || o.vendor_name,
      vendor?.contact_person,
      vendor?.email,
      vendor?.phone,
      vendor?.gst_number ? `GST: ${vendor.gst_number}` : "",
      vendor?.address,
    ].filter(Boolean) as string[];
    vlines.forEach(line => { y += 14; doc.text(String(line), 40, y); });

    autoTable(doc, {
      startY: y + 18,
      head: [["#", "Item", "Qty", "Unit Price (Rs.)", "Amount (Rs.)"]],
      body: (o.items || []).map((it: any, i: number) => [
        i + 1,
        it.product_name || it.description || "-",
        Number(it.quantity || 0).toLocaleString("en-IN"),
        fmt(it.unit_price),
        fmt(it.line_total ?? (Number(it.quantity || 0) * Number(it.unit_price || 0))),
      ]),
      headStyles: { fillColor: [79, 70, 229], textColor: 255, fontStyle: "bold" },
      styles: { fontSize: 9, cellPadding: 6 },
      columnStyles: { 0: { cellWidth: 30 }, 2: { halign: "right" }, 3: { halign: "right" }, 4: { halign: "right" } },
      margin: { left: 40, right: 40 },
    });

    const endY = (doc as any).lastAutoTable.finalY || y + 40;
    doc.setFontSize(12); doc.setTextColor(30, 41, 59);
    doc.text(`Total: Rs. ${fmt(o.total)}`, W - 40, endY + 26, { align: "right" });

    if (o.notes) {
      doc.setFontSize(9); doc.setTextColor(100, 116, 139);
      doc.text(doc.splitTextToSize(`Notes: ${o.notes}`, W - 220), 40, endY + 26);
    }
    return doc;
  };

  const printPO = (o: any) => {
    const doc = buildPdf(o);
    doc.autoPrint();
    const url = doc.output("bloburl");
    window.open(url, "_blank");
  };

  const emailPO = async (o: any) => {
    const vendor = vendors.find(v => String(v.id) === String(o.vendor));
    const to = window.prompt("Send this purchase order to:", vendor?.email || "");
    if (to === null) return;
    if (!to.trim()) { alert("Please enter a recipient email."); return; }
    setBusyId(o.id);
    try {
      const blob = buildPdf(o).output("blob");
      const fd = new FormData();
      fd.append("to", to.trim());
      fd.append("pdf", blob, `${o.number || "purchase-order"}.pdf`);
      const res = await fetch(`${getApiBase(domain)}/api/purchase-orders/${o.id}/email/`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token()}` }, // no Content-Type: let the browser set the multipart boundary
        body: fd,
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok) alert(`Purchase order emailed to ${to.trim()}.`);
      else alert(data.error || "Failed to email purchase order.");
    } catch { alert("Network error while emailing."); }
    finally { setBusyId(null); }
  };

  const openCreate = () => {
    setEditOrder(null);
    setForm({ vendor: "", status: "draft", order_date: new Date().toISOString().slice(0, 10), expected_date: "", notes: "" });
    setItems([{ ...blankItem }]);
    setShowModal(true);
  };
  const openEdit = (o: any) => {
    setEditOrder(o);
    setForm({ vendor: o.vendor || "", status: o.status, order_date: o.order_date || "", expected_date: o.expected_date || "", notes: o.notes || "" });
    setItems((o.items || []).map((it: any) => ({ product: String(it.product || ""), quantity: String(it.quantity), unit_price: String(it.unit_price) })));
    if (!o.items?.length) setItems([{ ...blankItem }]);
    setShowModal(true);
  };

  const setItem = (idx: number, patch: Partial<Item>) => setItems(prev => prev.map((it, i) => i === idx ? { ...it, ...patch } : it));
  const onProductChange = (idx: number, productId: string) => {
    const p = products.find(pp => String(pp.id) === productId);
    setItem(idx, { product: productId, unit_price: p ? String(p.cost_price || p.default_price || 0) : items[idx].unit_price });
  };
  const addRow = () => setItems(prev => [...prev, { ...blankItem }]);
  const removeRow = (idx: number) => setItems(prev => prev.length > 1 ? prev.filter((_, i) => i !== idx) : prev);

  const total = items.reduce((s, it) => s + (parseFloat(it.quantity) || 0) * (parseFloat(it.unit_price) || 0), 0);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    const payload = {
      vendor: form.vendor || null, status: form.status,
      order_date: form.order_date || null, expected_date: form.expected_date || null, notes: form.notes,
      items: items.filter(it => it.product).map(it => ({ product: parseInt(it.product), quantity: it.quantity || 0, unit_price: it.unit_price || 0 })),
    };
    const url = editOrder ? `${getApiBase(domain)}/api/purchase-orders/${editOrder.id}/` : `${getApiBase(domain)}/api/purchase-orders/`;
    try {
      const res = await fetch(url, { method: editOrder ? "PATCH" : "POST", headers: headers(), body: JSON.stringify(payload) });
      if (res.ok) { setShowModal(false); fetchAll(); } else alert("Failed to save purchase order.");
    } catch { alert("Network error."); } finally { setSaving(false); }
  };

  const receive = async (o: any) => {
    if (o.status === "received") return;
    if (!confirm(`Receive ${o.number}? This adds the ordered quantities into product stock.`)) return;
    try {
      const res = await fetch(`${getApiBase(domain)}/api/purchase-orders/${o.id}/`, { method: "PATCH", headers: headers(), body: JSON.stringify({ status: "received" }) });
      if (res.ok) fetchAll(); else alert("Failed to receive.");
    } catch { alert("Network error."); }
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Delete this purchase order?")) return;
    try {
      const res = await fetch(`${getApiBase(domain)}/api/purchase-orders/${id}/`, { method: "DELETE", headers: headers() });
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
          <h1 className="text-2xl font-bold text-slate-900">Purchases</h1>
          <p className="text-sm text-slate-500 mt-1">Order stock from vendors. Receiving a PO updates product stock.</p>
        </div>
        <button onClick={openCreate} className="bg-indigo-600 hover:bg-indigo-700 text-white px-5 py-2.5 rounded-xl text-sm font-semibold transition-colors flex items-center gap-2 shadow-sm">
          <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14" /></svg>
          New Purchase
        </button>
      </div>

      <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse min-w-[760px]">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200 text-xs uppercase tracking-wider text-slate-500 font-semibold">
                <th className="py-4 px-6">PO #</th><th className="py-4 px-6">Vendor</th><th className="py-4 px-6">Date</th>
                <th className="py-4 px-6 text-center">Status</th><th className="py-4 px-6 text-right">Total</th><th className="py-4 px-6 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {orders.length === 0 ? (
                <tr><td colSpan={6} className="py-12 text-center text-slate-500"><p className="font-medium text-slate-900">No purchase orders</p><p className="text-sm mt-1">Create one to restock your products.</p></td></tr>
              ) : orders.map(o => {
                const st = STATUS[o.status] || STATUS.draft;
                return (
                  <tr key={o.id} className="hover:bg-slate-50/50 transition-colors">
                    <td className="py-4 px-6 font-semibold text-slate-900">{o.number}</td>
                    <td className="py-4 px-6 text-slate-600">{o.vendor_name || "—"}</td>
                    <td className="py-4 px-6 text-slate-500 text-sm">{o.order_date || "—"}</td>
                    <td className="py-4 px-6 text-center"><span className={`inline-flex px-2.5 py-1 rounded-full text-xs font-semibold ${st.cls}`}>{st.label}</span></td>
                    <td className="py-4 px-6 text-right font-semibold text-slate-700">₹{parseFloat(o.total || 0).toLocaleString("en-IN")}</td>
                    <td className="py-4 px-6 text-right whitespace-nowrap">
                      {o.status !== "received" && o.status !== "cancelled" && <button onClick={() => receive(o)} className="text-emerald-600 hover:text-emerald-800 text-sm font-medium mr-4">Receive</button>}
                      <button onClick={() => printPO(o)} className="text-slate-600 hover:text-slate-900 text-sm font-medium mr-4">Print</button>
                      <button onClick={() => emailPO(o)} disabled={busyId === o.id} className="text-blue-600 hover:text-blue-800 text-sm font-medium mr-4 disabled:opacity-50">{busyId === o.id ? "Sending…" : "Email"}</button>
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
              <h3 className="font-bold text-lg text-slate-900">{editOrder ? `Edit ${editOrder.number}` : "New Purchase"}</h3>
              <button onClick={() => setShowModal(false)} className="text-slate-400 hover:text-slate-600"><svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12" /></svg></button>
            </div>
            <form onSubmit={handleSave} className="p-6 overflow-y-auto flex-1">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-5">
                <div>
                  <label className="block text-sm font-semibold text-slate-700 mb-1.5">Vendor *</label>
                  <select required value={form.vendor} onChange={e => setForm({ ...form, vendor: e.target.value })} className={field}>
                    <option value="">Select vendor...</option>
                    {vendors.map(v => <option key={v.id} value={v.id}>{v.name}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-semibold text-slate-700 mb-1.5">Status</label>
                  <select value={form.status} onChange={e => setForm({ ...form, status: e.target.value })} className={field}>
                    {Object.entries(STATUS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
                  </select>
                </div>
                <div><label className="block text-sm font-semibold text-slate-700 mb-1.5">Order Date</label><input type="date" value={form.order_date} onChange={e => setForm({ ...form, order_date: e.target.value })} className={field} /></div>
                <div><label className="block text-sm font-semibold text-slate-700 mb-1.5">Expected Date</label><input type="date" value={form.expected_date} onChange={e => setForm({ ...form, expected_date: e.target.value })} className={field} /></div>
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

              <div className="flex justify-between items-center py-3 border-t border-slate-100 mb-4">
                <span className="text-sm font-semibold text-slate-500">Total</span>
                <span className="text-xl font-bold text-slate-900">₹{total.toLocaleString("en-IN")}</span>
              </div>

              <div className="mb-6"><label className="block text-sm font-semibold text-slate-700 mb-1.5">Notes</label><textarea value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} rows={2} className={field} /></div>

              <div className="flex gap-3">
                <button type="button" onClick={() => setShowModal(false)} className="flex-1 px-4 py-2.5 text-slate-600 font-medium hover:bg-slate-50 rounded-xl transition-colors">Cancel</button>
                <button type="submit" disabled={saving} className="flex-1 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-2.5 rounded-xl transition shadow-sm disabled:opacity-50">{saving ? "Saving..." : "Save Purchase"}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

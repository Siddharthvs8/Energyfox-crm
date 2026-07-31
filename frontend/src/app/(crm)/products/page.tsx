"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";

const blankForm = { name: "", sku: "", unit: "unit", hsn: "", default_price: "", cost_price: "", stock_quantity: "0", reorder_level: "0" };

export default function ProductsPage({ params: paramsPromise }: { params: Promise<{ domain: string }> }) {
  const params = React.use(paramsPromise);
  const domain = APP_SLUG;
  const router = useRouter();

  const [products, setProducts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [showModal, setShowModal] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editProduct, setEditProduct] = useState<any>(null);
  const [form, setForm] = useState(blankForm);

  useEffect(() => { fetchProducts(); }, [domain]);

  const fetchProducts = async () => {
    const token = localStorage.getItem(`${domain}_access`);
    if (!token) { router.push(`/login`); return; }
    try {
      const res = await fetch(`${getApiBase(domain)}/api/products/`, { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) {
        const data = await res.json();
        setProducts(Array.isArray(data) ? data : data.results || []);
      } else setError("Failed to load products.");
    } catch { setError("Network error."); } finally { setLoading(false); }
  };

  const openCreateModal = () => { setEditProduct(null); setForm(blankForm); setShowModal(true); };
  const openEditModal = (p: any) => {
    setEditProduct(p);
    setForm({
      name: p.name || "", sku: p.sku || "", unit: p.unit || "unit", hsn: p.hsn || "",
      default_price: String(p.default_price ?? ""), cost_price: String(p.cost_price ?? ""),
      stock_quantity: String(p.stock_quantity ?? 0), reorder_level: String(p.reorder_level ?? 0),
    });
    setShowModal(true);
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    const token = localStorage.getItem(`${domain}_access`);
    const payload = {
      name: form.name, sku: form.sku, unit: form.unit, hsn: form.hsn,
      default_price: form.default_price || 0, cost_price: form.cost_price || 0,
      // Not parseInt: stock is decimal (metres of cable, part sets), and parsing
      // to an integer silently dropped the fraction on the way out.
      stock_quantity: form.stock_quantity || 0, reorder_level: form.reorder_level || 0,
    };
    const url = editProduct ? `${getApiBase(domain)}/api/products/${editProduct.id}/` : `${getApiBase(domain)}/api/products/`;
    try {
      const res = await fetch(url, {
        method: editProduct ? "PATCH" : "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (res.ok) { setShowModal(false); fetchProducts(); } else alert("Failed to save item.");
    } catch { alert("Network error."); } finally { setSaving(false); }
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Are you sure you want to delete this item?")) return;
    const token = localStorage.getItem(`${domain}_access`);
    try {
      const res = await fetch(`${getApiBase(domain)}/api/products/${id}/`, { method: "DELETE", headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) fetchProducts(); else alert("Failed to delete product.");
    } catch { alert("Network error."); }
  };

  const field = "w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none transition";

  if (loading) return (
    <div className="p-8 flex items-center justify-center h-full">
      <div className="w-8 h-8 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
    </div>
  );

  const lowCount = products.filter(p => (p.stock_quantity ?? 0) <= (p.reorder_level ?? 0)).length;

  return (
    <div className="max-w-6xl mx-auto p-4 sm:p-6 lg:p-8">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Item Master</h1>
          <p className="text-sm text-slate-500 mt-1">
            Manage items, pricing, and stock levels.
            {lowCount > 0 && <span className="ml-2 text-rose-600 font-medium">{lowCount} low on stock</span>}
          </p>
        </div>
        <button onClick={openCreateModal} className="bg-indigo-600 hover:bg-indigo-700 text-white px-5 py-2.5 rounded-xl text-sm font-semibold transition-colors flex items-center gap-2 shadow-sm">
          <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14" /></svg>
          Add Item
        </button>
      </div>

      {error && <div className="mb-6 p-4 bg-red-50 text-red-600 rounded-xl text-sm border border-red-100">{error}</div>}

      <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse min-w-[820px]">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200 text-xs uppercase tracking-wider text-slate-500 font-semibold">
                <th className="py-4 px-6">SKU</th>
                <th className="py-4 px-6">Name</th>
                <th className="py-4 px-6">HSN / SAC</th>
                <th className="py-4 px-6 text-right">Price</th>
                <th className="py-4 px-6 text-right">Cost</th>
                <th className="py-4 px-6 text-center">Stock</th>
                <th className="py-4 px-6 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {products.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-slate-500">
                    <div className="mx-auto w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center mb-3">
                      <svg width="24" height="24" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24"><path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z" /><line x1="7" y1="7" x2="7.01" y2="7" /></svg>
                    </div>
                    <p className="font-medium text-slate-900">No items found</p>
                    <p className="text-sm mt-1">Get started by creating a new product.</p>
                  </td>
                </tr>
              ) : (
                products.map((p) => {
                  const low = (p.stock_quantity ?? 0) <= (p.reorder_level ?? 0);
                  return (
                    <tr key={p.id} className="hover:bg-slate-50/50 transition-colors">
                      <td className="py-4 px-6 text-slate-500 font-mono text-xs">{p.sku || "—"}</td>
                      <td className="py-4 px-6 font-medium text-slate-900">{p.name}</td>
                      <td className="py-4 px-6 text-slate-500 font-mono text-xs">{p.hsn || "—"}</td>
                      <td className="py-4 px-6 text-right text-slate-700">₹{parseFloat(p.default_price || 0).toLocaleString("en-IN")}</td>
                      <td className="py-4 px-6 text-right text-slate-400">₹{parseFloat(p.cost_price || 0).toLocaleString("en-IN")}</td>
                      <td className="py-4 px-6 text-center">
                        <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold ${low ? "bg-rose-50 text-rose-600" : "bg-emerald-50 text-emerald-600"}`}>
                          {low && <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />}
                          {Number(p.stock_quantity ?? 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })} {p.unit || "unit"}{low ? " · Low" : ""}
                        </span>
                      </td>
                      <td className="py-4 px-6 text-right whitespace-nowrap">
                        <button onClick={() => openEditModal(p)} className="text-indigo-600 hover:text-indigo-900 text-sm font-medium mr-4">Edit</button>
                        <button onClick={() => handleDelete(p.id)} className="text-rose-600 hover:text-rose-900 text-sm font-medium">Delete</button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center px-4">
          <div className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm" onClick={() => setShowModal(false)} />
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg relative z-10 overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
              <h3 className="font-bold text-lg text-slate-900">{editProduct ? "Edit Item" : "Add Item"}</h3>
              <button onClick={() => setShowModal(false)} className="text-slate-400 hover:text-slate-600">
                <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12" /></svg>
              </button>
            </div>
            <form onSubmit={handleSave} className="p-6">
              <div className="space-y-4 mb-6">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-semibold text-slate-700 mb-1.5">Product Name *</label>
                    <input type="text" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className={field} placeholder="e.g. Premium Plan" />
                  </div>
                  <div>
                    <label className="block text-sm font-semibold text-slate-700 mb-1.5">SKU</label>
                    <input type="text" value={form.sku} onChange={(e) => setForm({ ...form, sku: e.target.value })} className={field} placeholder="e.g. A-100" />
                  </div>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-semibold text-slate-700 mb-1.5">Selling Price *</label>
                    <input type="number" step="0.01" min="0" required value={form.default_price} onChange={(e) => setForm({ ...form, default_price: e.target.value })} className={field} placeholder="0.00" />
                  </div>
                  <div>
                    <label className="block text-sm font-semibold text-slate-700 mb-1.5">Cost Price</label>
                    <input type="number" step="0.01" min="0" value={form.cost_price} onChange={(e) => setForm({ ...form, cost_price: e.target.value })} className={field} placeholder="0.00" />
                  </div>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  <div>
                    <label className="block text-sm font-semibold text-slate-700 mb-1.5">Stock Qty</label>
                    <input type="number" step="any" min="0" value={form.stock_quantity} onChange={(e) => setForm({ ...form, stock_quantity: e.target.value })} className={field} />
                  </div>
                  <div>
                    <label className="block text-sm font-semibold text-slate-700 mb-1.5">Reorder Level</label>
                    <input type="number" step="any" min="0" value={form.reorder_level} onChange={(e) => setForm({ ...form, reorder_level: e.target.value })} className={field} />
                  </div>
                  <div>
                    <label className="block text-sm font-semibold text-slate-700 mb-1.5">Unit</label>
                    <input type="text" value={form.unit} onChange={(e) => setForm({ ...form, unit: e.target.value })} className={field} placeholder="unit" />
                  </div>
                  <div>
                    <label className="block text-sm font-semibold text-slate-700 mb-1.5">HSN / SAC</label>
                    <input type="text" value={form.hsn} onChange={(e) => setForm({ ...form, hsn: e.target.value })} className={field} placeholder="e.g. 85414300" />
                  </div>
                </div>
              </div>
              <div className="flex gap-3">
                <button type="button" onClick={() => setShowModal(false)} className="flex-1 px-4 py-2.5 text-slate-600 font-medium hover:bg-slate-50 rounded-xl transition-colors">Cancel</button>
                <button type="submit" disabled={saving} className="flex-1 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-2.5 rounded-xl transition shadow-sm disabled:opacity-50">{saving ? "Saving..." : "Save Item"}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

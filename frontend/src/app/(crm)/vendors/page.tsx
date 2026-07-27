"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";

const blankForm = { name: "", contact_person: "", email: "", phone: "", gst_number: "", address: "", notes: "" };

export default function VendorsPage({ params: paramsPromise }: { params: Promise<{ domain: string }> }) {
  const params = React.use(paramsPromise);
  const domain = APP_SLUG;
  const router = useRouter();

  const [vendors, setVendors] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [showModal, setShowModal] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editVendor, setEditVendor] = useState<any>(null);
  const [form, setForm] = useState(blankForm);

  useEffect(() => { fetchVendors(); }, [domain]);

  const fetchVendors = async () => {
    const token = localStorage.getItem(`${domain}_access`);
    if (!token) { router.push(`/login`); return; }
    try {
      const res = await fetch(`${getApiBase(domain)}/api/vendors/`, { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) {
        const data = await res.json();
        setVendors(Array.isArray(data) ? data : data.results || []);
      }
    } catch {} finally { setLoading(false); }
  };

  const openCreate = () => { setEditVendor(null); setForm(blankForm); setShowModal(true); };
  const openEdit = (v: any) => {
    setEditVendor(v);
    setForm({ name: v.name || "", contact_person: v.contact_person || "", email: v.email || "", phone: v.phone || "", gst_number: v.gst_number || "", address: v.address || "", notes: v.notes || "" });
    setShowModal(true);
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    const token = localStorage.getItem(`${domain}_access`);
    const url = editVendor ? `${getApiBase(domain)}/api/vendors/${editVendor.id}/` : `${getApiBase(domain)}/api/vendors/`;
    try {
      const res = await fetch(url, {
        method: editVendor ? "PATCH" : "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      if (res.ok) { setShowModal(false); fetchVendors(); } else alert("Failed to save supplier.");
    } catch { alert("Network error."); } finally { setSaving(false); }
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Delete this supplier?")) return;
    const token = localStorage.getItem(`${domain}_access`);
    try {
      const res = await fetch(`${getApiBase(domain)}/api/vendors/${id}/`, { method: "DELETE", headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) fetchVendors(); else alert("Failed to delete supplier.");
    } catch { alert("Network error."); }
  };

  const field = "w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none transition";

  if (loading) return (
    <div className="p-8 flex items-center justify-center h-full">
      <div className="w-8 h-8 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
    </div>
  );

  const filtered = vendors.filter(v => !search || `${v.name} ${v.contact_person} ${v.email}`.toLowerCase().includes(search.toLowerCase()));

  return (
    <div className="max-w-6xl mx-auto p-4 sm:p-6 lg:p-8">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Suppliers</h1>
          <p className="text-sm text-slate-500 mt-1">Manage the suppliers you purchase stock from.</p>
        </div>
        <button onClick={openCreate} className="bg-indigo-600 hover:bg-indigo-700 text-white px-5 py-2.5 rounded-xl text-sm font-semibold transition-colors flex items-center gap-2 shadow-sm">
          <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14" /></svg>
          Add Supplier
        </button>
      </div>

      <div className="mb-4 relative max-w-sm">
        <svg className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8" /><path d="M21 21l-4.35-4.35" /></svg>
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search suppliers..." className="w-full bg-white border border-slate-200 rounded-xl pl-9 pr-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition" />
      </div>

      <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse min-w-[700px]">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200 text-xs uppercase tracking-wider text-slate-500 font-semibold">
                <th className="py-4 px-6">Supplier</th>
                <th className="py-4 px-6">Contact</th>
                <th className="py-4 px-6">Phone</th>
                <th className="py-4 px-6">GST</th>
                <th className="py-4 px-6 text-center">POs</th>
                <th className="py-4 px-6 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filtered.length === 0 ? (
                <tr><td colSpan={6} className="py-12 text-center text-slate-500">
                  <p className="font-medium text-slate-900">No suppliers found</p>
                  <p className="text-sm mt-1">Add a supplier to start creating purchase orders.</p>
                </td></tr>
              ) : filtered.map(v => (
                <tr key={v.id} className="hover:bg-slate-50/50 transition-colors">
                  <td className="py-4 px-6">
                    <div className="flex items-center gap-3">
                      <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-xs font-bold text-white flex-shrink-0">{v.name?.[0]?.toUpperCase() || "?"}</div>
                      <div className="min-w-0">
                        <p className="font-semibold text-slate-900 truncate">{v.name}</p>
                        {v.email && <p className="text-xs text-slate-400 truncate">{v.email}</p>}
                      </div>
                    </div>
                  </td>
                  <td className="py-4 px-6 text-slate-600">{v.contact_person || "—"}</td>
                  <td className="py-4 px-6 text-slate-600 font-mono text-xs">{v.phone || "—"}</td>
                  <td className="py-4 px-6 text-slate-500 font-mono text-xs">{v.gst_number || "—"}</td>
                  <td className="py-4 px-6 text-center"><span className="text-xs font-bold text-slate-600 bg-slate-100 px-2.5 py-1 rounded-full">{v.purchase_order_count ?? 0}</span></td>
                  <td className="py-4 px-6 text-right whitespace-nowrap">
                    <button onClick={() => openEdit(v)} className="text-indigo-600 hover:text-indigo-900 text-sm font-medium mr-4">Edit</button>
                    <button onClick={() => handleDelete(v.id)} className="text-rose-600 hover:text-rose-900 text-sm font-medium">Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center px-4">
          <div className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm" onClick={() => setShowModal(false)} />
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg relative z-10 overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
              <h3 className="font-bold text-lg text-slate-900">{editVendor ? "Edit Supplier" : "Add Supplier"}</h3>
              <button onClick={() => setShowModal(false)} className="text-slate-400 hover:text-slate-600"><svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12" /></svg></button>
            </div>
            <form onSubmit={handleSave} className="p-6">
              <div className="space-y-4 mb-6">
                <div>
                  <label className="block text-sm font-semibold text-slate-700 mb-1.5">Supplier Name *</label>
                  <input required value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} className={field} placeholder="e.g. Acme Supplies" />
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div><label className="block text-sm font-semibold text-slate-700 mb-1.5">Contact Person</label><input value={form.contact_person} onChange={e => setForm({ ...form, contact_person: e.target.value })} className={field} /></div>
                  <div><label className="block text-sm font-semibold text-slate-700 mb-1.5">Phone</label><input value={form.phone} onChange={e => setForm({ ...form, phone: e.target.value })} className={field} /></div>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div><label className="block text-sm font-semibold text-slate-700 mb-1.5">Email</label><input type="email" value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} className={field} /></div>
                  <div><label className="block text-sm font-semibold text-slate-700 mb-1.5">GST Number</label><input value={form.gst_number} onChange={e => setForm({ ...form, gst_number: e.target.value })} className={field} /></div>
                </div>
                <div><label className="block text-sm font-semibold text-slate-700 mb-1.5">Address</label><textarea value={form.address} onChange={e => setForm({ ...form, address: e.target.value })} rows={2} className={field} /></div>
                <div><label className="block text-sm font-semibold text-slate-700 mb-1.5">Notes</label><textarea value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} rows={2} className={field} /></div>
              </div>
              <div className="flex gap-3">
                <button type="button" onClick={() => setShowModal(false)} className="flex-1 px-4 py-2.5 text-slate-600 font-medium hover:bg-slate-50 rounded-xl transition-colors">Cancel</button>
                <button type="submit" disabled={saving} className="flex-1 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-2.5 rounded-xl transition shadow-sm disabled:opacity-50">{saving ? "Saving..." : "Save Supplier"}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

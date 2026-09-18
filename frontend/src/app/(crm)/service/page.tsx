"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { isSpectator } from "@/lib/spectator";

type Service = {
  id: number;
  customer_name: string;
  customer_id: string;
  scheduled_date: string | null;
  assigned_to: string;
};

const BLANK = { customer_name: "", customer_id: "", scheduled_date: "", assigned_to: "" };
const inputCls = "w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all";

export default function ServicePage() {
  const domain = APP_SLUG;
  const router = useRouter();
  const [authChecked, setAuthChecked] = useState(false);
  const [allowed, setAllowed] = useState(false);
  const [rows, setRows] = useState<Service[]>([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({ ...BLANK });
  const [editingId, setEditingId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);

  const token = () => localStorage.getItem(`${domain}_access`);
  const base = `${getApiBase(domain)}/api/service-entries/`;

  useEffect(() => {
    const t = token();
    if (!t) { router.push("/login"); return; }
    fetch(`${getApiBase(domain)}/api/users/me/`, { headers: { Authorization: `Bearer ${t}` } })
      .then(r => r.json())
      .then(d => {
        const ok = isSpectator(d) || d.role === "project_manager" || d.is_staff || d.is_general_manager;
        setAllowed(ok); setAuthChecked(true);
        if (!ok) router.replace("/");
      })
      .catch(() => setAuthChecked(true));
  }, [domain, router]);

  const loadRows = () => {
    fetch(base, { headers: { Authorization: `Bearer ${token()}` } })
      .then(r => (r.ok ? r.json() : []))
      .then(d => setRows(Array.isArray(d) ? d : (d.results || [])))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { if (allowed) loadRows(); }, [allowed]); // eslint-disable-line react-hooks/exhaustive-deps

  const resetForm = () => { setForm({ ...BLANK }); setEditingId(null); };

  const submit = async () => {
    if (!form.customer_name.trim()) { alert("Customer name is required."); return; }
    setSaving(true);
    try {
      const body = JSON.stringify({ ...form, scheduled_date: form.scheduled_date || null });
      const r = await fetch(editingId ? `${base}${editingId}/` : base, {
        method: editingId ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token()}` },
        body,
      });
      if (r.ok) { resetForm(); loadRows(); }
      else { const e = await r.json().catch(() => ({})); alert(e.detail || e.error || "Failed to save."); }
    } catch { alert("Network error."); }
    finally { setSaving(false); }
  };

  const edit = (s: Service) => {
    setEditingId(s.id);
    setForm({ customer_name: s.customer_name || "", customer_id: s.customer_id || "", scheduled_date: s.scheduled_date || "", assigned_to: s.assigned_to || "" });
  };

  const remove = async (id: number) => {
    if (!window.confirm("Delete this service entry?")) return;
    try {
      const r = await fetch(`${base}${id}/`, { method: "DELETE", headers: { Authorization: `Bearer ${token()}` } });
      if (r.ok || r.status === 204) loadRows();
      else alert("Could not delete.");
    } catch { alert("Network error."); }
  };

  if (!authChecked) return <div className="flex items-center justify-center min-h-[60vh]"><div className="w-8 h-8 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" /></div>;
  if (!allowed) return null;

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-[1100px]">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Service</h1>
        <p className="text-sm text-slate-500 mt-1">Scheduled service entries.</p>
      </div>

      {/* Add / edit form */}
      <div className="mb-6 bg-white border border-slate-200 rounded-2xl shadow-sm p-5">
        <h2 className="text-sm font-bold text-slate-900 mb-3">{editingId ? "Edit Service Entry" : "Add Service Entry"}</h2>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <div><label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wide mb-1.5">Customer Name</label><input value={form.customer_name} onChange={e => setForm({ ...form, customer_name: e.target.value })} className={inputCls} placeholder="Customer name" /></div>
          <div><label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wide mb-1.5">Customer ID</label><input value={form.customer_id} onChange={e => setForm({ ...form, customer_id: e.target.value })} className={inputCls} placeholder="Customer ID" /></div>
          <div><label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wide mb-1.5">Scheduled Date</label><input type="date" value={form.scheduled_date} onChange={e => setForm({ ...form, scheduled_date: e.target.value })} className={inputCls} /></div>
          <div><label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wide mb-1.5">Assigned To</label><input value={form.assigned_to} onChange={e => setForm({ ...form, assigned_to: e.target.value })} className={inputCls} placeholder="Assigned to" /></div>
        </div>
        <div className="flex items-center gap-3 mt-4">
          <button onClick={submit} disabled={saving} className="px-5 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 disabled:opacity-50 transition">{saving ? "Saving…" : editingId ? "Update" : "Add"}</button>
          {editingId && <button onClick={resetForm} className="px-4 py-2.5 bg-slate-100 text-slate-600 rounded-xl text-sm font-semibold hover:bg-slate-200 transition">Cancel</button>}
        </div>
      </div>

      {/* Table */}
      <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
        {loading ? (
          <div className="py-16 text-center text-sm text-slate-400">Loading…</div>
        ) : rows.length === 0 ? (
          <div className="py-12 text-center text-sm text-slate-400">No service entries yet.</div>
        ) : (
          /* Phone: the five columns do not fit, so the table scrolls as one
             piece inside the card instead of widening the page. */
          <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[640px]">
            <thead>
              <tr className="text-left text-[10px] font-bold text-slate-400 uppercase tracking-wide border-b border-slate-100">
                <th className="px-5 py-3">Customer Name</th>
                <th className="px-5 py-3">Customer ID</th>
                <th className="px-5 py-3">Scheduled Date</th>
                <th className="px-5 py-3">Assigned To</th>
                <th className="px-5 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(s => (
                <tr key={s.id} className="border-b border-slate-50 hover:bg-slate-50/60">
                  <td className="px-5 py-3 font-semibold text-slate-800">{s.customer_name || "—"}</td>
                  <td className="px-5 py-3 text-slate-600">{s.customer_id || "—"}</td>
                  <td className="px-5 py-3 text-slate-600">{s.scheduled_date ? new Date(s.scheduled_date).toLocaleDateString("en-IN") : "—"}</td>
                  <td className="px-5 py-3 text-slate-600">{s.assigned_to || "—"}</td>
                  <td className="px-5 py-3">
                    <div className="flex items-center justify-end gap-3">
                      <button onClick={() => edit(s)} className="text-[12px] font-semibold text-indigo-600 hover:text-indigo-800">Edit</button>
                      <button onClick={() => remove(s.id)} className="text-[12px] font-semibold text-rose-500 hover:text-rose-700">Delete</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </div>
    </div>
  );
}

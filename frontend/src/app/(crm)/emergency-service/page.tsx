"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

type Entry = {
  id: number;
  customer_name: string;
  service: string;
  remarks: string;
  dc_voltage: string;
  error_codes: string;
  ac_ne_voltage: string;
  ac_pn_voltage: string;
  ac_pe_voltage: string;
  monthly_production: string;
  created_by_name: string | null;
  created_at: string;
};

type CustomerSug = { id: number; first_name: string; last_name: string | null; phone: string | null; location: string | null };

const BLANK = {
  customer_name: "", service: "", remarks: "", dc_voltage: "", error_codes: "",
  ac_ne_voltage: "", ac_pn_voltage: "", ac_pe_voltage: "", monthly_production: "",
};

const inputCls = "w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all";
const labelCls = "block text-[10px] font-bold text-slate-400 uppercase tracking-wide mb-1.5";

export default function EmergencyServicePage() {
  const domain = APP_SLUG;
  const router = useRouter();
  const [authChecked, setAuthChecked] = useState(false);
  const [allowed, setAllowed] = useState(false);
  const [rows, setRows] = useState<Entry[]>([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({ ...BLANK });
  const [editingId, setEditingId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [customers, setCustomers] = useState<CustomerSug[]>([]);
  const [sugOpen, setSugOpen] = useState(false);

  const token = () => localStorage.getItem(`${domain}_access`);
  const base = `${getApiBase(domain)}/api/emergency-services/`;

  useEffect(() => {
    const t = token();
    if (!t) { router.push("/login"); return; }
    fetch(`${getApiBase(domain)}/api/users/me/`, { headers: { Authorization: `Bearer ${t}` } })
      .then(r => r.json())
      .then(d => {
        const ok = d.role === "liasoning_officer" || d.is_staff || d.is_general_manager;
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

  useEffect(() => {
    if (!allowed) return;
    fetch(`${getApiBase(domain)}/api/leads/liasoning/`, { headers: { Authorization: `Bearer ${token()}` } })
      .then(r => (r.ok ? r.json() : []))
      .then(d => setCustomers(Array.isArray(d) ? d : []))
      .catch(() => {});
  }, [allowed]); // eslint-disable-line react-hooks/exhaustive-deps

  const fullName = (c: CustomerSug) => `${c.first_name} ${c.last_name || ""}`.trim();
  const sugQuery = form.customer_name.trim().toLowerCase();
  const suggestions = sugQuery
    ? customers.filter(c =>
        fullName(c).toLowerCase().includes(sugQuery) || (c.phone || "").toLowerCase().includes(sugQuery)
      ).filter(c => fullName(c).toLowerCase() !== sugQuery).slice(0, 8)
    : customers.slice(0, 8);

  const resetForm = () => { setForm({ ...BLANK }); setEditingId(null); };

  const submit = async () => {
    if (!form.customer_name.trim() && !form.service.trim()) { alert("Enter the customer or the service done."); return; }
    setSaving(true);
    try {
      const r = await fetch(editingId ? `${base}${editingId}/` : base, {
        method: editingId ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token()}` },
        body: JSON.stringify(form),
      });
      if (r.ok) { resetForm(); loadRows(); }
      else { const e = await r.json().catch(() => ({})); alert(e.detail || e.error || "Failed to save."); }
    } catch { alert("Network error."); }
    finally { setSaving(false); }
  };

  const edit = (s: Entry) => {
    setEditingId(s.id);
    setForm({
      customer_name: s.customer_name || "", service: s.service || "", remarks: s.remarks || "",
      dc_voltage: s.dc_voltage || "", error_codes: s.error_codes || "",
      ac_ne_voltage: s.ac_ne_voltage || "", ac_pn_voltage: s.ac_pn_voltage || "", ac_pe_voltage: s.ac_pe_voltage || "",
      monthly_production: s.monthly_production || "",
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const remove = async (id: number) => {
    if (!window.confirm("Delete this emergency service entry?")) return;
    try {
      const r = await fetch(`${base}${id}/`, { method: "DELETE", headers: { Authorization: `Bearer ${token()}` } });
      if (r.ok || r.status === 204) loadRows();
      else alert("Could not delete.");
    } catch { alert("Network error."); }
  };

  if (!authChecked) return <div className="flex items-center justify-center min-h-[60vh]"><div className="w-8 h-8 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" /></div>;
  if (!allowed) return null;

  return (
    <div className="p-6 lg:p-8 max-w-[1300px]">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Emergency Service</h1>
        <p className="text-sm text-slate-500 mt-1">Urgent service visits with the on-site electrical readings.</p>
      </div>

      {/* Add / edit form */}
      <div className="mb-6 bg-white border border-slate-200 rounded-2xl shadow-sm p-5">
        <h2 className="text-sm font-bold text-slate-900 mb-3">{editingId ? "Edit Service Entry" : "Add Service Entry"}</h2>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          <div className="relative">
            <label className={labelCls}>Customer</label>
            <input
              value={form.customer_name}
              onChange={e => { setForm({ ...form, customer_name: e.target.value }); setSugOpen(true); }}
              onFocus={() => setSugOpen(true)}
              onBlur={() => setTimeout(() => setSugOpen(false), 150)}
              className={inputCls}
              placeholder="Search customer name…"
              autoComplete="off"
            />
            {sugOpen && suggestions.length > 0 && (
              <div className="absolute z-20 left-0 right-0 mt-1 bg-white border border-slate-200 rounded-xl shadow-lg overflow-hidden max-h-64 overflow-y-auto">
                {suggestions.map(c => (
                  <button
                    key={c.id}
                    type="button"
                    onMouseDown={e => { e.preventDefault(); setForm(f => ({ ...f, customer_name: fullName(c) })); setSugOpen(false); }}
                    className="w-full text-left px-3 py-2 hover:bg-indigo-50 transition-colors border-b border-slate-50 last:border-b-0"
                  >
                    <p className="text-sm font-semibold text-slate-800">{fullName(c)}</p>
                    <p className="text-[11px] text-slate-400">{c.phone || "—"}{c.location ? ` · ${c.location}` : ""}</p>
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="lg:col-span-2"><label className={labelCls}>Service</label><input value={form.service} onChange={e => setForm({ ...form, service: e.target.value })} className={inputCls} placeholder="Service done" /></div>
          <div><label className={labelCls}>DC Voltage</label><input value={form.dc_voltage} onChange={e => setForm({ ...form, dc_voltage: e.target.value })} className={inputCls} placeholder="e.g. 240 V" /></div>
          <div><label className={labelCls}>Error Codes (if any)</label><input value={form.error_codes} onChange={e => setForm({ ...form, error_codes: e.target.value })} className={inputCls} placeholder="Error codes" /></div>
          <div><label className={labelCls}>Monthly Production</label><input value={form.monthly_production} onChange={e => setForm({ ...form, monthly_production: e.target.value })} className={inputCls} placeholder="e.g. 550 kWh" /></div>
        </div>
        <div className="mt-4 bg-slate-50/70 border border-slate-100 rounded-xl p-4">
          <p className="text-[10px] font-bold text-indigo-600 uppercase tracking-wide mb-3">AC Voltage</p>
          <div className="grid sm:grid-cols-3 gap-3">
            <div><label className={labelCls}>N-E Voltage</label><input value={form.ac_ne_voltage} onChange={e => setForm({ ...form, ac_ne_voltage: e.target.value })} className={inputCls} placeholder="N-E" /></div>
            <div><label className={labelCls}>P-N</label><input value={form.ac_pn_voltage} onChange={e => setForm({ ...form, ac_pn_voltage: e.target.value })} className={inputCls} placeholder="P-N" /></div>
            <div><label className={labelCls}>P-E</label><input value={form.ac_pe_voltage} onChange={e => setForm({ ...form, ac_pe_voltage: e.target.value })} className={inputCls} placeholder="P-E" /></div>
          </div>
        </div>
        <div className="mt-4">
          <label className={labelCls}>Remarks</label>
          <input value={form.remarks} onChange={e => setForm({ ...form, remarks: e.target.value })} className={inputCls} placeholder="Remarks" />
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
          <div className="py-12 text-center text-sm text-slate-400">No emergency service entries yet.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[1000px]">
              <thead>
                <tr className="text-left text-[10px] font-bold text-slate-400 uppercase tracking-wide border-b border-slate-100 bg-slate-50/60">
                  <th className="px-4 py-3">Customer</th>
                  <th className="px-4 py-3">Service</th>
                  <th className="px-4 py-3">DC Voltage</th>
                  <th className="px-4 py-3">Error Codes</th>
                  <th className="px-4 py-3">AC Voltage (N-E / P-N / P-E)</th>
                  <th className="px-4 py-3">Monthly Production</th>
                  <th className="px-4 py-3">Remarks</th>
                  <th className="px-4 py-3">Date</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(s => (
                  <tr key={s.id} className="border-b border-slate-50 hover:bg-slate-50/60 align-top">
                    <td className="px-4 py-3 font-semibold text-slate-800">{s.customer_name || "—"}</td>
                    <td className="px-4 py-3 text-slate-600 max-w-[220px]"><span className="line-clamp-2">{s.service || "—"}</span></td>
                    <td className="px-4 py-3 text-slate-600">{s.dc_voltage || "—"}</td>
                    <td className="px-4 py-3 text-slate-600">{s.error_codes || "—"}</td>
                    <td className="px-4 py-3 text-slate-600 whitespace-nowrap">
                      {[s.ac_ne_voltage || "—", s.ac_pn_voltage || "—", s.ac_pe_voltage || "—"].join(" / ")}
                    </td>
                    <td className="px-4 py-3 text-slate-600">{s.monthly_production || "—"}</td>
                    <td className="px-4 py-3 text-slate-600 max-w-[180px]"><span className="line-clamp-2">{s.remarks || "—"}</span></td>
                    <td className="px-4 py-3 text-slate-500 whitespace-nowrap">{s.created_at ? new Date(s.created_at).toLocaleDateString("en-IN") : "—"}</td>
                    <td className="px-4 py-3">
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

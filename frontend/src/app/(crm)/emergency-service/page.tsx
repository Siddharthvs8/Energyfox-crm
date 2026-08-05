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
  // Each AC reading is typed and photographed — the meter shot is the evidence.
  ac_ne_photo: string | null;
  ac_pn_photo: string | null;
  ac_pe_photo: string | null;
  monthly_production: string;
  // What was found wrong, and what was swapped out.
  dc_side_condition: string; ac_side_condition: string; replacement: string;
  dc_side_condition_label: string; ac_side_condition_label: string; replacement_label: string;
  created_by_name: string | null;
  created_at: string;
};

type CustomerSug = { id: number; first_name: string; last_name: string | null; phone: string | null; location: string | null };

const BLANK = {
  customer_name: "", service: "", remarks: "", dc_voltage: "", error_codes: "",
  ac_ne_voltage: "", ac_pn_voltage: "", ac_pe_voltage: "", monthly_production: "",
  dc_side_condition: "", ac_side_condition: "", replacement: "",
};

/** Service condition — values must match EmergencyService's choices. */
const SERVICE_CONDITION = [
  {
    field: "dc_side_condition", label: "DC Side",
    options: [
      ["inverter_damage", "Inverter damage"],
      ["dc_fuse_damage", "DC fuse damage"],
      ["dc_mcb_damage", "DC MCB damage"],
      ["dc_box_burned", "DC box burned"],
      ["dc_spd_damage", "DC SPD damage"],
    ],
  },
  {
    field: "ac_side_condition", label: "AC Side",
    options: [
      ["ac_spd_damage", "AC SPD damage"],
      ["ac_mcb_isolator_damage", "AC MCB / isolator damage"],
      ["generation_meter_faulty", "Generation meter faulty / burned"],
      ["termination_point_damage", "Termination point damage"],
    ],
  },
  {
    field: "replacement", label: "Replacements",
    options: [
      ["inverter", "Inverter"],
      ["panel", "Panel"],
      ["dc_db", "DC DB"],
      ["ac_db", "AC DB"],
      ["dc_db_components", "DC DB components"],
      ["ac_db_components", "AC DB components"],
    ],
  },
] as const;

/** The three AC readings, each with its text field and its photo field. */
const AC_READINGS = [
  { text: "ac_ne_voltage", photo: "ac_ne_photo", label: "N-E Voltage", ph: "N-E" },
  { text: "ac_pn_voltage", photo: "ac_pn_photo", label: "P-N", ph: "P-N" },
  { text: "ac_pe_voltage", photo: "ac_pe_photo", label: "P-E", ph: "P-E" },
] as const;

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

  // Chosen files live outside `form`, which only carries the text values.
  const [photos, setPhotos] = useState<Record<string, File | null>>({});
  // What is already stored, so editing shows the shot rather than an empty box.
  const [existing, setExisting] = useState<Record<string, string | null>>({});

  const resetForm = () => {
    setForm({ ...BLANK }); setEditingId(null);
    setPhotos({}); setExisting({});
  };

  const submit = async () => {
    if (!form.customer_name.trim() && !form.service.trim()) { alert("Enter the customer or the service done."); return; }
    setSaving(true);
    try {
      // Multipart, because the readings carry photos. Only the photos actually
      // chosen are sent, so editing text does not wipe a stored shot.
      const body = new FormData();
      Object.entries(form).forEach(([k, v]) => body.append(k, String(v ?? "")));
      AC_READINGS.forEach(({ photo }) => {
        const f = photos[photo];
        if (f) body.append(photo, f);
      });
      const r = await fetch(editingId ? `${base}${editingId}/` : base, {
        method: editingId ? "PATCH" : "POST",
        headers: { Authorization: `Bearer ${token()}` },
        body,
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
      dc_side_condition: s.dc_side_condition || "", ac_side_condition: s.ac_side_condition || "",
      replacement: s.replacement || "",
    });
    setPhotos({});
    setExisting({ ac_ne_photo: s.ac_ne_photo, ac_pn_photo: s.ac_pn_photo, ac_pe_photo: s.ac_pe_photo });
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
          <p className="text-[11px] text-slate-400 -mt-2 mb-3">Type the reading and attach the meter photo.</p>
          <div className="grid sm:grid-cols-3 gap-3">
            {AC_READINGS.map(({ text, photo, label, ph }) => {
              const chosen = photos[photo];
              const stored = existing[photo];
              const preview = chosen ? URL.createObjectURL(chosen) : stored;
              return (
                <div key={text}>
                  <label className={labelCls}>{label}</label>
                  <input value={(form as any)[text]}
                    onChange={e => setForm({ ...form, [text]: e.target.value })}
                    className={inputCls} placeholder={ph} />

                  {preview && (
                    <a href={preview} target="_blank" rel="noreferrer"
                      className="block mt-2 h-20 rounded-lg border border-slate-200 overflow-hidden bg-white">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={preview} alt={`${label} reading`} className="w-full h-full object-cover" />
                    </a>
                  )}
                  <input type="file" accept="image/*" capture="environment"
                    onChange={e => setPhotos(p => ({ ...p, [photo]: e.target.files?.[0] ?? null }))}
                    className="mt-2 block w-full text-[11px] text-slate-500 file:mr-2 file:py-1 file:px-2 file:rounded-md file:border-0 file:text-[11px] file:font-semibold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100 transition cursor-pointer" />
                  {chosen && <p className="text-[10px] text-emerald-600 mt-1 truncate">{chosen.name}</p>}
                </div>
              );
            })}
          </div>
        </div>
        <div className="mt-4 bg-slate-50/70 border border-slate-100 rounded-xl p-4">
          <p className="text-[10px] font-bold text-indigo-600 uppercase tracking-wide mb-3">Service Condition</p>
          <div className="grid sm:grid-cols-3 gap-3">
            {SERVICE_CONDITION.map(({ field, label, options }) => (
              <div key={field}>
                <label className={labelCls}>{label}</label>
                <select value={(form as any)[field]}
                  onChange={e => setForm({ ...form, [field]: e.target.value })}
                  className={inputCls}>
                  <option value="">—</option>
                  {options.map(([value, text]) => (
                    <option key={value} value={value}>{text}</option>
                  ))}
                </select>
              </div>
            ))}
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
                  <th className="px-4 py-3">Service Condition</th>
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
                      {/* Each reading links to its meter photo when there is one. */}
                      <span className="inline-flex items-center gap-1">
                        {AC_READINGS.map(({ text, photo }, n) => {
                          const value = (s as any)[text] || "—";
                          const shot = (s as any)[photo] as string | null;
                          return (
                            <span key={text} className="inline-flex items-center">
                              {n > 0 && <span className="text-slate-300 mx-1">/</span>}
                              {shot ? (
                                <a href={shot} target="_blank" rel="noreferrer"
                                  title="Open the meter photo"
                                  className="text-indigo-600 hover:text-indigo-800 font-semibold underline decoration-dotted">
                                  {value}
                                </a>
                              ) : value}
                            </span>
                          );
                        })}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-600 min-w-[170px]">
                      {/* Labels come from the server, so the list never keeps its
                          own copy of the choice text. */}
                      {(() => {
                        const found = [
                          ["DC", s.dc_side_condition_label],
                          ["AC", s.ac_side_condition_label],
                          ["Replaced", s.replacement_label],
                        ].filter(([, v]) => !!v);
                        if (!found.length) return <span className="text-slate-300">—</span>;
                        return (
                          <div className="space-y-0.5">
                            {found.map(([k, v]) => (
                              <p key={k as string} className="text-[11px] leading-tight">
                                <span className="text-slate-400">{k}: </span>{v}
                              </p>
                            ))}
                          </div>
                        );
                      })()}
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

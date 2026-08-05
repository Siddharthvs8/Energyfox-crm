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
  dc_floating_voltage: string;
  error_codes: string;
  ac_ne_voltage: string;
  ac_pn_voltage: string;
  ac_pe_voltage: string;
  // Every reading is typed and photographed; several shots per reading.
  documents: EntryDoc[];
  monthly_production: string;
  // What was found wrong, and what was swapped out.
  dc_side_condition: string; ac_side_condition: string; replacement: string;
  dc_side_condition_label: string; ac_side_condition_label: string; replacement_label: string;
  created_by_name: string | null;
  created_at: string;
};

type EntryDoc = { id: number; doc_type: string; file: string; uploaded_at: string };

type CustomerSug = { id: number; first_name: string; last_name: string | null; phone: string | null; location: string | null };

const BLANK = {
  customer_name: "", service: "", remarks: "", dc_voltage: "", dc_floating_voltage: "",
  error_codes: "", ac_ne_voltage: "", ac_pn_voltage: "", ac_pe_voltage: "", monthly_production: "",
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

/** Photo slots, matching EmergencyService.PHOTO_SLOTS. */
const AC_READINGS = [
  { text: "ac_ne_voltage", slot: "ac_ne", label: "N-E Voltage", ph: "N-E" },
  { text: "ac_pn_voltage", slot: "ac_pn", label: "P-N", ph: "P-N" },
  { text: "ac_pe_voltage", slot: "ac_pe", label: "P-E", ph: "P-E" },
] as const;

/** The readings above the AC block, which take photos too. */
const TOP_READINGS = [
  { text: "dc_voltage", slot: "dc_voltage", label: "DC Voltage", ph: "e.g. 240 V" },
  { text: "dc_floating_voltage", slot: "dc_floating_voltage", label: "DC Floating Voltages", ph: "e.g. 12 V" },
  { text: "error_codes", slot: "error_codes", label: "Error Codes (if any)", ph: "Error codes" },
  { text: "monthly_production", slot: "monthly_production", label: "Monthly Production", ph: "e.g. 550 kWh" },
] as const;

/** Picture-only slots: the panel wash and what the plant made either side of the
 *  visit. Nothing to type for these, only the photograph. */
const PICTURE_SLOTS = [
  ["panel_before", "Panel Wash — Before"],
  ["panel_after", "Panel Wash — After"],
  ["production_before", "Production Before Service"],
  ["production_after", "Production After Service"],
] as const;

/** The API returns an absolute URL when it has the request in hand and a
 *  relative one otherwise; either has to open against the backend, not the app. */
const hrefFor = (apiBase: string, file: string) =>
  file.startsWith("http") ? file : `${apiBase}${file}`;

const inputCls = "w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all";
const labelCls = "block text-[10px] font-bold text-slate-400 uppercase tracking-wide mb-1.5";


/**
 * A slot's files: green links with a ✕, then "+ Add file(s)". Shared by the
 * readings and by the picture-only slots, which have no value to type.
 *
 * Defined here rather than inside the page: a component declared during render
 * is a new type on every keystroke, so React tears the subtree down and rebuilds
 * it, and the input loses focus after a single character.
 */
function FileSlot({ apiBase, stored, busy, onAdd, onDropStored }: {
  apiBase: string; stored: EntryDoc[]; busy: boolean;
  onAdd: (files: File[]) => void;
  onDropStored: (doc: EntryDoc) => void;
}) {
  return (
    <>
      {stored.length > 0 && (
        <ul className="mt-2 space-y-1">
          {stored.map(d => {
            const href = hrefFor(apiBase, d.file);
            const name = decodeURIComponent(d.file.split("/").pop() || "file");
            return (
              <li key={d.id} className="flex items-center gap-2 text-[11px]">
                <a href={href} target="_blank" rel="noreferrer" title={name}
                  className="font-semibold text-emerald-600 hover:underline truncate max-w-[150px]">{name}</a>
                <button type="button" onClick={() => onDropStored(d)} title="Delete file"
                  className="font-bold text-rose-500 hover:text-rose-700">✕</button>
              </li>
            );
          })}
        </ul>
      )}

      <label className={`mt-2 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-semibold transition ${busy ? "bg-slate-100 text-slate-400 cursor-not-allowed" : "bg-slate-100 text-slate-700 hover:bg-slate-200 cursor-pointer"}`}>
        {busy ? "Uploading…" : "+ Add file(s)"}
        <input type="file" accept="image/*,application/pdf" multiple capture="environment" disabled={busy} className="hidden"
          onChange={e => { const fs = Array.from(e.target.files || []); e.currentTarget.value = ""; onAdd(fs); }} />
      </label>
    </>
  );
}

/** A reading: the typed value, then its photos. */
function Reading({
  label, ph, value, apiBase, stored, busy, onChange, onAdd, onDropStored,
}: {
  slot: string; text: string; label: string; ph: string;
  value: string; apiBase: string; stored: EntryDoc[]; busy: boolean;
  onChange: (v: string) => void;
  onAdd: (files: File[]) => void;
  onDropStored: (doc: EntryDoc) => void;
}) {
  return (
    <div>
      <label className={labelCls}>{label}</label>
      <input value={value} onChange={e => onChange(e.target.value)}
        className={inputCls} placeholder={ph} />
      <FileSlot apiBase={apiBase} stored={stored} busy={busy} onAdd={onAdd} onDropStored={onDropStored} />
    </div>
  );
}

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
  const apiBase = getApiBase(domain);
  const base = `${apiBase}/api/emergency-services/`;

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

  // Photos stored against the entry being filled in or edited.
  const [stored, setStored] = useState<EntryDoc[]>([]);
  const [uploading, setUploading] = useState<string | null>(null);

  const resetForm = () => {
    setForm({ ...BLANK }); setEditingId(null); setStored([]);
  };

  /** Attach straight away, the way the site visit does.
   *
   *  Photos hang off a saved entry, so the first attachment on a new form
   *  creates the entry — from then on the form is editing it, and the button
   *  says Update. That is the price of uploading before save rather than after.
   */
  const addFiles = async (slot: string, files: File[]) => {
    if (!files.length) return;
    let entryId = editingId;
    if (!entryId && !form.customer_name.trim() && !form.service.trim()) {
      alert("Enter the customer or the service done before attaching photos.");
      return;
    }
    setUploading(slot);
    try {
      if (!entryId) {
        const r = await fetch(base, {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${token()}` },
          body: JSON.stringify(form),
        });
        if (!r.ok) {
          const e = await r.json().catch(() => ({}));
          alert(e.detail || e.error || "Could not start this entry.");
          return;
        }
        entryId = (await r.json()).id;
        setEditingId(entryId);
      }
      const added: EntryDoc[] = [];
      for (const file of files) {
        const body = new FormData();
        body.append("file", file);
        body.append("doc_type", slot);
        const r = await fetch(`${base}${entryId}/documents/`, {
          method: "POST", headers: { Authorization: `Bearer ${token()}` }, body,
        });
        if (!r.ok) {
          const e = await r.json().catch(() => ({}));
          alert(e.error || `Could not upload ${file.name}.`);
          break;
        }
        added.push(await r.json());
      }
      if (added.length) setStored(list => [...list, ...added]);
      loadRows();
    } catch { alert("Network error while uploading."); }
    finally { setUploading(null); }
  };

  /** Stored photos are removed straight away — the entry exists. */
  const dropStored = async (doc: EntryDoc) => {
    if (!window.confirm("Remove this photo?")) return;
    try {
      const r = await fetch(`${base}${editingId}/documents/${doc.id}/`, {
        method: "DELETE", headers: { Authorization: `Bearer ${token()}` },
      });
      if (r.ok || r.status === 204) { setStored(list => list.filter(d => d.id !== doc.id)); loadRows(); }
      else alert("Could not remove the photo.");
    } catch { alert("Network error."); }
  };

  const submit = async () => {
    if (!form.customer_name.trim() && !form.service.trim()) { alert("Enter the customer or the service done."); return; }
    setSaving(true);
    try {
      // Photos are already up — attaching one created the entry if it was new,
      // so this only ever saves the readings.
      const r = await fetch(editingId ? `${base}${editingId}/` : base, {
        method: editingId ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token()}` },
        body: JSON.stringify(form),
      });
      if (!r.ok) {
        const e = await r.json().catch(() => ({}));
        alert(e.detail || e.error || "Failed to save.");
        return;
      }
      resetForm(); loadRows();
    } catch { alert("Network error."); }
    finally { setSaving(false); }
  };

  const edit = (s: Entry) => {
    setEditingId(s.id);
    setForm({
      customer_name: s.customer_name || "", service: s.service || "", remarks: s.remarks || "",
      dc_voltage: s.dc_voltage || "", dc_floating_voltage: s.dc_floating_voltage || "",
      error_codes: s.error_codes || "",
      ac_ne_voltage: s.ac_ne_voltage || "", ac_pn_voltage: s.ac_pn_voltage || "", ac_pe_voltage: s.ac_pe_voltage || "",
      monthly_production: s.monthly_production || "",
      dc_side_condition: s.dc_side_condition || "", ac_side_condition: s.ac_side_condition || "",
      replacement: s.replacement || "",
    });
    setStored(s.documents || []);
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
          {TOP_READINGS.map(r => <Reading key={r.slot} {...r} value={(form as any)[r.text] || ""} apiBase={apiBase}
              stored={stored.filter(d => d.doc_type === r.slot)} busy={uploading === r.slot}
              onChange={v => setForm({ ...form, [r.text]: v })}
              onAdd={fs => addFiles(r.slot, fs)} onDropStored={dropStored} />)}
        </div>
        <div className="mt-4 bg-slate-50/70 border border-slate-100 rounded-xl p-4">
          <p className="text-[10px] font-bold text-indigo-600 uppercase tracking-wide mb-3">AC Voltage</p>
          <p className="text-[11px] text-slate-400 -mt-2 mb-3">Type the reading and attach the meter photo(s).</p>
          <div className="grid sm:grid-cols-3 gap-3">
            {AC_READINGS.map(r => <Reading key={r.slot} {...r} value={(form as any)[r.text] || ""} apiBase={apiBase}
              stored={stored.filter(d => d.doc_type === r.slot)} busy={uploading === r.slot}
              onChange={v => setForm({ ...form, [r.text]: v })}
              onAdd={fs => addFiles(r.slot, fs)} onDropStored={dropStored} />)}
          </div>
        </div>
        {/* Pictures — the wash, and what the plant made either side of the visit.
            Nothing to type for these, only the photograph. */}
        <div className="mt-4 bg-slate-50/70 border border-slate-100 rounded-xl p-4">
          <p className="text-[10px] font-bold text-indigo-600 uppercase tracking-wide mb-3">Photos</p>
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {PICTURE_SLOTS.map(([slot, label]) => (
              <div key={slot}>
                <label className={labelCls}>{label}</label>
                <FileSlot apiBase={apiBase} stored={stored.filter(d => d.doc_type === slot)}
                  busy={uploading === slot} onAdd={fs => addFiles(slot, fs)} onDropStored={dropStored} />
              </div>
            ))}
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
                    {/* Floating voltage sits under the DC reading rather than
                        claiming a column of its own. */}
                    <td className="px-4 py-3 text-slate-600">
                      {s.dc_voltage || "—"}
                      {s.dc_floating_voltage && (
                        <span className="block text-[11px] text-slate-400">Float {s.dc_floating_voltage}</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-slate-600">{s.error_codes || "—"}</td>
                    <td className="px-4 py-3 text-slate-600 whitespace-nowrap">
                      {/* Each reading links to its photos; a reading can have several. */}
                      <span className="inline-flex items-center gap-1">
                        {AC_READINGS.map(({ text, slot }, n) => {
                          const value = (s as any)[text] || "—";
                          const shots = (s.documents || []).filter(d => d.doc_type === slot);
                          return (
                            <span key={text} className="inline-flex items-center">
                              {n > 0 && <span className="text-slate-300 mx-1">/</span>}
                              {shots.length ? (
                                <a href={hrefFor(apiBase, shots[0].file)} target="_blank" rel="noreferrer"
                                  title={`${shots.length} photo(s)`}
                                  className="text-indigo-600 hover:text-indigo-800 font-semibold underline decoration-dotted">
                                  {value}{shots.length > 1 ? ` (${shots.length})` : ""}
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

"use client";
/**
 * Projects — the retail side's bundles of products.
 *
 * A project is the specification a customer is sold: which panels, which
 * inverter, which structure, and the balance of system that goes with them.
 * It carries no prices. The proforma is still priced from its own line items;
 * this is the sheet that says what the customer is getting, and picking a
 * project on a quote copies that sheet onto it.
 *
 * The four sections are fixed and always shown in this order, empty or not, so
 * every project reads the same way and the printed sheet never rearranges
 * itself between one customer and the next.
 *
 * (The API calls it ProjectSpec, to stay clear of the installation Project a
 * job passes through. Nothing user-facing says "spec".)
 */
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";

import React, { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

type Line = { section: string; item_name: string; brand: string; quantity: string; position: number };
type Project = {
  id: number; name: string; capacity: string; notes: string; is_active: boolean;
  price_dcr: string; price_non_dcr: string;
  tax_percent: string; price_includes_tax: boolean;
  pricing: Record<string, { price: string; base_amount: string; tax_amount: string; total: string }>;
  lines: Line[]; line_count: number; quoted_count: number;
};

// The same system, built with Indian-made modules or imported ones. A different
// price, not a different product — so a project quotes both.
const VARIANTS: [string, string][] = [["dcr", "DCR"], ["non_dcr", "Non-DCR"]];

const money = (v: string | number) =>
  Number(v || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** The same split the server does, for immediate feedback while typing.
 *
 * The server stays the authority — the invoice is always priced from its
 * figures, never from these — so this exists only so the box you tick shows its
 * effect before you save. Kept in the same shape as ProjectSpec.base_amount so
 * the two cannot drift apart unnoticed. */
function split(price: number, rate: number, inclusive: boolean) {
  if (!inclusive) {
    const tax = Math.round(price * rate) / 100;
    return { base: price, tax, total: price + tax };
  }
  const base = Math.round((price / (1 + rate / 100)) * 100) / 100;
  return { base, tax: price - base, total: price };
}

const SECTIONS: [string, string][] = [
  ["panels", "Panels"],
  ["inverter", "Inverter"],
  ["structure", "Structure"],
  ["bos", "Balance of System"],
];

// Only the balance of system is a table. The panels, the inverter and the
// structure are each simply named — "Topcon-Adani, Premier, Waaree" is the whole
// of what the sheet says about the panels — so those three take a name and
// nothing else. Mirrors SectionedSpecLine.NAMED_ONLY on the server.
const NAMED_ONLY = new Set(["panels", "inverter", "structure"]);

const blankLine = (section: string, position: number): Line =>
  ({ section, item_name: "", brand: "", quantity: "", position });

const inputCls =
  "w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-800 " +
  "placeholder:text-slate-400 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition";
const labelCls = "block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5";

/* ── The editor for one section: three columns, as many rows as needed ── */
function SectionEditor({ section, label, lines, onChange }: {
  section: string; label: string; lines: Line[];
  onChange: (section: string, lines: Line[]) => void;
}) {
  const rows = lines.filter(l => l.section === section);

  const setRow = (i: number, patch: Partial<Line>) =>
    onChange(section, rows.map((r, n) => (n === i ? { ...r, ...patch } : r)));
  const addRow = () => onChange(section, [...rows, blankLine(section, rows.length)]);
  const removeRow = (i: number) =>
    onChange(section, rows.filter((_, n) => n !== i).map((r, n) => ({ ...r, position: n })));

  const namedOnly = NAMED_ONLY.has(section);
  const grid = namedOnly ? "grid-cols-[1fr_32px]" : "sm:grid-cols-[1fr_1fr_180px_32px]";
  const remove = (i: number) => (
    <button type="button" onClick={() => removeRow(i)} title="Remove this line"
      className="justify-self-center text-slate-300 hover:text-rose-500 transition p-1">
      <svg width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2"
        strokeLinecap="round" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12" /></svg>
    </button>
  );

  return (
    <div className="border border-slate-200 rounded-xl overflow-hidden">
      <div className="flex items-center justify-between bg-slate-50 px-4 py-2.5 border-b border-slate-200">
        <h3 className="text-xs font-bold text-slate-700 uppercase tracking-wide">{label}</h3>
        <button type="button" onClick={addRow}
          className="text-[11px] font-bold text-indigo-600 hover:text-indigo-800 transition">
          + Add line
        </button>
      </div>

      {rows.length === 0 ? (
        <p className="px-4 py-4 text-[12px] text-slate-400">
          Nothing here yet — this section is left off the sheet.
        </p>
      ) : (
        <div className="divide-y divide-slate-100">
          {/* Headings once, not per row: repeating the labels down a long
              balance-of-system list made the sheet unreadable. */}
          {!namedOnly && (
            <div className="hidden sm:grid grid-cols-[1fr_1fr_180px_32px] gap-2 px-4 pt-3 pb-1">
              <span className={labelCls}>Item</span>
              <span className={labelCls}>Brand</span>
              <span className={labelCls}>Quantity</span>
              <span />
            </div>
          )}
          {rows.map((r, i) => (
            <div key={i} className={`grid ${grid} gap-2 px-4 py-2.5 items-center`}>
              <input value={r.item_name} onChange={e => setRow(i, { item_name: e.target.value })}
                placeholder={namedOnly
                  ? "e.g. Topcon-Adani, Premier, Waaree"
                  : "e.g. Array Junction Box (DCDB, MCB, SPD)"}
                className={inputCls} />
              {!namedOnly && (
                <>
                  <input value={r.brand} onChange={e => setRow(i, { brand: e.target.value })}
                    placeholder="e.g. MERSEN / L&T / SCHNEIDER" className={inputCls} />
                  {/* Free text, not a number: a real sheet says "1 Each", "36 M"
                      and "50 Sqmm AL Conductor, Earth Pit" in neighbouring rows. */}
                  <input value={r.quantity} onChange={e => setRow(i, { quantity: e.target.value })}
                    placeholder="1 Each · 36 M" className={inputCls} />
                </>
              )}
              {remove(i)}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── The sheet as the customer sees it ── */
export function SpecSheet({ lines }: { lines: Line[] }) {
  const of = (s: string) => lines.filter(l => l.section === s);
  const bos = of("bos");

  const Card = ({ title, rows }: { title: string; rows: Line[] }) => (
    <div className="mb-4">
      <div className="bg-slate-200/70 px-4 py-2 rounded-t-lg">
        <h4 className="font-black text-slate-800 text-sm">{title}</h4>
      </div>
      <div className="border border-t-0 border-slate-200 rounded-b-lg px-4 py-3 bg-white">
        {rows.length === 0 ? (
          <p className="text-[12px] text-slate-400">—</p>
        ) : rows.map((r, i) => (
          <div key={i} className="text-[13px] font-semibold text-slate-700 leading-snug mb-1.5 last:mb-0">
            {r.item_name}
          </div>
        ))}
      </div>
    </div>
  );

  return (
    <div className="grid lg:grid-cols-2 gap-5">
      <div>
        {SECTIONS.filter(([k]) => k !== "bos").map(([k, label]) => (
          <Card key={k} title={label} rows={of(k)} />
        ))}
      </div>
      <div>
        <div className="bg-slate-200/70 px-4 py-2 rounded-t-lg">
          <h4 className="font-black text-slate-800 text-sm text-center">Balance of System</h4>
        </div>
        <div className="border border-t-0 border-slate-200 rounded-b-lg overflow-x-auto bg-white">
          <table className="w-full text-left border-collapse text-[13px]">
            <thead>
              <tr className="border-b border-slate-200 text-slate-500">
                <th className="py-2 px-3 font-semibold">Item</th>
                <th className="py-2 px-3 font-semibold">Brand</th>
                <th className="py-2 px-3 font-semibold">Quantity</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {bos.length === 0 ? (
                <tr><td colSpan={3} className="py-4 px-3 text-slate-400">No balance-of-system lines yet.</td></tr>
              ) : bos.map((r, i) => (
                <tr key={i}>
                  <td className="py-2 px-3 text-slate-800">{r.item_name}</td>
                  <td className="py-2 px-3 text-slate-600">{r.brand || "—"}</td>
                  <td className="py-2 px-3 text-slate-600">{r.quantity || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default function ProjectsPage() {
  const domain = APP_SLUG;
  const router = useRouter();
  const api = getApiBase(domain);

  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [editing, setEditing] = useState<Project | null>(null);   // null = closed
  const [creating, setCreating] = useState(false);
  const [preview, setPreview] = useState<Project | null>(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ name: "", capacity: "", price_dcr: "", price_non_dcr: "", tax_percent: "", notes: "", price_includes_tax: false });
  const [lines, setLines] = useState<Line[]>([]);

  const auth = () => ({ Authorization: `Bearer ${localStorage.getItem(`${domain}_access`)}` });

  const load = useCallback(async () => {
    if (!localStorage.getItem(`${domain}_access`)) { router.push(`/login`); return; }
    try {
      const r = await fetch(`${api}/api/projects/?all=true`, { headers: auth() });
      if (!r.ok) { setError("Failed to load projects."); return; }
      const d = await r.json();
      setProjects(Array.isArray(d) ? d : d.results || []);
    } catch { setError("Network error."); } finally { setLoading(false); }
  }, [api, domain, router]);

  useEffect(() => { load(); }, [load]);

  const openNew = () => {
    setCreating(true); setEditing(null);
    setForm({ name: "", capacity: "", price_dcr: "", price_non_dcr: "", tax_percent: "", notes: "", price_includes_tax: false });
    setLines([]);
  };
  const openEdit = (p: Project) => {
    setCreating(false); setEditing(p);
    setForm({
      name: p.name, capacity: p.capacity || "", notes: p.notes || "",
      price_dcr: Number(p.price_dcr) ? String(Number(p.price_dcr)) : "",
      price_non_dcr: Number(p.price_non_dcr) ? String(Number(p.price_non_dcr)) : "",
      tax_percent: p.tax_percent && Number(p.tax_percent) ? String(Number(p.tax_percent)) : "",
      price_includes_tax: !!p.price_includes_tax,
    });
    setLines((p.lines || []).map(l => ({ ...l })));
  };
  const close = () => { setEditing(null); setCreating(false); };

  // One section's rows are replaced wholesale; the rest are untouched.
  const setSection = (section: string, rows: Line[]) =>
    setLines([...lines.filter(l => l.section !== section), ...rows]);

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim()) return;
    setSaving(true);
    // Blank rows are dropped rather than saved empty: an "add line" the user
    // thought better of should not reach the customer's sheet.
    const payload = {
      ...form,
      price_dcr: form.price_dcr || 0,
      price_non_dcr: form.price_non_dcr || 0,
      tax_percent: form.tax_percent || 0,
      lines: SECTIONS.flatMap(([k]) =>
        lines.filter(l => l.section === k && l.item_name.trim())
          .map((l, i) => ({ ...l, position: i }))),
    };
    const url = editing ? `${api}/api/projects/${editing.id}/` : `${api}/api/projects/`;
    try {
      const r = await fetch(url, {
        method: editing ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json", ...auth() },
        body: JSON.stringify(payload),
      });
      if (!r.ok) { const d = await r.json().catch(() => ({})); alert(d.detail || "Could not save this project."); return; }
      close(); await load();
    } catch { alert("Network error — nothing was saved."); }
    finally { setSaving(false); }
  };

  const duplicate = async (p: Project) => {
    try {
      const r = await fetch(`${api}/api/projects/${p.id}/duplicate/`, { method: "POST", headers: auth() });
      if (r.ok) await load(); else alert("Could not duplicate this project.");
    } catch { alert("Network error."); }
  };

  const remove = async (p: Project) => {
    const used = p.quoted_count > 0
      ? `\n\nIt is named on ${p.quoted_count} proforma invoice${p.quoted_count === 1 ? "" : "s"}. Those keep the specification they were issued with.`
      : "";
    if (!window.confirm(`Delete "${p.name}"?${used}`)) return;
    try {
      const r = await fetch(`${api}/api/projects/${p.id}/`, { method: "DELETE", headers: auth() });
      if (r.ok || r.status === 204) await load(); else alert("Could not delete this project.");
    } catch { alert("Network error."); }
  };

  if (loading) return (
    <div className="max-w-6xl mx-auto p-8">
      <div className="animate-pulse space-y-4">
        <div className="h-8 w-48 bg-slate-200 rounded" />
        <div className="h-64 bg-slate-200 rounded-2xl" />
      </div>
    </div>
  );

  const open = creating || editing !== null;

  return (
    <div className="max-w-6xl mx-auto p-4 sm:p-6 lg:p-8">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Project</h1>
          <p className="text-sm text-slate-500 mt-1">
            Bundles of products — panels, inverter, structure and balance of system.
            Pick one on a proforma invoice and its specification is copied across.
          </p>
        </div>
        <button onClick={openNew}
          className="bg-indigo-600 hover:bg-indigo-700 text-white px-5 py-2.5 rounded-xl text-sm font-semibold transition-colors flex items-center gap-2 shadow-sm">
          <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14" /></svg>
          New Project
        </button>
      </div>

      {error && <div className="mb-6 p-4 bg-red-50 text-red-600 rounded-xl text-sm border border-red-100">{error}</div>}

      <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse min-w-[720px]">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200 text-xs uppercase tracking-wider text-slate-500 font-semibold">
                <th className="py-4 px-6">Project</th>
                <th className="py-4 px-6">Capacity</th>
                <th className="py-4 px-6 text-right">Price</th>
                <th className="py-4 px-6 text-center">Items</th>
                <th className="py-4 px-6 text-center">Quoted on</th>
                <th className="py-4 px-6 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {projects.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-12 text-center text-slate-500">
                    <p className="font-medium text-slate-900">No projects yet</p>
                    <p className="text-sm mt-1">Create one, and it becomes selectable on every proforma invoice.</p>
                  </td>
                </tr>
              ) : projects.map(p => (
                <tr key={p.id} className="hover:bg-slate-50/50 transition-colors">
                  <td className="py-4 px-6">
                    <span className="font-medium text-slate-900">{p.name}</span>
                    {!p.is_active && <span className="ml-2 text-[10px] font-bold uppercase text-slate-400">Retired</span>}
                  </td>
                  <td className="py-4 px-6 text-slate-600">{p.capacity || "—"}</td>
                  <td className="py-4 px-6 text-right whitespace-nowrap">
                    {VARIANTS.some(([k]) => Number(p.pricing?.[k]?.price)) ? (
                      VARIANTS.map(([k, label]) => Number(p.pricing?.[k]?.price) ? (
                        <span key={k} className="block text-[12px]">
                          <span className="text-slate-400 mr-2">{label}</span>
                          <span className="text-slate-900 font-medium">₹{money(p.pricing[k].total)}</span>
                        </span>
                      ) : null)
                    ) : <span className="text-slate-400">—</span>}
                    {Number(p.tax_percent) > 0 && (
                      <span className="block text-[10px] text-slate-400 mt-0.5">
                        {p.price_includes_tax ? "incl." : "plus"} {Number(p.tax_percent)}% tax
                      </span>
                    )}
                  </td>
                  <td className="py-4 px-6 text-center text-slate-600">{p.line_count}</td>
                  <td className="py-4 px-6 text-center text-slate-400">{p.quoted_count || "—"}</td>
                  <td className="py-4 px-6 text-right whitespace-nowrap">
                    <button onClick={() => setPreview(p)} className="text-slate-500 hover:text-slate-800 text-sm font-medium mr-4">View</button>
                    <button onClick={() => openEdit(p)} className="text-indigo-600 hover:text-indigo-900 text-sm font-medium mr-4">Edit</button>
                    <button onClick={() => duplicate(p)} className="text-slate-500 hover:text-slate-800 text-sm font-medium mr-4">Duplicate</button>
                    <button onClick={() => remove(p)} className="text-rose-600 hover:text-rose-900 text-sm font-medium">Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* ── Editor ── */}
      {open && (
        <div className="fixed inset-0 bg-slate-900/40 flex items-start justify-center p-4 z-50 overflow-y-auto">
          <form onSubmit={save} className="bg-white rounded-2xl shadow-xl w-full max-w-4xl my-8">
            <div className="px-6 py-5 border-b border-slate-100">
              <h2 className="text-lg font-bold text-slate-900">
                {editing ? "Edit project" : "New project"}
              </h2>
              <p className="text-[12px] text-slate-400 mt-0.5">
                {editing && editing.quoted_count > 0
                  ? `Quoted on ${editing.quoted_count} proforma${editing.quoted_count === 1 ? "" : "s"} — those keep the specification they were issued with.`
                  : "The four sections always appear on the sheet, in this order."}
              </p>
            </div>

            <div className="px-6 py-5 space-y-5">
              <div className="grid sm:grid-cols-2 gap-4">
                <div>
                  <label className={labelCls}>Project name</label>
                  <input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}
                    placeholder="5kW Single Phase On-Grid" required className={inputCls} />
                </div>
                <div>
                  <label className={labelCls}>Capacity</label>
                  <input value={form.capacity} onChange={e => setForm({ ...form, capacity: e.target.value })}
                    placeholder="5kVA Single Phase" className={inputCls} />
                </div>
              </div>

              {/* ── What the package sells for ── */}
              <div className="border border-slate-200 rounded-xl px-4 py-4">
                <div className="grid sm:grid-cols-[1fr_1fr_120px] gap-4">
                  <div>
                    <label className={labelCls}>DCR price (₹)</label>
                    <input type="number" min="0" step="0.01" value={form.price_dcr}
                      onChange={e => setForm({ ...form, price_dcr: e.target.value })}
                      placeholder="200000" className={inputCls} />
                  </div>
                  <div>
                    <label className={labelCls}>Non-DCR price (₹)</label>
                    <input type="number" min="0" step="0.01" value={form.price_non_dcr}
                      onChange={e => setForm({ ...form, price_non_dcr: e.target.value })}
                      placeholder="180000" className={inputCls} />
                  </div>
                  <div>
                    <label className={labelCls}>Tax %</label>
                    <input type="number" min="0" step="0.01" value={form.tax_percent}
                      onChange={e => setForm({ ...form, tax_percent: e.target.value })}
                      placeholder="18" className={inputCls} />
                  </div>
                </div>

                <label className="mt-3 flex items-center gap-2.5 cursor-pointer select-none">
                  <input type="checkbox" checked={form.price_includes_tax}
                    onChange={e => setForm({ ...form, price_includes_tax: e.target.checked })}
                    className="w-4 h-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500/30" />
                  <span className="text-sm text-slate-700">Price includes tax</span>
                  <span className="text-[11px] text-slate-400">
                    {form.price_includes_tax
                      ? "the price above is the final amount"
                      : "tax is added on top of the price above"}
                  </span>
                </label>

                {(Number(form.price_dcr) > 0 || Number(form.price_non_dcr) > 0) && (
                  <div className="mt-3 pt-3 border-t border-slate-100 space-y-1.5">
                    {VARIANTS.map(([key, label]) => {
                      const typed = Number(key === "dcr" ? form.price_dcr : form.price_non_dcr);
                      if (!(typed > 0)) return null;
                      const s = split(typed, Number(form.tax_percent) || 0, form.price_includes_tax);
                      return (
                        <div key={key} className="flex flex-wrap gap-x-8 gap-y-1 text-[12px]">
                          <span className="font-bold text-slate-600 w-16">{label}</span>
                          <span className="text-slate-500">Base <b className="text-slate-700 ml-1">₹{money(s.base)}</b></span>
                          <span className="text-slate-500">Tax <b className="text-slate-700 ml-1">₹{money(s.tax)}</b></span>
                          <span className="text-slate-500">Customer pays <b className="text-slate-900 ml-1">₹{money(s.total)}</b></span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {SECTIONS.map(([k, label]) => (
                <SectionEditor key={k} section={k} label={label} lines={lines} onChange={setSection} />
              ))}

              <div>
                <label className={labelCls}>Notes</label>
                <textarea value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })}
                  rows={2} placeholder="Anything the team should know about this package."
                  className={inputCls} />
              </div>
            </div>

            <div className="px-6 py-4 border-t border-slate-100 flex justify-end gap-3">
              <button type="button" onClick={close}
                className="px-5 py-2.5 rounded-xl text-sm font-semibold text-slate-600 hover:bg-slate-50 transition">
                Cancel
              </button>
              <button type="submit" disabled={saving}
                className="px-5 py-2.5 rounded-xl bg-indigo-600 text-white text-sm font-semibold hover:bg-indigo-700 disabled:opacity-50 transition">
                {saving ? "Saving…" : editing ? "Save changes" : "Create project"}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* ── The sheet, as it will read ── */}
      {preview && (
        <div className="fixed inset-0 bg-slate-900/40 flex items-start justify-center p-4 z-50 overflow-y-auto"
          onClick={() => setPreview(null)}>
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-5xl my-8" onClick={e => e.stopPropagation()}>
            <div className="px-6 py-5 border-b border-slate-100 flex items-start justify-between gap-4">
              <div>
                <h2 className="text-lg font-bold text-slate-900">{preview.name}</h2>
                {preview.capacity && <p className="text-sm text-slate-500 mt-0.5">{preview.capacity}</p>}
              </div>
              <button onClick={() => setPreview(null)}
                className="text-slate-400 hover:text-slate-700 transition p-1">
                <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2"
                  strokeLinecap="round" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12" /></svg>
              </button>
            </div>
            <div className="px-6 py-6">
              {VARIANTS.some(([k]) => Number(preview.pricing?.[k]?.price)) && (
                <div className="mb-5 border border-slate-200 rounded-xl px-4 py-3 space-y-2">
                  {VARIANTS.map(([k, label]) => Number(preview.pricing?.[k]?.price) ? (
                    <div key={k} className="flex flex-wrap items-baseline gap-x-8 gap-y-1">
                      <span className="text-[12px] font-bold text-slate-600 w-16">{label}</span>
                      <span className="text-[12px] text-slate-500">Base <b className="text-slate-700 ml-1">₹{money(preview.pricing[k].base_amount)}</b></span>
                      {Number(preview.tax_percent) > 0 && (
                        <span className="text-[12px] text-slate-500">
                          Tax @ {Number(preview.tax_percent)}% <b className="text-slate-700 ml-1">₹{money(preview.pricing[k].tax_amount)}</b>
                        </span>
                      )}
                      <span className="text-[13px] text-slate-500 ml-auto">
                        Customer pays <b className="text-slate-900 text-base ml-1">₹{money(preview.pricing[k].total)}</b>
                      </span>
                    </div>
                  ) : null)}
                </div>
              )}
              <SpecSheet lines={preview.lines || []} />
              {preview.notes && (
                <p className="mt-4 text-[12px] text-slate-500 whitespace-pre-wrap">{preview.notes}</p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

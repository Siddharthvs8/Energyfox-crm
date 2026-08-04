"use client";
/**
 * Shared plumbing for the Inventory module's pages (Dashboard, Item Master,
 * Suppliers, Customers, Quotes, Sales / Dispatches, Purchases).
 *
 * The screens deliberately mirror their retail twins (/products, /vendors,
 * /quotes …): page header with an "Add …" button, a search box, a card table with
 * Edit / Delete links, and a centred modal for create and edit. The wholesale
 * *data* stays its own — StockItem's closing stock is derived from movements
 * rather than stored — so only the presentation is shared.
 */
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";

import React, { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";

/* ── Icons ────────────────────────────────────────────────────────────────── */
export const I = {
  Plus: () => <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14" /></svg>,
  X: () => <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12" /></svg>,
  Trash: () => <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><path d="M3 6h18" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" /></svg>,
  Alert: () => <svg width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><path d="m21.7 18-8-14a2 2 0 0 0-3.4 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.7-3z" /><path d="M12 9v4" /><path d="M12 17h.01" /></svg>,
  Check: () => <svg width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" /><path d="m9 12 2 2 4-4" /></svg>,
  Box: () => <svg width="24" height="24" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24"><path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z" /><line x1="7" y1="7" x2="7.01" y2="7" /></svg>,
  // ── Document row actions ──
  Download: () => <svg width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line x1="12" y1="15" x2="12" y2="3" /></svg>,
  Mail: () => <svg width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" /><polyline points="22,6 12,13 2,6" /></svg>,
  WhatsApp: () => <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><path d="M17.47 14.38c-.29-.15-1.71-.84-1.97-.94-.26-.1-.46-.15-.65.14-.19.29-.75.94-.92 1.13-.17.19-.34.21-.63.07-.29-.15-1.22-.45-2.33-1.44-.86-.77-1.44-1.72-1.61-2.01-.17-.29-.02-.44.13-.59.13-.13.29-.34.44-.51.15-.17.19-.29.29-.48.1-.19.05-.36-.02-.51-.07-.15-.65-1.57-.89-2.15-.24-.56-.48-.49-.65-.5-.17-.01-.36-.01-.56-.01-.19 0-.51.07-.78.36-.27.29-1.02 1-1.02 2.42 0 1.43 1.04 2.81 1.19 3 .15.19 2.05 3.13 4.97 4.39.69.3 1.23.48 1.65.61.69.22 1.32.19 1.82.12.56-.08 1.71-.7 1.95-1.37.24-.67.24-1.25.17-1.37-.07-.12-.26-.19-.55-.34z" /><path d="M20.52 3.44A11.86 11.86 0 0012.05 0C5.5 0 .18 5.31.17 11.85c0 2.09.55 4.13 1.59 5.93L0 24l6.38-1.67a11.87 11.87 0 005.67 1.44h.01c6.55 0 11.87-5.31 11.87-11.85 0-3.17-1.23-6.15-3.41-8.48zM12.06 21.2h-.01a9.86 9.86 0 01-5.02-1.37l-.36-.21-3.79.99 1.01-3.69-.23-.38a9.82 9.82 0 01-1.51-5.24c0-5.44 4.43-9.86 9.9-9.86 2.64 0 5.13 1.03 7 2.9a9.82 9.82 0 012.9 6.97c0 5.44-4.43 9.86-9.89 9.86z" /></svg>,
  Edit: () => <svg width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" /><path d="M18.5 2.5a2.12 2.12 0 0 1 3 3L12 15l-4 1 1-4z" /></svg>,
  Truck: () => <svg width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><path d="M14 18V6a2 2 0 0 0-2-2H3a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h2" /><path d="M14 9h4l4 4v4a1 1 0 0 1-1 1h-1" /><circle cx="7" cy="18" r="2" /><circle cx="17" cy="18" r="2" /></svg>,
};

export const CATS = ["Solar Panel", "Inverter", "Battery", "Mounting Structure", "Cable", "BOS Accessory", "Other"];

/** Money. Shows paise only when there are any, so ₹90,000 stays clean while
 *  ₹2,252.25 keeps its fraction instead of being rounded to ₹2,252. */
export const rupee = (n: any) => {
  const v = Number(n || 0);
  return "₹" + v.toLocaleString("en-IN", {
    minimumFractionDigits: Number.isInteger(v) ? 0 : 2,
    maximumFractionDigits: 2,
  });
};
export const num = (n: any) => Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 });
export const todayISO = () => new Date().toISOString().slice(0, 10);

/** Modal input + label, matching /products and /vendors. */
export const FIELD = "w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none transition";
export const LABEL = "block text-sm font-semibold text-slate-700 mb-1.5";

/* ── Data ─────────────────────────────────────────────────────────────────── */

/** Collections a page can ask for, mapped to their REST paths. */
const SOURCES: Record<string, string> = {
  summary: "stock-summary",
  items: "stock-items",
  receipts: "goods-receipts",
  dispatches: "stock-dispatches",
  suppliers: "vendors",
  customers: "stock-customers",
  quotes: "stock-quotes",
  purchaseOrders: "stock-purchase-orders",
};

const asArray = (d: any) => (Array.isArray(d) ? d : d?.results || []);

/** Pull a readable message out of whatever the API returned. */
const explain = async (r: Response, fallback: string) => {
  try {
    const e = await r.json();
    return e.error || e.detail || Object.values(e).flat().join("\n") || fallback;
  } catch { return fallback; }
};

export function useStock(want: (keyof typeof SOURCES)[]) {
  const domain = APP_SLUG;
  const api = getApiBase(domain);
  const router = useRouter();

  const [data, setData] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(true);
  const [denied, setDenied] = useState(false);

  const token = () => localStorage.getItem(`${domain}_access`);
  const key = want.join(",");

  const load = useCallback(async () => {
    if (!token()) { router.push(`/login`); return; }
    const names = key.split(",") as (keyof typeof SOURCES)[];
    try {
      const h = { Authorization: `Bearer ${token()}` };
      const res = await Promise.all(names.map(n => fetch(`${api}/api/${SOURCES[n]}/`, { headers: h })));
      if (res.some(r => r.status === 403)) { setDenied(true); return; }
      const next: Record<string, any> = {};
      for (let i = 0; i < names.length; i++) {
        if (!res[i].ok) continue;
        const body = await res[i].json();
        next[names[i]] = names[i] === "summary" ? body : asArray(body);
      }
      setData(next);
    } catch { /* keep what we had */ } finally { setLoading(false); }
  }, [api, key]);

  useEffect(() => { load(); }, [load]);

  const authJson = () => ({ "Content-Type": "application/json", Authorization: `Bearer ${token()}` });

  /** Create when `id` is absent, update when present.
   *
   *  Returns the saved row on success and false on refusal — callers that only
   *  check truthiness are unaffected, and the ones that need what the server
   *  assigned (a document number, say) can read it. */
  const save = async (source: keyof typeof SOURCES, body: any, id?: number | null) => {
    const url = id ? `${api}/api/${SOURCES[source]}/${id}/` : `${api}/api/${SOURCES[source]}/`;
    const r = await fetch(url, { method: id ? "PATCH" : "POST", headers: authJson(), body: JSON.stringify(body) });
    if (!r.ok) { alert(await explain(r, "Could not save.")); return false; }
    const saved = await r.json().catch(() => true);
    load();
    return saved;
  };

  /** `ask` overrides the confirmation when the consequences need spelling out. */
  const remove = async (source: keyof typeof SOURCES, id: number, label: string, ask?: string) => {
    if (!confirm(ask || `Delete this ${label}?`)) return;
    const r = await fetch(`${api}/api/${SOURCES[source]}/${id}/`, { method: "DELETE", headers: authJson() });
    if (!r.ok) { alert(await explain(r, "Could not delete.")); return; }
    load();
  };

  /** POST to an action endpoint (e.g. a quote's convert) and refresh. */
  const act = async (path: string, body?: any) => {
    const r = await fetch(`${api}/api/${path}/`, {
      method: "POST", headers: authJson(), body: JSON.stringify(body || {}),
    });
    if (!r.ok) { alert(await explain(r, "That action could not be completed.")); return null; }
    const d = await r.json().catch(() => ({}));
    load();
    return d;
  };

  return { ...data, loading, denied, save, remove, act, reload: load } as any;
}

/* ── Page frame ───────────────────────────────────────────────────────────── */

export function StockPage({ title, subtitle, action, loading, denied, children }: {
  title: string; subtitle: React.ReactNode; action?: React.ReactNode;
  loading?: boolean; denied?: boolean; children: React.ReactNode;
}) {
  if (loading) return (
    <div className="p-8 flex items-center justify-center h-full">
      <div className="w-8 h-8 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
    </div>
  );

  if (denied) return (
    <div className="max-w-2xl mx-auto p-8">
      <div className="bg-white border border-slate-200 rounded-2xl p-8 text-center">
        <div className="w-12 h-12 mx-auto rounded-xl bg-amber-50 text-amber-600 flex items-center justify-center mb-3"><I.Alert /></div>
        <h1 className="text-lg font-bold text-slate-900">{title}</h1>
        <p className="text-sm text-slate-500 mt-1">Inventory is for admins, general managers and purchase staff.</p>
      </div>
    </div>
  );

  return (
    <div className="max-w-6xl mx-auto p-4 sm:p-6 lg:p-8">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">{title}</h1>
          <p className="text-sm text-slate-500 mt-1">{subtitle}</p>
        </div>
        {action}
      </div>
      {children}
    </div>
  );
}

/** The header's primary button, e.g. "Add Item". */
export function AddButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button onClick={onClick}
      className="bg-indigo-600 hover:bg-indigo-700 text-white px-5 py-2.5 rounded-xl text-sm font-semibold transition-colors flex items-center gap-2 shadow-sm flex-shrink-0">
      <I.Plus /> {label}
    </button>
  );
}

export function SearchBar({ value, onChange, placeholder }: {
  value: string; onChange: (v: string) => void; placeholder: string;
}) {
  return (
    <div className="mb-4 relative max-w-sm">
      <svg className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8" /><path d="M21 21l-4.35-4.35" /></svg>
      <input value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder}
        className="w-full bg-white border border-slate-200 rounded-xl pl-9 pr-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition" />
    </div>
  );
}

/** Centred dialog, the same shell the retail pages use for create/edit. */
export function Modal({ show, title, onClose, onSubmit, saving, submitLabel, wide, xl, children }: {
  show: boolean; title: string; onClose: () => void; onSubmit: (e: React.FormEvent) => void;
  // `xl` is for forms with a wide line table — a purchase order's row carries
  // seven fields, and they are unreadable squeezed into the standard width.
  saving?: boolean; submitLabel: string; wide?: boolean; xl?: boolean; children: React.ReactNode;
}) {
  if (!show) return null;
  const width = xl ? "max-w-6xl" : wide ? "max-w-3xl" : "max-w-lg";
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center px-4">
      <div className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm" onClick={onClose} />
      <div className={`bg-white rounded-2xl shadow-xl w-full ${width} relative z-10 overflow-hidden max-h-[92vh] flex flex-col`}>
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between flex-shrink-0">
          <h3 className="font-bold text-lg text-slate-900">{title}</h3>
          <button type="button" onClick={onClose} className="text-slate-400 hover:text-slate-600"><I.X /></button>
        </div>
        <form onSubmit={onSubmit} className="p-6 overflow-y-auto">
          <div className="space-y-4 mb-6">{children}</div>
          <div className="flex gap-3">
            <button type="button" onClick={onClose}
              className="flex-1 px-4 py-2.5 text-slate-600 font-medium hover:bg-slate-50 rounded-xl transition-colors">
              Cancel
            </button>
            <button type="submit" disabled={saving}
              className="flex-1 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-2.5 rounded-xl transition shadow-sm disabled:opacity-50">
              {saving ? "Saving..." : submitLabel}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export function Fld({ label, children }: { label: string; children: React.ReactNode }) {
  return <div><label className={LABEL}>{label}</label>{children}</div>;
}

/** Field row inside a modal — two-up or three-up, stacking on mobile. */
export function Row({ cols = 2, children }: { cols?: 2 | 3; children: React.ReactNode }) {
  return (
    <div className={`grid grid-cols-1 gap-4 ${cols === 3 ? "sm:grid-cols-3" : "sm:grid-cols-2"}`}>
      {children}
    </div>
  );
}

/** Edit / Delete text links, as the retail tables use. */
export function RowActions({ onEdit, onDelete }: { onEdit?: () => void; onDelete?: () => void }) {
  return (
    <span className="whitespace-nowrap">
      {onEdit && <button onClick={onEdit} className="text-indigo-600 hover:text-indigo-900 text-sm font-medium mr-4">Edit</button>}
      {onDelete && <button onClick={onDelete} className="text-rose-600 hover:text-rose-900 text-sm font-medium">Delete</button>}
    </span>
  );
}

/**
 * The action set on a document row — download, send, edit, delete.
 *
 * Icons rather than words: the three document tables carry five actions each,
 * and spelled out they crowded the row off the side of the table. Every button
 * keeps a title so the meaning is still one hover away.
 *
 * The wrapper stops clicks reaching the row, which opens the preview.
 */
export function DocActions({ busy, onDownload, onEmail, onWhatsApp, onDispatch, onEdit, onDelete }: {
  busy?: boolean;
  onDownload?: () => void; onEmail?: () => void; onWhatsApp?: () => void;
  onDispatch?: () => void; onEdit?: () => void; onDelete?: () => void;
}) {
  const btn = "w-8 h-8 inline-flex items-center justify-center rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed";
  return (
    <span className="inline-flex items-center gap-1 whitespace-nowrap" onClick={e => e.stopPropagation()}>
      {onDownload && (
        <button onClick={onDownload} disabled={busy} title="Download PDF" aria-label="Download PDF"
          className={`${btn} text-slate-500 hover:text-indigo-700 hover:bg-indigo-50`}>
          {busy ? <span className="w-3.5 h-3.5 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" /> : <I.Download />}
        </button>
      )}
      {onEmail && (
        <button onClick={onEmail} disabled={busy} title="Send by email" aria-label="Send by email"
          className={`${btn} text-slate-500 hover:text-indigo-700 hover:bg-indigo-50`}><I.Mail /></button>
      )}
      {onWhatsApp && (
        <button onClick={onWhatsApp} disabled={busy} title="Send on WhatsApp" aria-label="Send on WhatsApp"
          className={`${btn} text-emerald-600 hover:text-emerald-800 hover:bg-emerald-50`}><I.WhatsApp /></button>
      )}
      {onDispatch && (
        <button onClick={onDispatch} disabled={busy} title="Dispatch this invoice" aria-label="Dispatch this invoice"
          className={`${btn} text-amber-600 hover:text-amber-800 hover:bg-amber-50`}><I.Truck /></button>
      )}
      {onEdit && (
        <button onClick={onEdit} disabled={busy} title="Edit" aria-label="Edit"
          className={`${btn} text-slate-500 hover:text-slate-900 hover:bg-slate-100`}><I.Edit /></button>
      )}
      {onDelete && (
        <button onClick={onDelete} disabled={busy} title="Delete" aria-label="Delete"
          className={`${btn} text-rose-500 hover:text-rose-700 hover:bg-rose-50`}><I.Trash /></button>
      )}
    </span>
  );
}

export type Col = { label: string; align?: "left" | "right" | "center" };

/** Card table with the retail look: grey header, roomy cells, illustrated empty state. */
export function DataTable({ columns, rows, empty, minWidth = 720, onRowClick, rowTitle }: {
  columns: (string | Col)[]; rows: React.ReactNode[][];
  empty?: { title: string; hint?: string }; minWidth?: number;
  // Opening a row is a read action (a document preview); the buttons inside the
  // Actions cell stop the event so they never trigger it by accident.
  onRowClick?: (index: number) => void; rowTitle?: string;
}) {
  const cols: Col[] = columns.map(c => (typeof c === "string" ? { label: c } : c));
  const align = (a?: string) => (a === "right" ? "text-right" : a === "center" ? "text-center" : "text-left");

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse" style={{ minWidth }}>
          <thead>
            <tr className="bg-slate-50 border-b border-slate-200 text-xs uppercase tracking-wider text-slate-500 font-semibold">
              {cols.map((c, i) => <th key={i} className={`py-4 px-6 ${align(c.align)} whitespace-nowrap`}>{c.label}</th>)}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.length === 0 ? (
              <tr>
                <td colSpan={cols.length} className="py-12 text-center text-slate-500">
                  <div className="mx-auto w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center mb-3 text-slate-400"><I.Box /></div>
                  <p className="font-medium text-slate-900">{empty?.title || "Nothing here yet"}</p>
                  {empty?.hint && <p className="text-sm mt-1">{empty.hint}</p>}
                </td>
              </tr>
            ) : rows.map((row, ri) => (
              <tr key={ri}
                onClick={onRowClick ? () => onRowClick(ri) : undefined}
                title={onRowClick ? rowTitle : undefined}
                className={`hover:bg-slate-50/50 transition-colors ${onRowClick ? "cursor-pointer" : ""}`}>
                {row.map((cell, ci) => (
                  <td key={ci} className={`py-4 px-6 text-sm text-slate-700 ${align(cols[ci]?.align)}`}>{cell}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function Panel({ title, subtitle, children, right }: {
  title: string; subtitle?: string; children: React.ReactNode; right?: React.ReactNode;
}) {
  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-5">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div>
          <h2 className="text-sm font-bold text-slate-900">{title}</h2>
          {subtitle && <p className="text-[11px] text-slate-400 mt-0.5">{subtitle}</p>}
        </div>
        {right}
      </div>
      {children}
    </div>
  );
}

export function Empty({ text }: { text: string }) {
  return <p className="text-sm text-slate-400 text-center py-10">{text}</p>;
}

export function StatusPill({ status }: { status: string }) {
  const ok = status === "OK";
  return (
    <span className={`inline-flex text-[10px] font-bold uppercase tracking-wider px-2 py-1 rounded-full ${
      ok ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700"}`}>{status}</span>
  );
}

/* ── Suppliers / Customers: one whole screen, different columns ───────────── */

export type PartyCol = { key: string; label: string; required?: boolean; placeholder?: string;
                         mono?: boolean; defaultValue?: string; options?: string[] };

export function PartyScreen({ title, subtitle, noun, columns, rows, loading, denied, onSave, onDelete }: {
  title: string; subtitle: string; noun: string; columns: PartyCol[]; rows: any[];
  loading?: boolean; denied?: boolean;
  onSave: (body: any, id?: number | null) => Promise<boolean>;
  onDelete: (id: number) => void;
}) {
  const blank = Object.fromEntries(columns.map(c => [c.key, c.defaultValue ?? ""]));
  const [form, setForm] = useState<any>(blank);
  const [editing, setEditing] = useState<any>(null);
  const [show, setShow] = useState(false);
  const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState("");

  const openCreate = () => { setEditing(null); setForm(blank); setShow(true); };
  const openEdit = (r: any) => {
    setEditing(r);
    setForm(Object.fromEntries(columns.map(c => [c.key, r[c.key] || c.defaultValue || ""])));
    setShow(true);
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!String(form[columns[0].key] || "").trim()) return;
    setSaving(true);
    const ok = await onSave(form, editing?.id);
    setSaving(false);
    if (ok) { setShow(false); setEditing(null); setForm(blank); }
  };

  const term = search.trim().toLowerCase();
  const list: any[] = rows || [];
  const filtered = !term ? list
    : list.filter(r => columns.some(c => String(r[c.key] || "").toLowerCase().includes(term)));

  return (
    <StockPage title={title} subtitle={subtitle} loading={loading} denied={denied}
      action={<AddButton label={`Add ${noun}`} onClick={openCreate} />}>

      <SearchBar value={search} onChange={setSearch} placeholder={`Search ${noun.toLowerCase()}s...`} />

      <DataTable
        columns={[...columns.map(c => c.label), { label: "Actions", align: "right" }]}
        empty={{ title: `No ${noun.toLowerCase()}s found`, hint: `Add a ${noun.toLowerCase()} to get started.` }}
        rows={filtered.map(r => [
          ...columns.map((c, i) => (
            i === 0
              ? <span className="font-semibold text-slate-900">{r[c.key] || "—"}</span>
              : <span className={c.mono ? "font-mono text-xs text-slate-500" : ""}>{r[c.key] || "—"}</span>
          )),
          <RowActions onEdit={() => openEdit(r)} onDelete={() => onDelete(r.id)} />,
        ])} />

      <Modal show={show} title={`${editing ? "Edit" : "Add"} ${noun}`} onClose={() => setShow(false)}
        onSubmit={submit} saving={saving} submitLabel={`Save ${noun}`}>
        {columns.map(c => (
          <Fld key={c.key} label={c.required ? `${c.label} *` : c.label}>
            {c.options ? (
              <select value={form[c.key]} onChange={e => setForm({ ...form, [c.key]: e.target.value })}
                className={FIELD}>
                {c.options.map(o => <option key={o} value={o}>{o}</option>)}
              </select>
            ) : (
              <input required={c.required} value={form[c.key]} placeholder={c.placeholder}
                onChange={e => setForm({ ...form, [c.key]: e.target.value })} className={FIELD} />
            )}
          </Fld>
        ))}
      </Modal>
    </StockPage>
  );
}

/**
 * Preview a generated document without leaving the list.
 *
 * The PDF is built in the browser (the client owns the template), so the
 * preview is that same file shown in an object frame rather than a second
 * rendering that could drift from what downloads. `render` is called when the
 * viewer opens and the blob URL is revoked when it closes, so a long session
 * browsing documents doesn't leak them.
 */
export function DocumentPreview({ open, title, fileName, render, onClose, actions }: {
  open: boolean; title: string; fileName: string;
  render: () => Promise<any | null>;
  onClose: () => void;
  actions?: React.ReactNode;
}) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!open) return;
    let revoked = false;
    let made: string | null = null;
    setUrl(null); setFailed(false);
    (async () => {
      try {
        const doc = await render();
        if (!doc) { setFailed(true); return; }
        made = URL.createObjectURL(doc.output("blob"));
        if (revoked) { URL.revokeObjectURL(made); return; }
        setUrl(made);
      } catch { setFailed(true); }
    })();
    return () => { revoked = true; if (made) URL.revokeObjectURL(made); };
  }, [open]);   // eslint-disable-line react-hooks/exhaustive-deps

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center px-4">
      <div className="absolute inset-0 bg-slate-900/50 backdrop-blur-sm" onClick={onClose} />
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-5xl relative z-10 overflow-hidden max-h-[94vh] flex flex-col">
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between gap-4 flex-shrink-0">
          <div className="min-w-0">
            <h3 className="font-bold text-lg text-slate-900 truncate">{title}</h3>
            <p className="text-xs text-slate-400 truncate">{fileName}</p>
          </div>
          <div className="flex items-center gap-3 flex-shrink-0">
            {actions}
            <button type="button" onClick={onClose} className="text-slate-400 hover:text-slate-600"><I.X /></button>
          </div>
        </div>
        <div className="flex-1 bg-slate-100 min-h-[60vh]">
          {failed ? (
            <div className="h-full flex items-center justify-center text-sm text-slate-500">
              Could not build this document.
            </div>
          ) : !url ? (
            <div className="h-full flex items-center justify-center gap-3 text-sm text-slate-500">
              <span className="w-5 h-5 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
              Rendering…
            </div>
          ) : (
            <object data={url} type="application/pdf" className="w-full h-[74vh]">
              {/* Browsers without an inline PDF viewer still get the file. */}
              <div className="h-full flex flex-col items-center justify-center gap-3 text-sm text-slate-500">
                This browser can&apos;t show PDFs inline.
                <a href={url} download={fileName}
                  className="px-4 py-2 bg-indigo-600 text-white rounded-xl text-xs font-semibold hover:bg-indigo-700">
                  Download instead
                </a>
              </div>
            </object>
          )}
        </div>
      </div>
    </div>
  );
}

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

  /** Create when `id` is absent, update when present. Returns false on refusal. */
  const save = async (source: keyof typeof SOURCES, body: any, id?: number | null) => {
    const url = id ? `${api}/api/${SOURCES[source]}/${id}/` : `${api}/api/${SOURCES[source]}/`;
    const r = await fetch(url, { method: id ? "PATCH" : "POST", headers: authJson(), body: JSON.stringify(body) });
    if (!r.ok) { alert(await explain(r, "Could not save.")); return false; }
    load();
    return true;
  };

  const remove = async (source: keyof typeof SOURCES, id: number, label: string) => {
    if (!confirm(`Delete this ${label}?`)) return;
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
export function Modal({ show, title, onClose, onSubmit, saving, submitLabel, wide, children }: {
  show: boolean; title: string; onClose: () => void; onSubmit: (e: React.FormEvent) => void;
  saving?: boolean; submitLabel: string; wide?: boolean; children: React.ReactNode;
}) {
  if (!show) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center px-4">
      <div className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm" onClick={onClose} />
      <div className={`bg-white rounded-2xl shadow-xl w-full ${wide ? "max-w-3xl" : "max-w-lg"} relative z-10 overflow-hidden max-h-[92vh] flex flex-col`}>
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

export type Col = { label: string; align?: "left" | "right" | "center" };

/** Card table with the retail look: grey header, roomy cells, illustrated empty state. */
export function DataTable({ columns, rows, empty, minWidth = 720 }: {
  columns: (string | Col)[]; rows: React.ReactNode[][];
  empty?: { title: string; hint?: string }; minWidth?: number;
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
              <tr key={ri} className="hover:bg-slate-50/50 transition-colors">
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

/* ── Purchases / Dispatches: one screen, the arrow reversed ───────────────── */

export function MovementScreen({ kind, rows, items, parties, loading, denied, onSave, onDelete }: {
  kind: "receipt" | "dispatch"; rows: any[]; items: any[]; parties: any[];
  loading?: boolean; denied?: boolean;
  onSave: (body: any, id?: number | null) => Promise<boolean>;
  onDelete: (id: number) => void;
}) {
  const isReceipt = kind === "receipt";
  const refKey = isReceipt ? "grn_no" : "invoice_no";
  const partyKey = isReceipt ? "supplier" : "customer";

  const blank = {
    [refKey]: "", date: todayISO(), [partyKey]: "", item: "",
    quantity: "", rate: "", tax_percent: "", site: "", notes: "",
  } as any;

  const [form, setForm] = useState<any>(blank);
  const [editing, setEditing] = useState<any>(null);
  const [show, setShow] = useState(false);
  const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState("");

  const itemList: any[] = items || [];
  const partyList: any[] = parties || [];
  const list: any[] = rows || [];

  const openCreate = () => { setEditing(null); setForm({ ...blank }); setShow(true); };
  const openEdit = (r: any) => {
    setEditing(r);
    setForm({
      [refKey]: r[refKey] || "", date: r.date || todayISO(),
      [partyKey]: r[partyKey] || "", item: r.item || "",
      quantity: r.quantity ?? "", rate: r.rate ?? "", tax_percent: r.tax_percent ?? "",
      site: r.site || "", notes: r.notes || "",
    });
    setShow(true);
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.item || !form.quantity) return;
    setSaving(true);
    const body: any = { ...form, [partyKey]: form[partyKey] || null, rate: form.rate || 0 };
    if (isReceipt) delete body.tax_percent;      // receipts carry no tax
    else body.tax_percent = form.tax_percent || 0;
    const ok = await onSave(body, editing?.id);
    setSaving(false);
    if (ok) { setShow(false); setEditing(null); setForm({ ...blank }); }
  };

  const term = search.trim().toLowerCase();
  const filtered = !term ? list : list.filter(r =>
    `${r[refKey] || ""} ${r.item_code || ""} ${r.item_label || ""} ${(isReceipt ? r.supplier_name : r.customer_name) || ""}`
      .toLowerCase().includes(term));

  const noun = isReceipt ? "Receipt" : "Dispatch";

  // Live totals for the modal, mirroring the server: goods value, then tax on top.
  const goodsValue = (Number(form.quantity) || 0) * (Number(form.rate) || 0);
  const taxValue = goodsValue * (Number(form.tax_percent) || 0) / 100;
  const lineTotal = goodsValue + taxValue;

  return (
    <StockPage
      title={isReceipt ? "Purchases" : "Sales / Dispatches"}
      subtitle={isReceipt
        ? "Every stock receipt from a supplier (GRN)."
        : "Every outward delivery to a customer or project site."}
      loading={loading} denied={denied}
      action={itemList.length > 0 ? <AddButton label={`New ${noun}`} onClick={openCreate} /> : undefined}>

      {itemList.length === 0 ? (
        <DataTable columns={["Item"]} rows={[]}
          empty={{ title: "No items yet", hint: "Add an item in Item Master first — every movement is logged against one." }} />
      ) : (
        <>
          <SearchBar value={search} onChange={setSearch}
            placeholder={isReceipt ? "Search receipts..." : "Search dispatches..."} />

          <DataTable
            columns={[
              isReceipt ? "GRN" : "Invoice", "Date", isReceipt ? "Supplier" : "Customer", "Item",
              { label: "Qty", align: "right" }, { label: "Rate", align: "right" },
              { label: "Amount", align: "right" },
              ...(isReceipt ? [] : [{ label: "Tax", align: "right" as const },
                                    { label: "Total", align: "right" as const }]),
              "Logged by", { label: "Actions", align: "right" },
            ]}
            minWidth={isReceipt ? 980 : 1140}
            empty={{ title: `No ${noun.toLowerCase()}s yet`, hint: `Record your first ${noun.toLowerCase()}.` }}
            rows={filtered.map(r => [
              <span className="font-mono font-semibold text-slate-900">{r[refKey] || "—"}</span>,
              <span className="font-mono text-xs text-slate-500">{r.date}</span>,
              (isReceipt ? r.supplier_name : r.customer_name) || "—",
              <span><span className="font-mono text-xs">{r.item_code}</span> <span className="text-slate-400">— {r.item_label}</span></span>,
              <span className="tabular-nums font-semibold">{num(r.quantity)}</span>,
              <span className="tabular-nums">{rupee(r.rate)}</span>,
              <span className="tabular-nums">{rupee(r.amount)}</span>,
              ...(isReceipt ? [] : [
                <span className="tabular-nums text-slate-500">
                  {Number(r.tax_percent || 0) > 0
                    ? <>{num(r.tax_percent)}% <span className="text-slate-400">· {rupee(r.tax_amount)}</span></>
                    : "—"}
                </span>,
                <span className="tabular-nums font-semibold">{rupee(r.total)}</span>,
              ]),
              <span className="text-xs text-slate-400">{r.created_by_name || "—"}</span>,
              <RowActions onEdit={() => openEdit(r)} onDelete={() => onDelete(r.id)} />,
            ])} />
        </>
      )}

      <Modal show={show} title={`${editing ? "Edit" : "New"} ${noun}`} onClose={() => setShow(false)}
        onSubmit={submit} saving={saving} submitLabel={`Save ${noun}`}>
        <Row>
          <Fld label={isReceipt ? "GRN No." : "Invoice No."}>
            <input value={form[refKey]} onChange={e => setForm({ ...form, [refKey]: e.target.value })}
              className={`${FIELD} font-mono`} placeholder={isReceipt ? "GRN-0001" : "INV-S001"} />
          </Fld>
          <Fld label="Date *">
            <input type="date" required value={form.date}
              onChange={e => setForm({ ...form, date: e.target.value })} className={FIELD} />
          </Fld>
        </Row>
        <Row>
          <Fld label={isReceipt ? "Supplier" : "Customer"}>
            <select value={form[partyKey]} onChange={e => setForm({ ...form, [partyKey]: e.target.value })} className={FIELD}>
              <option value="">—</option>
              {partyList.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </Fld>
          <Fld label="Item *">
            <select required value={form.item} onChange={e => setForm({ ...form, item: e.target.value })} className={FIELD}>
              <option value="">Select item…</option>
              {itemList.map(i => <option key={i.id} value={i.id}>{i.code} — {`${i.brand} ${i.model_name}`.trim()}</option>)}
            </select>
          </Fld>
        </Row>
        <Row>
          <Fld label={isReceipt ? "Qty Received *" : "Qty Dispatched *"}>
            <input type="number" step="any" min="0" required value={form.quantity}
              onChange={e => setForm({ ...form, quantity: e.target.value })} className={FIELD} />
          </Fld>
          <Fld label="Unit Rate (₹)">
            <input type="number" step="any" min="0" value={form.rate}
              onChange={e => setForm({ ...form, rate: e.target.value })} className={FIELD} />
          </Fld>
        </Row>
        {!isReceipt && (
          <>
            <Row>
              <Fld label="Tax %">
                <input type="number" step="any" min="0" max="100" value={form.tax_percent}
                  onChange={e => setForm({ ...form, tax_percent: e.target.value })}
                  className={FIELD} placeholder="e.g. 18" />
              </Fld>
              <Fld label="Total">
                {/* Read-only preview so the invoiced figure is visible while typing. */}
                <div className={`${FIELD} bg-slate-100 text-slate-700 font-semibold tabular-nums`}>
                  {rupee(lineTotal)}
                  {taxValue > 0 && (
                    <span className="font-normal text-slate-400"> (incl. {rupee(taxValue)} tax)</span>
                  )}
                </div>
              </Fld>
            </Row>
            <Fld label="Site Address">
              <input value={form.site} onChange={e => setForm({ ...form, site: e.target.value })} className={FIELD} />
            </Fld>
          </>
        )}
        <Fld label="Notes">
          <textarea rows={2} value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} className={FIELD} />
        </Fld>
      </Modal>
    </StockPage>
  );
}

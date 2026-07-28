"use client";
/**
 * Shared plumbing for the Inventory module's pages (Dashboard, Item Master,
 * Suppliers, Customers, Quotes, Sales / Dispatches, Purchases). Each page is a
 * thin shell over `useStock`, which loads only the collections it needs.
 */
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";

import React, { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";

/* ── Icons (inline, matching the rest of the app) ─────────────────────────── */
export const I = {
  Plus: () => <svg width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14" /></svg>,
  Trash: () => <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><path d="M3 6h18" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" /></svg>,
  Alert: () => <svg width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><path d="m21.7 18-8-14a2 2 0 0 0-3.4 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.7-3z" /><path d="M12 9v4" /><path d="M12 17h.01" /></svg>,
  Check: () => <svg width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" /><path d="m9 12 2 2 4-4" /></svg>,
  Search: () => <svg width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" /></svg>,
};

export const CATS = ["Solar Panel", "Inverter", "Battery", "Mounting Structure", "Cable", "BOS Accessory", "Other"];

export const rupee = (n: any) => "₹" + Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 });
export const num = (n: any) => Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 });
export const todayISO = () => new Date().toISOString().slice(0, 10);

export const FIELD = "w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition";

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
    } catch {} finally { setLoading(false); }
  }, [api, key]);

  useEffect(() => { load(); }, [load]);

  const authJson = () => ({ "Content-Type": "application/json", Authorization: `Bearer ${token()}` });

  /** POST a new row; returns false (and explains) when the API refuses. */
  const create = async (source: keyof typeof SOURCES, body: any) => {
    const r = await fetch(`${api}/api/${SOURCES[source]}/`, { method: "POST", headers: authJson(), body: JSON.stringify(body) });
    if (!r.ok) {
      const e = await r.json().catch(() => ({}));
      alert(e.error || e.detail || Object.values(e).flat().join("\n") || "Could not save.");
      return false;
    }
    load();
    return true;
  };

  const remove = async (source: keyof typeof SOURCES, id: number, label: string) => {
    if (!confirm(`Delete this ${label}?`)) return;
    const r = await fetch(`${api}/api/${SOURCES[source]}/${id}/`, { method: "DELETE", headers: authJson() });
    if (!r.ok) {
      const e = await r.json().catch(() => ({}));
      alert(e.error || e.detail || "Could not delete.");
      return;
    }
    load();
  };

  /** POST to an action endpoint (e.g. a quote's convert) and refresh. Returns the
   *  response body on success, null when the API refuses. */
  const act = async (path: string, body?: any) => {
    const r = await fetch(`${api}/api/${path}/`, {
      method: "POST", headers: authJson(), body: JSON.stringify(body || {}),
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) { alert(d.error || d.detail || "That action could not be completed."); return null; }
    load();
    return d;
  };

  return { ...data, loading, denied, create, remove, act, reload: load } as any;
}

/* ── Page frame ───────────────────────────────────────────────────────────── */

export function StockPage({ title, subtitle, loading, denied, children }: {
  title: string; subtitle: string; loading?: boolean; denied?: boolean; children: React.ReactNode;
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
    <div className="max-w-7xl mx-auto p-4 sm:p-6 lg:p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">{title}</h1>
        <p className="text-sm text-slate-500 mt-1">{subtitle}</p>
      </div>
      {children}
    </div>
  );
}

/* ── Shared UI bits ───────────────────────────────────────────────────────── */

export function Panel({ title, children, right }: { title: string; children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-5">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-bold text-slate-900">{title}</h2>
        {right}
      </div>
      {children}
    </div>
  );
}

export function Empty({ text }: { text: string }) {
  return <p className="text-sm text-slate-400 text-center py-10">{text}</p>;
}

export function FormPanel({ title, children, onSubmit, saving, action }: any) {
  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-5 mb-5">
      <h2 className="text-sm font-bold text-slate-900 mb-3">{title}</h2>
      <form onSubmit={onSubmit} className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3 items-end">
        {children}
        <button type="submit" disabled={saving}
          className="flex items-center justify-center gap-1.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white rounded-xl px-4 h-[38px] text-sm font-semibold transition-colors shadow-sm">
          <I.Plus /> {saving ? "Saving…" : action}
        </button>
      </form>
    </div>
  );
}

export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="block"><span className="block text-[11px] font-semibold text-slate-500 mb-1">{label}</span>{children}</label>;
}

export function StatusPill({ status }: { status: string }) {
  const ok = status === "OK";
  return (
    <span className={`inline-flex text-[10px] font-bold uppercase tracking-wider px-2 py-1 rounded-full ${
      ok ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700"}`}>{status}</span>
  );
}

export function DeleteBtn({ onClick }: { onClick: () => void }) {
  return (
    <button onClick={onClick} aria-label="Delete"
      className="w-7 h-7 flex items-center justify-center rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-all">
      <I.Trash />
    </button>
  );
}

export function Table({ columns, rows }: { columns: string[]; rows: React.ReactNode[][] }) {
  return (
    <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-200">
              {columns.map((c, i) => (
                <th key={i} className="py-3 px-4 text-[10px] font-bold uppercase tracking-wider text-slate-500 whitespace-nowrap">{c}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {rows.length === 0 ? (
              <tr><td colSpan={columns.length} className="py-12 text-center text-sm text-slate-400">Nothing logged yet.</td></tr>
            ) : rows.map((row, ri) => (
              <tr key={ri} className="hover:bg-slate-50/60 transition-colors">
                {row.map((cell, ci) => (
                  <td key={ci} className="py-3 px-4 text-[13px] text-slate-700 whitespace-nowrap">{cell}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ── Purchases and Dispatch are the same screen with the arrow reversed ───── */

export function MovementPage({ kind, rows, items, parties, onAdd, onDelete }: any) {
  const isReceipt = kind === "receipt";
  const blank = isReceipt
    ? { grn_no: "", date: todayISO(), supplier: "", item: "", quantity: "", rate: "" }
    : { invoice_no: "", date: todayISO(), customer: "", item: "", quantity: "", rate: "", site: "" };
  const [form, setForm] = useState<any>(blank);
  const [saving, setSaving] = useState(false);

  const partyKey = isReceipt ? "supplier" : "customer";

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.item || !form.quantity) return;
    setSaving(true);
    const ok = await onAdd({ ...form, [partyKey]: form[partyKey] || null, rate: form.rate || 0 });
    setSaving(false);
    if (ok) setForm({ ...blank, date: form.date });
  };

  if ((items || []).length === 0) {
    return <Empty text="Add an item in Item Master first — every movement is logged against one." />;
  }

  return (
    <div>
      <FormPanel title={isReceipt ? "Log a receipt" : "Log a dispatch"} onSubmit={submit} saving={saving}
        action={isReceipt ? "Log receipt" : "Log dispatch"}>
        <Field label={isReceipt ? "GRN no." : "Invoice no."}>
          <input value={isReceipt ? form.grn_no : form.invoice_no}
            onChange={e => setForm({ ...form, [isReceipt ? "grn_no" : "invoice_no"]: e.target.value })}
            className={`${FIELD} font-mono`} placeholder={isReceipt ? "GRN-0001" : "INV-S001"} />
        </Field>
        <Field label="Date"><input type="date" required value={form.date} onChange={e => setForm({ ...form, date: e.target.value })} className={FIELD} /></Field>
        <Field label={isReceipt ? "Supplier" : "Customer"}>
          <select value={form[partyKey]} onChange={e => setForm({ ...form, [partyKey]: e.target.value })} className={FIELD}>
            <option value="">—</option>
            {(parties || []).map((p: any) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </Field>
        <Field label="Item *">
          <select required value={form.item} onChange={e => setForm({ ...form, item: e.target.value })} className={FIELD}>
            <option value="">Select item…</option>
            {items.map((i: any) => <option key={i.id} value={i.id}>{i.code} — {`${i.brand} ${i.model_name}`.trim()}</option>)}
          </select>
        </Field>
        <Field label={isReceipt ? "Qty received *" : "Qty dispatched *"}>
          <input type="number" step="any" required value={form.quantity} onChange={e => setForm({ ...form, quantity: e.target.value })} className={FIELD} />
        </Field>
        <Field label="Unit rate (₹)"><input type="number" step="any" value={form.rate} onChange={e => setForm({ ...form, rate: e.target.value })} className={FIELD} /></Field>
        {!isReceipt && <Field label="Site address"><input value={form.site} onChange={e => setForm({ ...form, site: e.target.value })} className={FIELD} /></Field>}
      </FormPanel>

      <Table columns={[isReceipt ? "GRN" : "Invoice", "Date", isReceipt ? "Supplier" : "Customer", "Item", "Qty", "Rate", "Amount", "Logged by", ""]}
        rows={(rows || []).map((r: any) => [
          <span className="font-mono font-semibold text-slate-800">{(isReceipt ? r.grn_no : r.invoice_no) || "—"}</span>,
          <span className="font-mono text-slate-500">{r.date}</span>,
          (isReceipt ? r.supplier_name : r.customer_name) || "—",
          <span><span className="font-mono">{r.item_code}</span> <span className="text-slate-400">— {r.item_label}</span></span>,
          <span className="tabular-nums font-semibold">{num(r.quantity)}</span>,
          <span className="tabular-nums">{rupee(r.rate)}</span>,
          <span className="tabular-nums font-semibold">{rupee(r.amount)}</span>,
          <span className="text-slate-400 text-xs">{r.created_by_name || "—"}</span>,
          <DeleteBtn onClick={() => onDelete(r.id)} />,
        ])} />
    </div>
  );
}

/* ── Suppliers and Customers are the same screen with different columns ───── */

export function PartyPage({ noun, columns, rows, onAdd, onDelete }: any) {
  const blank = Object.fromEntries(columns.map((c: any) => [c.key, ""]));
  const [form, setForm] = useState<any>(blank);
  const [saving, setSaving] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form[columns[0].key]?.trim()) return;
    setSaving(true);
    const ok = await onAdd(form);
    setSaving(false);
    if (ok) setForm(blank);
  };

  return (
    <div>
      <FormPanel title={`Add ${noun}`} onSubmit={submit} saving={saving} action="Add">
        {columns.map((c: any) => (
          <Field key={c.key} label={c.required ? `${c.label} *` : c.label}>
            <input required={c.required} value={form[c.key]} onChange={e => setForm({ ...form, [c.key]: e.target.value })} className={FIELD} />
          </Field>
        ))}
      </FormPanel>

      <Table columns={[...columns.map((c: any) => c.label), ""]}
        rows={(rows || []).map((r: any) => [
          ...columns.map((c: any) => r[c.key] || "—"),
          <DeleteBtn onClick={() => onDelete(r.id)} />,
        ])} />
    </div>
  );
}

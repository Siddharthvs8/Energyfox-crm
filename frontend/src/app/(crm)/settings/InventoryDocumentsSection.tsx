"use client";
/**
 * Settings → Documents → Inventory Documents.
 *
 * The letterhead, artwork and bank block printed on the inventory documents —
 * the proforma invoice, the dispatch invoice and the purchase order. Retail and
 * wholesale keep their own profile so the two sides can trade under different
 * identities.
 *
 * Every field is optional: what is left blank prints the organisation's own
 * setting instead, which is shown in the box as a placeholder so an empty field
 * never looks like nothing is configured.
 */
import React, { useCallback, useEffect, useState } from "react";
import { getApiBase } from "@/lib/mock-data";

type Side = "b2c" | "b2b";

type Profile = {
  side: Side;
  company_name: string; address: string; phone: string; email: string;
  gst: string; cin: string; pan: string;
  logo: string | null; signature: string | null; seal: string | null;
  bank_name: string; bank_account_name: string; bank_account_number: string;
  bank_ifsc: string; bank_branch: string;
  effective: Record<string, string | null>;
};

const FIELD = "w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition";
const LABEL = "block text-sm font-semibold text-slate-700 mb-1.5";

const SIDES: { key: Side; label: string; blurb: string }[] = [
  { key: "b2c", label: "B2C", blurb: "Printed on the retail proforma invoice." },
  { key: "b2b", label: "B2B", blurb: "Printed on the wholesale proforma invoice, dispatch invoice and purchase order." },
];

const LETTERHEAD: [keyof Profile, string, string][] = [
  ["company_name", "Company Name", "name"],
  ["address", "Address", "address"],
  ["phone", "Tel", "phone"],
  ["email", "Email", "email"],
  ["gst", "GST No", "gst"],
  ["cin", "CIN No", "cin"],
  ["pan", "PAN", "pan"],
];

const BANK: [keyof Profile, string, string][] = [
  ["bank_name", "Bank", "bank_name"],
  ["bank_account_name", "Account Name", "bank_account_name"],
  ["bank_account_number", "Account Number", "bank_account_number"],
  ["bank_ifsc", "IFSC", "bank_ifsc"],
  ["bank_branch", "Branch", "bank_branch"],
];

const ART: [keyof Profile, string][] = [
  ["logo", "Logo"], ["signature", "Signature"], ["seal", "Seal"],
];

export default function InventoryDocumentsSection({ domain, isAdmin }: { domain: string; isAdmin: boolean }) {
  const api = getApiBase(domain);
  const token = () => localStorage.getItem(`${domain}_access`);

  const [side, setSide] = useState<Side>("b2c");
  const [profiles, setProfiles] = useState<Record<Side, Profile> | null>(null);
  const [files, setFiles] = useState<Record<string, File | null>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [note, setNote] = useState("");

  const load = useCallback(async () => {
    try {
      const r = await fetch(`${api}/api/inventory-documents/`, {
        headers: { Authorization: `Bearer ${token()}` },
      });
      if (r.ok) setProfiles(await r.json());
    } catch { /* leave what we had */ } finally { setLoading(false); }
  }, [api]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { load(); }, [load]);

  const p = profiles?.[side];
  const set = (k: keyof Profile, v: string) =>
    setProfiles(prev => (prev ? { ...prev, [side]: { ...prev[side], [k]: v } } : prev));

  const save = async () => {
    if (!p) return;
    setSaving(true); setNote("");
    try {
      const body = new FormData();
      body.append("side", side);
      [...LETTERHEAD, ...BANK].forEach(([key]) => body.append(key, String(p[key] ?? "")));
      ART.forEach(([key]) => {
        const f = files[`${side}:${key}`];
        if (f) body.append(key, f);
      });
      const r = await fetch(`${api}/api/inventory-documents/`, {
        method: "PATCH", headers: { Authorization: `Bearer ${token()}` }, body,
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) { setNote(d.error || "Could not save."); return; }
      setProfiles(prev => (prev ? { ...prev, [side]: d } : prev));
      setFiles(prev => ({ ...prev, ...Object.fromEntries(ART.map(([k]) => [`${side}:${k}`, null])) }));
      setNote(`${side.toUpperCase()} document settings saved.`);
    } catch { setNote("Network error while saving."); }
    finally { setSaving(false); }
  };

  if (loading) return <p className="text-sm text-slate-400">Loading document settings…</p>;
  if (!p) return <p className="text-sm text-rose-600">Could not load document settings.</p>;

  const current = SIDES.find(s => s.key === side)!;

  return (
    <div>
      <h3 className="text-lg font-bold text-slate-900 mb-1">Inventory Documents</h3>
      <p className="text-sm text-slate-500 mb-5">
        The letterhead, sign-off and bank block printed on the proforma invoice, dispatch invoice
        and purchase order. Retail and wholesale are configured separately.
      </p>

      <div className="flex flex-wrap items-center gap-3 mb-2">
        <div className="inline-flex rounded-xl bg-slate-100 p-1">
          {SIDES.map(s => (
            <button key={s.key} type="button" onClick={() => setSide(s.key)}
              className={`px-5 py-1.5 rounded-lg text-xs font-bold transition-colors ${
                side === s.key ? "bg-white text-indigo-600 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}>
              {s.label}
            </button>
          ))}
        </div>
        <span className="text-xs text-slate-400">{current.blurb}</span>
      </div>
      <p className="text-[11px] text-slate-400 mb-5">
        Leave a field blank to keep the default shown in it.
      </p>

      <div className="grid sm:grid-cols-2 gap-5">
        {LETTERHEAD.map(([key, label, eff]) => (
          <div key={key} className={key === "address" ? "sm:col-span-2" : ""}>
            <label className={LABEL}>{label}</label>
            <input value={String(p[key] ?? "")} disabled={!isAdmin}
              onChange={e => set(key, e.target.value)}
              placeholder={String(p.effective?.[eff] ?? "")}
              className={`${FIELD} disabled:opacity-70`} />
          </div>
        ))}
      </div>

      <h4 className="text-sm font-bold text-slate-800 mt-7 mb-3">Artwork</h4>
      <div className="grid sm:grid-cols-3 gap-5">
        {ART.map(([key, label]) => {
          const chosen = files[`${side}:${key}`];
          const shown = chosen ? URL.createObjectURL(chosen)
                               : (p[key] as string | null) || (p.effective?.[key] as string | null);
          const url = shown && shown.startsWith("blob:") ? shown
                    : shown ? `${shown.startsWith("http") ? "" : api}${shown}` : null;
          return (
            <div key={key}>
              <label className={LABEL}>{label}</label>
              <div className="h-24 bg-slate-50 border border-slate-200 rounded-xl flex items-center justify-center overflow-hidden mb-2">
                {url
                  /* eslint-disable-next-line @next/next/no-img-element */
                  ? <img src={url} alt={label} className="max-h-full max-w-full object-contain" />
                  : <span className="text-xs text-slate-400">None</span>}
              </div>
              <input type="file" accept="image/*" disabled={!isAdmin}
                onChange={e => setFiles(prev => ({ ...prev, [`${side}:${key}`]: e.target.files?.[0] ?? null }))}
                className="block w-full text-xs text-slate-500 file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100 transition cursor-pointer disabled:opacity-60" />
              {!p[key] && (
                <p className="text-[10px] text-slate-400 mt-1">Using the organisation&apos;s {label.toLowerCase()}.</p>
              )}
            </div>
          );
        })}
      </div>

      <h4 className="text-sm font-bold text-slate-800 mt-7 mb-3">Bank Details</h4>
      <div className="grid sm:grid-cols-2 gap-5">
        {BANK.map(([key, label, eff]) => (
          <div key={key}>
            <label className={LABEL}>{label}</label>
            <input value={String(p[key] ?? "")} disabled={!isAdmin}
              onChange={e => set(key, e.target.value)}
              placeholder={String(p.effective?.[eff] ?? "")}
              className={`${FIELD} disabled:opacity-70`} />
          </div>
        ))}
      </div>

      {isAdmin && (
        <div className="flex items-center gap-3 mt-6">
          <button type="button" onClick={save} disabled={saving}
            className="px-5 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 disabled:opacity-50 transition">
            {saving ? "Saving…" : `Save ${side.toUpperCase()} documents`}
          </button>
          {note && <span className="text-xs font-semibold text-slate-500">{note}</span>}
        </div>
      )}
    </div>
  );
}

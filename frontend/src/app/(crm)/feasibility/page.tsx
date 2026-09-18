"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import DeletedLeadCleanup, { DeletedLeadBadge } from "@/components/DeletedLeadCleanup";
import { isSpectator } from "@/lib/spectator";
import BdeTag from "@/components/BdeTag";
type Receipt = { id: number; doc_type: string; file: string };
type Feasibility = {
  /** Who did the site visit — shown as a tag on the row. */
  bde_name?: string | null;
  // Set when the lead behind this row has been deleted; the row is then
  // unopenable, and an admin gets a control to clear it out.
  lead_deleted?: boolean;
  can_cleanup?: boolean;
  id: number;
  first_name: string; last_name: string | null;
  phone: string | null; location: string | null; product_name: string | null;
  pushed_at: string | null;
  po_signed_date: string | null;
  kseb_feasibility_taken: string;
  kseb_feasibility_date: string | null;
  kseb_feasibility_complete: boolean;
  feasibility_due_date: string | null;
  receipts: Receipt[];
  can_edit: boolean;
};

const inputCls = "w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-sm text-slate-800 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all disabled:opacity-70 disabled:cursor-not-allowed";
const labelCls = "block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5";

export default function FeasibilityPage() {
  const domain = APP_SLUG;
  const router = useRouter();
  const apiBase = getApiBase(domain);
  const token = () => localStorage.getItem(`${domain}_access`);
  const authHeader = () => ({ Authorization: `Bearer ${token()}` });

  const [authChecked, setAuthChecked] = useState(false);
  const [allowed, setAllowed] = useState(false);
  const [rows, setRows] = useState<Feasibility[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [openId, setOpenId] = useState<number | null>(null);

  useEffect(() => {
    const t = token();
    if (!t) { router.push("/login"); return; }
    fetch(`${apiBase}/api/users/me/`, { headers: authHeader() })
      .then(r => r.json())
      .then(d => {
        const ok = isSpectator(d) || d.role === "bde" || d.is_staff || d.is_general_manager || d.is_manager;
        setAllowed(ok); setAuthChecked(true);
        if (!ok) router.replace("/");
      })
      .catch(() => setAuthChecked(true));
  }, [domain]); // eslint-disable-line react-hooks/exhaustive-deps

  const loadRows = () => {
    fetch(`${apiBase}/api/leads/bde-feasibility/`, { headers: authHeader() })
      .then(r => (r.ok ? r.json() : []))
      .then(d => setRows(Array.isArray(d) ? d : []))
      .catch(() => {})
      .finally(() => setLoading(false));
  };
  useEffect(() => { if (allowed) loadRows(); }, [allowed]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!authChecked) return <div className="flex items-center justify-center min-h-[60vh]"><div className="w-8 h-8 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" /></div>;
  if (!allowed) return null;

  const filtered = rows.filter(l => {
    const q = search.trim().toLowerCase();
    if (!q) return true;
    return (`${l.first_name} ${l.last_name || ""}`.toLowerCase().includes(q) || (l.phone || "").toLowerCase().includes(q) || (l.location || "").toLowerCase().includes(q));
  });

  const badge = (l: Feasibility) => {
    if (l.kseb_feasibility_complete) return { label: "Completed", cls: "bg-emerald-50 text-emerald-700" };
    if (l.po_signed_date && l.kseb_feasibility_taken === "no") return { label: "Feasibility pending", cls: "bg-amber-50 text-amber-700" };
    if (l.po_signed_date && l.kseb_feasibility_taken === "yes") return { label: "Feasibility taken", cls: "bg-sky-50 text-sky-700" };
    // Nothing recorded yet on the feasibility itself — which is the outstanding
    // work here, whether or not the PO date has been filled in.
    return { label: "Feasibility not taken", cls: "bg-slate-100 text-slate-600" };
  };

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-[1100px]">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">KSEB Feasibility</h1>
        <p className="text-sm text-slate-500 mt-1">Leads with a signed PO, plus anything pushed to documentation. Take the KSEB feasibility within 2 days of the PO date; completing it sends the dates to accounts.</p>
      </div>

      <div className="mb-5 flex items-center gap-3">
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search by name, phone or location…"
          className="w-full max-w-md bg-white border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all" />
        <span className="text-xs font-semibold text-slate-400">{filtered.length} lead{filtered.length === 1 ? "" : "s"}</span>
      </div>

      {loading ? (
        <div className="py-16 text-center text-sm text-slate-400">Loading…</div>
      ) : filtered.length === 0 ? (
        <div className="bg-white border border-dashed border-slate-200 rounded-2xl p-12 text-center text-sm text-slate-400">Nothing waiting on feasibility yet.</div>
      ) : (
        <div className="space-y-3">
          {filtered.map(l => {
            const b = badge(l);
            const open = openId === l.id;
            return (
              <div key={l.id} className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
                <div className="flex items-center">
                <button onClick={() => setOpenId(open ? null : l.id)} className="flex-1 min-w-0 flex items-center justify-between gap-4 px-5 py-4 hover:bg-slate-50/60 transition-colors text-left">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="text-sm font-bold text-slate-900 truncate">{l.first_name} {l.last_name}</p>
                      <BdeTag name={l.bde_name} />
                      <span className={`text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full ${b.cls}`}>{b.label}</span>
                      {l.lead_deleted && <DeletedLeadBadge />}
                    </div>
                    <p className="text-xs text-slate-500 mt-0.5 truncate">{l.phone || "—"} · {l.location || "No location"}{l.product_name ? ` · ${l.product_name}` : ""}</p>
                  </div>
                  <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" className={`text-slate-300 flex-shrink-0 transition-transform ${open ? "rotate-90" : ""}`}><polyline points="9 18 15 12 9 6" /></svg>
                </button>
                {l.can_cleanup && (
                  <div className="pr-5 flex-shrink-0">
                    <DeletedLeadCleanup leadId={l.id} module="feasibility"
                      name={`${l.first_name} ${l.last_name || ""}`.trim()}
                      onRemoved={loadRows} />
                  </div>
                )}
                </div>
                {open && (
                  <div className="border-t border-slate-100 p-5">
                    <FeasibilityForm lead={l} apiBase={apiBase} authHeader={authHeader} onChanged={loadRows} />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function FeasibilityForm({ lead, apiBase, authHeader, onChanged }: {
  lead: Feasibility; apiBase: string; authHeader: () => { Authorization: string }; onChanged: () => void;
}) {
  const base = `${apiBase}/api/leads/${lead.id}`;
  const [poDate, setPoDate] = useState(lead.po_signed_date || "");
  const [taken, setTaken] = useState(lead.kseb_feasibility_taken || "");
  const [ksebDate, setKsebDate] = useState(lead.kseb_feasibility_date || "");
  const [receipts, setReceipts] = useState<Receipt[]>(lead.receipts || []);
  const [complete, setComplete] = useState(!!lead.kseb_feasibility_complete);
  const [saving, setSaving] = useState(false);
  const [completing, setCompleting] = useState(false);
  const [uploading, setUploading] = useState(false);

  const canEdit = lead.can_edit && !complete;
  const due = (() => {
    if (!poDate) return "";
    const d = new Date(poDate);
    if (isNaN(d.getTime())) return "";
    d.setDate(d.getDate() + 2);
    return d.toLocaleDateString("en-IN");
  })();

  const saveScalars = async () => {
    const r = await fetch(`${base}/kseb-feasibility/`, {
      method: "PATCH", headers: { "Content-Type": "application/json", ...authHeader() },
      body: JSON.stringify({ po_signed_date: poDate || null, kseb_feasibility_taken: taken, kseb_feasibility_date: ksebDate || null }),
    });
    if (!r.ok) { const e = await r.json().catch(() => ({})); alert(e.error || "Failed to save."); return false; }
    return true;
  };
  const save = async () => { setSaving(true); try { if (await saveScalars()) onChanged(); } finally { setSaving(false); } };

  const addReceipt = async (files: File[]) => {
    if (!files.length) return;
    setUploading(true);
    try {
      for (const f of files) {
        const fd = new FormData(); fd.append("file", f);
        const r = await fetch(`${base}/kseb-feasibility/documents/`, { method: "POST", headers: authHeader(), body: fd });
        if (r.ok) { const created = await r.json(); setReceipts(prev => [...prev, created]); }
        else { const e = await r.json().catch(() => ({})); alert(e.error || "Upload failed."); }
      }
      onChanged();
    } finally { setUploading(false); }
  };
  const delReceipt = async (id: number) => {
    if (!window.confirm("Delete this receipt?")) return;
    const r = await fetch(`${base}/kseb-feasibility/documents/${id}/`, { method: "DELETE", headers: authHeader() });
    if (r.ok || r.status === 204) { setReceipts(prev => prev.filter(x => x.id !== id)); onChanged(); }
    else alert("Could not delete.");
  };

  const ready = !!poDate && taken === "yes" && !!ksebDate;
  const completeFeas = async () => {
    if (!ready) { alert("Record the PO date and the KSEB feasibility (taken + date) first."); return; }
    setCompleting(true);
    try {
      if (!(await saveScalars())) return;
      const r = await fetch(`${base}/complete-kseb-feasibility/`, { method: "POST", headers: authHeader() });
      if (r.ok) { setComplete(true); onChanged(); alert("KSEB feasibility completed. PO & feasibility dates sent to accounts."); }
      else { const e = await r.json().catch(() => ({})); alert(e.error || "Could not complete."); }
    } finally { setCompleting(false); }
  };

  return (
    <div className="space-y-4">
      {complete && (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-2.5 text-xs font-semibold text-emerald-700">
          ✓ Completed — PO &amp; feasibility dates sent to the accounts module.
        </div>
      )}
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <div>
          <label className={labelCls}>PO Signed Date</label>
          <input type="date" value={poDate} disabled={!canEdit} onChange={e => setPoDate(e.target.value)} className={inputCls} />
        </div>

        {poDate && (
          <div>
            <label className={labelCls}>KSEB Feasibility Taken</label>
            <select value={taken} disabled={!canEdit} onChange={e => setTaken(e.target.value)} className={inputCls}>
              <option value="">—</option>
              <option value="yes">Yes</option>
              <option value="no">No</option>
            </select>
          </div>
        )}

        {poDate && taken === "yes" && (
          <div>
            <label className={labelCls}>KSEB Feasibility Date</label>
            <input type="date" value={ksebDate} disabled={!canEdit} onChange={e => setKsebDate(e.target.value)} className={inputCls} />
          </div>
        )}
      </div>

      {/* If taken — receipt upload */}
      {poDate && taken === "yes" && (
        <div>
          <label className={labelCls}>Feasibility Receipt</label>
          {receipts.length > 0 && (
            <ul className="mb-2 space-y-1">
              {receipts.map(d => {
                const href = d.file.startsWith("http") ? d.file : `${apiBase}${d.file}`;
                const name = decodeURIComponent(d.file.split("/").pop() || "file");
                return (
                  <li key={d.id} className="flex items-center gap-2 text-[11px]">
                    <a href={href} target="_blank" rel="noreferrer" className="font-semibold text-emerald-600 hover:underline truncate max-w-[200px]" title={name}>{name}</a>
                    {canEdit && <button type="button" onClick={() => delReceipt(d.id)} className="font-bold text-rose-500 hover:text-rose-700">✕</button>}
                  </li>
                );
              })}
            </ul>
          )}
          {canEdit && (
            <label className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-semibold transition ${uploading ? "bg-slate-100 text-slate-400 cursor-not-allowed" : "bg-slate-100 text-slate-700 hover:bg-slate-200 cursor-pointer"}`}>
              {uploading ? "Uploading…" : "+ Add receipt"}
              <input type="file" accept="image/*,application/pdf" multiple disabled={uploading} className="hidden"
                onChange={e => { const fs = Array.from(e.target.files || []); e.currentTarget.value = ""; addReceipt(fs); }} />
            </label>
          )}
        </div>
      )}

      {/* If not taken — due date + reminder */}
      {poDate && taken === "no" && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 flex items-start gap-2">
          <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" className="mt-0.5 flex-shrink-0"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" /><line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" /></svg>
          <span><span className="font-semibold">KSEB Feasibility pending</span> — due by <span className="font-bold">{due || "—"}</span> (2 days from PO signing). A reminder is sent to the BDE on save.</span>
        </div>
      )}

      {canEdit && (
        <div className="flex flex-wrap items-center gap-3 pt-1">
          <button onClick={save} disabled={saving || completing} className="px-5 py-2.5 bg-slate-800 text-white rounded-xl text-sm font-semibold hover:bg-slate-900 disabled:opacity-50 transition">{saving ? "Saving…" : "Save"}</button>
          <button onClick={completeFeas} disabled={completing || saving || !ready} title={!ready ? "PO date + feasibility taken + feasibility date required" : ""}
            className="px-5 py-2.5 bg-emerald-600 text-white rounded-xl text-sm font-semibold hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed transition">{completing ? "Completing…" : "Complete & send to Accounts"}</button>
        </div>
      )}
      {!lead.can_edit && !complete && <p className="text-xs text-slate-400">Read-only — not your lead.</p>}
    </div>
  );
}

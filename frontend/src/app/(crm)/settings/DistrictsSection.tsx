"use client";
/**
 * Settings → Districts.
 *
 * The districts a lead can belong to. It ships with Kerala's fourteen and is
 * maintained here from then on.
 *
 * The list is not decoration: it is the vocabulary an import is matched against.
 * A CSV column or a Meta form answer is filed only if it names a district on
 * this list — case-insensitively, settling on the spelling below, so "KOLLAM",
 * "kollam" and "kollaM" all land in "Kollam". Anything else is dropped and the
 * lead arrives without a district; the lead itself is never rejected over it.
 *
 * Saves are immediate, like Roles & Permissions — this is its own resource
 * rather than a field on the workspace-settings form.
 */
import React, { useEffect, useState } from "react";
import { getApiBase } from "@/lib/mock-data";

type District = {
  id: number; name: string; is_active: boolean; lead_count: number;
};

const FIELD = "w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition";

export default function DistrictsSection({ domain, isAdmin }: { domain: string; isAdmin: boolean }) {
  const api = getApiBase(domain);
  const token = () => localStorage.getItem(`${domain}_access`);
  const authJson = () => ({ "Content-Type": "application/json", Authorization: `Bearer ${token()}` });

  const [districts, setDistricts] = useState<District[]>([]);
  const [loading, setLoading] = useState(true);
  const [newName, setNewName] = useState("");
  const [busy, setBusy] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");

  const load = async () => {
    try {
      const r = await fetch(`${api}/api/districts/`, { headers: { Authorization: `Bearer ${token()}` } });
      if (r.ok) { const d = await r.json(); setDistricts(Array.isArray(d) ? d : d.results || []); }
    } catch { /* leave the section empty rather than breaking Settings */ }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [domain]); // eslint-disable-line react-hooks/exhaustive-deps

  /** Pull the server's sentence out of a refusal — it explains the clash. */
  const explain = async (r: Response, fallback: string) => {
    try {
      const d = await r.json();
      const first = d.error || d.detail || (Array.isArray(d.name) ? d.name[0] : d.name);
      return first || fallback;
    } catch { return fallback; }
  };

  const say = (message: string) => { setNote(message); setError(""); setTimeout(() => setNote(""), 4000); };
  const fail = (message: string) => { setError(message); setNote(""); };

  const add = async () => {
    const name = newName.trim();
    if (!name) return;
    setBusy(true);
    try {
      const r = await fetch(`${api}/api/districts/`, {
        method: "POST", headers: authJson(), body: JSON.stringify({ name }),
      });
      if (!r.ok) { fail(await explain(r, "Could not add that district.")); return; }
      setNewName("");
      say(`${name} added.`);
      load();
    } finally { setBusy(false); }
  };

  const rename = async (d: District) => {
    const name = editName.trim();
    if (!name || name === d.name) { setEditingId(null); return; }
    setBusy(true);
    try {
      const r = await fetch(`${api}/api/districts/${d.id}/`, {
        method: "PATCH", headers: authJson(), body: JSON.stringify({ name }),
      });
      if (!r.ok) { fail(await explain(r, "Could not rename that district.")); return; }
      setEditingId(null);
      // Leads already filed keep the old spelling — their district is a name, not
      // a link — so say so rather than let it be discovered later.
      say(d.lead_count > 0
        ? `Renamed to ${name}. The ${d.lead_count} lead(s) already filed keep "${d.name}".`
        : `Renamed to ${name}.`);
      load();
    } finally { setBusy(false); }
  };

  const toggleActive = async (d: District) => {
    setBusy(true);
    try {
      const r = await fetch(`${api}/api/districts/${d.id}/`, {
        method: "PATCH", headers: authJson(), body: JSON.stringify({ is_active: !d.is_active }),
      });
      if (!r.ok) { fail(await explain(r, "Could not update that district.")); return; }
      say(d.is_active
        ? `${d.name} switched off — imports will stop matching it.`
        : `${d.name} switched back on.`);
      load();
    } finally { setBusy(false); }
  };

  const remove = async (d: District) => {
    if (!confirm(`Remove ${d.name} from the list?`)) return;
    setBusy(true);
    try {
      let r = await fetch(`${api}/api/districts/${d.id}/`, {
        method: "DELETE", headers: authJson(),
      });
      if (!r.ok) {
        const body = await r.clone().json().catch(() => ({} as any));
        if (!body?.can_force || !confirm(`${body.error}\n\nDelete anyway?`)) {
          fail(await explain(r, "Could not remove that district."));
          return;
        }
        r = await fetch(`${api}/api/districts/${d.id}/?force=1`, {
          method: "DELETE", headers: authJson(),
        });
        if (!r.ok) { fail(await explain(r, "Could not remove that district.")); return; }
      }
      say(`${d.name} removed.`);
      load();
    } finally { setBusy(false); }
  };

  const active = districts.filter(d => d.is_active).length;

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden">
      <div className="p-6 sm:p-8">
        <h3 className="text-lg font-bold text-slate-900 mb-2">Districts</h3>
        <p className="text-sm text-slate-500 mb-6 max-w-3xl">
          The districts a lead can belong to — Kerala&apos;s fourteen to start with.
          When leads are imported from the CSV template or arrive from Meta, the
          district is filed only if it names one on this list. Capitalisation does
          not matter: <span className="font-semibold text-slate-600">KOLLAM</span>,{" "}
          <span className="font-semibold text-slate-600">kollam</span> and{" "}
          <span className="font-semibold text-slate-600">kollaM</span> all file under{" "}
          <span className="font-semibold text-slate-600">Kollam</span>. Anything not on
          the list is left blank — the lead is still imported, just without a district.
        </p>

        {note && <div className="mb-4 p-3 bg-emerald-50 text-emerald-700 rounded-xl text-sm border border-emerald-100">{note}</div>}
        {error && <div className="mb-4 p-3 bg-red-50 text-red-600 rounded-xl text-sm border border-red-100">{error}</div>}

        {isAdmin && (
          <div className="flex gap-3 mb-6">
            <input
              value={newName}
              onChange={e => setNewName(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter") { e.preventDefault(); add(); } }}
              placeholder="e.g. Mahe"
              className={FIELD}
            />
            <button type="button" onClick={add} disabled={busy || !newName.trim()}
              className="bg-indigo-600 hover:bg-indigo-700 text-white font-bold px-6 py-2.5 rounded-xl transition whitespace-nowrap disabled:opacity-50">
              Add District
            </button>
          </div>
        )}

        {loading ? (
          <p className="text-sm text-slate-400">Loading…</p>
        ) : districts.length === 0 ? (
          <p className="text-sm text-slate-400 italic">
            No districts configured — every imported district will be left blank until one is added.
          </p>
        ) : (
          <>
            <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-widest mb-3">
              {active} active · {districts.length} total
            </p>
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {districts.map(d => (
                <div key={d.id}
                  className={`border rounded-xl p-4 flex items-center justify-between gap-3 ${
                    d.is_active ? "bg-slate-50 border-slate-200" : "bg-white border-dashed border-slate-200"}`}>
                  {editingId === d.id ? (
                    <input
                      autoFocus
                      value={editName}
                      onChange={e => setEditName(e.target.value)}
                      onKeyDown={e => {
                        if (e.key === "Enter") { e.preventDefault(); rename(d); }
                        if (e.key === "Escape") setEditingId(null);
                      }}
                      onBlur={() => rename(d)}
                      className="flex-1 min-w-0 bg-white border border-indigo-300 rounded-lg px-2.5 py-1 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20"
                    />
                  ) : (
                    <div className="min-w-0">
                      <p className={`font-bold text-sm truncate ${d.is_active ? "text-slate-800" : "text-slate-400"}`}>
                        {d.name}
                        {!d.is_active && <span className="ml-1.5 text-[9px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded bg-slate-100 text-slate-500">Off</span>}
                      </p>
                      <p className="text-[11px] text-slate-400">
                        {d.lead_count} lead{d.lead_count === 1 ? "" : "s"}
                      </p>
                    </div>
                  )}

                  {isAdmin && editingId !== d.id && (
                    <div className="flex items-center gap-1 flex-shrink-0">
                      <button type="button" title="Rename"
                        onClick={() => { setEditingId(d.id); setEditName(d.name); }}
                        className="w-7 h-7 flex items-center justify-center rounded-lg text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 transition">
                        <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" /><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" /></svg>
                      </button>
                      <button type="button"
                        title={d.is_active ? "Switch off — imports stop matching it" : "Switch back on"}
                        onClick={() => toggleActive(d)}
                        className={`w-7 h-7 flex items-center justify-center rounded-lg transition ${
                          d.is_active ? "text-slate-400 hover:text-amber-600 hover:bg-amber-50"
                                      : "text-slate-400 hover:text-emerald-600 hover:bg-emerald-50"}`}>
                        {d.is_active
                          ? <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M18.36 6.64A9 9 0 1 1 5.64 6.64" /><line x1="12" y1="2" x2="12" y2="12" /></svg>
                          : <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12" /></svg>}
                      </button>
                      <button type="button" title="Remove from the list" onClick={() => remove(d)}
                        className="w-7 h-7 flex items-center justify-center rounded-lg text-slate-400 hover:text-red-500 hover:bg-red-50 transition">
                        <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6" /><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6" /><path d="M10 11v6M14 11v6" /><path d="M9 6V4a1 1 0 011-1h4a1 1 0 011 1v2" /></svg>
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </>
        )}

        {!isAdmin && (
          <p className="text-xs text-slate-400 italic mt-5">
            Only an admin can change this list.
          </p>
        )}
      </div>
    </div>
  );
}

"use client";
/**
 * Activity Log — every change made in the CRM, and who made it.
 *
 * For admins and super admins. Not the same thing as a lead's own timeline,
 * which tells the story of a customer; this answers "who changed this, when,
 * and what did it used to say" — the question that gets asked after something
 * has gone wrong and nobody remembers.
 *
 * Rows are read-only, permanently. An audit trail that can be edited is not one.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";

type Change = { from: string | null; to: string | null };
type Entry = {
  id: number; actor: number | null; actor_display: string;
  action: "created" | "updated" | "deleted"; action_display: string;
  category: string; model_label: string; object_id: string; object_label: string;
  changes: Record<string, Change>; summary: string; created_at: string;
};

const ACTION_STYLE: Record<string, string> = {
  created: "bg-emerald-50 text-emerald-700 border-emerald-100",
  updated: "bg-amber-50 text-amber-700 border-amber-100",
  deleted: "bg-rose-50 text-rose-700 border-rose-100",
};

const inputCls =
  "bg-white border border-slate-200 rounded-xl px-3 py-2.5 text-sm text-slate-800 " +
  "placeholder:text-slate-400 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition";

/** "2 minutes ago" for the recent ones, a date once that stops being useful. */
function when(iso: string) {
  const then = new Date(iso), now = new Date();
  const mins = Math.round((now.getTime() - then.getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  if (mins < 60 * 24) return `${Math.round(mins / 60)} h ago`;
  return then.toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
}

const fieldLabel = (f: string) =>
  f.replace(/_id$/, "").replace(/_/g, " ").replace(/^\w/, c => c.toUpperCase());

const shown = (v: string | null) =>
  v === null || v === "" ? "—" : v;

export default function ActivityLogPage() {
  const api = getApiBase(APP_SLUG);
  const router = useRouter();
  const headers = useCallback(() => ({
    "Content-Type": "application/json",
    Authorization: `Bearer ${localStorage.getItem(`${APP_SLUG}_access`)}`,
  }), []);

  const [rows, setRows] = useState<Entry[]>([]);
  const [count, setCount] = useState(0);
  const [next, setNext] = useState<string | null>(null);
  const [opts, setOpts] = useState<{ categories: string[]; actions: any[]; actors: any[] }>(
    { categories: [], actions: [], actors: [] });
  const [category, setCategory] = useState("all");
  const [act, setAct] = useState("all");
  const [actor, setActor] = useState("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [denied, setDenied] = useState(false);

  // Typing shouldn't fire a request per keystroke.
  useEffect(() => {
    const t = setTimeout(() => setQuery(search.trim()), 350);
    return () => clearTimeout(t);
  }, [search]);

  const url = useMemo(() => {
    const q = new URLSearchParams();
    if (category !== "all") q.set("category", category);
    if (act !== "all") q.set("action", act);
    if (actor) q.set("actor", actor);
    if (query) q.set("search", query);
    return `${api}/api/activity-log/?${q.toString()}`;
  }, [api, category, act, actor, query]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(url, { headers: headers() });
      if (r.status === 403) { setDenied(true); return; }
      if (!r.ok) return;
      const d = await r.json();
      setRows(d.results || []);
      setCount(d.count ?? (d.results || []).length);
      setNext(d.next || null);
    } catch { /* an empty list rather than a broken page */ }
    finally { setLoading(false); }
  }, [url, headers]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    (async () => {
      try {
        const r = await fetch(`${api}/api/activity-log/filters/`, { headers: headers() });
        if (r.ok) setOpts(await r.json());
      } catch { /* the filters simply stay empty */ }
    })();
  }, [api, headers]);

  const loadMore = async () => {
    if (!next) return;
    try {
      const r = await fetch(next, { headers: headers() });
      if (!r.ok) return;
      const d = await r.json();
      setRows(prev => [...prev, ...(d.results || [])]);
      setNext(d.next || null);
    } catch { /* the button simply does nothing */ }
  };

  if (denied) {
    return (
      <div className="p-8 max-w-lg mx-auto text-center">
        <h1 className="text-xl font-black text-slate-900">Activity Log</h1>
        <p className="text-sm text-slate-500 mt-2">
          This log is for admins and super admins.
        </p>
        <button onClick={() => router.push("/")}
          className="mt-5 px-5 py-2.5 rounded-xl bg-indigo-600 text-white text-sm font-bold hover:bg-indigo-700 transition">
          Back to the dashboard
        </button>
      </div>
    );
  }

  const filtered = category !== "all" || act !== "all" || actor || query;

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-[1400px] mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-black text-slate-900">Activity Log</h1>
        <p className="text-sm text-slate-500 mt-1">
          Every change made in the CRM, and who made it.
        </p>
      </div>

      {/* ── Filters ── */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-[1fr_180px_150px_180px] mb-5">
        <input value={search} onChange={e => setSearch(e.target.value)}
          placeholder="Search what changed, which record, or who changed it…"
          className={inputCls} />
        <select value={category} onChange={e => setCategory(e.target.value)} className={inputCls}>
          <option value="all">All categories</option>
          {opts.categories.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <select value={act} onChange={e => setAct(e.target.value)} className={inputCls}>
          <option value="all">All actions</option>
          {opts.actions.map((a: any) => <option key={a.value} value={a.value}>{a.label}</option>)}
        </select>
        <select value={actor} onChange={e => setActor(e.target.value)} className={inputCls}>
          <option value="">Everyone</option>
          {opts.actors.map((u: any) => <option key={u.id} value={u.id}>{u.name}</option>)}
        </select>
      </div>

      <div className="flex flex-wrap items-center gap-3 mb-4">
        <p className="text-[12px] text-slate-400">
          {loading ? "Loading…" : `${count.toLocaleString("en-IN")} ${count === 1 ? "entry" : "entries"}`}
          {filtered && " matching"}
        </p>
        {filtered && (
          <button onClick={() => { setCategory("all"); setAct("all"); setActor(""); setSearch(""); }}
            className="text-[12px] font-bold text-indigo-600 hover:text-indigo-800">
            Clear filters
          </button>
        )}
      </div>

      {/* ── The log ── */}
      <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden">
        {loading && rows.length === 0 ? (
          <p className="py-14 text-center text-slate-400 text-sm">Loading…</p>
        ) : rows.length === 0 ? (
          <p className="py-14 text-center text-slate-500 text-sm">
            {filtered ? "Nothing matches those filters." : "Nothing has been changed yet."}
          </p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {rows.map(e => {
              const fields = Object.entries(e.changes || {});
              const open = expanded === e.id;
              return (
                <li key={e.id} className="px-5 py-4 hover:bg-slate-50/60 transition">
                  <div className="flex flex-wrap items-start gap-x-3 gap-y-2">
                    <span className={`px-2 py-0.5 rounded-full border text-[10px] font-bold uppercase tracking-wide ${
                      ACTION_STYLE[e.action] || "bg-slate-50 text-slate-600 border-slate-100"}`}>
                      {e.action_display}
                    </span>
                    <span className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 text-[10px] font-bold">
                      {e.category}
                    </span>
                    <p className="text-sm text-slate-800 min-w-0 flex-1">{e.summary}</p>
                    <span className="text-[11px] text-slate-400 whitespace-nowrap" title={e.created_at}>
                      {when(e.created_at)}
                    </span>
                  </div>

                  <div className="flex flex-wrap items-center gap-3 mt-1.5 pl-1">
                    <span className="text-[11px] text-slate-500">
                      by <b className="text-slate-700">{e.actor_display}</b>
                    </span>
                    {fields.length > 0 && (
                      <button onClick={() => setExpanded(open ? null : e.id)}
                        className="text-[11px] font-bold text-indigo-600 hover:text-indigo-800">
                        {open ? "Hide" : `What changed (${fields.length})`}
                      </button>
                    )}
                  </div>

                  {open && fields.length > 0 && (
                    <div className="mt-3 border border-slate-100 rounded-xl overflow-hidden">
                      <table className="w-full text-[12px]">
                        <thead className="bg-slate-50 text-slate-500">
                          <tr>
                            <th className="text-left font-semibold px-3 py-2">Field</th>
                            <th className="text-left font-semibold px-3 py-2">Was</th>
                            <th className="text-left font-semibold px-3 py-2">Became</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                          {fields.map(([field, move]) => (
                            <tr key={field}>
                              <td className="px-3 py-2 font-semibold text-slate-700 align-top">
                                {fieldLabel(field)}
                              </td>
                              <td className="px-3 py-2 text-slate-500 align-top break-words">
                                {shown(move.from)}
                              </td>
                              <td className="px-3 py-2 text-slate-800 align-top break-words">
                                {shown(move.to)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {next && (
        <div className="text-center mt-5">
          <button onClick={loadMore}
            className="px-5 py-2.5 rounded-xl border border-slate-200 bg-white text-sm font-bold text-slate-600 hover:bg-slate-50 transition">
            Load more
          </button>
        </div>
      )}
    </div>
  );
}

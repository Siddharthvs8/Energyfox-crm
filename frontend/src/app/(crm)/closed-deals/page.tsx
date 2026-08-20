"use client";
/**
 * Closed Deals — the business actually won.
 *
 * A closed deal is a converted lead whose money has landed: in accounts, with a
 * payment part or full received. That is the same definition the Converted Leads
 * board already uses; this module is the board for those deals alone, with the
 * money on it.
 *
 * The server decides which deals a person sees — the same privilege scoping the
 * Leads list runs on, so a BDE opens this and finds their own closed deals. It
 * also does the filtering, so the totals on the summary strip always describe
 * exactly the rows underneath them.
 */
import { APP_SLUG } from "@/lib/config";
import { getApiBase, formatCurrency, getSourceLabel } from "@/lib/mock-data";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";

type Deal = {
  id: number;
  name: string;
  email: string | null;
  phone: string | null;
  place: string | null;
  district: string | null;
  source: string;
  product: string | null;
  value: string;
  amount_received: string;
  balance: string;
  payment_status: "fully_paid" | "partially_paid";
  payment_verified: boolean;
  tele_caller: number | null;
  tele_caller_name: string | null;
  bde: number | null;
  bde_name: string | null;
  closed_on: string;
  pipeline_stage_label: string;
};

type Person = { id: number; name: string };

type Board = {
  deals: Deal[];
  summary: {
    count: number; deal_value: string; received: string; outstanding: string;
    fully_paid: number; partially_paid: number;
  };
  tele_callers: Person[];
  bdes: Person[];
  // The window the server applied, named — so the strip above the table says
  // what it is describing rather than leaving the reader to infer it.
  period: string;
  period_label: string;
};

const PAYMENT_META: Record<string, { label: string; cls: string }> = {
  fully_paid: { label: "Fully Paid", cls: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  partially_paid: { label: "Partially Paid", cls: "bg-amber-50 text-amber-700 border-amber-200" },
};

const I = {
  Trophy: () => <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><path d="M6 9H4.5a2.5 2.5 0 010-5H6" /><path d="M18 9h1.5a2.5 2.5 0 000-5H18" /><path d="M4 22h16" /><path d="M10 14.66V17c0 1.1-.9 2-2 2H6" /><path d="M14 14.66V17c0 1.1.9 2 2 2h2" /><path d="M18 4H6v5c0 3.31 2.69 6 6 6s6-2.69 6-6V4z" /></svg>,
  Search: () => <svg width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8" /><path d="M21 21l-4.35-4.35" /></svg>,
  X: () => <svg width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12" /></svg>,
};

const SELECT = "w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all";
// The same set Company Performance offers, in the same order.
const PERIODS = [
  { key: "this_fy", label: "This FY" },
  { key: "this_month", label: "This month" },
  { key: "this_year", label: "This year" },
  { key: "all", label: "All time" },
  { key: "custom", label: "Custom" },
];

const LABEL = "block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1.5";

function Tile({ label, value, tone = "slate" }: { label: string; value: string; tone?: string }) {
  const tones: Record<string, string> = {
    slate: "text-slate-900", emerald: "text-emerald-600", amber: "text-amber-600", indigo: "text-indigo-600",
  };
  return (
    <div className="bg-white rounded-2xl border border-slate-100 shadow-[0_4px_20px_rgb(0,0,0,0.04)] px-5 py-4">
      <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">{label}</p>
      <p className={`text-xl font-black mt-1 tabular-nums ${tones[tone]}`}>{value}</p>
    </div>
  );
}

export default function ClosedDealsPage() {
  const domain = APP_SLUG;
  const api = getApiBase(domain);

  const [board, setBoard] = useState<Board | null>(null);
  const [loading, setLoading] = useState(true);
  const [denied, setDenied] = useState(false);

  const [payment, setPayment] = useState("");
  const [teleCaller, setTeleCaller] = useState("");
  const [bde, setBde] = useState("");
  const [search, setSearch] = useState("");
  // All time by default: this is a working list, and a deal closed last year
  // should not go missing behind a filter nobody set. The server agrees.
  const [period, setPeriod] = useState("all");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  // Typing shouldn't fire a request per keystroke; the rest apply immediately.
  const [debounced, setDebounced] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setDebounced(search), 300);
    return () => clearTimeout(t);
  }, [search]);

  const load = useCallback(async () => {
    const token = localStorage.getItem(`${domain}_access`);
    if (!token) return;
    setLoading(true);
    const q = new URLSearchParams();
    q.append("period", period);
    // A custom range with neither end set would filter nothing out, so it is
    // sent as-is and the server treats a missing end as today.
    if (period === "custom") {
      if (from) q.append("from", from);
      if (to) q.append("to", to);
    }
    if (payment) q.append("payment", payment);
    if (teleCaller) q.append("tele_caller", teleCaller);
    if (bde) q.append("bde", bde);
    if (debounced.trim()) q.append("search", debounced.trim());
    try {
      const r = await fetch(`${api}/api/leads/closed-deals/${q.toString() ? `?${q}` : ""}`,
        { headers: { Authorization: `Bearer ${token}` } });
      if (r.status === 403) { setDenied(true); return; }
      if (r.ok) setBoard(await r.json());
    } catch { /* leave the last good board on screen */ }
    finally { setLoading(false); }
  }, [api, domain, payment, teleCaller, bde, debounced, period, from, to]);

  useEffect(() => { load(); }, [load]);

  // The pickers come from the whole board, so they stay put while filtering;
  // hold on to them so they don't blink between requests.
  const [pickers, setPickers] = useState<{ tele_callers: Person[]; bdes: Person[] }>(
    { tele_callers: [], bdes: [] });
  useEffect(() => {
    if (board && !payment && !teleCaller && !bde && !debounced.trim()) {
      setPickers({ tele_callers: board.tele_callers, bdes: board.bdes });
    }
  }, [board, payment, teleCaller, bde, debounced]);

  const activeFilters = [payment, teleCaller, bde, search.trim(),
                         period === "all" ? "" : period].filter(Boolean).length;
  const clearFilters = () => {
    setPayment(""); setTeleCaller(""); setBde(""); setSearch("");
    setPeriod("all"); setFrom(""); setTo("");
  };

  if (denied) {
    return (
      <div className="min-h-screen bg-[#f4f6fa] flex items-center justify-center px-6">
        <div className="bg-white rounded-2xl border border-slate-100 px-8 py-10 text-center max-w-sm">
          <p className="font-bold text-slate-800">Closed Deals is not open to you</p>
          <p className="text-sm text-slate-500 mt-2">
            This board belongs to the sales side of the house. Ask an admin if you need it.
          </p>
        </div>
      </div>
    );
  }

  const s = board?.summary;
  const deals = board?.deals || [];

  return (
    <div className="min-h-screen bg-[#f4f6fa]">
      <div className="max-w-[1440px] mx-auto px-4 sm:px-6 xl:px-8 py-6">

        <div className="flex items-center gap-3 mb-6">
          <div className="w-11 h-11 rounded-2xl bg-indigo-600 text-white flex items-center justify-center shadow-sm shadow-indigo-200">
            <I.Trophy />
          </div>
          <div>
            <h1 className="text-xl font-black text-slate-900 leading-tight">Closed Deals</h1>
            <p className="text-[12px] text-slate-400">
              Converted customers whose payment has reached accounts — part or full.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-5">
          <Tile label="Closed Deals" value={s ? String(s.count) : "—"} tone="indigo" />
          <Tile label="Deal Value" value={s ? formatCurrency(Number(s.deal_value)) : "—"} />
          <Tile label="Received" value={s ? formatCurrency(Number(s.received)) : "—"} tone="emerald" />
          <Tile label="Outstanding" value={s ? formatCurrency(Number(s.outstanding)) : "—"} tone="amber" />
        </div>

        {/* When the deals closed. The same control Company Performance carries,
            reading the same periods from the same helper, so "This FY" means one
            thing wherever it is offered. Measured on the Closed date, which is
            the one in the table. */}
        <div className="bg-white border border-slate-200 rounded-2xl p-3 mb-4 flex flex-wrap items-center gap-2">
          <div className="flex flex-wrap gap-1">
            {PERIODS.map(p => (
              <button key={p.key} onClick={() => setPeriod(p.key)}
                className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                  period === p.key ? "bg-indigo-600 text-white" : "text-slate-600 hover:bg-slate-100"}`}>
                {p.label}
              </button>
            ))}
          </div>
          {period === "custom" && (
            <div className="flex items-center gap-2">
              <input type="date" value={from} max={to || undefined} aria-label="From"
                onChange={e => setFrom(e.target.value)} className={SELECT} />
              <span className="text-xs text-slate-400">to</span>
              <input type="date" value={to} min={from || undefined} aria-label="To"
                onChange={e => setTo(e.target.value)} className={SELECT} />
            </div>
          )}
          {board?.period_label && (
            <span className="ml-auto text-[11px] text-slate-400">
              <b className="text-slate-600">{board.period_label}</b> · by the date the deal closed
            </span>
          )}
        </div>

        {/* Filters — the same set the Converted Leads board carries. */}
        <div className="bg-white rounded-2xl border border-slate-100 shadow-[0_4px_20px_rgb(0,0,0,0.04)] p-4 mb-5 flex flex-wrap items-end gap-4">
          <div className="min-w-[200px] flex-1 max-w-xs">
            <label className={LABEL}>Search</label>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none"><I.Search /></span>
              <input value={search} onChange={e => setSearch(e.target.value)}
                placeholder="Name, phone, email, place…" className={`${SELECT} pl-9`} />
            </div>
          </div>
          <div className="min-w-[160px]">
            <label className={LABEL}>Payment</label>
            {/* Only the two a closed deal can be: the money has landed, so
                "converted, nothing yet" and "lost" cannot appear here. */}
            <select value={payment} onChange={e => setPayment(e.target.value)} className={SELECT}>
              <option value="">All payments</option>
              <option value="partially_paid">Partially Paid{s ? ` (${s.partially_paid})` : ""}</option>
              <option value="fully_paid">Fully Paid{s ? ` (${s.fully_paid})` : ""}</option>
            </select>
          </div>
          {/* Shown whenever there is anyone to pick, not only when there are
              several: hiding the control on a one-person board makes the page
              look as though it cannot filter by owner at all. Labelled Owner to
              match the column — it is the tele caller who worked the deal,
              falling back to the current assignee. */}
          {pickers.tele_callers.length > 0 && (
            <div className="min-w-[160px]">
              <label className={LABEL}>Owner</label>
              <select value={teleCaller} onChange={e => setTeleCaller(e.target.value)} className={SELECT}>
                <option value="">All owners</option>
                {pickers.tele_callers.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </div>
          )}
          {pickers.bdes.length > 0 && (
            <div className="min-w-[160px]">
              <label className={LABEL}>BDE</label>
              <select value={bde} onChange={e => setBde(e.target.value)} className={SELECT}>
                <option value="">All BDEs</option>
                {pickers.bdes.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </div>
          )}
          {activeFilters > 0 && (
            <button onClick={clearFilters}
              className="ml-auto flex items-center gap-1.5 px-4 py-2 text-sm font-bold text-slate-500 hover:text-slate-700 bg-slate-50 hover:bg-slate-100 rounded-xl transition-colors">
              <I.X /> Clear ({activeFilters})
            </button>
          )}
        </div>

        <div className="bg-white rounded-2xl border border-slate-100 shadow-[0_4px_20px_rgb(0,0,0,0.04)] overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
            <h2 className="text-[15px] font-black text-slate-800">Deals</h2>
            <span className="bg-indigo-50 text-indigo-700 text-[10px] font-black px-2.5 py-1 rounded-full">
              {deals.length} record{deals.length === 1 ? "" : "s"}
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full min-w-[1000px] text-sm">
              <thead>
                <tr className="bg-slate-50/70 text-[10px] font-black text-slate-400 uppercase tracking-widest">
                  <th className="text-left px-6 py-3">Customer</th>
                  <th className="text-left px-4 py-3">District</th>
                  <th className="text-left px-4 py-3">Owner</th>
                  <th className="text-left px-4 py-3">BDE</th>
                  <th className="text-right px-4 py-3">Deal Value</th>
                  <th className="text-right px-4 py-3">Received</th>
                  <th className="text-right px-4 py-3">Balance</th>
                  <th className="text-center px-4 py-3">Payment</th>
                  <th className="text-left px-4 py-3">Stage</th>
                  <th className="text-left px-6 py-3">Closed</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {loading && deals.length === 0 && (
                  <tr><td colSpan={10} className="px-6 py-14 text-center text-sm text-slate-400">Loading…</td></tr>
                )}
                {!loading && deals.length === 0 && (
                  <tr>
                    <td colSpan={10} className="px-6 py-14 text-center">
                      <p className="font-semibold text-slate-600">No closed deals</p>
                      <p className="text-xs text-slate-400 mt-1">
                        {activeFilters > 0
                          ? "Nothing matches these filters."
                          : "A deal lands here once accounts records a payment against it."}
                      </p>
                    </td>
                  </tr>
                )}
                {deals.map(d => {
                  const m = PAYMENT_META[d.payment_status];
                  return (
                    <tr key={d.id} className="hover:bg-slate-50/60 transition-colors">
                      <td className="px-6 py-3">
                        <Link href={`/leads/${d.id}`} className="font-semibold text-slate-900 hover:text-indigo-600">
                          {d.name || "—"}
                        </Link>
                        <p className="text-[11px] text-slate-400">
                          {d.phone || "—"}
                          {d.product && <span className="ml-1.5 text-slate-300">· {d.product}</span>}
                          <span className="ml-1.5 text-slate-300">· {getSourceLabel(d.source)}</span>
                        </p>
                      </td>
                      <td className="px-4 py-3 text-slate-600">{d.district || d.place || "—"}</td>
                      <td className="px-4 py-3 text-slate-600">{d.tele_caller_name || "—"}</td>
                      <td className="px-4 py-3 text-slate-600">{d.bde_name || "—"}</td>
                      <td className="px-4 py-3 text-right tabular-nums font-semibold text-slate-900">
                        {formatCurrency(Number(d.value))}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums text-emerald-600 font-semibold">
                        {formatCurrency(Number(d.amount_received))}
                      </td>
                      <td className={`px-4 py-3 text-right tabular-nums font-semibold ${
                        Number(d.balance) > 0 ? "text-amber-600" : "text-slate-300"}`}>
                        {Number(d.balance) > 0 ? formatCurrency(Number(d.balance)) : "—"}
                      </td>
                      <td className="px-4 py-3 text-center">
                        <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-[10px] font-bold border ${m.cls}`}>
                          {m.label}
                        </span>
                        {!d.payment_verified && (
                          <span title="Accounts has taken the money but not signed the verification off yet."
                            className="block text-[9px] font-bold text-slate-400 mt-1">unverified</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-slate-500 text-[12px]">{d.pipeline_stage_label}</td>
                      <td className="px-6 py-3 text-slate-500 text-[12px] whitespace-nowrap">
                        {new Date(d.closed_on).toLocaleDateString("en-IN",
                          { day: "2-digit", month: "short", year: "numeric" })}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

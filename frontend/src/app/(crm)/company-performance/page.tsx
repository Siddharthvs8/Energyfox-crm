"use client";
/**
 * Company Performance — the whole business on one page.
 *
 * Every figure comes from the same definitions the rest of the CRM uses (won
 * means closed, revenue is net of discount, a BDE gets credit for what they
 * closed), so this board can be read against any other screen without having to
 * reconcile it first.
 *
 * Two windows are at work and the page says so where it matters: leads are
 * counted by when they arrived, money by when the deal was won.
 */
import React, { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend,
  ComposedChart, Line, PieChart, Pie, Cell,
} from "recharts";
import { APP_SLUG } from "@/lib/config";
import { getApiBase, formatCurrency } from "@/lib/mock-data";
import { exportCompanyPerformancePdf, findChartSvg } from "./performancePdf";

type Row = Record<string, any>;
type Ranked = {
  rows: Row[]; count: number; best: Row | null; worst: Row | null;
  only_earner?: boolean; without_revenue: string[];
  unattributed_revenue?: string; unattributed_deals?: number;
};

const PERIODS = [
  { key: "this_fy", label: "This FY" },
  { key: "this_month", label: "This month" },
  { key: "this_year", label: "This year" },
  { key: "all", label: "All time" },
  { key: "custom", label: "Custom" },
];

const FIELD = "bg-slate-50 border border-slate-200 rounded-xl px-3 py-1.5 text-xs outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all";

function Tile({ label, value, sub, tone = "slate" }: {
  label: string; value: string; sub?: string; tone?: string;
}) {
  const tones: Record<string, string> = {
    slate: "text-slate-900", emerald: "text-emerald-600",
    amber: "text-amber-600", indigo: "text-indigo-600", rose: "text-rose-600",
  };
  return (
    <div className="bg-white rounded-2xl border border-slate-100 shadow-[0_4px_20px_rgb(0,0,0,0.04)] px-5 py-4">
      <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">{label}</p>
      <p className={`text-xl font-black mt-1 tabular-nums ${tones[tone]}`}>{value}</p>
      {sub && <p className="text-[11px] text-slate-400 mt-0.5">{sub}</p>}
    </div>
  );
}

function Panel({ title, subtitle, right, children }: {
  title: string; subtitle?: string; right?: React.ReactNode; children: React.ReactNode;
}) {
  return (
    <div className="bg-white rounded-2xl border border-slate-100 shadow-[0_4px_20px_rgb(0,0,0,0.04)] p-5">
      <div className="flex items-start justify-between gap-3 mb-4">
        <div>
          <h2 className="text-sm font-black text-slate-800">{title}</h2>
          {subtitle && <p className="text-[11px] text-slate-400 mt-0.5">{subtitle}</p>}
        </div>
        {right}
      </div>
      {children}
    </div>
  );
}

/** A labelled row of the palette, used wherever a small ranking reads better
 *  as bars than as a chart. Widths are relative to the biggest row, so the
 *  shape of the list is visible at a glance. */
function MiniBars({ rows, colour = "#6366f1", unit }: {
  rows: { name: string; value: number; note?: string }[]; colour?: string; unit?: (v: number) => string;
}) {
  const top = Math.max(...rows.map(r => r.value), 1);
  if (rows.length === 0) return <p className="py-6 text-center text-sm text-slate-400">Nothing here yet.</p>;
  return (
    <div className="space-y-2.5">
      {rows.map(r => (
        <div key={r.name}>
          <div className="flex items-baseline justify-between gap-3 text-[12px] mb-1">
            <span className="text-slate-600 truncate">{r.name}</span>
            <span className="tabular-nums font-semibold text-slate-800 flex-shrink-0">
              {unit ? unit(r.value) : r.value}
              {r.note && <span className="ml-2 font-normal text-slate-400">{r.note}</span>}
            </span>
          </div>
          <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
            <div className="h-full rounded-full transition-all duration-700"
              style={{ width: `${Math.max(2, (r.value / top) * 100)}%`, background: colour }} />
          </div>
        </div>
      ))}
    </div>
  );
}

/** Money in: how it was paid, and how much of what was billed has landed. */
function CollectionPanel({ c }: { c: any }) {
  if (!c) return null;
  const MODE_COLOURS = ["#10b981", "#6366f1", "#f59e0b", "#0ea5e9", "#ec4899", "#94a3b8"];
  const pie = (c.by_mode || []).map((m: any, i: number) => ({
    name: m.label, value: Number(m.amount), count: m.count,
    fill: MODE_COLOURS[i % MODE_COLOURS.length],
  })).filter((r: any) => r.value > 0);

  return (
    <Panel title="Money in" subtitle="How the closed deals were paid, and what has actually landed">
      <div className="grid sm:grid-cols-2 gap-4 items-center">
        <div className="h-[170px]">
          {pie.length === 0 ? (
            <p className="py-14 text-center text-sm text-slate-400">Nothing collected yet.</p>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={pie} dataKey="value" nameKey="name" innerRadius={42} outerRadius={68}
                  paddingAngle={2} stroke="none">
                  {pie.map((r: any) => <Cell key={r.name} fill={r.fill} />)}
                </Pie>
                <Tooltip contentStyle={{ borderRadius: 12, border: "1px solid #e2e8f0", fontSize: 12, fontWeight: 600 }}
                  formatter={(v: any, n: any) => [formatCurrency(Number(v)), n]} />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>
        <div className="space-y-2 text-[12px]">
          {(c.by_mode || []).map((m: any, i: number) => (
            <div key={m.mode} className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-2 text-slate-600">
                <span className="w-2.5 h-2.5 rounded-sm flex-shrink-0"
                  style={{ background: MODE_COLOURS[i % MODE_COLOURS.length] }} />
                {m.label} <span className="text-slate-400">({m.count})</span>
              </span>
              <span className="font-bold text-slate-800 tabular-nums">{formatCurrency(Number(m.amount))}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-4 pt-4 border-t border-slate-50 grid grid-cols-3 gap-3 text-[12px]">
        <div>
          <p className="text-slate-400">Fully paid</p>
          <p className="font-bold text-emerald-600 tabular-nums">{c.fully_paid}</p>
        </div>
        <div>
          <p className="text-slate-400">Part paid</p>
          <p className="font-bold text-amber-600 tabular-nums">{c.partially_paid}</p>
        </div>
        <div>
          <p className="text-slate-400">Collected of billed</p>
          <p className="font-bold text-slate-800 tabular-nums">{c.collection_rate}%</p>
        </div>
      </div>
      <p className="mt-3 text-[11px] text-slate-400">
        A deal counts as fully paid once what was received covers the value less its discount —
        the same net figure the revenue tile uses.
      </p>
    </Panel>
  );
}

/** Delivery: a won deal is a promise, this is how much of it has been kept. */
function DeliveryPanel({ d }: { d: any }) {
  if (!d) return null;
  const total = Math.max(d.won || 0, 1);
  const parts = [
    { label: "Completed", n: d.completed, colour: "#10b981" },
    { label: "In progress", n: d.in_progress, colour: "#6366f1" },
    { label: "Not started", n: d.not_started, colour: "#e2e8f0" },
  ];
  return (
    <Panel title="Delivery" subtitle="Of the deals won in this window, how many have been built">
      <div className="flex h-4 rounded-full overflow-hidden bg-slate-100 mb-4">
        {parts.map(p => p.n > 0 && (
          <div key={p.label} style={{ width: `${(p.n / total) * 100}%`, background: p.colour }}
            title={`${p.label}: ${p.n}`} />
        ))}
      </div>
      <div className="space-y-2 text-[12px]">
        {parts.map(p => (
          <div key={p.label} className="flex items-center justify-between">
            <span className="flex items-center gap-2 text-slate-600">
              <span className="w-2.5 h-2.5 rounded-sm" style={{ background: p.colour }} />
              {p.label}
            </span>
            <span className="font-bold text-slate-800 tabular-nums">{p.n}</span>
          </div>
        ))}
      </div>
      <div className="mt-4 pt-4 border-t border-slate-50 grid grid-cols-2 gap-3 text-[12px]">
        <div>
          <p className="text-slate-400">Completion rate</p>
          <p className="font-bold text-slate-800 tabular-nums">{d.completion_rate}%</p>
        </div>
        <div>
          <p className="text-slate-400">Average days to build</p>
          <p className="font-bold text-slate-800 tabular-nums">{d.avg_days_to_complete}</p>
        </div>
      </div>
    </Panel>
  );
}

/** A ranked group — branches, teams or people — with its two ends called out.
 *
 * "bare" drops the card chrome and the heading for callers that already supply
 * their own, so a tabbed group does not sit in a card inside a card. */
function RankedPanel({ title, subtitle, data, unit, one, note, bare }: {
  title: string; subtitle: string; data: Ranked | undefined;
  unit: string; one: string; note?: string; bare?: boolean;
}) {
  if (!data) return null;
  const unattributed = Number(data.unattributed_revenue || 0);
  const count = <span className="text-[11px] text-slate-400">{data.count} {data.count === 1 ? one : unit}</span>;
  const Shell = ({ children }: { children: React.ReactNode }) => bare ? (
    <div className="px-4 pt-4 pb-4">
      <div className="flex items-start justify-between gap-3 mb-4">
        <p className="text-[11px] text-slate-400">{subtitle}</p>
        {count}
      </div>
      {children}
    </div>
  ) : (
    <Panel title={title} subtitle={subtitle} right={count}>{children}</Panel>
  );
  return (
    <Shell>
      {data.rows.length === 0 ? (
        <p className="py-6 text-center text-sm text-slate-400">No {unit} yet.</p>
      ) : (
        <>
          {/* Both ends come from the {unit} that actually earned. With only one
              earner there is no ranking to show, so it says so rather than
              printing the same name twice. */}
          {data.best ? (
            <div className="grid sm:grid-cols-2 gap-3 mb-4">
              <div className="rounded-xl border border-emerald-100 bg-emerald-50/60 px-4 py-3">
                <p className="text-[10px] font-black text-emerald-700 uppercase tracking-widest">Most revenue</p>
                <p className="text-sm font-bold text-slate-800 mt-1">{data.best.name}</p>
                <p className="text-lg font-black text-emerald-600 tabular-nums">
                  {formatCurrency(Number(data.best.revenue))}
                </p>
              </div>
              <div className="rounded-xl border border-amber-100 bg-amber-50/60 px-4 py-3">
                <p className="text-[10px] font-black text-amber-700 uppercase tracking-widest">Least revenue</p>
                {data.worst ? (
                  <>
                    <p className="text-sm font-bold text-slate-800 mt-1">{data.worst.name}</p>
                    <p className="text-lg font-black text-amber-600 tabular-nums">
                      {formatCurrency(Number(data.worst.revenue))}
                    </p>
                  </>
                ) : (
                  <p className="text-sm text-slate-500 mt-2">
                    Only one {one} has earned in this window.
                  </p>
                )}
                {data.without_revenue.length > 0 && (
                  <p className="text-[10px] text-amber-700/80 mt-1">
                    Nothing yet: {data.without_revenue.join(", ")}
                  </p>
                )}
              </div>
            </div>
          ) : (
            <p className="mb-4 rounded-xl border border-slate-100 bg-slate-50 px-4 py-3 text-[12px] text-slate-500">
              No {one} has brought in revenue in this window yet.
              {data.without_revenue.length > 0 && <> Waiting on: {data.without_revenue.join(", ")}.</>}
            </p>
          )}

          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-sm">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200 text-[10px] uppercase tracking-wider text-slate-500 font-semibold">
                  <th className="py-2.5 px-3">Name</th>
                  <th className="py-2.5 px-3 text-right">Leads</th>
                  <th className="py-2.5 px-3 text-right">Closed</th>
                  <th className="py-2.5 px-3 text-right">Close rate</th>
                  <th className="py-2.5 px-3 text-right">Revenue</th>
                  <th className="py-2.5 px-3 text-right">Collected</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.rows.map(r => (
                  <tr key={`${r.id}-${r.name}`} className="hover:bg-slate-50/60 transition-colors">
                    <td className="py-2.5 px-3">
                      <span className="font-semibold text-slate-800">{r.name}</span>
                      <span className="block text-[10px] text-slate-400">
                        {r.role || r.manager_name || r.code || ""}
                        {r.branch ? ` · ${r.branch}` : ""}
                        {typeof r.staff === "number" ? `${r.role || r.manager_name || r.code ? " · " : ""}${r.staff} staff` : ""}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-right tabular-nums">{r.leads}</td>
                    <td className="py-2.5 px-3 text-right tabular-nums font-semibold">{r.closed_deals}</td>
                    <td className="py-2.5 px-3 text-right tabular-nums text-slate-500">{r.close_rate}%</td>
                    <td className="py-2.5 px-3 text-right tabular-nums font-bold text-slate-900">
                      {formatCurrency(Number(r.revenue))}
                    </td>
                    <td className="py-2.5 px-3 text-right tabular-nums text-emerald-600">
                      {formatCurrency(Number(r.collected))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Say why the rows do not add up rather than let someone chase it. */}
          {data.count > data.rows.length && (
            <p className="mt-3 text-[11px] text-slate-400">
              Showing the top {data.rows.length} of {data.count} {unit} by revenue.
            </p>
          )}
          {note && <p className="mt-3 text-[11px] text-slate-400">{note}</p>}
          {unattributed > 0 && (
            <p className="mt-3 text-[11px] text-slate-400">
              {formatCurrency(unattributed)} from {data.unattributed_deals} deal
              {data.unattributed_deals === 1 ? "" : "s"} is not counted above — nobody who
              worked those leads is on a branch.
            </p>
          )}
        </>
      )}
    </Shell>
  );
}

/** People, with the two front-line roles on their own tabs.
 *
 * The role tabs are the same rows filtered, not a second sum — a person reads
 * the same on their own tab as on Everyone, and the same as My Performance. */
function PeoplePanel({ data }: { data: any }) {
  const TABS = [
    { key: "employees", label: "Everyone", unit: "people", one: "person",
      subtitle: "Everyone who worked a lead in this window — owner, BDE or tele caller" },
    { key: "bdes", label: "BDEs", unit: "BDEs", one: "BDE",
      subtitle: "Business development executives, ranked by revenue in this window" },
    { key: "tele_callers", label: "Tele Callers", unit: "tele callers", one: "tele caller",
      subtitle: "Tele callers, ranked by revenue in this window" },
  ];
  const [tab, setTab] = useState("employees");
  const active = TABS.find(t => t.key === tab) || TABS[0];
  const shown: Ranked | undefined = data?.[active.key];

  return (
    <div className="bg-white rounded-2xl border border-slate-100 shadow-[0_4px_20px_rgb(0,0,0,0.04)]">
      <h2 className="text-sm font-black text-slate-800 px-5 pt-5">People</h2>
      <div className="flex items-center gap-1 px-4 pt-2 border-b border-slate-100 overflow-x-auto">
        {TABS.map(t => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`relative px-4 py-2.5 text-xs font-bold whitespace-nowrap transition-colors ${
              tab === t.key ? "text-indigo-600" : "text-slate-400 hover:text-slate-600"}`}>
            {t.label}
            <span className="ml-1.5 text-[10px] font-semibold text-slate-400">
              {data?.[t.key]?.count ?? 0}
            </span>
            {tab === t.key && (
              <span className="absolute left-2 right-2 -bottom-px h-0.5 rounded-full bg-indigo-600" />
            )}
          </button>
        ))}
      </div>
      <div className="p-1">
        <RankedPanel key={tab} title="People" subtitle={active.subtitle} data={shown}
          unit={active.unit} one={active.one} bare
          note={"A deal worked by a BDE and a tele caller is credited to both, so these " +
                "rows add up to more than the company total. Each row is what that person " +
                "had a hand in, not a slice of the revenue."} />
      </div>
    </div>
  );
}

export default function CompanyPerformancePage() {
  const api = getApiBase(APP_SLUG);
  const [period, setPeriod] = useState("this_fy");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [d, setD] = useState<any>(null);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [denied, setDenied] = useState(false);

  const query = useMemo(() => {
    const q = new URLSearchParams({ period });
    if (period === "custom") {
      if (!from && !to) return "period=all";
      if (from) q.append("from", from);
      if (to) q.append("to", to);
    }
    return q.toString();
  }, [period, from, to]);

  useEffect(() => {
    const token = localStorage.getItem(`${APP_SLUG}_access`);
    if (!token) return;
    setLoading(true);
    fetch(`${api}/api/company-performance/?${query}`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => { if (r.status === 403) { setDenied(true); return null; } return r.ok ? r.json() : null; })
      .then(body => { if (body) setD(body); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [api, query]);

  /** The chart lives in the DOM as an SVG; the exporter redraws it from there,
   *  so what lands in the PDF is the same plot rather than a picture of it. */
  const onExport = async () => {
    if (!d || saving) return;
    setSaving(true);
    try {
      await exportCompanyPerformancePdf(d, findChartSvg(document.querySelector("#cp-chart")));
    } finally {
      setSaving(false);
    }
  };

  if (denied) return (
    <div className="min-h-screen bg-[#f4f6fa] flex items-center justify-center px-6">
      <div className="bg-white rounded-2xl border border-slate-100 px-8 py-10 text-center max-w-sm">
        <p className="font-bold text-slate-800">Company Performance is not open to you</p>
        <p className="text-sm text-slate-500 mt-2">
          It reports the whole company. Your own figures are under My Performance.
        </p>
      </div>
    </div>
  );

  const h = d?.headline;
  const chart = (d?.monthly || []).map((m: Row) => ({
    name: m.name, Leads: m.leads, Revenue: Number(m.revenue),
    "Running total": Number(m.cumulative || 0),
  }));

  return (
    <div className="min-h-screen bg-[#f4f6fa]">
      <div className="max-w-[1440px] mx-auto px-4 sm:px-6 xl:px-8 py-6">

        <div className="mb-5">
          <h1 className="text-xl font-black text-slate-900">Company Performance</h1>
          <p className="text-[12px] text-slate-400">
            Leads, deals, revenue and the people behind them — one report for the whole business.
          </p>
        </div>

        <div className="bg-white border border-slate-200 rounded-2xl p-3 mb-5 flex flex-wrap items-center gap-2">
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
              <input type="date" value={from} max={to || undefined}
                onChange={e => setFrom(e.target.value)} aria-label="From" className={FIELD} />
              <span className="text-xs text-slate-400">to</span>
              <input type="date" value={to} min={from || undefined}
                onChange={e => setTo(e.target.value)} aria-label="To" className={FIELD} />
            </div>
          )}
          {d?.period_label && (
            <span className="ml-auto text-[11px] text-slate-400 hidden xl:inline">
              <b className="text-slate-600">{d.period_label}</b> · leads by arrival, money by when the deal was won
            </span>
          )}
          <button onClick={onExport} disabled={!d || saving}
            className="ml-auto xl:ml-3 flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-bold
                       bg-slate-900 text-white hover:bg-slate-800 disabled:opacity-40
                       disabled:cursor-not-allowed transition-all">
            <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2"
              strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
              <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
            {saving ? "Preparing…" : "Export PDF"}
          </button>
        </div>

        {loading && !d ? (
          <p className="py-20 text-center text-sm text-slate-400">Loading…</p>
        ) : !h ? (
          <p className="py-20 text-center text-sm text-slate-400">No data yet.</p>
        ) : (
          <>
            <div className="grid grid-cols-2 lg:grid-cols-6 gap-3 mb-5">
              <Tile label="Leads" value={String(h.leads)} sub={`${h.lost} lost`} />
              <Tile label="Closed deals" value={String(h.closed_deals)} sub={`${h.close_rate}% of leads`} tone="indigo" />
              <Tile label="Revenue" value={formatCurrency(Number(h.revenue))} sub="net of discount" tone="emerald" />
              <Tile label="Collected" value={formatCurrency(Number(h.collected))} sub="money in" tone="emerald" />
              <Tile label="Outstanding" value={formatCurrency(Number(h.outstanding))} sub="still owed" tone="amber" />
              <Tile label="Projects done" value={String(h.completed_projects)} sub="all time" />
            </div>

            <div className="grid lg:grid-cols-[1.6fr_1fr] gap-5 mb-5">
              <Panel title="Leads and revenue" subtitle={`Month by month · ${d.period_label}`}>
                <div className="h-[280px]" id="cp-chart">
                  {chart.length === 0 ? (
                    <p className="py-20 text-center text-sm text-slate-400">Nothing in this window.</p>
                  ) : (
                    <ResponsiveContainer width="100%" height="100%">
                      <ComposedChart data={chart} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                        <XAxis dataKey="name" axisLine={false} tickLine={false}
                          tick={{ fontSize: 11, fill: "#94a3b8", fontWeight: 500 }} dy={8} />
                        <YAxis yAxisId="l" axisLine={false} tickLine={false}
                          tick={{ fontSize: 11, fill: "#94a3b8" }} />
                        <YAxis yAxisId="r" orientation="right" axisLine={false} tickLine={false}
                          tick={{ fontSize: 11, fill: "#94a3b8" }}
                          tickFormatter={(v: number) => (v >= 1000 ? `₹${(v / 1000).toFixed(0)}k` : `₹${v}`)} />
                        <Tooltip cursor={{ fill: "#f8fafc" }}
                          contentStyle={{ borderRadius: 12, border: "1px solid #e2e8f0", fontWeight: 600, fontSize: 12 }}
                          formatter={(v: any, n: any) => (n === "Revenue" ? formatCurrency(Number(v)) : v)} />
                        <Legend wrapperStyle={{ fontSize: 11, fontWeight: 600 }} />
                        <Bar yAxisId="l" dataKey="Leads" fill="#a5b4fc" radius={[6, 6, 0, 0]} maxBarSize={26} />
                        <Bar yAxisId="r" dataKey="Revenue" fill="#10b981" radius={[6, 6, 0, 0]} maxBarSize={26} />
                        {/* The pace of the year, on the same axis as the months
                            it is made of. */}
                        <Line yAxisId="r" type="monotone" dataKey="Running total" stroke="#1e293b"
                          strokeWidth={2} dot={{ r: 2.5, fill: "#1e293b" }} activeDot={{ r: 4 }} />
                      </ComposedChart>
                    </ResponsiveContainer>
                  )}
                </div>
              </Panel>

              <Panel title="Where the business falls away"
                subtitle="Each step is a subset of the one above it">
                <div className="space-y-2.5">
                  {(d.funnel || []).map((f: Row) => (
                    <div key={f.stage}>
                      <div className="flex items-baseline justify-between text-[12px] mb-1">
                        <span className="font-semibold text-slate-700">{f.stage}</span>
                        <span className="tabular-nums text-slate-500">
                          <b className="text-slate-800">{f.count}</b> · {f.of_leads}%
                        </span>
                      </div>
                      <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                        <div className="h-full rounded-full bg-indigo-500 transition-all duration-700"
                          style={{ width: `${Math.max(2, f.of_leads)}%` }} />
                      </div>
                    </div>
                  ))}
                </div>
                <div className="mt-4 pt-4 border-t border-slate-50 grid grid-cols-2 gap-3 text-[12px]">
                  <div>
                    <p className="text-slate-400">Average deal</p>
                    <p className="font-bold text-slate-800 tabular-nums">{formatCurrency(Number(h.avg_deal_value))}</p>
                  </div>
                  <div>
                    <p className="text-slate-400">Average days to close</p>
                    <p className="font-bold text-slate-800 tabular-nums">{h.avg_days_to_close}</p>
                  </div>
                </div>
              </Panel>
            </div>

            <div className="grid lg:grid-cols-2 gap-5 mb-5">
              <CollectionPanel c={d.collection} />
              <DeliveryPanel d={d.delivery} />
            </div>

            <div className="grid lg:grid-cols-2 gap-5 mb-5">
              <Panel title="Where deals are lost"
                subtitle="Counted by when they were written off, not when they arrived"
                right={<span className="text-[11px] text-slate-400">
                  {d.lost?.count || 0} lost
                  {/* Only when there is a figure: "1 lost - 0" reads as a bug. */}
                  {Number(d.lost?.value || 0) > 0 && <> · {formatCurrency(Number(d.lost.value))}</>}
                </span>}>
                <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2.5">Reason</p>
                <MiniBars colour="#f43f5e"
                  rows={(d.lost?.reasons || []).map((r: Row) => ({
                    name: r.name, value: r.count,
                    note: Number(r.value) > 0 ? formatCurrency(Number(r.value)) : undefined,
                  }))} />
                <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mt-5 mb-2.5">
                  How far they got
                </p>
                {/* The stage is the useful part: losing at tele caller is a
                    qualification problem, losing at accounts is a pricing one. */}
                <MiniBars colour="#fb923c"
                  rows={(d.lost?.by_stage || []).map((r: Row) => ({
                    name: r.label, value: r.count,
                    note: Number(r.value) > 0 ? formatCurrency(Number(r.value)) : undefined,
                  }))} />
              </Panel>

              <Panel title="What we sell"
                subtitle="Recorded at the site visit, so deals without one show as not recorded">
                <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2.5">
                  Connection type
                </p>
                <MiniBars colour="#0ea5e9" unit={v => formatCurrency(v)}
                  rows={(d.segments?.by_connection || []).map((r: Row) => ({
                    name: r.name, value: Number(r.revenue), note: `${r.count} deal${r.count === 1 ? "" : "s"}`,
                  }))} />
                <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mt-5 mb-2.5">
                  Roof type
                </p>
                <MiniBars colour="#8b5cf6" unit={v => formatCurrency(v)}
                  rows={(d.segments?.by_roof || []).map((r: Row) => ({
                    name: r.name, value: Number(r.revenue), note: `${r.count} deal${r.count === 1 ? "" : "s"}`,
                  }))} />
              </Panel>
            </div>

            <div className="grid lg:grid-cols-2 gap-5 mb-5">
              <RankedPanel title="Branches" subtitle="Ranked by revenue in this window"
                data={d.branches} unit="branches" one="branch" />
              <RankedPanel title="Teams" subtitle="Ranked by revenue in this window"
                data={d.teams} unit="teams" one="team" />
            </div>

            <div className="mb-5">
              <PeoplePanel data={d} />
            </div>

            <div className="grid lg:grid-cols-3 gap-5">
              <Panel title="Where the work is sitting" subtitle="Right now, whatever the window">
                <div className="space-y-2">
                  {(d.pipeline || []).map((p: Row) => (
                    <div key={p.stage} className="flex items-center justify-between text-[12px]">
                      <span className="text-slate-600">{p.label}</span>
                      <span className="font-bold text-slate-800 tabular-nums">{p.count}</span>
                    </div>
                  ))}
                  {(d.pipeline || []).length === 0 && (
                    <p className="py-4 text-center text-sm text-slate-400">Nothing in the pipeline.</p>
                  )}
                </div>
              </Panel>

              {([["Sources", d.sources], ["Districts", d.districts]] as const).map(([title, rows]) => (
                <Panel key={title} title={title} subtitle="By revenue">
                  <div className="space-y-2">
                    {(rows || []).slice(0, 8).map((r: Row) => (
                      <div key={r.name} className="flex items-center justify-between gap-3 text-[12px]">
                        <span className="text-slate-600 truncate">{r.name}</span>
                        <span className="flex items-center gap-3 flex-shrink-0">
                          <span className="text-slate-400 tabular-nums">{r.leads} leads</span>
                          <span className="font-bold text-slate-800 tabular-nums">
                            {formatCurrency(Number(r.revenue))}
                          </span>
                        </span>
                      </div>
                    ))}
                    {(rows || []).length === 0 && (
                      <p className="py-4 text-center text-sm text-slate-400">Nothing yet.</p>
                    )}
                  </div>
                </Panel>
              ))}
            </div>

            <p className="mt-5 text-[11px] text-slate-400">
              Won means closed — a deal counts once the money has reached accounts — and revenue is
              the agreed value less any discount. The same rule the dashboard, the leaderboard and
              the <Link href="/closed-deals" className="font-semibold text-indigo-600 hover:text-indigo-800">Closed Deals</Link> board use.
            </p>
          </>
        )}
      </div>
    </div>
  );
}

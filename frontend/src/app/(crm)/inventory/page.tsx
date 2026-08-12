"use client";
/**
 * Inventory → Dashboard (wholesale).
 *
 * Deliberately the same layout as the retail inventory dashboard: five KPI cards,
 * a six-month purchases-vs-sales chart, a low-stock panel, then pipeline cards.
 * The figures come from the stock register, where closing stock is derived from
 * movements rather than stored.
 */
import React, { useMemo, useState } from "react";
import Link from "next/link";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend,
} from "recharts";
import { rupee, num, useStock, StockPage, Panel, Empty, I, FIELD } from "./shared";
import { exportInventoryDashboardPdf } from "./dashboardPdf";

type Period = "all" | "this_month" | "this_year" | "custom";

const PERIODS: { key: Period; label: string }[] = [
  { key: "all", label: "All time" },
  { key: "this_month", label: "This month" },
  { key: "this_year", label: "This year" },
  { key: "custom", label: "Custom" },
];

const STATUS_STYLE: Record<string, string> = {
  draft: "bg-slate-100 text-slate-600",
  sent: "bg-sky-50 text-sky-700",
  accepted: "bg-emerald-50 text-emerald-700",
  declined: "bg-rose-50 text-rose-700",
  converted: "bg-indigo-50 text-indigo-700",
};

export default function StockDashboardPage() {
  const [period, setPeriod] = useState<Period>("this_month");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [exporting, setExporting] = useState(false);

  // A custom range with neither end chosen would ask the server for everything
  // twice over, so it waits until there is something to ask for.
  const query = useMemo(() => {
    const q = new URLSearchParams({ period });
    if (period === "custom") {
      if (!from && !to) return "period=all";
      if (from) q.append("from", from);
      if (to) q.append("to", to);
    }
    return q.toString();
  }, [period, from, to]);

  const { summary, loading, denied } = useStock(["summary"], "dashboard", query);
  const d = summary || null;

  const exportPdf = async () => {
    if (!d) return;
    setExporting(true);
    try { await exportInventoryDashboardPdf(d); }
    catch { alert("Could not build the PDF."); }
    finally { setExporting(false); }
  };

  const chart = ((d?.monthly || []) as any[]).map(m => ({
    name: m.name, Purchases: Number(m.purchases), Sales: Number(m.sales),
  }));
  const alerts: any[] = d?.reorder_alerts || [];

  return (
    <StockPage title="Inventory Dashboard" loading={loading} denied={denied}
      subtitle="Stock on hand, and where the quotes, receipts and dispatches stand."
      action={
        <button onClick={exportPdf} disabled={!d || exporting}
          className="flex items-center gap-1.5 px-4 py-2 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 active:scale-[0.97] transition-all disabled:opacity-50">
          <I.Download /> {exporting ? "Building…" : "Export PDF"}
        </button>
      }>

      {/* Period. Governs the movement figures — the quotes, receipts and
          dispatches. Stock on hand is what is on the shelf now and does not
          move with it, which the note below spells out. */}
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
            <input type="date" value={from} max={to || undefined} onChange={e => setFrom(e.target.value)}
              aria-label="From date" className={`${FIELD} !w-auto !py-1.5 text-xs`} />
            <span className="text-xs text-slate-400">to</span>
            <input type="date" value={to} min={from || undefined} onChange={e => setTo(e.target.value)}
              aria-label="To date" className={`${FIELD} !w-auto !py-1.5 text-xs`} />
          </div>
        )}
        {d?.period_label && (
          <span className="ml-auto text-[11px] text-slate-400">
            Movements: <b className="text-slate-600">{d.period_label}</b> · stock on hand is current
          </span>
        )}
      </div>

      {!d ? <Empty text="No stock data yet." /> : (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 mb-6">
            <Metric label="Items" value={d.sku_count ?? 0} href="/inventory/items" />
            <Metric label="Stock Value" value={rupee(d.total_value)} accent />
            <Metric label="Low Stock" value={d.reorder_count ?? 0} warn={(d.reorder_count ?? 0) > 0} href="/inventory/items" />
            <Metric label="Open Quotes" value={rupee(d.open_quote_value)} href="/inventory/quotes" />
            <Metric label="Dispatched" value={rupee(d.period_sales)} href="/inventory/dispatch" />
          </div>

          <div className="grid lg:grid-cols-[1.5fr_1fr] gap-5">
            <Panel title="Purchases vs sales" subtitle={`Movement value · ${d.period_label || ""}`}>
              <div className="h-[270px]">
                {chart.length === 0 ? <Empty text="No movements yet." /> : (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={chart} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                      <XAxis dataKey="name" axisLine={false} tickLine={false}
                        tick={{ fontSize: 11, fill: "#94a3b8", fontWeight: 500 }} dy={8} />
                      <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 11, fill: "#94a3b8", fontWeight: 500 }}
                        tickFormatter={(v: number) => (v >= 1000 ? `₹${(v / 1000).toFixed(0)}k` : `₹${v}`)} />
                      <Tooltip cursor={{ fill: "#f8fafc" }}
                        contentStyle={{ borderRadius: 12, border: "1px solid #e2e8f0", fontWeight: 600, fontSize: 12 }}
                        formatter={(v: any) => rupee(v)} />
                      <Legend wrapperStyle={{ fontSize: 11, fontWeight: 600 }} />
                      <Bar dataKey="Purchases" fill="#f59e0b" radius={[6, 6, 0, 0]} maxBarSize={26} />
                      <Bar dataKey="Sales" fill="#6366f1" radius={[6, 6, 0, 0]} maxBarSize={26} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>
            </Panel>

            <Panel title="Low stock" subtitle="At or below the reorder level"
              right={<Link href="/inventory/items" className="text-[11px] font-semibold text-indigo-600 hover:text-indigo-800">Open item master →</Link>}>
              {alerts.length === 0 ? (
                <p className="flex items-center justify-center gap-2 text-sm font-medium text-emerald-600 py-6">
                  <I.Check /> All items above their reorder level.
                </p>
              ) : (
                <div className="divide-y divide-slate-50 -mt-1">
                  {alerts.map(a => (
                    <div key={a.id} className="flex items-center justify-between py-2.5 gap-3">
                      <div className="min-w-0">
                        <p className="text-[13px] font-mono font-semibold text-slate-800 truncate">{a.code}</p>
                        <p className="text-[11px] text-slate-400 truncate">{`${a.brand} ${a.model_name}`.trim() || "—"}</p>
                      </div>
                      <div className="text-right flex-shrink-0">
                        <p className="text-[13px] font-bold text-rose-600 tabular-nums">{num(a.closing_stock)} {a.unit}</p>
                        <p className="text-[10px] text-slate-400 tabular-nums">reorder at {num(a.reorder_level)}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Panel>
          </div>

          <div className="grid md:grid-cols-3 gap-5 mt-5">
            <Pipeline title="Quotes" href="/inventory/quotes" total={d.quote_count} counts={d.quote_status}
              footer={<>Open value <b className="text-slate-700">{rupee(d.open_quote_value)}</b></>} />
            <Pipeline title="Sales / Dispatches" href="/inventory/dispatch" total={d.dispatch_count}
              footer={<>Dispatched <b className="text-slate-700">{rupee(d.period_sales)}</b> · {d.customer_count ?? 0} customers</>} />
            {/* Counts the stock received to date; the module itself is now the
                purchase orders raised on suppliers. */}
            <Pipeline title="Purchases" href="/inventory/purchase-orders" total={d.receipt_count}
              footer={<>Received <b className="text-slate-700">{rupee(d.period_purchases)}</b> · {d.supplier_count ?? 0} suppliers</>} />
          </div>
        </>
      )}
    </StockPage>
  );
}

/* ── bits ─────────────────────────────────────────────────────────────────── */

function Metric({ label, value, accent, warn, href }: {
  label: string; value: any; accent?: boolean; warn?: boolean; href?: string;
}) {
  const card = (
    <div className={`bg-white border border-slate-200 rounded-2xl p-4 border-t-4 h-full ${
      warn ? "border-t-rose-500" : accent ? "border-t-indigo-500" : "border-t-slate-300"} ${
      href ? "hover:shadow-md transition-shadow" : ""}`}>
      <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">{label}</p>
      <p className={`text-xl font-bold mt-1.5 tabular-nums ${warn ? "text-rose-600" : "text-slate-900"}`}>{value}</p>
    </div>
  );
  return href ? <Link href={href}>{card}</Link> : card;
}

function Pipeline({ title, href, total, counts, footer }: {
  title: string; href: string; total?: number; counts?: Record<string, number>; footer?: React.ReactNode;
}) {
  const entries = Object.entries(counts || {});
  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-5">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-bold text-slate-900">{title}</h2>
        <Link href={href} className="text-[11px] font-semibold text-indigo-600 hover:text-indigo-800">Open →</Link>
      </div>
      <p className="text-2xl font-bold text-slate-900 tabular-nums">{total ?? 0}</p>
      <p className="text-[11px] text-slate-400 mb-3">total records</p>
      {entries.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {entries.map(([status, n]) => (
            <span key={status}
              className={`text-[10px] font-bold uppercase tracking-wide px-2 py-1 rounded-full ${STATUS_STYLE[status] || "bg-slate-100 text-slate-600"}`}>
              {status} {n}
            </span>
          ))}
        </div>
      )}
      {footer && <p className="text-[11px] text-slate-400 mt-3 pt-3 border-t border-slate-50">{footer}</p>}
    </div>
  );
}

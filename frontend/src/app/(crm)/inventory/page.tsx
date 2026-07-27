"use client";
import React from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from "recharts";
import { I, rupee, num, useStock, StockPage, Panel, Empty } from "../inventory/shared";

export default function InventoryDashboardPage() {
  const { summary, loading, denied } = useStock(["summary"]);

  return (
    <StockPage title="Inventory Dashboard" loading={loading} denied={denied}
      subtitle="Live snapshot of stock, value, and this month's movement.">
      {!summary ? <Empty text="No stock data yet." /> : <Dashboard summary={summary} />}
    </StockPage>
  );
}

function Dashboard({ summary }: { summary: any }) {
  const alerts = summary.reorder_alerts || [];

  return (
    <div>
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 mb-6">
        <Metric label="Total SKUs" value={summary.sku_count} />
        <Metric label="Total Stock Value" value={rupee(summary.total_value)} accent />
        <Metric label="Needs Reorder" value={summary.reorder_count} warn={summary.reorder_count > 0} />
        <Metric label="This Month Purchases" value={rupee(summary.month_purchases)} />
        <Metric label="This Month Dispatch" value={rupee(summary.month_sales)} />
      </div>

      <div className="grid lg:grid-cols-[1.4fr_1fr] gap-5">
        <Panel title="Stock value by category">
          <div className="h-[260px]">
            {(summary.by_category || []).length === 0 ? <Empty text="Add items to see the split." /> : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={(summary.by_category || []).map((c: any) => ({ name: c.name, value: Number(c.value) }))}
                  margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                  <XAxis dataKey="name" axisLine={false} tickLine={false} interval={0}
                    tick={{ fontSize: 10, fill: "#94a3b8", fontWeight: 500 }} dy={8} />
                  <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 11, fill: "#94a3b8", fontWeight: 500 }}
                    tickFormatter={(v: number) => (v >= 1000 ? `₹${(v / 1000).toFixed(0)}k` : `₹${v}`)} />
                  <Tooltip cursor={{ fill: "#f8fafc" }}
                    contentStyle={{ borderRadius: 12, border: "1px solid #e2e8f0", fontWeight: 600, fontSize: 12 }}
                    formatter={(v: any) => [rupee(v), "Stock value"]} />
                  <Bar dataKey="value" fill="#6366f1" radius={[6, 6, 0, 0]} maxBarSize={54} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </Panel>

        <Panel title="Reorder alerts"
          right={<span className={alerts.length ? "text-rose-500" : "text-slate-300"}><I.Alert /></span>}>
          {alerts.length === 0 ? (
            <p className="flex items-center gap-2 text-sm font-medium text-emerald-600 mt-2"><I.Check /> All stock levels healthy</p>
          ) : (
            <div className="divide-y divide-slate-50">
              {alerts.map((a: any) => (
                <div key={a.id} className="flex items-center justify-between py-2.5">
                  <div className="min-w-0">
                    <p className="text-[13px] font-mono font-semibold text-slate-800 truncate">{a.code}</p>
                    <p className="text-[11px] text-slate-400 truncate">{`${a.brand} ${a.model_name}`.trim() || "—"}</p>
                  </div>
                  <div className="text-right flex-shrink-0 pl-3">
                    <p className="text-[13px] font-bold text-rose-600 tabular-nums">{num(a.closing_stock)} {a.unit}</p>
                    <p className="text-[10px] text-slate-400 tabular-nums">reorder at {num(a.reorder_level)}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Panel>
      </div>

      <div className="mt-5">
        <Panel title="Stock levels">
          {(summary.stock_levels || []).length === 0 ? <Empty text="No items yet." /> : (
            <div className="space-y-2.5 mt-1">
              {summary.stock_levels.map((r: any) => <Gauge key={r.id} row={r} />)}
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}

function Gauge({ row }: { row: any }) {
  // Full bar = three times the reorder level, so the marker sits at a third and
  // "comfortable" reads as visibly past it.
  const target = Number(row.reorder_level) * 3 || Math.max(Number(row.closing_stock), 1);
  const pct = Math.max(0, Math.min(100, (Number(row.closing_stock) / target) * 100));
  const markerPct = Math.min(100, (Number(row.reorder_level) / target) * 100);
  const low = row.status === "REORDER";
  return (
    <div className="grid grid-cols-[130px_1fr_100px] gap-3 items-center">
      <span className="text-xs font-mono font-semibold text-slate-700 truncate">{row.code}</span>
      <div className="relative h-2.5 bg-slate-100 rounded-full overflow-hidden">
        <div className={`absolute inset-y-0 left-0 rounded-full transition-all duration-500 ${low ? "bg-rose-500" : "bg-emerald-500"}`}
          style={{ width: `${pct}%` }} />
        <div className="absolute inset-y-0 w-0.5 bg-slate-400" style={{ left: `${markerPct}%` }} title="Reorder level" />
      </div>
      <span className={`text-xs font-semibold tabular-nums text-right ${low ? "text-rose-600" : "text-slate-500"}`}>
        {num(row.closing_stock)} {row.unit}
      </span>
    </div>
  );
}

function Metric({ label, value, accent, warn }: { label: string; value: any; accent?: boolean; warn?: boolean }) {
  return (
    <div className={`bg-white border border-slate-200 rounded-2xl p-4 border-t-4 ${warn ? "border-t-rose-500" : accent ? "border-t-indigo-500" : "border-t-slate-300"}`}>
      <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">{label}</p>
      <p className={`text-xl font-bold mt-1.5 tabular-nums ${warn ? "text-rose-600" : "text-slate-900"}`}>{value}</p>
    </div>
  );
}

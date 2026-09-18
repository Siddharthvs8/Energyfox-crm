"use client";
/**
 * Inventory Dashboard — the overview screen for the retail inventory module:
 * item stock plus the quote, dispatch and purchase pipelines.
 * (The wholesale side has its own dashboard under B2B → Inventory.)
 */
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend,
} from "recharts";

/** Money. Shows paise only when there are any, so ₹90,000 stays clean while
 *  ₹2,252.25 keeps its fraction instead of being rounded to ₹2,252. */
const rupee = (n: any) => {
  const v = Number(n || 0);
  return "₹" + v.toLocaleString("en-IN", {
    minimumFractionDigits: Number.isInteger(v) ? 0 : 2,
    maximumFractionDigits: 2,
  });
};
const num = (n: any) => Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 });

/** Status pill colours, shared by all three document types. */
const STATUS_STYLE: Record<string, string> = {
  draft: "bg-slate-100 text-slate-600",
  sent: "bg-sky-50 text-sky-700",
  accepted: "bg-emerald-50 text-emerald-700",
  declined: "bg-rose-50 text-rose-700",
  converted: "bg-indigo-50 text-indigo-700",
  ordered: "bg-amber-50 text-amber-700",
  received: "bg-emerald-50 text-emerald-700",
  cancelled: "bg-rose-50 text-rose-700",
  confirmed: "bg-sky-50 text-sky-700",
  shipped: "bg-violet-50 text-violet-700",
  delivered: "bg-emerald-50 text-emerald-700",
};

export default function InventoryDashboardPage() {
  const domain = APP_SLUG;
  const router = useRouter();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [denied, setDenied] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem(`${domain}_access`);
    if (!token) { router.push(`/login`); return; }
    fetch(`${getApiBase(domain)}/api/inventory-dashboard/`, { headers: { Authorization: `Bearer ${token}` } })
      .then(async r => {
        if (r.status === 403) { setDenied(true); return null; }
        return r.ok ? r.json() : null;
      })
      .then(d => { if (d) setData(d); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [domain]); // eslint-disable-line react-hooks/exhaustive-deps

  if (loading) return (
    <div className="p-8 flex items-center justify-center h-full">
      <div className="w-8 h-8 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
    </div>
  );

  if (denied) return (
    <div className="max-w-2xl mx-auto p-4 sm:p-8">
      <div className="bg-white border border-slate-200 rounded-2xl p-8 text-center">
        <h1 className="text-lg font-bold text-slate-900">Inventory Dashboard</h1>
        <p className="text-sm text-slate-500 mt-1">This module is for admins and general managers.</p>
      </div>
    </div>
  );

  const chart = (data?.monthly || []).map((m: any) => ({
    name: m.name, Purchases: Number(m.purchases), Sales: Number(m.sales),
  }));

  return (
    <div className="max-w-7xl mx-auto p-4 sm:p-6 lg:p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Inventory Dashboard</h1>
        <p className="text-sm text-slate-500 mt-1">Stock on hand, and where the quotes, orders and purchases stand.</p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 mb-6">
        <Metric label="Items" value={data?.product_count ?? 0} href="/products" />
        <Metric label="Stock Value" value={rupee(data?.stock_value)} accent />
        <Metric label="Low Stock" value={data?.low_stock_count ?? 0} warn={(data?.low_stock_count ?? 0) > 0} href="/products" />
        <Metric label="Open Quotes" value={rupee(data?.open_quote_value)} href="/quotes" />
        <Metric label="Open Orders" value={rupee(data?.open_sales_value)} href="/sales-orders" />
      </div>

      <div className="grid lg:grid-cols-[1.5fr_1fr] gap-5">
        <Panel title="Purchases vs sales" subtitle="Document value, last 6 months">
          <div className="h-[270px]">
            {chart.length === 0 ? <Empty text="No documents yet." /> : (
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
          action={<Link href="/products" className="text-[11px] font-semibold text-indigo-600 hover:text-indigo-800">Open item master →</Link>}>
          {(data?.low_stock || []).length === 0 ? (
            <p className="text-sm font-medium text-emerald-600 py-6 text-center">All items above their reorder level.</p>
          ) : (
            <div className="divide-y divide-slate-50 -mt-1">
              {data.low_stock.map((p: any) => (
                <div key={p.id} className="flex items-center justify-between py-2.5 gap-3">
                  <div className="min-w-0">
                    <p className="text-[13px] font-semibold text-slate-800 truncate">{p.name}</p>
                    {p.sku && <p className="text-[11px] font-mono text-slate-400 truncate">{p.sku}</p>}
                  </div>
                  <div className="text-right flex-shrink-0">
                    <p className="text-[13px] font-bold text-rose-600 tabular-nums">{num(p.stock_quantity)} {p.unit}</p>
                    <p className="text-[10px] text-slate-400 tabular-nums">reorder at {num(p.reorder_level)}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Panel>
      </div>

      <div className="grid md:grid-cols-3 gap-5 mt-5">
        <Pipeline title="Quotes" href="/quotes" total={data?.quote_count} counts={data?.quote_status}
          footer={<>Open value <b className="text-slate-700">{rupee(data?.open_quote_value)}</b></>} />
        <Pipeline title="Sales / Dispatches" href="/sales-orders" total={data?.sales_order_count} counts={data?.sales_order_status}
          footer={<>Open value <b className="text-slate-700">{rupee(data?.open_sales_value)}</b></>} />
        <Pipeline title="Purchases" href="/purchase-orders" total={data?.purchase_order_count} counts={data?.purchase_order_status}
          footer={<>Committed <b className="text-slate-700">{rupee(data?.open_purchase_value)}</b> · {data?.vendor_count ?? 0} suppliers</>} />
      </div>
    </div>
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

function Panel({ title, subtitle, children, action }: {
  title: string; subtitle?: string; children: React.ReactNode; action?: React.ReactNode;
}) {
  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-5">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div>
          <h2 className="text-sm font-bold text-slate-900">{title}</h2>
          {subtitle && <p className="text-[11px] text-slate-400 mt-0.5">{subtitle}</p>}
        </div>
        {action}
      </div>
      {children}
    </div>
  );
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
      <p className="text-[11px] text-slate-400 mb-3">total documents</p>
      {entries.length === 0 ? (
        <p className="text-xs text-slate-400">Nothing raised yet.</p>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {entries.map(([status, n]) => (
            <span key={status}
              className={`text-[10px] font-bold uppercase tracking-wide px-2 py-1 rounded-full ${STATUS_STYLE[status] || "bg-slate-100 text-slate-600"}`}>
              {status.replace(/_/g, " ")} {n}
            </span>
          ))}
        </div>
      )}
      {footer && <p className="text-[11px] text-slate-400 mt-3 pt-3 border-t border-slate-50">{footer}</p>}
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return <p className="text-sm text-slate-400 text-center py-10">{text}</p>;
}

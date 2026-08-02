"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase, formatCurrency } from "@/lib/mock-data";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import DeletedLeadCleanup, { DeletedLeadBadge } from "@/components/DeletedLeadCleanup";
type PurchaseLead = {
  // Set when the lead behind this row has been deleted; the row is then
  // unopenable, and an admin gets a control to clear it out.
  lead_deleted?: boolean;
  can_cleanup?: boolean;
  id: number;
  first_name: string;
  last_name: string | null;
  phone: string | null;
  location: string | null;
  product_name: string | null;
  value: number;
  purchase_staff_name: string | null;
  purchase_complete: boolean;
  /** Which payment bucket the customer is in — null before any verification. */
  payment_state: "partially_paid" | "fully_paid" | null;
  balance_amount: number | null;
  amount_received: number | null;
};

export default function PurchasePage() {
  const domain = APP_SLUG;
  const router = useRouter();
  const [authChecked, setAuthChecked] = useState(false);
  const [allowed, setAllowed] = useState(false);
  const [leads, setLeads] = useState<PurchaseLead[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  // Procurement starts on a part payment, so the queue holds both — this splits them.
  const [payment, setPayment] = useState<"all" | "partially_paid" | "fully_paid">("all");

  const token = () => localStorage.getItem(`${domain}_access`);

  useEffect(() => {
    const t = token();
    if (!t) { router.push("/login"); return; }
    fetch(`${getApiBase(domain)}/api/users/me/`, { headers: { Authorization: `Bearer ${t}` } })
      .then(r => r.json())
      .then(d => {
        const ok = d.role === "purchase_staff" || d.is_staff || d.is_general_manager;
        setAllowed(ok);
        setAuthChecked(true);
        if (!ok) router.replace("/");
      })
      .catch(() => setAuthChecked(true));
  }, [domain, router]);

  useEffect(() => {
    if (!allowed) return;
    fetch(`${getApiBase(domain)}/api/leads/purchase/`, { headers: { Authorization: `Bearer ${token()}` } })
      .then(r => (r.ok ? r.json() : []))
      .then(d => setLeads(Array.isArray(d) ? d : []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [allowed, domain]);

  if (!authChecked) return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="w-8 h-8 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
    </div>
  );
  if (!allowed) return null;

  const counts = {
    all: leads.length,
    partially_paid: leads.filter(l => l.payment_state === "partially_paid").length,
    fully_paid: leads.filter(l => l.payment_state === "fully_paid").length,
  };

  const filtered = leads.filter(l => {
    if (payment !== "all" && l.payment_state !== payment) return false;
    const q = search.trim().toLowerCase();
    if (!q) return true;
    return (`${l.first_name} ${l.last_name || ""}`.toLowerCase().includes(q)
      || (l.phone || "").toLowerCase().includes(q)
      || (l.location || "").toLowerCase().includes(q));
  });

  const TABS: { key: typeof payment; label: string }[] = [
    { key: "all", label: "All" },
    { key: "partially_paid", label: "Partially Paid" },
    { key: "fully_paid", label: "Fully Paid" },
  ];

  return (
    <div className="p-6 lg:p-8 max-w-[1200px]">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Purchase &amp; Logistics</h1>
        <p className="text-sm text-slate-500 mt-1">Customers who have paid — in part or in full — ready for procurement. Open one to track structure material, BOM and pending items.</p>
      </div>

      <div className="flex gap-1 mb-5 border-b border-slate-200 overflow-x-auto no-scrollbar">
        {TABS.map(t => (
          <button key={t.key} onClick={() => setPayment(t.key)}
            className={`flex items-center gap-2 px-4 py-2.5 text-sm font-semibold whitespace-nowrap border-b-2 -mb-px transition-colors ${
              payment === t.key ? "border-indigo-600 text-indigo-600" : "border-transparent text-slate-500 hover:text-slate-800"}`}>
            {t.label}
            <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full ${
              payment === t.key ? "bg-indigo-50 text-indigo-700" : "bg-slate-100 text-slate-500"}`}>
              {counts[t.key]}
            </span>
          </button>
        ))}
      </div>

      <div className="mb-5 flex items-center gap-3">
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search by name, phone or location…"
          className="w-full max-w-md bg-white border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all"
        />
        <span className="text-xs font-semibold text-slate-400">{filtered.length} customer{filtered.length === 1 ? "" : "s"}</span>
      </div>

      {loading ? (
        <div className="py-16 text-center text-sm text-slate-400">Loading…</div>
      ) : filtered.length === 0 ? (
        <div className="bg-white border border-dashed border-slate-200 rounded-2xl p-12 text-center text-sm text-slate-400">
          {payment === "all"
            ? "No customers in purchase & logistics yet."
            : `No ${payment === "fully_paid" ? "fully" : "partially"} paid customers here yet.`}
        </div>
      ) : (
        <div className="space-y-4">
          {filtered.map(l => (
            <Link key={l.id} href={`/purchase/${l.id}`} className="block bg-white border border-slate-200 rounded-2xl shadow-sm px-5 py-4 hover:bg-slate-50/60 hover:border-indigo-200 transition-colors">
              <div className="flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-bold text-slate-900 truncate">{l.first_name} {l.last_name}</p>
                    {l.lead_deleted && <DeletedLeadBadge />}
                    <span className={`text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full ${l.purchase_complete ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>
                      {l.purchase_complete ? "Done" : "Pending"}
                    </span>
                    {l.payment_state && (
                      <span className={`text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full ${
                        l.payment_state === "fully_paid" ? "bg-emerald-50 text-emerald-700" : "bg-sky-50 text-sky-700"}`}>
                        {l.payment_state === "fully_paid" ? "Fully Paid" : "Partially Paid"}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-slate-500 mt-0.5 truncate">{l.phone || "—"} · {l.location || "No location"}{l.product_name ? ` · ${l.product_name}` : ""}</p>
                </div>
                <div className="flex items-center gap-4 flex-shrink-0">
                  <div className="hidden sm:block text-right">
                    <p className="text-[10px] text-slate-400 uppercase tracking-wide">Deal Value</p>
                    <p className="text-xs font-semibold text-slate-700">{l.value ? `₹${formatCurrency(l.value)}` : "—"}</p>
                  </div>
                  {l.payment_state === "partially_paid" && (
                    <div className="hidden lg:block text-right">
                      <p className="text-[10px] text-slate-400 uppercase tracking-wide">Balance Due</p>
                      <p className="text-xs font-semibold text-sky-700">₹{formatCurrency(l.balance_amount || 0)}</p>
                    </div>
                  )}
                  <div className="hidden md:block text-right">
                    <p className="text-[10px] text-slate-400 uppercase tracking-wide">Purchase Staff</p>
                    <p className="text-xs font-semibold text-slate-600">{l.purchase_staff_name || "Unassigned"}</p>
                  </div>
                  {l.can_cleanup && (
                    <DeletedLeadCleanup leadId={l.id} module="purchase"
                      name={`${l.first_name} ${l.last_name || ""}`.trim()}
                      onRemoved={() => setLeads(prev => prev.filter(x => x.id !== l.id))} />
                  )}
                  <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" className="text-slate-300"><polyline points="9 18 15 12 9 6" /></svg>
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

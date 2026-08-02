"use client";
import { getApiBase, formatCurrency } from "@/lib/mock-data";
import { APP_SLUG } from "@/lib/config";

import React, { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import PurchaseLogisticsSection from "./PurchaseLogisticsSection";

import ActivityTimeline from "@/components/ActivityTimeline";
type PaymentVerification = {
  deal_value: string | number | null;
  amount_received: string | number | null;
  discount_value: string | number | null;
  balance_amount: string | number | null;
  payment_mode: string | null;
  utr_details: string | null;
  discount_given_by: string | null;
  completed_by_name: string | null;
  is_complete: boolean;
} | null;

type PurchaseDetail = {
  id: number;
  first_name: string; last_name: string | null;
  phone: string | null; email: string | null;
  location: string | null; installation_location: string | null;
  product_name: string | null; value: number; status: string;
  bde_name: string | null;
  accounts_staff_name: string | null;
  purchase_staff: number | null;
  purchase_staff_name: string | null;
  pushed_at: string | null;
  payment_verification: PaymentVerification;
  payment_complete: boolean;
  can_edit_purchase: boolean;
  can_assign: boolean;
  can_reopen_purchase: boolean;
};

const PAYMENT_MODE_LABELS: Record<string, string> = { cash: "Cash", cheque: "Cheque", card: "Card", upi: "UPI" };
const money = (v: any) => (v === null || v === undefined || v === "" ? "—" : `₹${formatCurrency(parseFloat(String(v)) || 0)}`);

export default function PurchaseDetailPage({ params: paramsPromise }: { params: Promise<{ id: string }> }) {
  const params = React.use(paramsPromise);
  const id = params.id;
  const domain = APP_SLUG;
  const router = useRouter();

  const [data, setData] = useState<PurchaseDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [staff, setStaff] = useState<{ id: number; name: string; branch_name: string | null }[]>([]);
  const [selectedStaff, setSelectedStaff] = useState("");
  const [assigning, setAssigning] = useState(false);

  const token = () => localStorage.getItem(`${domain}_access`);

  const load = useCallback(async () => {
    const t = token();
    if (!t) { router.push("/login"); return; }
    try {
      const r = await fetch(`${getApiBase(domain)}/api/leads/${id}/purchase-detail/`, { headers: { Authorization: `Bearer ${t}` } });
      if (r.ok) {
        const d = await r.json();
        setData(d);
        setSelectedStaff(d.purchase_staff ? String(d.purchase_staff) : "");
        if (d.can_assign) {
          const sr = await fetch(`${getApiBase(domain)}/api/users/purchase-staff/`, { headers: { Authorization: `Bearer ${t}` } });
          if (sr.ok) setStaff(await sr.json());
        }
      } else if (r.status === 403 || r.status === 404) {
        setError("You don't have access to this customer, or it isn't in purchase & logistics.");
      } else setError("Failed to load.");
    } catch { setError("Network error."); }
    finally { setLoading(false); }
  }, [domain, id, router]);

  useEffect(() => { load(); }, [load]);

  const assign = async () => {
    setAssigning(true);
    try {
      const r = await fetch(`${getApiBase(domain)}/api/leads/${id}/assign-purchase/`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token()}` },
        body: JSON.stringify({ staff: selectedStaff || null }),
      });
      if (r.ok) { await load(); alert("Purchase staff updated."); }
      else { const d = await r.json().catch(() => ({})); alert(d.error || "Failed to assign."); }
    } catch { alert("Network error."); }
    finally { setAssigning(false); }
  };

  if (loading) return <div className="flex items-center justify-center min-h-[60vh]"><div className="w-8 h-8 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" /></div>;
  if (error || !data) return (
    <div className="p-6 lg:p-8 max-w-[900px]">
      <Link href="/purchase" className="text-sm text-indigo-600 hover:underline">← Back to Purchase &amp; Logistics</Link>
      <p className="mt-6 text-sm text-rose-600">{error || "Not found."}</p>
    </div>
  );

  const pv = data.payment_verification;

  return (
    <div className="p-6 lg:p-8 max-w-[1100px]">
      <div className="flex items-center justify-between gap-3">
        <Link href="/purchase" className="text-sm text-indigo-600 hover:underline">← Back to Purchase &amp; Logistics</Link>
        <ActivityTimeline leadId={params.id} />
      </div>

      {/* Header */}
      <div className="mt-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">{data.first_name} {data.last_name}</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {data.phone || "—"}{data.email ? ` · ${data.email}` : ""}{data.location ? ` · ${data.location}` : ""}
          </p>
        </div>
        <div className="text-right">
          <p className="text-[10px] text-slate-400 uppercase tracking-wide">Purchase Staff</p>
          <p className="text-sm font-semibold text-amber-600">{data.purchase_staff_name || "Unassigned"}</p>
        </div>
      </div>

      {/* Assign (admins / general managers) */}
      {data.can_assign && (
        <div className="mt-5 bg-white border border-slate-200 rounded-2xl shadow-sm p-5">
          <h2 className="text-sm font-bold text-slate-900 mb-3">Assign Purchase Staff</h2>
          <div className="flex flex-col sm:flex-row gap-3 sm:items-end">
            <div className="flex-1">
              <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wide mb-1.5">Staff</label>
              <select value={selectedStaff} onChange={e => setSelectedStaff(e.target.value)} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all">
                <option value="">— Unassigned —</option>
                {staff.map(s => <option key={s.id} value={s.id}>{s.name}{s.branch_name ? ` (${s.branch_name})` : ""}</option>)}
              </select>
              {staff.length === 0 && <p className="text-[11px] text-amber-600 mt-1.5">No purchase staff yet — set a user&apos;s role to &quot;Purchase Staff&quot; under Team.</p>}
            </div>
            <button onClick={assign} disabled={assigning} className="px-5 py-2.5 bg-amber-600 text-white rounded-xl text-sm font-semibold hover:bg-amber-700 disabled:opacity-50 transition-all">{assigning ? "Saving…" : "Save"}</button>
          </div>
        </div>
      )}

      {/* Customer details */}
      <div className="mt-5 bg-white border border-slate-200 rounded-2xl shadow-sm p-5">
        <h2 className="text-sm font-bold text-slate-900 mb-4">Customer</h2>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-3">
          <Detail label="Installation Location" value={data.installation_location} />
          <Detail label="Product" value={data.product_name} />
          <Detail label="Deal Value" value={data.value ? `₹${formatCurrency(data.value)}` : null} />
          <Detail label="BDE" value={data.bde_name} />
          <Detail label="Accounts Staff" value={data.accounts_staff_name} />
          <Detail label="Moved to Purchase" value={data.pushed_at ? new Date(data.pushed_at).toLocaleString("en-IN") : null} />
        </div>
      </div>

      {/* Accounts / payment data — read-only, so purchase staff see both stages */}
      <div className="mt-5 bg-white border border-slate-200 rounded-2xl shadow-sm p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-bold text-slate-900">Accounts — Payment</h2>
          <span className={`text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full ${data.payment_complete ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>
            {data.payment_complete ? "Verified" : "Pending"}
          </span>
        </div>
        {pv ? (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-3">
            <Detail label="Deal Value" value={money(pv.deal_value)} />
            <Detail label="Amount Received" value={money(pv.amount_received)} />
            <Detail label="Discount Value" value={money(pv.discount_value)} />
            <Detail label="Balance to be Received" value={money(pv.balance_amount)} />
            <Detail label="Payment Mode" value={pv.payment_mode ? (PAYMENT_MODE_LABELS[pv.payment_mode] || pv.payment_mode) : null} />
            <Detail label="UTR / Transaction" value={pv.utr_details} />
            <Detail label="Discount Given By" value={pv.discount_given_by} />
            <Detail label="Verified By" value={pv.completed_by_name} />
          </div>
        ) : (
          <p className="text-sm text-slate-400">No payment details recorded.</p>
        )}
      </div>

      {/* Purchase & logistics form */}
      <PurchaseLogisticsSection
        leadId={data.id}
        canEdit={data.can_edit_purchase}
        canReopen={data.can_reopen_purchase}
        onChanged={load}
      />
    </div>
  );
}

function Detail({ label, value }: { label: string; value: any }) {
  return (
    <div>
      <p className="text-[10px] text-slate-400 uppercase tracking-wide">{label}</p>
      <p className="text-sm font-medium text-slate-700 break-words">{value === null || value === undefined || value === "" ? "—" : String(value)}</p>
    </div>
  );
}

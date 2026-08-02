"use client";
import { getApiBase, formatCurrency } from "@/lib/mock-data";
import { APP_SLUG } from "@/lib/config";

import React, { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import ActivityTimeline from "@/components/ActivityTimeline";
type LiasoningDetail = {
  id: number;
  first_name: string; last_name: string | null;
  phone: string | null; email: string | null;
  location: string | null; installation_location: string | null;
  product_name: string | null; value: number; status: string;
  bde_name: string | null;
  pushed_at: string | null;
  is_complete: boolean;
  can_edit: boolean;
  record: { completed_by_name: string | null; completed_at: string | null } | null;
};

export default function LiasoningDetailPage({ params: paramsPromise }: { params: Promise<{ id: string }> }) {
  const params = React.use(paramsPromise);
  const id = params.id;
  const domain = APP_SLUG;
  const router = useRouter();

  const [data, setData] = useState<LiasoningDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [completing, setCompleting] = useState(false);

  const token = () => localStorage.getItem(`${domain}_access`);

  const load = useCallback(async () => {
    const t = token();
    if (!t) { router.push("/login"); return; }
    try {
      const r = await fetch(`${getApiBase(domain)}/api/leads/${id}/liasoning-detail/`, { headers: { Authorization: `Bearer ${t}` } });
      if (r.ok) setData(await r.json());
      else if (r.status === 403 || r.status === 404) setError("You don't have access to this customer, or it isn't in liasoning & service.");
      else setError("Failed to load.");
    } catch { setError("Network error."); }
    finally { setLoading(false); }
  }, [domain, id, router]);

  useEffect(() => { load(); }, [load]);

  const complete = async () => {
    if (!window.confirm("Mark Liasoning & Service complete for this customer?")) return;
    setCompleting(true);
    try {
      const r = await fetch(`${getApiBase(domain)}/api/leads/${id}/complete-liasoning/`, { method: "POST", headers: { Authorization: `Bearer ${token()}` } });
      if (r.ok) { setData(await r.json()); }
      else { const d = await r.json().catch(() => ({})); alert(d.error || "Could not complete."); }
    } catch { alert("Network error."); }
    finally { setCompleting(false); }
  };

  if (loading) return <div className="flex items-center justify-center min-h-[60vh]"><div className="w-8 h-8 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" /></div>;
  if (error || !data) return (
    <div className="p-6 lg:p-8 max-w-[900px]">
      <Link href="/liasoning" className="text-sm text-indigo-600 hover:underline">← Back to Liasoning &amp; Service</Link>
      <p className="mt-6 text-sm text-rose-600">{error || "Not found."}</p>
    </div>
  );

  return (
    <div className="p-6 lg:p-8 max-w-[1100px]">
      <div className="flex items-center justify-between gap-3">
        <Link href="/liasoning" className="text-sm text-indigo-600 hover:underline">← Back to Liasoning &amp; Service</Link>
        <ActivityTimeline leadId={params.id} />
      </div>

      <div className="mt-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">{data.first_name} {data.last_name}</h1>
          <p className="text-sm text-slate-500 mt-0.5">{data.phone || "—"}{data.email ? ` · ${data.email}` : ""}{data.location ? ` · ${data.location}` : ""}</p>
        </div>
        {data.is_complete && (
          <span className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-emerald-50 border border-emerald-200 text-emerald-700 rounded-lg text-xs font-semibold">
            ✓ Completed{data.record?.completed_by_name ? ` by ${data.record.completed_by_name}` : ""}
          </span>
        )}
      </div>

      {/* Customer details */}
      <div className="mt-5 bg-white border border-slate-200 rounded-2xl shadow-sm p-5">
        <h2 className="text-sm font-bold text-slate-900 mb-4">Customer</h2>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-3">
          <Detail label="Installation Location" value={data.installation_location} />
          <Detail label="Product" value={data.product_name} />
          <Detail label="Deal Value" value={data.value ? `₹${formatCurrency(data.value)}` : null} />
          <Detail label="BDE" value={data.bde_name} />
          <Detail label="Status" value={data.status} />
          <Detail label="Reached Liasoning" value={data.pushed_at ? new Date(data.pushed_at).toLocaleString("en-IN") : null} />
        </div>
      </div>

      {/* Liasoning & Service work (fields to be added) */}
      <div className="mt-5 bg-white border border-slate-200 rounded-2xl shadow-sm p-5">
        <h2 className="text-base font-bold text-slate-900">Liasoning &amp; Service</h2>
        <p className="text-xs text-slate-400 mt-0.5 mb-4">The liasoning &amp; service fields will be added here.</p>
        {data.can_edit && !data.is_complete && (
          <button onClick={complete} disabled={completing}
            className="px-5 py-2.5 bg-emerald-600 text-white rounded-xl text-sm font-semibold hover:bg-emerald-700 disabled:opacity-50 transition">
            {completing ? "Completing…" : "Mark Complete"}
          </button>
        )}
        {!data.can_edit && <p className="text-xs text-slate-400">Read-only.</p>}
      </div>
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

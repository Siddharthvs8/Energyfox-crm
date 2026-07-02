"use client";
import { getApiBase, formatCurrency } from "@/lib/mock-data";
import { APP_SLUG } from "@/lib/config";

import React, { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import RegistrationFeeSection from "./RegistrationFeeSection";

type CompletedDetail = {
  id: number;
  first_name: string; last_name: string | null;
  phone: string | null; email: string | null;
  location: string | null; installation_location: string | null;
  product_name: string | null; value: number; status: string;
  bde_name: string | null;
  accounts_staff_name: string | null;
  project_manager_name: string | null;
  project_completed_at: string | null;
  rf_pushed: boolean;
  can_edit_rf: boolean;
};

export default function CompletedProjectDetailPage({ params: paramsPromise }: { params: Promise<{ id: string }> }) {
  const params = React.use(paramsPromise);
  const id = params.id;
  const domain = APP_SLUG;
  const router = useRouter();

  const [data, setData] = useState<CompletedDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const token = () => localStorage.getItem(`${domain}_access`);

  const load = useCallback(async () => {
    const t = token();
    if (!t) { router.push("/login"); return; }
    try {
      const r = await fetch(`${getApiBase(domain)}/api/leads/${id}/accounts-completed-detail/`, { headers: { Authorization: `Bearer ${t}` } });
      if (r.ok) {
        setData(await r.json());
      } else if (r.status === 403 || r.status === 404) {
        setError("You don't have access to this customer, or its project isn't complete yet.");
      } else setError("Failed to load.");
    } catch { setError("Network error."); }
    finally { setLoading(false); }
  }, [domain, id, router]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <div className="flex items-center justify-center min-h-[60vh]"><div className="w-8 h-8 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" /></div>;
  if (error || !data) return (
    <div className="p-6 lg:p-8 max-w-[900px]">
      <Link href="/accounts/completed" className="text-sm text-indigo-600 hover:underline">← Back to Completed Projects</Link>
      <p className="mt-6 text-sm text-rose-600">{error || "Not found."}</p>
    </div>
  );

  return (
    <div className="p-6 lg:p-8 max-w-[1100px]">
      <Link href="/accounts/completed" className="text-sm text-indigo-600 hover:underline">← Back to Completed Projects</Link>

      {/* Header */}
      <div className="mt-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">{data.first_name} {data.last_name}</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {data.phone || "—"}{data.email ? ` · ${data.email}` : ""}{data.location ? ` · ${data.location}` : ""}
          </p>
        </div>
        <div className="text-right">
          <p className="text-[10px] text-slate-400 uppercase tracking-wide">Accounts Staff</p>
          <p className="text-sm font-semibold text-amber-600">{data.accounts_staff_name || "Unassigned"}</p>
        </div>
      </div>

      {/* Customer details */}
      <div className="mt-5 bg-white border border-slate-200 rounded-2xl shadow-sm p-5">
        <h2 className="text-sm font-bold text-slate-900 mb-4">Customer</h2>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-3">
          <Detail label="Installation Location" value={data.installation_location} />
          <Detail label="Product" value={data.product_name} />
          <Detail label="Deal Value" value={data.value ? `₹${formatCurrency(data.value)}` : null} />
          <Detail label="BDE" value={data.bde_name} />
          <Detail label="Project Manager" value={data.project_manager_name} />
          <Detail label="Project Completed" value={data.project_completed_at ? new Date(data.project_completed_at).toLocaleString("en-IN") : null} />
        </div>
      </div>

      {/* Registration fee */}
      <RegistrationFeeSection
        leadId={data.id}
        canEdit={data.can_edit_rf}
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

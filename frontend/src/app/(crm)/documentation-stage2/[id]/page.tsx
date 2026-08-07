"use client";
import { getApiBase, formatCurrency } from "@/lib/mock-data";
import { APP_SLUG } from "@/lib/config";

import React, { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import DocumentationStage2Section from "./DocumentationStage2Section";

import ActivityTimeline from "@/components/ActivityTimeline";
type Stage2Detail = {
  id: number;
  first_name: string; last_name: string | null;
  phone: string | null; email: string | null;
  location: string | null; installation_location: string | null;
  product_name: string | null; value: number; status: string;
  bde_name: string | null;
  documentation_staff_name: string | null;
  doc_stage2_staff: number | null;
  doc_stage2_staff_name: string | null;
  can_assign: boolean;
  pushed_at: string | null;
  is_complete: boolean;
  can_edit: boolean;
  record: { completed_by_name: string | null; completed_at: string | null } | null;
};

type StaffOption = { id: number; name: string; branch_name?: string | null };

export default function DocumentationStage2DetailPage({ params: paramsPromise }: { params: Promise<{ id: string }> }) {
  const params = React.use(paramsPromise);
  const id = params.id;
  const domain = APP_SLUG;
  const router = useRouter();

  const [data, setData] = useState<Stage2Detail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const token = () => localStorage.getItem(`${domain}_access`);

  const load = useCallback(async () => {
    const t = token();
    if (!t) { router.push("/login"); return; }
    try {
      const r = await fetch(`${getApiBase(domain)}/api/leads/${id}/documentation-stage2-detail/`, { headers: { Authorization: `Bearer ${t}` } });
      if (r.ok) setData(await r.json());
      else if (r.status === 403 || r.status === 404) setError("You don't have access to this customer, or it isn't in Documentation Stage 2.");
      else setError("Failed to load.");
    } catch { setError("Network error."); }
    finally { setLoading(false); }
  }, [domain, id, router]);

  useEffect(() => { load(); }, [load]);

  // ── Stage 2 assignment (documentation manager → documentation staff) ──
  const [staffList, setStaffList] = useState<StaffOption[]>([]);
  const [showAssign, setShowAssign] = useState(false);
  const [selectedStaff, setSelectedStaff] = useState<string>("");
  const [assigning, setAssigning] = useState(false);

  const openAssign = async () => {
    setSelectedStaff(data?.doc_stage2_staff ? String(data.doc_stage2_staff) : "");
    setShowAssign(true);
    try {
      const r = await fetch(`${getApiBase(domain)}/api/users/`, { headers: { Authorization: `Bearer ${token()}` } });
      const d = await r.json().catch(() => ({}));
      const rows = Array.isArray(d) ? d : d.results || [];
      setStaffList(rows
        .filter((u: any) => u.role === "documentation_staff")
        .map((u: any) => ({
          id: u.id,
          name: `${u.first_name || ""} ${u.last_name || ""}`.trim() || u.username,
          branch_name: u.branch_name,
        })));
    } catch { /* leave the list empty — the dialog explains */ }
  };

  const assign = async () => {
    setAssigning(true);
    try {
      const r = await fetch(`${getApiBase(domain)}/api/leads/${id}/assign-doc-stage2/`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token()}` },
        body: JSON.stringify({ staff: selectedStaff || null }),
      });
      if (r.ok) { setShowAssign(false); await load(); }
      else { const e = await r.json().catch(() => ({})); alert(e.error || "Could not assign."); }
    } catch { alert("Network error."); }
    finally { setAssigning(false); }
  };

  if (loading) return <div className="flex items-center justify-center min-h-[60vh]"><div className="w-8 h-8 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" /></div>;
  if (error || !data) return (
    <div className="p-6 lg:p-8 max-w-[900px]">
      <Link href="/documentation-stage2" className="text-sm text-indigo-600 hover:underline">← Back to Documentation Stage 2</Link>
      <p className="mt-6 text-sm text-rose-600">{error || "Not found."}</p>
    </div>
  );

  return (
    <div className="p-6 lg:p-8 max-w-[1100px]">
      <div className="flex items-center justify-between gap-3">
        <Link href="/documentation-stage2" className="text-sm text-indigo-600 hover:underline">← Back to Documentation Stage 2</Link>
        <ActivityTimeline leadId={params.id} />
      </div>

      <div className="mt-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">{data.first_name} {data.last_name}</h1>
          <p className="text-sm text-slate-500 mt-0.5">{data.phone || "—"}{data.email ? ` · ${data.email}` : ""}{data.location ? ` · ${data.location}` : ""}</p>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          {data.is_complete && (
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-emerald-50 border border-emerald-200 text-emerald-700 rounded-lg text-xs font-semibold">
              ✓ Completed{data.record?.completed_by_name ? ` by ${data.record.completed_by_name}` : ""}
            </span>
          )}
          {data.can_assign && (
            <button onClick={openAssign}
              className="px-4 py-2 bg-amber-600 text-white rounded-xl text-xs font-semibold hover:bg-amber-700 transition shadow-sm">
              {data.doc_stage2_staff_name ? "Reassign Stage 2" : "Assign Stage 2"}
            </button>
          )}
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
          <Detail label="Stage 1 Staff" value={data.documentation_staff_name} />
          <Detail label="Stage 2 Staff" value={data.doc_stage2_staff_name || "Unassigned"} />
          <Detail label="Reached Stage 2" value={data.pushed_at ? new Date(data.pushed_at).toLocaleString("en-IN") : null} />
        </div>
      </div>

      {/* Documentation Stage 2 form */}
      <DocumentationStage2Section
        leadId={data.id}
        canEdit={data.can_edit}
        onChanged={load}
      />

      {/* Assign Stage 2 to documentation staff (documentation manager / admin) */}
      {showAssign && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm px-4">
          <div className="bg-white w-full max-w-md rounded-2xl shadow-2xl overflow-hidden" onClick={e => e.stopPropagation()}>
            <div className="px-6 py-4 border-b border-slate-100">
              <h2 className="text-[15px] font-bold text-slate-900">Assign Documentation Stage 2</h2>
              <p className="text-xs text-slate-400 mt-0.5">Hand this customer&apos;s Stage 2 paperwork to a documentation staff member.</p>
            </div>
            <div className="p-6">
              <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">Documentation Staff</label>
              <select value={selectedStaff} onChange={e => setSelectedStaff(e.target.value)}
                className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm text-slate-800 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all">
                <option value="">— Unassigned —</option>
                {staffList.map(s => <option key={s.id} value={s.id}>{s.name}{s.branch_name ? ` (${s.branch_name})` : ""}</option>)}
              </select>
              {staffList.length === 0 && (
                <p className="text-[11px] text-amber-600 mt-2">No documentation staff found. Set a user&apos;s role to &quot;Documentation Staff&quot; under Team first.</p>
              )}
            </div>
            <div className="px-6 py-4 border-t border-slate-100 flex gap-3">
              <button onClick={() => setShowAssign(false)} className="flex-1 py-2.5 border border-slate-200 rounded-xl text-sm font-semibold text-slate-600 hover:bg-slate-50 transition-all">Cancel</button>
              <button onClick={assign} disabled={assigning} className="flex-1 py-2.5 bg-amber-600 text-white rounded-xl text-sm font-semibold hover:bg-amber-700 disabled:opacity-50 transition-all">
                {assigning ? "Assigning…" : "Assign"}
              </button>
            </div>
          </div>
        </div>
      )}
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

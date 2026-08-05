"use client";
import { getApiBase, formatCurrency } from "@/lib/mock-data";
import { APP_SLUG } from "@/lib/config";

import React, { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import ProjectSection from "./ProjectSection";

import ActivityTimeline from "@/components/ActivityTimeline";
import { DeadlineBanner, type DeadlineInfo } from "@/components/ProjectDeadline";

// The deadline block comes down with the rest of the project payload.
type ProjectDetail = DeadlineInfo & {
  id: number;
  first_name: string; last_name: string | null;
  phone: string | null; email: string | null;
  location: string | null; installation_location: string | null;
  product_name: string | null; value: number; status: string;
  bde_name: string | null;
  project_manager: number | null;
  project_manager_name: string | null;
  pushed_at: string | null;
  can_edit_project: boolean;
  can_assign: boolean;
  can_reopen_project: boolean;
};

export default function ProjectDetailPage({ params: paramsPromise }: { params: Promise<{ id: string }> }) {
  const params = React.use(paramsPromise);
  const id = params.id;
  const domain = APP_SLUG;
  const router = useRouter();

  const [data, setData] = useState<ProjectDetail | null>(null);
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
      const r = await fetch(`${getApiBase(domain)}/api/leads/${id}/project-detail/`, { headers: { Authorization: `Bearer ${t}` } });
      if (r.ok) {
        const d = await r.json();
        setData(d);
        setSelectedStaff(d.project_manager ? String(d.project_manager) : "");
        if (d.can_assign) {
          const sr = await fetch(`${getApiBase(domain)}/api/users/project-managers/`, { headers: { Authorization: `Bearer ${t}` } });
          if (sr.ok) setStaff(await sr.json());
        }
      } else if (r.status === 403 || r.status === 404) {
        setError("You don't have access to this customer, or it isn't in the project stage.");
      } else setError("Failed to load.");
    } catch { setError("Network error."); }
    finally { setLoading(false); }
  }, [domain, id, router]);

  useEffect(() => { load(); }, [load]);

  const assign = async () => {
    setAssigning(true);
    try {
      const r = await fetch(`${getApiBase(domain)}/api/leads/${id}/assign-project/`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token()}` },
        body: JSON.stringify({ staff: selectedStaff || null }),
      });
      if (r.ok) { await load(); alert("Project manager updated."); }
      else { const d = await r.json().catch(() => ({})); alert(d.error || "Failed to assign."); }
    } catch { alert("Network error."); }
    finally { setAssigning(false); }
  };

  if (loading) return <div className="flex items-center justify-center min-h-[60vh]"><div className="w-8 h-8 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" /></div>;
  if (error || !data) return (
    <div className="p-6 lg:p-8 max-w-[900px]">
      <Link href="/project" className="text-sm text-indigo-600 hover:underline">← Back to Project</Link>
      <p className="mt-6 text-sm text-rose-600">{error || "Not found."}</p>
    </div>
  );

  return (
    <div className="p-6 lg:p-8 max-w-[1100px]">
      <div className="flex items-center justify-between gap-3">
        <Link href="/project" className="text-sm text-indigo-600 hover:underline">← Back to Project</Link>
        <ActivityTimeline leadId={params.id} />
      </div>

      <div className="mt-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">{data.first_name} {data.last_name}</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {data.phone || "—"}{data.email ? ` · ${data.email}` : ""}{data.location ? ` · ${data.location}` : ""}
          </p>
        </div>
        <div className="text-right">
          <p className="text-[10px] text-slate-400 uppercase tracking-wide">Project Manager</p>
          <p className="text-sm font-semibold text-amber-600">{data.project_manager_name || "Unassigned"}</p>
        </div>
      </div>

      <DeadlineBanner
        leadId={data.id}
        name={`${data.first_name} ${data.last_name || ""}`.trim()}
        info={data}
        domain={domain}
        onReleased={load}
      />

      {data.can_assign && (
        <div className="mt-5 bg-white border border-slate-200 rounded-2xl shadow-sm p-5">
          <h2 className="text-sm font-bold text-slate-900 mb-3">Assign Project Manager</h2>
          <div className="flex flex-col sm:flex-row gap-3 sm:items-end">
            <div className="flex-1">
              <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wide mb-1.5">Manager</label>
              <select value={selectedStaff} onChange={e => setSelectedStaff(e.target.value)} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all">
                <option value="">— Unassigned —</option>
                {staff.map(s => <option key={s.id} value={s.id}>{s.name}{s.branch_name ? ` (${s.branch_name})` : ""}</option>)}
              </select>
              {staff.length === 0 && <p className="text-[11px] text-amber-600 mt-1.5">No project managers yet — set a user&apos;s role to &quot;Project Manager&quot; under Team.</p>}
            </div>
            <button onClick={assign} disabled={assigning} className="px-5 py-2.5 bg-amber-600 text-white rounded-xl text-sm font-semibold hover:bg-amber-700 disabled:opacity-50 transition-all">{assigning ? "Saving…" : "Save"}</button>
          </div>
        </div>
      )}

      <div className="mt-5 bg-white border border-slate-200 rounded-2xl shadow-sm p-5">
        <h2 className="text-sm font-bold text-slate-900 mb-4">Customer</h2>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-3">
          <Detail label="Installation Location" value={data.installation_location} />
          <Detail label="Product" value={data.product_name} />
          <Detail label="Deal Value" value={data.value ? `₹${formatCurrency(data.value)}` : null} />
          <Detail label="BDE" value={data.bde_name} />
          <Detail label="Status" value={data.status} />
          <Detail label="Moved to Project" value={data.pushed_at ? new Date(data.pushed_at).toLocaleString("en-IN") : null} />
        </div>
      </div>

      <ProjectSection
        leadId={data.id}
        canEdit={data.can_edit_project}
        canReopen={data.can_reopen_project}
        lockedReason={data.project_overdue
          ? "Locked — past the deadline. A super admin has to release it."
          : undefined}
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

"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase, formatCurrency } from "@/lib/mock-data";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import DeletedLeadCleanup, { DeletedLeadBadge } from "@/components/DeletedLeadCleanup";
import { PageSkeleton } from "@/components/Skeleton";
import FilterBar, { FilterField } from "@/components/FilterBar";
type Row = {
  id: number;
  // Set when the lead behind this row has been deleted; the row is then
  // unopenable, and an admin gets a control to clear it out.
  lead_deleted?: boolean;
  can_cleanup?: boolean;
  name: string;
  phone: string | null;
  location: string | null;
  product_name: string | null;
  value: number;
  status: string;
  bde_name: string | null;
  documentation_staff_name: string | null;
  pushed_at: string | null;
  stage1_status: "not_started" | "in_progress" | "completed";
  stage1_completed_at: string | null;
  stage1_completed_by: string | null;
  stage2_status: "pending" | "in_progress" | "completed" | "not_started";
};

const STAGE_STYLES: Record<string, { label: string; cls: string }> = {
  completed: { label: "Completed", cls: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  in_progress: { label: "In progress", cls: "bg-amber-50 text-amber-700 border-amber-200" },
  not_started: { label: "Not started", cls: "bg-slate-100 text-slate-500 border-slate-200" },
  pending: { label: "Pending", cls: "bg-slate-100 text-slate-500 border-slate-200" },
};

function StageBadge({ status }: { status: string }) {
  const s = STAGE_STYLES[status] || STAGE_STYLES.not_started;
  return <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-[11px] font-semibold border ${s.cls}`}>{s.label}</span>;
}

export default function DocumentationStatusPage() {
  const domain = APP_SLUG;
  const router = useRouter();
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [q, setQ] = useState("");
  const [stage1Filter, setStage1Filter] = useState("all");
  const [staffFilter, setStaffFilter] = useState("all");

  const token = () => localStorage.getItem(`${domain}_access`);

  const load = useCallback(async () => {
    const t = token();
    if (!t) { router.push("/login"); return; }
    try {
      const r = await fetch(`${getApiBase(domain)}/api/leads/documentation-overview/`, { headers: { Authorization: `Bearer ${t}` } });
      if (r.ok) setRows(await r.json());
      else if (r.status === 403) setError("This view isn't available for the documentation team — use the Documentation work queue.");
      else setError("Failed to load.");
    } catch { setError("Network error."); }
    finally { setLoading(false); }
  }, [domain, router]);

  useEffect(() => { load(); }, [load]);

  const staffOptions = useMemo(
    () => Array.from(new Set(rows.map(r => r.documentation_staff_name).filter(Boolean))) as string[],
    [rows]
  );

  const filtered = useMemo(() => rows.filter(r => {
    if (stage1Filter !== "all" && r.stage1_status !== stage1Filter) return false;
    if (staffFilter !== "all" && r.documentation_staff_name !== staffFilter) return false;
    if (q.trim()) {
      const hay = `${r.name} ${r.phone || ""} ${r.location || ""} ${r.bde_name || ""}`.toLowerCase();
      if (!hay.includes(q.trim().toLowerCase())) return false;
    }
    return true;
  }), [rows, q, stage1Filter, staffFilter]);

  const counts = useMemo(() => ({
    total: rows.length,
    completed: rows.filter(r => r.stage1_status === "completed").length,
    in_progress: rows.filter(r => r.stage1_status === "in_progress").length,
    not_started: rows.filter(r => r.stage1_status === "not_started").length,
  }), [rows]);

  if (loading) return <PageSkeleton />;

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-[1200px]">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Documentation</h1>
        <p className="text-sm text-slate-500 mt-0.5">Track every lead currently in the documentation process and its stage status.</p>
      </div>

      {error ? (
        <p className="text-sm text-rose-600">{error}</p>
      ) : (
        <>
          {/* Summary */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
            {[
              { label: "In Documentation", value: counts.total, cls: "text-slate-900" },
              { label: "Stage 1 Completed", value: counts.completed, cls: "text-emerald-600" },
              { label: "Stage 1 In Progress", value: counts.in_progress, cls: "text-amber-600" },
              { label: "Stage 1 Not Started", value: counts.not_started, cls: "text-slate-500" },
            ].map(c => (
              <div key={c.label} className="bg-white border border-slate-200 rounded-2xl shadow-sm p-4 card-interactive">
                <p className="text-[10px] uppercase tracking-wide text-slate-400 font-bold">{c.label}</p>
                <p className={`text-2xl font-black mt-1 ${c.cls}`}>{c.value}</p>
              </div>
            ))}
          </div>

          {/* Filters */}
          <div className="mb-4">
            <FilterBar
              activeCount={(stage1Filter !== "all" ? 1 : 0) + (staffFilter !== "all" ? 1 : 0)}
              onClear={() => { setStage1Filter("all"); setStaffFilter("all"); }}
              resultCount={filtered.length}
              search={
                <input value={q} onChange={e => setQ(e.target.value)} placeholder="Search name, phone, location, BDE…"
                  className="w-full bg-white border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition" />
              }
            >
              <FilterField label="Stage 1">
                <select value={stage1Filter} onChange={e => setStage1Filter(e.target.value)} className="dropdown-premium">
                  <option value="all">Stage 1: All</option>
                  <option value="completed">Stage 1: Completed</option>
                  <option value="in_progress">Stage 1: In progress</option>
                  <option value="not_started">Stage 1: Not started</option>
                </select>
              </FilterField>
              <FilterField label="Doc staff">
                <select value={staffFilter} onChange={e => setStaffFilter(e.target.value)} className="dropdown-premium">
                  <option value="all">Doc staff: All</option>
                  {staffOptions.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </FilterField>
            </FilterBar>
          </div>

          {/* Table */}
          <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[820px] text-sm">
                <thead className="bg-slate-50 border-b border-slate-200 text-left">
                  <tr className="text-[11px] uppercase tracking-wide text-slate-500">
                    <th className="px-5 py-3 font-bold">Customer</th>
                    <th className="px-5 py-3 font-bold">BDE</th>
                    <th className="px-5 py-3 font-bold">Doc Staff</th>
                    <th className="px-5 py-3 font-bold">Pushed</th>
                    <th className="px-5 py-3 font-bold">Stage 1</th>
                    <th className="px-5 py-3 font-bold">Stage 2</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.length === 0 ? (
                    <tr><td colSpan={6} className="px-5 py-12 text-center text-sm text-slate-400">No leads in documentation match your filters.</td></tr>
                  ) : filtered.map(r => (
                    <tr key={r.id} onClick={() => router.push(`/documentation-status/${r.id}`)}
                      className="border-b border-slate-100 hover:bg-indigo-50/40 transition cursor-pointer">
                      <td className="px-5 py-3.5">
                        <span className="font-semibold text-slate-800">{r.name || "—"}</span>
                        {r.lead_deleted && (
                          <span className="ml-2 inline-flex align-middle"><DeletedLeadBadge /></span>
                        )}
                        {r.can_cleanup && (
                          <span className="ml-2 inline-flex align-middle">
                            <DeletedLeadCleanup leadId={r.id} module="documentation" name={r.name}
                              onRemoved={() => setRows(prev => prev.filter(x => x.id !== r.id))} />
                          </span>
                        )}
                        <div className="text-[11px] text-slate-400">
                          {r.phone || "—"}{r.location ? ` · ${r.location}` : ""}{r.value ? ` · ₹${formatCurrency(r.value)}` : ""}
                        </div>
                      </td>
                      <td className="px-5 py-3.5 text-slate-600">{r.bde_name || "—"}</td>
                      <td className="px-5 py-3.5 text-slate-600">{r.documentation_staff_name || <span className="text-slate-400">Unassigned</span>}</td>
                      <td className="px-5 py-3.5 text-slate-500 text-[12px]">{r.pushed_at ? new Date(r.pushed_at).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) : "—"}</td>
                      <td className="px-5 py-3.5">
                        <StageBadge status={r.stage1_status} />
                        {r.stage1_status === "completed" && r.stage1_completed_by && (
                          <div className="text-[10px] text-slate-400 mt-1">by {r.stage1_completed_by}</div>
                        )}
                      </td>
                      <td className="px-5 py-3.5"><StageBadge status={r.stage2_status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <p className="text-[11px] text-slate-400 mt-3">Stage 2 is not configured yet — it will show live status here once it&apos;s set up.</p>
        </>
      )}
    </div>
  );
}

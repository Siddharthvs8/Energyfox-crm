"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase, formatCurrency } from "@/lib/mock-data";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import DeletedLeadCleanup, { DeletedLeadBadge } from "@/components/DeletedLeadCleanup";
import { ReleaseDialog, asDate, deadlineNote, type DeadlineInfo } from "@/components/ProjectDeadline";

// The row carries the whole deadline block, so the shared banner and dialog can
// read it without a second fetch.
type ProjectLead = DeadlineInfo & {
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
  project_manager_name: string | null;
};

export default function ProjectPage() {
  const domain = APP_SLUG;
  const router = useRouter();
  const [authChecked, setAuthChecked] = useState(false);
  const [allowed, setAllowed] = useState(false);
  const [leads, setLeads] = useState<ProjectLead[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  // The list opens on the work still to be done; finished jobs and the ones that
  // blew their deadline are each one tap away.
  const [tab, setTab] = useState<"pending" | "overdue" | "completed">("pending");
  // The row a super admin is releasing back to the project team.
  const [releasing, setReleasing] = useState<ProjectLead | null>(null);

  const token = () => localStorage.getItem(`${domain}_access`);

  useEffect(() => {
    const t = token();
    if (!t) { router.push("/login"); return; }
    fetch(`${getApiBase(domain)}/api/users/me/`, { headers: { Authorization: `Bearer ${t}` } })
      .then(r => r.json())
      .then(d => {
        const ok = d.role === "project_manager" || d.is_staff || d.is_general_manager;
        setAllowed(ok);
        setAuthChecked(true);
        if (!ok) router.replace("/");
      })
      .catch(() => setAuthChecked(true));
  }, [domain, router]);

  useEffect(() => {
    if (!allowed) return;
    fetch(`${getApiBase(domain)}/api/leads/project/`, { headers: { Authorization: `Bearer ${token()}` } })
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

  const matchesSearch = (l: ProjectLead) => {
    const q = search.trim().toLowerCase();
    if (!q) return true;
    return (`${l.first_name} ${l.last_name || ""}`.toLowerCase().includes(q)
      || (l.phone || "").toLowerCase().includes(q)
      || (l.location || "").toLowerCase().includes(q));
  };

  // Counts are of the search results, so the tabs show where the matches went
  // rather than a total that disagrees with the list underneath.
  // An overdue project leaves Pending entirely — that is the point of the queue.
  const found = leads.filter(matchesSearch);
  const inTab = (l: ProjectLead, key: typeof tab) =>
    key === "completed" ? l.project_complete
      : key === "overdue" ? (!l.project_complete && l.project_overdue)
        : (!l.project_complete && !l.project_overdue);
  const counts = {
    pending: found.filter(l => inTab(l, "pending")).length,
    overdue: found.filter(l => inTab(l, "overdue")).length,
    completed: found.filter(l => inTab(l, "completed")).length,
  };
  const filtered = found.filter(l => inTab(l, tab));

  return (
    <div className="p-6 lg:p-8 max-w-[1200px]">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Project</h1>
        <p className="text-sm text-slate-500 mt-1">Installation projects (purchase &amp; logistics complete). Open one to track structure/electrical work and geotagged site photos.</p>
      </div>

      <div className="mb-5 flex flex-wrap items-center gap-3">
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search by name, phone or location…"
          className="w-full max-w-md bg-white border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all"
        />
        <div className="inline-flex rounded-xl bg-slate-100 p-1">
          {([["pending", "Pending"], ["overdue", "Overdue"], ["completed", "Completed"]] as const).map(([key, label]) => {
            // Overdue is the exception queue: it reads red even unselected, and
            // only while something is actually sitting in it.
            const alarm = key === "overdue" && counts.overdue > 0;
            return (
              <button
                key={key}
                type="button"
                onClick={() => setTab(key)}
                className={`px-4 py-1.5 rounded-lg text-xs font-bold transition-colors ${
                  tab === key
                    ? `bg-white shadow-sm ${alarm ? "text-rose-600" : "text-indigo-600"}`
                    : alarm ? "text-rose-500 hover:text-rose-600" : "text-slate-500 hover:text-slate-700"
                }`}
              >
                {label}
                <span className={`ml-1.5 ${tab === key ? (alarm ? "text-rose-400" : "text-indigo-400") : "text-slate-400"}`}>{counts[key]}</span>
              </button>
            );
          })}
        </div>
      </div>

      {tab === "overdue" && (
        <p className="mb-4 -mt-1 text-xs text-slate-500">
          Past the {leads[0]?.deadline_days ?? 20}-day deadline that started with the customer&apos;s first payment.
          Locked to the project team — a super admin releases one back with a fresh deadline.
        </p>
      )}

      {loading ? (
        <div className="py-16 text-center text-sm text-slate-400">Loading…</div>
      ) : filtered.length === 0 ? (
        <div className="bg-white border border-dashed border-slate-200 rounded-2xl p-12 text-center text-sm text-slate-400">
          {leads.length === 0
            ? "No installation projects yet."
            : found.length === 0
              ? "No projects match your search."
              : tab === "completed"
                ? "No completed projects yet."
                : tab === "overdue"
                  ? "Nothing overdue — every project is inside its deadline."
                  : "No pending projects — everything here is done."}
        </div>
      ) : (
        <div className="space-y-4">
          {filtered.map(l => (
            <Link key={l.id} href={`/project/${l.id}`} className="block bg-white border border-slate-200 rounded-2xl shadow-sm px-5 py-4 hover:bg-slate-50/60 hover:border-indigo-200 transition-colors">
              <div className="flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-bold text-slate-900 truncate">{l.first_name} {l.last_name}</p>
                    {l.lead_deleted && <DeletedLeadBadge />}
                    <span className={`text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full ${
                      l.project_complete ? "bg-emerald-50 text-emerald-700"
                        : l.project_overdue ? "bg-rose-50 text-rose-700"
                          : "bg-amber-50 text-amber-700"}`}>
                      {l.project_complete ? "Done" : l.project_overdue ? "Overdue" : "In Progress"}
                    </span>
                    {/* The deadline only matters while the work is still running. */}
                    {!l.project_complete && (
                      <span className={`text-[10px] font-semibold ${l.project_overdue ? "text-rose-600" : (l.days_to_deadline ?? 99) <= 3 ? "text-amber-600" : "text-slate-400"}`}>
                        {deadlineNote(l)}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-slate-500 mt-0.5 truncate">{l.phone || "—"} · {l.location || "No location"}{l.product_name ? ` · ${l.product_name}` : ""}</p>
                  {!l.project_complete && l.deadline_date && (
                    <p className="text-[11px] text-slate-400 mt-0.5">
                      Deadline {asDate(l.deadline_date)}
                      {l.extended_deadline ? " (extended)" : l.payment_started_on ? ` · paid ${asDate(l.payment_started_on)}` : ""}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-4 flex-shrink-0">
                  <div className="hidden sm:block text-right">
                    <p className="text-[10px] text-slate-400 uppercase tracking-wide">Deal Value</p>
                    <p className="text-xs font-semibold text-slate-700">{l.value ? `₹${formatCurrency(l.value)}` : "—"}</p>
                  </div>
                  <div className="hidden md:block text-right">
                    <p className="text-[10px] text-slate-400 uppercase tracking-wide">Project Manager</p>
                    <p className="text-xs font-semibold text-slate-600">{l.project_manager_name || "Unassigned"}</p>
                  </div>
                  {/* Only the super admin can lift the lock, and only from here. */}
                  {l.project_overdue && !l.project_complete && l.can_release_project && (
                    <button
                      type="button"
                      onClick={e => { e.preventDefault(); e.stopPropagation(); setReleasing(l); }}
                      className="px-3 py-1.5 rounded-lg bg-rose-600 text-white text-[11px] font-bold hover:bg-rose-700 transition whitespace-nowrap"
                    >
                      Release
                    </button>
                  )}
                  {l.can_cleanup && (
                    <DeletedLeadCleanup leadId={l.id} module="project"
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

      {releasing && (
        <ReleaseDialog
          leadId={releasing.id}
          name={`${releasing.first_name} ${releasing.last_name || ""}`.trim()}
          info={releasing}
          domain={domain}
          onClose={() => setReleasing(null)}
          onReleased={row => {
            setLeads(prev => prev.map(x => (x.id === row.id ? row : x)));
            setReleasing(null);
            setTab("pending");
          }}
        />
      )}
    </div>
  );
}

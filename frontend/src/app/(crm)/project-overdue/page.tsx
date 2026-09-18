"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase, formatCurrency } from "@/lib/mock-data";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import DeletedLeadCleanup, { DeletedLeadBadge } from "@/components/DeletedLeadCleanup";
import { ReleaseDialog, asDate, deadlineNote, type DeadlineInfo } from "@/components/ProjectDeadline";
import { isSpectator } from "@/lib/spectator";
import BdeTag from "@/components/BdeTag";

/**
 * Overdue Projects — installations that missed the 20-day deadline counted from
 * the customer's first payment.
 *
 * They leave the Project queue entirely and land here, locked: nobody but a
 * super admin can edit one until it is released back with a fresh deadline.
 */
type OverdueLead = DeadlineInfo & {
  /** Who did the site visit — shown as a tag on the row. */
  bde_name?: string | null;
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

export default function OverdueProjectsPage() {
  const domain = APP_SLUG;
  const router = useRouter();
  const [authChecked, setAuthChecked] = useState(false);
  const [allowed, setAllowed] = useState(false);
  const [leads, setLeads] = useState<OverdueLead[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [releasing, setReleasing] = useState<OverdueLead | null>(null);

  const token = () => localStorage.getItem(`${domain}_access`);

  useEffect(() => {
    const t = token();
    if (!t) { router.push("/login"); return; }
    fetch(`${getApiBase(domain)}/api/users/me/`, { headers: { Authorization: `Bearer ${t}` } })
      .then(r => r.json())
      .then(d => {
        const ok = isSpectator(d) || d.role === "project_manager" || d.is_staff || d.is_general_manager
          || (d.permissions || []).includes("project-overdue");
        setAllowed(ok);
        setAuthChecked(true);
        if (!ok) router.replace("/");
      })
      .catch(() => setAuthChecked(true));
  }, [domain, router]);

  const load = () => {
    fetch(`${getApiBase(domain)}/api/leads/project-overdue/`, { headers: { Authorization: `Bearer ${token()}` } })
      .then(r => (r.ok ? r.json() : []))
      .then(d => setLeads(Array.isArray(d) ? d : []))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { if (allowed) load(); }, [allowed]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!authChecked) return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="w-8 h-8 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
    </div>
  );
  if (!allowed) return null;

  const q = search.trim().toLowerCase();
  const filtered = leads.filter(l =>
    !q || `${l.first_name} ${l.last_name || ""}`.toLowerCase().includes(q)
    || (l.phone || "").toLowerCase().includes(q)
    || (l.location || "").toLowerCase().includes(q));

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-[1200px]">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Overdue Projects</h1>
        <p className="text-sm text-slate-500 mt-1">
          Installations past the {leads[0]?.deadline_days ?? 20}-day deadline that started with the
          customer&apos;s first payment. Locked to the project team — a super admin releases one back
          with a fresh deadline.
        </p>
      </div>

      <div className="mb-5 flex flex-wrap items-center gap-3">
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search by name, phone or location…"
          className="w-full max-w-md bg-white border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all"
        />
        {leads.length > 0 && (
          <span className="text-[10px] font-bold uppercase tracking-wide px-2.5 py-1 rounded-full bg-rose-50 text-rose-700">
            {leads.length} locked
          </span>
        )}
      </div>

      {loading ? (
        <div className="py-16 text-center text-sm text-slate-400">Loading…</div>
      ) : filtered.length === 0 ? (
        <div className="bg-white border border-dashed border-slate-200 rounded-2xl p-12 text-center text-sm text-slate-400">
          {leads.length === 0
            ? "Nothing overdue — every project is inside its deadline."
            : "No overdue projects match your search."}
        </div>
      ) : (
        <div className="space-y-4">
          {filtered.map(l => (
            <Link key={l.id} href={`/project/${l.id}`}
              className="block bg-white border border-rose-200 rounded-2xl shadow-sm px-5 py-4 hover:bg-rose-50/40 transition-colors">
              <div className="flex items-center justify-between gap-4">
                <div className="min-w-0">
                  {/* Wraps on a phone: name, tag, badge and deadline do not
                      fit on one 390px line. */}
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <p className="text-sm font-bold text-slate-900 truncate">{l.first_name} {l.last_name}</p>
                    <BdeTag name={l.bde_name} />
                    {l.lead_deleted && <DeletedLeadBadge />}
                    <span className="text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full bg-rose-50 text-rose-700 whitespace-nowrap flex-shrink-0">
                      Overdue
                    </span>
                    <span className="text-[10px] font-semibold text-rose-600 whitespace-nowrap flex-shrink-0">{deadlineNote(l)}</span>
                  </div>
                  <p className="text-xs text-slate-500 mt-0.5 truncate">
                    {l.phone || "—"} · {l.location || "No location"}{l.product_name ? ` · ${l.product_name}` : ""}
                  </p>
                  {l.deadline_date && (
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
                  {/* Only the super admin can lift the lock. */}
                  {l.can_release_project && (
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
            // Released with a fresh deadline, so it belongs to Project again.
            setLeads(prev => prev.filter(x => x.id !== row.id));
            setReleasing(null);
          }}
        />
      )}
    </div>
  );
}

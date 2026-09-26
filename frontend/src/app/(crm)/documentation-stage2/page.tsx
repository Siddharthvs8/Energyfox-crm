"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import DeletedLeadCleanup, { DeletedLeadBadge } from "@/components/DeletedLeadCleanup";
import { isSpectator } from "@/lib/spectator";
import BdeTag from "@/components/BdeTag";
import { RemarkSummary, RemarkSummaryData } from "@/components/DocumentationRemarks";
type Stage2Lead = {
  /** Who did the site visit — shown as a tag on the row. */
  bde_name?: string | null;
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
  documentation_staff_name: string | null;
  doc_stage2_staff_name: string | null;
  is_complete: boolean;
  // Signed off but the subsidy has not been claimed — decided server-side so
  // the list and the record agree on what "pending" means.
  subsidy_requested?: boolean;
  subsidy_pending?: boolean;
  pushed_at: string | null;
  /** The latest remark — usually why the customer is held up. */
  latest_remark?: RemarkSummaryData;
  remark_count?: number;
};

/** The three buckets are disjoint: a signed-off customer whose subsidy has not
 *  been claimed is not finished, which is the whole point of separating it. */
type Bucket = "pending" | "done" | "subsidy_pending";
const bucketOf = (l: Stage2Lead): Bucket =>
  !l.is_complete ? "pending" : l.subsidy_pending ? "subsidy_pending" : "done";

const TABS: { key: Bucket; label: string }[] = [
  { key: "pending", label: "Pending" },
  { key: "done", label: "Done" },
  { key: "subsidy_pending", label: "Subsidy Pending" },
];

const EMPTY: Record<Bucket, string> = {
  pending: "Nothing pending — every customer here has been signed off.",
  done: "No completed customers yet.",
  subsidy_pending: "No subsidies outstanding — every signed-off customer has theirs requested.",
};

export default function DocumentationStage2Page() {
  const domain = APP_SLUG;
  const router = useRouter();
  const [authChecked, setAuthChecked] = useState(false);
  const [allowed, setAllowed] = useState(false);
  const [leads, setLeads] = useState<Stage2Lead[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  // Opens on the work still to do, like Purchase & Logistics does.
  const [bucket, setBucket] = useState<Bucket>("pending");

  const token = () => localStorage.getItem(`${domain}_access`);

  useEffect(() => {
    const t = token();
    if (!t) { router.push("/login"); return; }
    fetch(`${getApiBase(domain)}/api/users/me/`, { headers: { Authorization: `Bearer ${t}` } })
      .then(r => r.json())
      .then(d => {
        const ok = isSpectator(d) || ["documentation_staff", "documentation_manager"].includes(d.role) || d.is_staff || d.is_general_manager;
        setAllowed(ok);
        setAuthChecked(true);
        if (!ok) router.replace("/");
      })
      .catch(() => setAuthChecked(true));
  }, [domain, router]);

  useEffect(() => {
    if (!allowed) return;
    fetch(`${getApiBase(domain)}/api/leads/documentation-stage2/`, { headers: { Authorization: `Bearer ${token()}` } })
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

  const matchesSearch = (l: Stage2Lead) => {
    const q = search.trim().toLowerCase();
    if (!q) return true;
    return (`${l.first_name} ${l.last_name || ""}`.toLowerCase().includes(q)
      || (l.phone || "").toLowerCase().includes(q)
      || (l.location || "").toLowerCase().includes(q)
      // A reason is worth searching by: "bank" finds everyone held up on one.
      || (l.latest_remark?.body || "").toLowerCase().includes(q));
  };

  // Counts are of the search results, so the tabs can't disagree with the list.
  const found = leads.filter(matchesSearch);
  const counts: Record<Bucket, number> = {
    pending: found.filter(l => bucketOf(l) === "pending").length,
    done: found.filter(l => bucketOf(l) === "done").length,
    subsidy_pending: found.filter(l => bucketOf(l) === "subsidy_pending").length,
  };
  const filtered = found.filter(l => bucketOf(l) === bucket);

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-[1200px]">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Documentation Stage 2</h1>
        <p className="text-sm text-slate-500 mt-1">Customers whose installation is complete, now in the second documentation stage.</p>
      </div>

      <div className="flex gap-1 mb-5 border-b border-slate-200 overflow-x-auto no-scrollbar">
        {TABS.map(t => (
          <button key={t.key} onClick={() => setBucket(t.key)}
            className={`flex items-center gap-2 px-4 py-2.5 text-sm font-semibold whitespace-nowrap border-b-2 -mb-px transition-colors ${
              bucket === t.key ? "border-indigo-600 text-indigo-600" : "border-transparent text-slate-500 hover:text-slate-800"}`}>
            {t.label}
            <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full ${
              bucket === t.key ? "bg-indigo-50 text-indigo-700" : "bg-slate-100 text-slate-500"}`}>
              {counts[t.key]}
            </span>
          </button>
        ))}
      </div>

      <div className="mb-5 flex items-center gap-3">
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search by name, phone, location or remark…"
          className="w-full max-w-md bg-white border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all"
        />
        <span className="text-xs font-semibold text-slate-400 whitespace-nowrap flex-shrink-0">{filtered.length} customer{filtered.length === 1 ? "" : "s"}</span>
      </div>

      {loading ? (
        <div className="py-16 text-center text-sm text-slate-400">Loading…</div>
      ) : filtered.length === 0 ? (
        <div className="bg-white border border-dashed border-slate-200 rounded-2xl p-12 text-center text-sm text-slate-400">
          {leads.length === 0
            ? "No customers in Documentation Stage 2 yet."
            : found.length === 0 ? "No customers match your search." : EMPTY[bucket]}
        </div>
      ) : (
        <div className="space-y-4">
          {filtered.map(l => (
            <Link key={l.id} href={`/documentation-stage2/${l.id}`} className="block bg-white border border-slate-200 rounded-2xl shadow-sm px-5 py-4 hover:bg-slate-50/60 hover:border-indigo-200 transition-colors">
              <div className="flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-bold text-slate-900 truncate">{l.first_name} {l.last_name}</p>
                    <BdeTag name={l.bde_name} />
                    {l.lead_deleted && <DeletedLeadBadge />}
                    {(() => {
                      const b = bucketOf(l);
                      const tone = b === "done" ? "bg-emerald-50 text-emerald-700"
                        : b === "subsidy_pending" ? "bg-violet-50 text-violet-700"
                        : "bg-amber-50 text-amber-700";
                      const text = b === "done" ? "Done"
                        : b === "subsidy_pending" ? "Subsidy Pending" : "In Progress";
                      return (
                        <span className={`text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full ${tone}`}>
                          {text}
                        </span>
                      );
                    })()}
                  </div>
                  <p className="text-xs text-slate-500 mt-0.5 truncate">{l.phone || "—"} · {l.location || "No location"}{l.product_name ? ` · ${l.product_name}` : ""}</p>
                  <RemarkSummary remark={l.latest_remark} since={l.pushed_at} pending={!l.is_complete} />
                </div>
                <div className="flex items-center gap-4 flex-shrink-0">
                  <div className="hidden md:block text-right">
                    <p className="text-[10px] text-slate-400 uppercase tracking-wide">Stage 2 Staff</p>
                    <p className={`text-xs font-semibold ${l.doc_stage2_staff_name ? "text-slate-600" : "text-amber-600"}`}>{l.doc_stage2_staff_name || "Unassigned"}</p>
                  </div>
                  {l.can_cleanup && (
                    <DeletedLeadCleanup leadId={l.id} module="documentation-stage2"
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

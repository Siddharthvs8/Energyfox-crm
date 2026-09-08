"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import DeletedLeadCleanup, { DeletedLeadBadge } from "@/components/DeletedLeadCleanup";
import { isSpectator } from "@/lib/spectator";
import BdeTag from "@/components/BdeTag";
type DocLead = {
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
  attachments: { label: string }[];
  /** Stage 1 signed off — decides which tab the row lands in. */
  stage1_complete?: boolean;
};

export default function DocumentationPage() {
  const domain = APP_SLUG;
  const router = useRouter();
  const [authChecked, setAuthChecked] = useState(false);
  const [allowed, setAllowed] = useState(false);
  const [leads, setLeads] = useState<DocLead[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  // Opens on the paperwork still to be done; the signed-off ones are one tap away.
  const [tab, setTab] = useState<"pending" | "completed">("pending");

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
    fetch(`${getApiBase(domain)}/api/leads/documentation/`, { headers: { Authorization: `Bearer ${token()}` } })
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

  const matchesSearch = (l: DocLead) => {
    const q = search.trim().toLowerCase();
    if (!q) return true;
    return (`${l.first_name} ${l.last_name || ""}`.toLowerCase().includes(q)
      || (l.phone || "").toLowerCase().includes(q)
      || (l.location || "").toLowerCase().includes(q));
  };

  // Counts are of the search results, so the tabs show where the matches went
  // rather than a total that disagrees with the list underneath.
  const found = leads.filter(matchesSearch);
  const counts = {
    pending: found.filter(l => !l.stage1_complete).length,
    completed: found.filter(l => l.stage1_complete).length,
  };
  const filtered = found.filter(l => (tab === "completed" ? !!l.stage1_complete : !l.stage1_complete));

  return (
    <div className="p-6 lg:p-8 max-w-[1200px]">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Documentation Stage 1</h1>
        <p className="text-sm text-slate-500 mt-1">Customers pushed for documentation. Open one to preview and download their attachments.</p>
      </div>

      <div className="mb-5 flex flex-wrap items-center gap-3">
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search by name, phone or location…"
          className="w-full max-w-md bg-white border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all"
        />
        <div className="inline-flex rounded-xl bg-slate-100 p-1">
          {([["pending", "Pending"], ["completed", "Completed"]] as const).map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => setTab(key)}
              className={`px-4 py-1.5 rounded-lg text-xs font-bold transition-colors ${
                tab === key ? "bg-white text-indigo-600 shadow-sm" : "text-slate-500 hover:text-slate-700"
              }`}
            >
              {label}
              <span className={`ml-1.5 ${tab === key ? "text-indigo-400" : "text-slate-400"}`}>{counts[key]}</span>
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="py-16 text-center text-sm text-slate-400">Loading…</div>
      ) : filtered.length === 0 ? (
        <div className="bg-white border border-dashed border-slate-200 rounded-2xl p-12 text-center text-sm text-slate-400">
          {leads.length === 0
            ? "No customers pushed to documentation yet."
            : found.length === 0
              ? "No customers match your search."
              : tab === "completed"
                ? "No completed documentation yet."
                : "No pending documentation — everything here is done."}
        </div>
      ) : (
        <div className="space-y-4">
          {filtered.map(l => (
            <Link key={l.id} href={`/documentation/${l.id}`} className="block bg-white border border-slate-200 rounded-2xl shadow-sm px-5 py-4 hover:bg-slate-50/60 hover:border-indigo-200 transition-colors">
              <div className="flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-bold text-slate-900 truncate">{l.first_name} {l.last_name}</p>
                    <BdeTag name={l.bde_name} />
                    {l.lead_deleted && <DeletedLeadBadge />}
                    <span className={`text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full ${
                      l.stage1_complete ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>
                      {l.stage1_complete ? "Done" : "Pending"}
                    </span>
                    <span className="text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">{l.attachments.length} file{l.attachments.length === 1 ? "" : "s"}</span>
                  </div>
                  <p className="text-xs text-slate-500 mt-0.5 truncate">{l.phone || "—"} · {l.location || "No location"}{l.product_name ? ` · ${l.product_name}` : ""}</p>
                </div>
                <div className="flex items-center gap-4 flex-shrink-0">
                  <div className="hidden sm:block text-right">
                    <p className="text-[10px] text-slate-400 uppercase tracking-wide">Doc Staff</p>
                    <p className="text-xs font-semibold text-slate-600">{l.documentation_staff_name || "Unassigned"}</p>
                  </div>
                  {l.can_cleanup && (
                    <DeletedLeadCleanup leadId={l.id} module="documentation"
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

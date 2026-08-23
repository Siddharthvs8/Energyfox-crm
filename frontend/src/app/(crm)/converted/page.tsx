"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";
import { useLeadStatuses } from "@/hooks/useLeadStatuses";
import { FALLBACK_STATUS_META } from "@/lib/lead-statuses";
import { StageTag } from "@/lib/pipeline-stages";

import React, { useState, useEffect, use, useRef } from "react";
import { formatCurrency, getSourceLabel } from "@/lib/mock-data";

// ─── Icons ────────────────────────────────────────────────────────────────────
const I = {
  Trophy:   () => <svg width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><path d="M6 9H4.5a2.5 2.5 0 010-5H6"/><path d="M18 9h1.5a2.5 2.5 0 000-5H18"/><path d="M4 22h16"/><path d="M10 14.66V17c0 1.1-.9 2-2 2H6"/><path d="M14 14.66V17c0 1.1.9 2 2 2h2"/><path d="M18 4H6v5c0 3.31 2.69 6 6 6s6-2.69 6-6V4z"/></svg>,
  TrendUp:  () => <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>,
  Clock:    () => <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>,
  Target:   () => <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg>,
  X:        () => <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg>,
  Mail:     () => <svg width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>,
  Invoice:  () => <svg width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>,
  Phone:    () => <svg width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6 19.79 19.79 0 01-3.07-8.67A2 2 0 014.11 2h3a2 2 0 012 1.72 12.84 12.84 0 00.7 2.81 2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l2.27-2.27a2 2 0 012.11-.45 12.84 12.84 0 002.81.7A2 2 0 0122 16.92z"/></svg>,
  Task:     () => <svg width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M9 11l3 3 8-8"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/></svg>,
  Attach:   () => <svg width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48"/></svg>,
  Download: () => <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>,
  History:  () => <svg width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 101.01-4.95L1 10"/></svg>,
  Star:     () => <svg width="14" height="14" fill="#f59e0b" stroke="#f59e0b" strokeWidth="1.5" strokeLinecap="round" viewBox="0 0 24 24"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>,
};

// ─── Status pill (uses dynamic statusMeta passed as prop) ────────────────────
function StatusPill({ status, statusMeta }: { status: string; statusMeta: Record<string, { label: string; bg: string; text: string; dot: string; hex: string }> }) {
  const m = statusMeta[status] || FALLBACK_STATUS_META;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-bold ${m.bg} ${m.text}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${m.dot}`} />
      {m.label}
    </span>
  );
}

// ─── Deal classification (fulfilment / payment milestone) ───────────────────────
const DEAL_CLASS_META: Record<string, { label: string; cls: string }> = {
  partially_paid: { label: "Partially Paid", cls: "bg-amber-50 text-amber-700 border-amber-100" },
  fully_paid:     { label: "Fully Paid",     cls: "bg-emerald-50 text-emerald-700 border-emerald-100" },
  lost:           { label: "Lost",           cls: "bg-rose-50 text-rose-700 border-rose-100" },
};
const CHIP = "inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold border";

/** Closed Deal = in accounts with a payment (partial or full) taken. Shown next
 *  to the payment detail, so a paid deal reads "Closed Deal · Partially Paid". */
function DealClassBadge({ value, closed }: { value?: string | null; closed?: boolean }) {
  const m = value ? DEAL_CLASS_META[value] : null;
  if (!m && !closed) return null;
  return (
    <>
      {closed && <span className={`${CHIP} bg-indigo-50 text-indigo-700 border-indigo-100`}>Closed Deal</span>}
      {m && <span className={`${CHIP} ${m.cls}`}>{m.label}</span>}
    </>
  );
}

// ─── Timeline event config ────────────────────────────────────────────────────
const typeConfig: Record<string, { label: string; bg: string; accent: string; icon: React.ReactNode }> = {
  lead_created:       { label:"Lead Created",       bg:"bg-indigo-100",  accent:"text-indigo-600",  icon:<svg width="11" height="11" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg> },
  lead_status_change: { label:"Status Changed",     bg:"bg-amber-100",   accent:"text-amber-600",   icon:<svg width="11" height="11" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M17 3l4 4-4 4"/><path d="M7 21l-4-4 4-4"/><path d="M21 7H9a4 4 0 000 8h6"/></svg> },
  note_added:         { label:"Note",               bg:"bg-teal-100",    accent:"text-teal-600",    icon:<svg width="11" height="11" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg> },
  task_created:       { label:"Task Created",       bg:"bg-violet-100",  accent:"text-violet-600",  icon:<svg width="11" height="11" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 11h18"/></svg> },
  task_stage_change:  { label:"Task Stage Changed", bg:"bg-sky-100",     accent:"text-sky-600",     icon:<svg width="11" height="11" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg> },
  task_completed:     { label:"Task Completed",     bg:"bg-emerald-100", accent:"text-emerald-600", icon:<svg width="11" height="11" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M9 11l3 3 8-8"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/></svg> },
  meta_import:        { label:"Meta Import",        bg:"bg-blue-100",    accent:"text-blue-600",    icon:<svg width="11" height="11" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" viewBox="0 0 24 24"><rect x="5" y="2" width="14" height="20" rx="2"/></svg> },
  user_joined:        { label:"User Joined",        bg:"bg-rose-100",    accent:"text-rose-600",    icon:<svg width="11" height="11" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg> },
};

// ─── Main Page ────────────────────────────────────────────────────────────────
export default function ConvertedLeadsPage({ params: paramsPromise }: { params: Promise<{ domain: string }> }) {
  const params = use(paramsPromise);
  const domain = APP_SLUG;

  const getRecordingUrl = (url: string, id: number) => {
    if (!url) return "";
    if (url.includes("exotel") || url.includes("recordings.exotel")) {
      const token = localStorage.getItem(`${domain}_access`);
      return `${getApiBase(domain)}/api/calls/${id}/recording_proxy/${token ? `?token=${token}` : ''}`;
    }
    return url;
  };

  // ─── Dynamic lead statuses (standard + tenant custom) ──────────────────────
  const { statusMeta, statusOptions } = useLeadStatuses(domain);

  // ── Page data
  const [loading,   setLoading]   = useState(true);
  const [metrics,   setMetrics]   = useState<any>(null);
  const [leads,     setLeads]     = useState<any[]>([]);
  const [search,    setSearch]    = useState("");
  const [currentUser, setCurrentUser] = useState<any>(null);
  // ── Filters (combinable)
  const [stageFilter,      setStageFilter]      = useState("");  // '', 'converted', 'closed_deal', 'partially_paid', 'fully_paid'
  const [telecallerFilter, setTelecallerFilter] = useState("");  // assigned_to id
  const [bdeFilter,        setBdeFilter]        = useState("");  // bde id

  // ── Drawer state
  const [selected,         setSelected]         = useState<any>(null);
  const [drawerOpen,       setDrawerOpen]        = useState(false);
  const [history,          setHistory]           = useState<any[]>([]);
  const [histLoading,      setHistLoading]       = useState(false);
  const [tasks,            setTasks]             = useState<any[]>([]);
  const [tasksLoading,     setTasksLoading]      = useState(false);
  const [calls,            setCalls]             = useState<any[]>([]);
  const [callsLoading,     setCallsLoading]      = useState(false);
  const [attachments,      setAttachments]       = useState<any[]>([]);
  const [attLoading,       setAttLoading]        = useState(false);
  const [activeTab,        setActiveTab]         = useState<"overview"|"history"|"tasks"|"calls"|"files">("overview");

  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [previewFile, setPreviewFile] = useState<{ url: string; name: string } | null>(null);

  useEffect(() => { fetchData(); }, [domain]);

  const fetchData = async () => {
    setLoading(true);
    const token = localStorage.getItem(`${domain}_access`);
    if (!token) return;
    try {
      const [mRes, lRes, uRes] = await Promise.all([
        fetch(`${getApiBase(domain)}/api/converted-analytics/`, { headers: { Authorization: `Bearer ${token}` } }),
        fetch(`${getApiBase(domain)}/api/leads/?status=converted`, { headers: { Authorization: `Bearer ${token}` } }),
        fetch(`${getApiBase(domain)}/api/users/me/`, { headers: { Authorization: `Bearer ${token}` } }),
      ]);
      if (mRes.ok) setMetrics(await mRes.json());
      else setMetrics({ total_conversions: 0, total_revenue: 0, closed_deal_count: 0, avg_conversion_days: 0, top_sources: [] });
      if (lRes.ok) { const d = await lRes.json(); setLeads(Array.isArray(d) ? d : d.results || []); }
      if (uRes.ok) setCurrentUser(await uRes.json());
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  };

  const openDrawer = async (lead: any) => {
    setSelected(lead);
    setDrawerOpen(true);
    setActiveTab("overview");
    setHistory([]); setTasks([]); setCalls([]); setAttachments([]);

    const token = localStorage.getItem(`${domain}_access`);
    const h = { Authorization: `Bearer ${token}` };

    setHistLoading(true);
    setTasksLoading(true);
    setCallsLoading(true);
    setAttLoading(true);

    const [histRes, tasksRes, callsRes, attRes] = await Promise.all([
      fetch(`${getApiBase(domain)}/api/leads/${lead.id}/history/`, { headers: h }),
      fetch(`${getApiBase(domain)}/api/tasks/?lead=${lead.id}`, { headers: h }),
      fetch(`${getApiBase(domain)}/api/calls/?lead=${lead.id}`, { headers: h }),
      fetch(`${getApiBase(domain)}/api/leads/${lead.id}/attachments/`, { headers: h }),
    ]);

    if (histRes.ok) setHistory(await histRes.json()); setHistLoading(false);
    if (tasksRes.ok) { const d = await tasksRes.json(); setTasks(Array.isArray(d) ? d : d.results || []); } setTasksLoading(false);
    if (callsRes.ok) { const d = await callsRes.json(); setCalls(Array.isArray(d) ? d : d.results || []); } setCallsLoading(false);
    if (attRes.ok) setAttachments(await attRes.json()); setAttLoading(false);
  };

  const closeDrawer = () => { setDrawerOpen(false); setTimeout(() => setSelected(null), 300); };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !selected) return;
    if (file.size > 50 * 1024 * 1024) { alert("Max 50MB"); return; }
    setUploading(true);
    const token = localStorage.getItem(`${domain}_access`);
    const fd = new FormData(); fd.append("file", file);
    try {
      const r = await fetch(`${getApiBase(domain)}/api/leads/${selected.id}/attachments/`, {
        method: "POST", headers: { Authorization: `Bearer ${token}` }, body: fd,
      });
      if (r.ok) { const newAtt = await r.json(); setAttachments(prev => [newAtt, ...prev]); }
      else alert("Upload failed");
    } catch { alert("Error uploading"); }
    finally { setUploading(false); if (fileRef.current) fileRef.current.value = ""; }
  };

  const deleteAttachment = async (attId: number, name: string) => {
    if (!selected || !confirm(`Delete "${name}"?`)) return;
    const token = localStorage.getItem(`${domain}_access`);
    const r = await fetch(`${getApiBase(domain)}/api/leads/${selected.id}/attachments/${attId}/`, {
      method: "DELETE", headers: { Authorization: `Bearer ${token}` },
    });
    if (r.ok || r.status === 204) setAttachments(prev => prev.filter(a => a.id !== attId));
  };

  // ── Derived
  const data = metrics || { total_conversions: 0, total_revenue: 0, closed_deal_count: 0, avg_conversion_days: 0, top_sources: [] };
  const maxSrc = data.top_sources.length > 0 ? Math.max(...data.top_sources.map((s: any) => s.count)) : 1;
  const isManagerOrAdmin = !!(currentUser?.is_staff || currentUser?.is_general_manager || currentUser?.is_manager);

  // Assignee filter options, derived from the converted leads actually present.
  const uniqueBy = (items: [string, string][]) => Array.from(new Map(items).entries());
  // Owners whose role is actually tele caller. The rows are matched on
  // `assigned_to`, which is simply whoever owns the lead — an admin or a BDE can
  // own one — so listing every owner put superadmins and BDEs in a picker
  // labelled "Tele Caller". The role rides along on `assigned_to_details`.
  const telecallerOptions = uniqueBy(
    leads.filter(l => l.assigned_to && l.assigned_to_details?.role === "tele_caller")
         .map(l => [String(l.assigned_to), l.assigned_to_name || `#${l.assigned_to}`] as [string, string]));
  const bdeOptions        = uniqueBy(leads.filter(l => l.bde).map(l => [String(l.bde), l.bde_name || `#${l.bde}`] as [string, string]));

  const stageMatch = (l: any) => {
    if (!stageFilter) return true;
    if (stageFilter === "converted") return !l.deal_classification && !l.is_closed_deal;  // nothing landed yet
    if (stageFilter === "closed_deal") return !!l.is_closed_deal;
    return l.deal_classification === stageFilter;
  };
  const filtered = leads.filter(l =>
    (!search || `${l.first_name} ${l.last_name} ${l.email} ${l.phone} ${l.company}`.toLowerCase().includes(search.toLowerCase()))
    && stageMatch(l)
    && (!telecallerFilter || String(l.assigned_to) === telecallerFilter)
    && (!bdeFilter || String(l.bde) === bdeFilter)
  );

  const activeFilterCount = (stageFilter ? 1 : 0) + (telecallerFilter ? 1 : 0) + (bdeFilter ? 1 : 0);
  const clearFilters = () => { setStageFilter(""); setTelecallerFilter(""); setBdeFilter(""); };

  const daysInPipeline = (lead: any) => {
    const created   = new Date(lead.created_at);
    // Use the exact enrollment timestamp; fall back to updated_at as the closest proxy
    const converted = new Date(lead.status_changed_at || lead.updated_at || lead.created_at);
    return Math.max(0, Math.round((converted.getTime() - created.getTime()) / 86400000));
  };

  const markLost = async (lead: any) => {
    const reason = window.prompt(
      `Mark "${lead.first_name} ${lead.last_name || ""}" as lost?\nOptional reason (customer skipped / backed out, other issue…):`,
      ""
    );
    if (reason === null) return; // cancelled
    const token = localStorage.getItem(`${domain}_access`);
    const r = await fetch(`${getApiBase(domain)}/api/leads/${lead.id}/mark-lost/`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ reason }),
    });
    if (r.ok) fetchData();
    else { const e = await r.json().catch(() => ({})); alert(e.error || "Could not mark this lead as lost."); }
  };

  const restoreLost = async (lead: any) => {
    if (!window.confirm(`Restore "${lead.first_name} ${lead.last_name || ""}" from lost?`)) return;
    const token = localStorage.getItem(`${domain}_access`);
    const r = await fetch(`${getApiBase(domain)}/api/leads/${lead.id}/restore-lost/`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (r.ok) fetchData();
    else { const e = await r.json().catch(() => ({})); alert(e.error || "Could not restore this lead."); }
  };

  const exportCSV = async () => {
    const token = localStorage.getItem(`${domain}_access`);
    if (!token) return;
    try {
      const r = await fetch(`${getApiBase(domain)}/api/leads/export_csv/?status=converted`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (!r.ok) throw new Error("Failed to export");
      const blob = await r.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `Converted_Leads_Report_${new Date().toISOString().split('T')[0]}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (e) {
      alert("Error exporting report");
    }
  };

  // ── Loading
  if (loading && !metrics) return (
    <div className="min-h-screen bg-[#f4f6fa] flex items-center justify-center">
      <div className="flex flex-col items-center gap-4">
        <div className="w-10 h-10 border-4 border-emerald-500 border-t-transparent rounded-full animate-spin" />
        <p className="text-sm font-semibold text-slate-500 uppercase tracking-widest animate-pulse">Loading Command Centre…</p>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-[#f4f6fa] font-sans pb-24">

      {/* ─── Header ───────────────────────────────────────────────────────── */}
      <div className="bg-white border-b border-slate-200/50 sticky top-0 z-30 shadow-sm">
        <div className="max-w-[1440px] mx-auto px-6 xl:px-8 h-[68px] flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-br from-emerald-400 to-teal-500 rounded-xl flex items-center justify-center text-white shadow-lg shadow-teal-500/20">
              <I.Trophy />
            </div>
            <div>
              <h1 className="text-[17px] font-black text-slate-900 leading-none">Converted Leads</h1>
              <p className="text-[11px] text-slate-400 mt-0.5">{leads.length} converted clients</p>
            </div>
          </div>
          {/* Search */}
          <div className="flex items-center gap-3">
            <div className="relative hidden sm:block">
              <svg className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
              <input
                value={search} onChange={e => setSearch(e.target.value)}
                placeholder="Search clients…"
                className="pl-9 pr-4 py-2 text-sm bg-slate-50 border border-slate-200 rounded-xl outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-400 transition-all w-[220px]"
              />
            </div>
            <button onClick={exportCSV} className="px-4 py-2 bg-white border border-slate-200 text-slate-700 font-bold rounded-xl text-sm shadow-sm hover:bg-slate-50 transition-all text-[13px] flex items-center gap-2">
              <I.Download /> Export Report
            </button>
          </div>
        </div>
      </div>

      <div className="max-w-[1440px] mx-auto px-6 xl:px-8 mt-7">

        {/* ─── KPI Grid ─────────────────────────────────────────────────── */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-5 mb-7">
          {[
            // Won means closed — in accounts with money received. The badge says
            // so, because it sits next to a count of every converted lead and
            // the two would otherwise read as one figure.
            { label: "Won Revenue",     value: formatCurrency(data.total_revenue), icon: <I.TrendUp />, color: "from-emerald-400 to-teal-400", badge: `${data.closed_deal_count ?? 0} closed deals`, badgeColor: "bg-emerald-50 text-emerald-600" },
            { label: "Total Converts",  value: `${data.total_conversions}`, sub: "deals", icon: <I.Trophy />, color: "from-indigo-400 to-violet-400", badge: "Active Lifecycle", badgeColor: "bg-indigo-50 text-indigo-600" },
            { label: "Avg Time to Convert", value: `${data.avg_conversion_days}`, sub: "days", icon: <I.Clock />, color: "from-amber-400 to-orange-400", badge: "From Creation", badgeColor: "bg-amber-50 text-amber-600" },
            { label: "Top Source", value: data.top_sources[0]?.source ? getSourceLabel(data.top_sources[0].source) : "—", icon: <I.Target />, color: "from-fuchsia-400 to-pink-400", badge: data.top_sources[0]?.count ? `${data.top_sources[0].count} leads` : "No data", badgeColor: "bg-fuchsia-50 text-fuchsia-600" },
          ].map((c, i) => (
            <div key={i} className="bg-white rounded-2xl p-5 border border-slate-100 shadow-[0_4px_20px_rgb(0,0,0,0.04)] relative overflow-hidden group hover:shadow-[0_8px_30px_rgb(0,0,0,0.08)] transition-shadow">
              <div className={`absolute inset-x-0 bottom-0 h-1 bg-gradient-to-r ${c.color}`} />
              <div className="flex items-start justify-between mb-3">
                <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">{c.label}</p>
                <div className={`w-6 h-6 rounded-lg bg-gradient-to-br ${c.color} flex items-center justify-center text-white opacity-70`}>{c.icon}</div>
              </div>
              <p className="text-3xl font-black text-slate-900 leading-none">
                {c.value} {c.sub && <span className="text-base text-slate-400 font-semibold">{c.sub}</span>}
              </p>
              <span className={`inline-block mt-3 text-[10px] font-bold px-2 py-0.5 rounded-md ${c.badgeColor}`}>{c.badge}</span>
            </div>
          ))}
        </div>

        {/* ─── Source mini chart ─────────────────────────────────────────── */}
        {data.top_sources.length > 1 && (
          <div className="bg-white rounded-2xl p-5 border border-slate-100 shadow-[0_4px_20px_rgb(0,0,0,0.04)] mb-7">
            <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-4">Source Breakdown</p>
            <div className="flex flex-col gap-3">
              {data.top_sources.map((s: any, i: number) => {
                const pct = Math.max(6, Math.round((s.count / maxSrc) * 100));
                const cols = ["bg-indigo-500","bg-violet-400","bg-emerald-400","bg-amber-400","bg-fuchsia-400"];
                return (
                  <div key={i} className="flex items-center gap-3">
                    <p className="text-[11px] text-slate-600 font-semibold w-24 flex-shrink-0">{getSourceLabel(s.source)}</p>
                    <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
                      <div className={`h-full rounded-full ${cols[i % 5]} transition-all duration-700`} style={{ width: `${pct}%` }} />
                    </div>
                    <p className="text-[11px] font-black text-slate-700 w-6 text-right">{s.count}</p>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ─── Filters (combinable) ──────────────────────────────────────── */}
        <div className="bg-white rounded-2xl border border-slate-100 shadow-[0_4px_20px_rgb(0,0,0,0.04)] p-4 mb-5 flex flex-wrap items-end gap-4">
          <div className="min-w-[160px]">
            <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1.5">Stage</label>
            <select value={stageFilter} onChange={e => setStageFilter(e.target.value)}
              className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-400 transition-all">
              <option value="">All stages</option>
              <option value="converted">Converted</option>
              <option value="closed_deal">Closed Deal</option>
              <option value="partially_paid">Partially Paid</option>
              <option value="fully_paid">Fully Paid</option>
              <option value="lost">Lost</option>
            </select>
          </div>
          {isManagerOrAdmin && (
            <div className="min-w-[160px]">
              <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1.5">Tele Caller</label>
              <select value={telecallerFilter} onChange={e => setTelecallerFilter(e.target.value)}
                className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-400 transition-all">
                <option value="">All tele callers</option>
                {telecallerOptions.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
              </select>
            </div>
          )}
          {isManagerOrAdmin && (
            <div className="min-w-[160px]">
              <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1.5">BDE</label>
              <select value={bdeFilter} onChange={e => setBdeFilter(e.target.value)}
                className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-400 transition-all">
                <option value="">All BDEs</option>
                {bdeOptions.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
              </select>
            </div>
          )}
          {activeFilterCount > 0 && (
            <button onClick={clearFilters}
              className="ml-auto px-4 py-2 text-sm font-bold text-slate-500 hover:text-slate-700 bg-slate-50 hover:bg-slate-100 rounded-xl transition-colors">
              Clear filters ({activeFilterCount})
            </button>
          )}
        </div>

        {/* ─── Client Table ──────────────────────────────────────────────── */}
        <div className="bg-white rounded-2xl border border-slate-100 shadow-[0_4px_20px_rgb(0,0,0,0.04)] overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
            <div>
              <h2 className="text-[15px] font-black text-slate-800">Converted Clients</h2>
              <p className="text-[11px] text-slate-400 mt-0.5">Click a row to view full profile & history</p>
            </div>
            <span className="bg-emerald-100 text-emerald-700 text-[10px] font-black px-2.5 py-1 rounded-full">{filtered.length} records</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left min-w-[780px]">
              <thead>
                <tr className="bg-slate-50">
                  {["Client", "Converted On", "Velocity", "Deal Value", "Source", "Assigned To", ""].map(h => (
                    <th key={h} className="px-5 py-3.5 text-[10px] font-black text-slate-400 uppercase tracking-widest">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {filtered.length === 0 && (
                  <tr><td colSpan={7} className="py-20 text-center">
                    <div className="w-14 h-14 bg-slate-50 rounded-full flex items-center justify-center mx-auto mb-4 text-slate-300"><I.Trophy /></div>
                    <p className="text-base font-black text-slate-600">No converted clients found</p>
                    <p className="text-sm text-slate-400 mt-1">Leads marked 'Converted' will appear here</p>
                  </td></tr>
                )}
                {filtered.map(lead => (
                  <tr
                    key={lead.id}
                    onClick={() => openDrawer(lead)}
                    className="hover:bg-emerald-50/40 cursor-pointer transition-colors group"
                  >
                    <td className="px-5 py-4">
                      <div className="flex items-center gap-3">
                        <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-emerald-400 to-teal-400 flex items-center justify-center text-white text-[11px] font-black flex-shrink-0 shadow-md shadow-emerald-200">
                          {lead.first_name?.[0]}{lead.last_name?.[0]}
                        </div>
                        <div>
                          <p className="text-[13px] font-bold text-slate-800 group-hover:text-emerald-700 transition-colors">{lead.first_name} {lead.last_name}</p>
                          <p className="text-[11px] text-slate-400">{lead.email || lead.phone || "—"}</p>
                          <div className="mt-1 flex items-center gap-1.5 flex-wrap"><StageTag stage={lead.pipeline_stage} /><DealClassBadge value={lead.deal_classification} closed={lead.is_closed_deal} /></div>
                        </div>
                      </div>
                    </td>
                    <td className="px-5 py-4">
                      <p className="text-[12px] font-semibold text-slate-700">
                        {lead.status_changed_at
                          ? new Date(lead.status_changed_at).toLocaleDateString('en-IN', { day:'2-digit', month:'short', year:'numeric' })
                          : new Date(lead.created_at).toLocaleDateString('en-IN', { day:'2-digit', month:'short', year:'numeric' })}
                      </p>
                      <span className="text-[10px] font-bold text-emerald-500">✓ Converted</span>
                    </td>
                    <td className="px-5 py-4">
                      <span className="inline-flex items-center gap-1 text-[11px] font-bold text-slate-600 bg-slate-100 px-2.5 py-1 rounded-lg">
                        <I.Clock /> {daysInPipeline(lead)}d
                      </span>
                    </td>
                    <td className="px-5 py-4">
                      <span className="inline-flex items-center text-[13px] font-black text-emerald-700 bg-emerald-50 border border-emerald-100 px-3 py-1 rounded-lg">
                        {formatCurrency(lead.value)}
                      </span>
                    </td>
                    <td className="px-5 py-4">
                      <span className="text-[11px] font-bold text-slate-600 bg-slate-100 px-2.5 py-1 rounded-md">{getSourceLabel(lead.source)}</span>
                    </td>
                    <td className="px-5 py-4">
                      {lead.assigned_to_name
                        ? <div className="flex items-center gap-2">
                            <div className="w-6 h-6 rounded-full bg-gradient-to-br from-indigo-400 to-violet-500 text-white flex items-center justify-center text-[9px] font-black">{lead.assigned_to_name.charAt(0)}</div>
                            <span className="text-[11px] font-semibold text-slate-600">{lead.assigned_to_name}</span>
                          </div>
                        : <span className="text-[11px] text-slate-300 italic">Unassigned</span>}
                    </td>
                    <td className="px-5 py-4">
                      <div className="flex items-center gap-1.5">
                        {lead.invoice && (
                          <a href={lead.invoice} target="_blank" rel="noreferrer" title="Download Invoice"
                            onClick={e => e.stopPropagation()}
                            className="flex items-center gap-1 px-2.5 py-1.5 bg-fuchsia-50 hover:bg-fuchsia-100 text-fuchsia-700 font-bold text-[10px] rounded-lg transition-colors">
                            <I.Download /> Invoice
                          </a>
                        )}
                        <button onClick={e => { e.stopPropagation(); openDrawer(lead); }}
                          className="flex items-center gap-1 px-2.5 py-1.5 bg-emerald-50 hover:bg-emerald-100 text-emerald-700 font-bold text-[10px] rounded-lg transition-colors">
                          <I.History /> View
                        </button>
                        <button onClick={e => { e.stopPropagation(); alert(`Welcome sequence triggered for ${lead.first_name}`); }}
                          className="flex items-center gap-1 px-2.5 py-1.5 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 font-bold text-[10px] rounded-lg transition-colors">
                          <I.Mail /> Welcome
                        </button>
                        {lead.can_mark_lost && (lead.deal_classification === 'lost' ? (
                          <button onClick={e => { e.stopPropagation(); restoreLost(lead); }}
                            className="flex items-center gap-1 px-2.5 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-600 font-bold text-[10px] rounded-lg transition-colors">
                            Restore
                          </button>
                        ) : (
                          <button onClick={e => { e.stopPropagation(); markLost(lead); }}
                            className="flex items-center gap-1 px-2.5 py-1.5 bg-rose-50 hover:bg-rose-100 text-rose-700 font-bold text-[10px] rounded-lg transition-colors">
                            <I.X /> Mark Lost
                          </button>
                        ))}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* ─── Drawer Overlay ────────────────────────────────────────────────── */}
      {drawerOpen && (
        <div className="fixed inset-0 z-40 bg-black/30 backdrop-blur-[2px]" />
      )}

      {/* ─── Slide-in Drawer ──────────────────────────────────────────────── */}
      <div
        className={`fixed top-0 right-0 h-full z-50 bg-white shadow-2xl flex flex-col transition-all duration-300 ease-out
          ${drawerOpen ? "translate-x-0 w-full sm:w-[580px] lg:w-[680px]" : "translate-x-full w-[680px]"}`}
      >
        {selected && (
          <>
            {/* Drawer Header */}
            <div className="flex-shrink-0 bg-gradient-to-r from-emerald-600 to-teal-500 text-white px-6 py-5">
              <div className="flex items-start justify-between gap-4">
                <div className="flex items-center gap-4">
                  <div className="w-14 h-14 rounded-2xl bg-white/20 backdrop-blur flex items-center justify-center text-2xl font-black flex-shrink-0 shadow-lg">
                    {selected.first_name?.[0]}{selected.last_name?.[0]}
                  </div>
                  <div>
                    <h2 className="text-xl font-black leading-tight">{selected.first_name} {selected.last_name}</h2>
                    <p className="text-sm text-emerald-100 mt-0.5">{selected.company || selected.email || selected.phone || "No contact info"}</p>
                    <div className="flex items-center gap-2 mt-2">
                      <span className="inline-flex items-center gap-1 bg-white/20 text-white text-[10px] font-bold px-2.5 py-1 rounded-full">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-300" />Converted
                      </span>
                      <span className="text-[10px] text-emerald-200 font-semibold">{formatCurrency(selected.value)}</span>
                    </div>
                  </div>
                </div>
                <button onClick={closeDrawer}
                  className="w-8 h-8 mt-1 flex items-center justify-center rounded-xl bg-white/20 hover:bg-white/30 transition-colors flex-shrink-0">
                  <I.X />
                </button>
              </div>

              {/* Tab Bar */}
              <div className="flex gap-1 mt-5 bg-white/10 rounded-xl p-1">
                {([ { key:"overview", label:"Overview", icon:<I.Star /> },
                    { key:"history",  label:"History",  icon:<I.History /> },
                    { key:"tasks",    label:"Tasks",    icon:<I.Task /> },
                    { key:"calls",    label:"Calls",    icon:<I.Phone /> },
                    { key:"files",    label:"Files",    icon:<I.Attach /> },
                ] as { key: "overview"|"history"|"tasks"|"calls"|"files"; label: string; icon: React.ReactNode }[]).map(t => (
                  <button key={t.key} onClick={() => setActiveTab(t.key)}
                    className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-[10px] font-black transition-all
                      ${activeTab === t.key ? "bg-white text-emerald-700 shadow-sm" : "text-white/70 hover:text-white"}`}>
                    {t.icon} <span className="hidden sm:inline">{t.label}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Drawer Body */}
            <div className="flex-1 overflow-y-auto">

              {/* ── Overview Tab ── */}
              {activeTab === "overview" && (
                <div className="p-6 space-y-5">
                  {/* Contact Info Grid */}
                  <div>
                    <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-3">Contact Information</p>
                    <div className="grid grid-cols-2 gap-3">
                      {[
                        { label:"Email",      value: selected.email || "—" },
                        { label:"Phone",      value: selected.phone || "—" },
                        { label:"Company",    value: selected.company || "—" },
                        { label:"Source",     value: getSourceLabel(selected.source) },
                        { label:"Assigned To",value: selected.assigned_to_name || "Unassigned" },
                        { label:"Deal Value", value: formatCurrency(selected.value) },
                      ].map(({ label, value }) => (
                        <div key={label} className="bg-slate-50 rounded-xl p-3.5 border border-slate-100">
                          <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">{label}</p>
                          <p className="text-[13px] font-semibold text-slate-800 truncate">{value}</p>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Metrics */}
                  <div>
                    <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-3">Conversion Metrics</p>
                    <div className="grid grid-cols-3 gap-3">
                      <div className="bg-emerald-50 border border-emerald-100 rounded-xl p-4 text-center">
                        <p className="text-2xl font-black text-emerald-700">{daysInPipeline(selected)}</p>
                        <p className="text-[10px] text-emerald-600 font-bold mt-1">Days to Close</p>
                      </div>
                      <div className="bg-indigo-50 border border-indigo-100 rounded-xl p-4 text-center">
                        <p className="text-2xl font-black text-indigo-700">{tasks.length}</p>
                        <p className="text-[10px] text-indigo-600 font-bold mt-1">Tasks</p>
                      </div>
                      <div className="bg-teal-50 border border-teal-100 rounded-xl p-4 text-center">
                        <p className="text-2xl font-black text-teal-700">{calls.length}</p>
                        <p className="text-[10px] text-teal-600 font-bold mt-1">Calls</p>
                      </div>
                    </div>
                  </div>

                  {/* Dates */}
                  <div>
                    <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-3">Timeline</p>
                    <div className="space-y-2">
                      {[
                        { label: "Created", val: selected.created_at },
                        { label: "Converted", val: selected.status_changed_at || selected.created_at },
                        { label: "Last Updated", val: selected.updated_at },
                      ].map(({ label, val }) => {
                        const d = new Date(val);
                        return (
                          <div key={label} className="flex items-center justify-between bg-slate-50 rounded-xl px-4 py-3 border border-slate-100">
                            <p className="text-[11px] font-bold text-slate-500">{label}</p>
                            <div className="text-right">
                              <span className="text-[12px] font-semibold text-slate-800">
                                {d.toLocaleDateString('en-IN', { day:'2-digit', month:'short', year:'numeric' })}
                              </span>
                              <span className="text-[10px] text-slate-400 ml-2">
                                {d.toLocaleTimeString('en-IN', { hour:'2-digit', minute:'2-digit', hour12:true })}
                              </span>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {/* Notes */}
                  {selected.notes && (
                    <div>
                      <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-3">Notes</p>
                      <div className="bg-amber-50 border border-amber-100 rounded-xl p-4">
                        <p className="text-[13px] text-slate-700 leading-relaxed whitespace-pre-wrap">{selected.notes}</p>
                      </div>
                    </div>
                  )}

                  {/* Quick Actions */}
                  <div>
                    <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-3">Quick Actions</p>
                    <div className="grid grid-cols-2 gap-3">
                      <button onClick={() => alert(`Welcome sequence triggered for ${selected.first_name}`)}
                        className="flex items-center justify-center gap-2 py-3 bg-indigo-600 hover:bg-indigo-700 text-white font-bold rounded-xl text-[12px] transition-colors shadow-md shadow-indigo-200">
                        <I.Mail /> Send Welcome
                      </button>
                      {selected.invoice ? (
                        <button onClick={() => setPreviewFile({ url: selected.invoice, name: "Official Invoice" })}
                          className="flex items-center justify-center gap-2 py-3 bg-fuchsia-600 hover:bg-fuchsia-700 text-white font-bold rounded-xl text-[12px] transition-colors shadow-md shadow-fuchsia-200">
                          <I.Download /> View Invoice
                        </button>
                      ) : (
                        <button onClick={() => alert(`Invoice generation triggered for ${selected.first_name}`)}
                          className="flex items-center justify-center gap-2 py-3 bg-slate-800 hover:bg-slate-900 text-white font-bold rounded-xl text-[12px] transition-colors shadow-md shadow-slate-200">
                          <I.Invoice /> Generate Invoice
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* ── History Tab ── */}
              {activeTab === "history" && (
                <div className="p-6">
                  {histLoading && (
                    <div className="flex items-center justify-center py-20">
                      <div className="w-7 h-7 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
                    </div>
                  )}
                  {!histLoading && history.length === 0 && (
                    <div className="flex flex-col items-center py-20 text-slate-300">
                      <I.History />
                      <p className="text-sm mt-3 text-slate-400">No history events yet</p>
                    </div>
                  )}
                  {!histLoading && history.length > 0 && (
                    <div className="relative">
                      <div className="absolute left-4 top-2 bottom-2 w-px bg-slate-100" />
                      <div className="space-y-4">
                        {history.map((log: any) => {
                          const cfg = typeConfig[log.type] || { label: log.type, bg:"bg-slate-100", accent:"text-slate-500", icon:<I.History /> };
                          const ts = new Date(log.timestamp);
                          return (
                            <div key={log.id} className="flex gap-4">
                              <div className={`w-8 h-8 rounded-xl ${cfg.bg} ${cfg.accent} flex items-center justify-center flex-shrink-0 z-10 mt-0.5`}>
                                {cfg.icon}
                              </div>
                              <div className="flex-1 bg-slate-50 rounded-xl p-3.5 border border-slate-100">
                                <div className="flex items-start justify-between gap-2 mb-1">
                                  <span className={`text-[10px] font-black uppercase tracking-wide ${cfg.accent}`}>{cfg.label}</span>
                                  <span className="text-[10px] text-slate-400 flex-shrink-0">
                                    {ts.toLocaleDateString('en-IN', { day:'2-digit', month:'short' })} · {ts.toLocaleTimeString('en-IN', { hour:'2-digit', minute:'2-digit', hour12:true })}
                                  </span>
                                </div>
                                <p className="text-[12px] text-slate-700 font-medium">{log.description}</p>
                                {log.extra?.note && <div className="mt-2 bg-teal-50 border border-teal-100 rounded-lg px-3 py-2"><p className="text-[11px] text-slate-700">{log.extra.note}</p></div>}
                                {log.extra?.old_status && log.extra?.new_status && (
                                  <div className="flex items-center gap-2 mt-2">
                                    <StatusPill status={log.extra.old_status} statusMeta={statusMeta} />
                                    <svg width="10" height="10" fill="none" stroke="#94a3b8" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
                                    <StatusPill status={log.extra.new_status} statusMeta={statusMeta} />
                                  </div>
                                )}
                                {log.actor && <p className="text-[10px] text-slate-400 mt-1.5">by {log.actor}</p>}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* ── Tasks Tab ── */}
              {activeTab === "tasks" && (
                <div className="p-6">
                  {tasksLoading ? <div className="flex justify-center py-20"><div className="w-7 h-7 border-2 border-violet-500 border-t-transparent rounded-full animate-spin" /></div> :
                    tasks.length === 0 ? <div className="flex flex-col items-center py-20 text-slate-300"><I.Task /><p className="text-sm mt-3 text-slate-400">No tasks linked</p></div> :
                    <div className="space-y-3">
                      {tasks.map((t: any) => {
                        const sc: Record<string, string> = { todo:"bg-slate-100 text-slate-600", in_progress:"bg-blue-50 text-blue-600", review:"bg-violet-50 text-violet-600", done:"bg-emerald-50 text-emerald-600" };
                        const pc: Record<string, string> = { high:"text-red-500", medium:"text-amber-500", low:"text-emerald-500" };
                        return (
                          <div key={t.id} className={`bg-white border border-slate-100 rounded-xl p-4 shadow-sm ${t.status === "done" ? "opacity-50" : ""}`}>
                            <div className="flex items-start justify-between gap-2">
                              <p className={`text-[13px] font-semibold text-slate-800 ${t.status === "done" ? "line-through text-slate-400" : ""}`}>{t.title}</p>
                              <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full flex-shrink-0 ${sc[t.status] || "bg-slate-100 text-slate-500"}`}>
                                {t.status.replace("_"," ")}
                              </span>
                            </div>
                            <div className="flex items-center gap-3 mt-2">
                              <span className={`text-[10px] font-bold ${pc[t.priority] || "text-slate-400"}`}>● {t.priority}</span>
                              {t.due_date && <span className="text-[10px] text-slate-400">Due: {new Date(t.due_date).toLocaleDateString('en-IN', { day:'2-digit', month:'short' })}</span>}
                            </div>
                          </div>
                        );
                      })}
                    </div>}
                </div>
              )}

              {/* ── Calls Tab ── */}
              {activeTab === "calls" && (
                <div className="p-6">
                  {callsLoading ? <div className="flex justify-center py-20"><div className="w-7 h-7 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" /></div> :
                    calls.length === 0 ? <div className="flex flex-col items-center py-20 text-slate-300"><I.Phone /><p className="text-sm mt-3 text-slate-400">No calls recorded</p></div> :
                    <div className="space-y-3">
                      {calls.map((c: any) => {
                        const oc: Record<string, string> = {
                          connected: "bg-emerald-50 text-emerald-700 border-emerald-100",
                          completed: "bg-emerald-50 text-emerald-700 border-emerald-100",
                          rnr: "bg-orange-50 text-orange-700 border-orange-100",
                          busy: "bg-blue-50 text-blue-700 border-blue-100",
                          rejected: "bg-blue-50 text-blue-700 border-blue-100",
                          failed: "bg-blue-50 text-blue-700 border-blue-100",
                          cancelled: "bg-rose-50 text-rose-700 border-rose-100",
                          canceled: "bg-rose-50 text-rose-700 border-rose-100",
                        };
                        const ol: Record<string, string> = {
                          connected: 'Connected',
                          completed: 'Connected',
                          rnr: 'RNR',
                          'no-answer': 'RNR',
                          busy: 'Busy',
                          rejected: 'Busy',
                          failed: 'Busy',
                          cancelled: 'Cancelled',
                          canceled: 'Cancelled',
                          initiated: 'Initiated',
                        };
                        return (
                          <div key={c.id} className="bg-white border border-slate-100 rounded-xl p-4 shadow-sm">
                            <div className="flex items-center justify-between mb-2">
                              <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-black uppercase tracking-wider border ${oc[c.outcome] || "bg-slate-100 text-slate-600 border-slate-200"}`}>
                                {ol[c.outcome] || c.outcome}
                              </span>
                              <span className="text-[12px] font-mono text-slate-500">
                                {Math.floor(c.duration_seconds/60)}:{(c.duration_seconds%60).toString().padStart(2,"0")}
                              </span>
                            </div>
                            {c.recording_url && <audio controls className="w-full h-7 mt-2" src={getRecordingUrl(c.recording_url, c.id)} />}
                            <p className="text-[10px] text-slate-400 mt-2">
                              {new Date(c.created_at).toLocaleDateString('en-IN', { day:'2-digit', month:'short', year:'numeric' })} at {new Date(c.created_at).toLocaleTimeString('en-IN', { hour:'2-digit', minute:'2-digit' })}
                            </p>
                          </div>
                        );
                      })}
                    </div>}
                </div>
              )}

              {/* ── Files Tab ── */}
              {activeTab === "files" && (
                <div className="p-6">
                  <div className="flex items-center justify-between mb-4">
                    <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Attachments ({attachments.length})</p>
                    <button
                      onClick={() => fileRef.current?.click()}
                      disabled={uploading}
                      className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white text-[11px] font-bold rounded-lg transition-colors disabled:opacity-50 shadow-md shadow-emerald-200"
                    >
                      {uploading ? <><div className="w-3 h-3 border border-white border-t-transparent rounded-full animate-spin" />Uploading…</> : <><I.Attach /> Attach File</>}
                    </button>
                    <input ref={fileRef} type="file" className="hidden" onChange={handleFileUpload} />
                  </div>

                  {attLoading ? <div className="flex justify-center py-16"><div className="w-7 h-7 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" /></div> :
                    attachments.length === 0 && !selected.invoice ? (
                      <div onClick={() => fileRef.current?.click()}
                        className="border-2 border-dashed border-slate-200 hover:border-emerald-300 hover:bg-emerald-50/30 rounded-2xl py-14 text-center cursor-pointer transition-all group">
                        <div className="flex justify-center mb-3 text-slate-300 group-hover:text-emerald-400 transition-colors"><I.Attach /></div>
                        <p className="text-[13px] font-semibold text-slate-400 group-hover:text-emerald-600 transition-colors">Click to attach files</p>
                        <p className="text-[11px] text-slate-300 mt-1">PDF, images, docs — max 50MB each</p>
                      </div>
                    ) : (
                      <div className="space-y-2">
                        {selected.invoice && (
                          <div 
                            onClick={() => setPreviewFile({ url: selected.invoice, name: "Official Invoice" })}
                            className="flex items-center justify-between p-3 rounded-xl border border-fuchsia-100 bg-fuchsia-50 hover:bg-fuchsia-100 transition-colors group cursor-pointer"
                          >
                            <div className="flex items-center gap-3">
                              <div className="w-10 h-10 rounded-lg bg-fuchsia-200 flex items-center justify-center text-xl">💰</div>
                              <div>
                                <p className="text-[12px] font-bold text-fuchsia-900 group-hover:text-fuchsia-800 transition-colors">Official Invoice</p>
                                <p className="text-[10px] text-fuchsia-600 font-semibold mt-0.5">Required for Converted Status</p>
                              </div>
                            </div>
                            <button onClick={(e) => { e.stopPropagation(); window.open(selected.invoice, '_blank'); }}
                              className="w-8 h-8 rounded-lg bg-fuchsia-100 flex items-center justify-center text-fuchsia-600 hover:bg-fuchsia-600 hover:text-white transition-all shadow-sm">
                              <I.Download />
                            </button>
                          </div>
                        )}
                        {attachments.map((att: any) => {
                          const ext = (att.file_name || "").split(".").pop()?.toLowerCase() || "";
                          const icon = ["jpg","jpeg","png","gif","webp"].includes(ext) ? "🖼️" : ext === "pdf" ? "📄" : "📎";
                          return (
                            <div 
                              key={att.id} 
                              onClick={() => setPreviewFile({ url: att.file_url, name: att.file_name })}
                              className="flex items-center gap-3 p-3.5 bg-slate-50 border border-slate-100 hover:bg-emerald-50/40 hover:border-emerald-100 rounded-xl transition-all group cursor-pointer"
                            >
                              <div className="w-9 h-9 rounded-xl bg-white border border-slate-200 flex items-center justify-center text-base flex-shrink-0 shadow-sm">{icon}</div>
                              <div className="flex-1 min-w-0">
                                <p className="text-[12px] font-semibold text-slate-700 truncate">{att.file_name}</p>
                                <p className="text-[10px] text-slate-400">{att.file_size_kb} KB · {new Date(att.uploaded_at).toLocaleDateString('en-IN',{day:'2-digit',month:'short'})}</p>
                              </div>
                              <button onClick={(e) => { e.stopPropagation(); window.open(att.file_url, '_blank'); }}
                                className="w-7 h-7 flex items-center justify-center text-slate-300 hover:text-emerald-600 hover:bg-emerald-100 rounded-lg transition-colors" title="Download">
                                <I.Download />
                              </button>
                              <button onClick={() => deleteAttachment(att.id, att.file_name)}
                                className="w-7 h-7 flex items-center justify-center text-slate-300 hover:text-rose-500 hover:bg-rose-50 rounded-lg transition-colors" title="Delete">
                                <svg width="11" height="11" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4a1 1 0 011-1h4a1 1 0 011 1v2"/></svg>
                              </button>
                            </div>
                          );
                        })}
                      </div>
                    )}
                </div>
              )}

            </div>
          </>
        )}
      </div>


      {/* File Preview Modal */}
      {previewFile && (
        <div className="fixed inset-0 z-[100] flex flex-col bg-black/90 backdrop-blur-md transition-all">
          <div className="flex items-center justify-between px-6 py-4 bg-gradient-to-b from-black/50 to-transparent">
            <h3 className="text-white font-semibold text-sm truncate max-w-[80%]">{previewFile.name}</h3>
            <div className="flex items-center gap-3">
              <button onClick={(e) => { e.stopPropagation(); window.open(previewFile.url, '_blank'); }} className="px-3 py-1.5 bg-white/10 hover:bg-white/20 text-white rounded-lg text-xs font-semibold flex items-center gap-2 transition-colors">
                <I.Download /> Download
              </button>
              <button onClick={() => setPreviewFile(null)} className="w-8 h-8 flex items-center justify-center rounded-lg bg-white/10 hover:bg-white/20 text-white transition-colors">
                <I.X />
              </button>
            </div>
          </div>
          <div className="flex-1 p-6 flex items-center justify-center overflow-hidden" onClick={e => e.stopPropagation()}>
            {previewFile.url.toLowerCase().match(/\.(jpg|jpeg|png|gif|webp)$/) ? (
              <img src={previewFile.url} alt="Preview" className="max-w-full max-h-full object-contain rounded-lg shadow-2xl" />
            ) : previewFile.url.toLowerCase().endsWith('.pdf') ? (
              <iframe src={previewFile.url} className="w-full h-full max-w-5xl bg-white rounded-xl shadow-2xl" />
            ) : (
              <div className="text-center text-white bg-white/5 rounded-2xl p-10 border border-white/10">
                <div className="text-4xl mb-4">📎</div>
                <p className="font-semibold mb-2">Preview not available</p>
                <p className="text-sm text-white/50 mb-6">This file type cannot be previewed in the browser.</p>
                <button onClick={() => window.open(previewFile.url, '_blank')} className="inline-flex px-6 py-2.5 bg-indigo-600 hover:bg-indigo-500 rounded-xl font-bold transition-colors shadow-lg shadow-indigo-500/20">
                  Download File
                </button>
              </div>
            )}
          </div>
        </div>
      )}

    </div>
  );
}

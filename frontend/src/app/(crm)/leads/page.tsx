"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";
import { useLeadStatuses } from "@/hooks/useLeadStatuses";
import { useDistricts, districtOptions } from "@/hooks/useDistricts";
import { FALLBACK_STATUS_META, getLatestNote } from "@/lib/lead-statuses";
import { STAGE_META, STAGE_OPTIONS, StageTag } from "@/lib/pipeline-stages";

import React, { useState, useEffect, useRef, Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { getSourceLabel, formatCurrency } from "@/lib/mock-data";

function formatRelativeTime(dateStr: string) {
  if (!dateStr) return "";
  try {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffSecs = Math.floor(diffMs / 1000);
    const diffMins = Math.floor(diffSecs / 60);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffSecs < 60) {
      return "just now";
    } else if (diffMins < 60) {
      return `${diffMins}m ago`;
    } else if (diffHours < 24) {
      return `${diffHours}h ago`;
    } else if (diffDays < 7) {
      return `${diffDays}d ago`;
    } else {
      return date.toLocaleDateString("en-IN", { day: "2-digit", month: "short" });
    }
  } catch {
    return "";
  }
}

// ─── SVG Icons ────────────────────────────────────────────────────────────────
const I = {
  Plus:        () => <svg width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14" /></svg>,
  Search:      () => <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8" /><path d="M21 21l-4.35-4.35" /></svg>,
  Upload:      () => <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" /><polyline points="17 8 12 3 7 8" /><line x1="12" y1="3" x2="12" y2="15" /></svg>,
  Download:    () => <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line x1="12" y1="15" x2="12" y2="3" /></svg>,
  Edit:        () => <svg width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" /><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" /></svg>,
  Trash:       () => <svg width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6" /><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6" /><path d="M10 11v6M14 11v6" /><path d="M9 6V4a1 1 0 011-1h4a1 1 0 011 1v2" /></svg>,
  Users:       () => <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M23 21v-2a4 4 0 00-3-3.87" /><path d="M16 3.13a4 4 0 010 7.75" /></svg>,
  X:           ({ className }: { className?: string }) => <svg className={className} width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12" /></svg>,
  ChevronDown: ({ className }: { className?: string }) => <svg className={className} width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" viewBox="0 0 24 24"><polyline points="6 9 12 15 18 9" /></svg>,
  Filter:      () => <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><line x1="4" y1="6" x2="20" y2="6" /><line x1="8" y1="12" x2="16" y2="12" /><line x1="11" y1="18" x2="13" y2="18" /></svg>,
  Eye:         () => <svg width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" /></svg>,
  Clock:       () => <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" /><path d="M12 6v6l4 2" /></svg>,
  Task:        () => <svg width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M9 11l3 3 8-8" /><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" /></svg>,
  Toggle:      () => <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14" /></svg>,
  Phone:       () => <svg width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6 19.79 19.79 0 01-3.07-8.67A2 2 0 014.11 2h3a2 2 0 012 1.72 12.84 12.84 0 00.7 2.81 2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l2.27-2.27a2 2 0 012.11-.45 12.84 12.84 0 002.81.7A2 2 0 0122 16.92z" /></svg>,
  Flag:        ({ level }: { level: string }) => { const c = level === "high" ? "#ef4444" : level === "medium" ? "#f59e0b" : "#10b981"; return <svg width="11" height="11" fill={c} stroke={c} strokeWidth="1.5" strokeLinecap="round" viewBox="0 0 24 24"><path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z" /><line x1="4" y1="22" x2="4" y2="15" /></svg>; },
  Activity:    ({ className }: { className?: string }) => <svg className={className} width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12" /></svg>,
  ArrowUp:     ({ className }: { className?: string }) => <svg className={className} width="10" height="10" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" viewBox="0 0 24 24"><path d="M18 15l-6-6-6 6" /></svg>,
  ArrowDown:   ({ className }: { className?: string }) => <svg className={className} width="10" height="10" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" viewBox="0 0 24 24"><path d="M6 9l6 6 6-6" /></svg>,
  ArrowUpDown: ({ className }: { className?: string }) => <svg className={className} width="11" height="11" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><path d="M8 9l4-4 4 4M8 15l4 4 4-4" /></svg>,
};

// ─── Task draft type (for the modal's pending tasks list) ─────────────────────
interface PendingTask {
  _key: string; // client-side unique key
  title: string;
  priority: "high" | "medium" | "low";
  due_date: string;
  due_time: string;
  assignee_id: string; // team member id as string
}

// ─── Status config (now dynamic — see useLeadStatuses hook) ──────────────────

const SOURCE_META: Record<string, { bg: string; text: string }> = {
  meta:     { bg: "bg-blue-50",    text: "text-blue-700" },
  meta_ads: { bg: "bg-blue-50",    text: "text-blue-700" },
  manual:   { bg: "bg-slate-100",  text: "text-slate-600" },
  website:  { bg: "bg-emerald-50", text: "text-emerald-700" },
  referral: { bg: "bg-violet-50",  text: "text-violet-700" },
  linkedin: { bg: "bg-sky-50",     text: "text-sky-700" },
};

// ─── Small reusable components ────────────────────────────────────────────────
function Checkbox({ checked, onChange }: { checked: boolean; onChange: () => void }) {
  return (
    <div
      onClick={onChange}
      className={`w-4 h-4 rounded-[5px] border-2 flex items-center justify-center cursor-pointer flex-shrink-0 transition-all
        ${checked ? "bg-indigo-600 border-indigo-600" : "border-slate-300 hover:border-indigo-400"}`}
    >
      {checked && <svg width="8" height="8" fill="none" stroke="white" strokeWidth="3" strokeLinecap="round" viewBox="0 0 12 12"><polyline points="2 6 5 9 10 3" /></svg>}
    </div>
  );
}

function StatusBadge({ status, meta }: { status: string; meta: Record<string, { label: string; bg: string; text: string; dot: string; hex: string }> }) {
  const m = meta[status] || FALLBACK_STATUS_META;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-semibold ${m.bg} ${m.text}`}>
      <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${m.dot}`} />
      {m.label}
    </span>
  );
}

const FIELD = "w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all";
const SELECT_FIELD = `${FIELD} appearance-none pr-8 cursor-pointer font-medium`;
const LABEL = "block text-[11px] font-semibold text-slate-500 uppercase tracking-wide mb-1.5";

// ─── Pending-task tag (Zoho-style colored due-date badge) ───────────────────────
const TASK_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function TaskTag({ task }: { task: { title?: string; due_date: string; state: string; pending_count?: number } }) {
  const meta: Record<string, string> = {
    overdue:  "bg-rose-50 text-rose-700 ring-rose-200",
    today:    "bg-amber-50 text-amber-700 ring-amber-200",
    upcoming: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  };
  const cls = meta[task.state] || meta.upcoming;

  let label = "";
  if (task.state === "today") {
    label = "Today";
  } else {
    const [, m, d] = task.due_date.split("-").map(Number);
    label = `${TASK_MONTHS[(m || 1) - 1]} ${d}`;
    if (task.state === "overdue") label = `Overdue · ${label}`;
  }

  const extra = (task.pending_count || 1) - 1;
  const tip = `${task.title || "Task"}${extra > 0 ? `  (+${extra} more pending)` : ""}`;

  return (
    <span
      title={tip}
      className={`mt-1 inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wide ring-1 ${cls}`}
    >
      <svg width="9" height="9" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
        <circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" />
      </svg>
      {label}
      {extra > 0 && <span className="opacity-70 font-extrabold">+{extra}</span>}
    </span>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────
export default function LeadsPage({ params: paramsPromise }: { params: Promise<{ domain: string }> }) {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <LeadsPageContent paramsPromise={paramsPromise} />
    </Suspense>
  );
}

function LeadsPageContent({ paramsPromise }: { paramsPromise: Promise<{ domain: string }> }) {
  const params = React.use(paramsPromise);
  const domain = APP_SLUG;

  const getRecordingUrl = (url: string, id: number) => {
    if (!url) return "";
    if (url.includes("exotel") || url.includes("recordings.exotel")) {
      const token = localStorage.getItem(`${domain}_access`);
      return `${getApiBase(domain)}/api/calls/${id}/recording_proxy/${token ? `?token=${token}` : ''}`;
    }
    return url;
  };


  const [leads,          setLeads]          = useState<any[]>([]);
  const [totalLeadsCount, setTotalLeadsCount] = useState(0);
  const [page,           setPage]           = useState(1);
  const [totalPages,     setTotalPages]     = useState(1);
  const [loading,        setLoading]        = useState(true);
  const [search,         setSearch]         = useState("");
  const [statusFilter,   setStatusFilter]   = useState("all");
  const [sourceFilter,   setSourceFilter]   = useState("all");
  const [assigneeFilter, setAssigneeFilter] = useState("all");
  const [campaignFilter, setCampaignFilter] = useState("all");
  const [campaignsList, setCampaignsList]   = useState<{id: number, name: string}[]>([]);
  const [productsList, setProductsList]     = useState<{id: number, name: string, default_price: string}[]>([]);
  const [productFilter, setProductFilter]   = useState("all");
  // Which Meta Lead Ads account (one per branch) the lead arrived from.
  const [metaIntegrationFilter, setMetaIntegrationFilter] = useState("all");
  const [integrationsList, setIntegrationsList] = useState<{id: number, name: string}[]>([]);
  const [stageFilter,   setStageFilter]     = useState("all");
  // District the lead sits in. Options are the districts actually on the leads,
  // not a fixed list — the field is free text and arrives from CSV and Meta.
  const [districtFilter, setDistrictFilter]  = useState("all");
  const [districtsList,  setDistrictsList]   = useState<string[]>([]);
  const [createdType,    setCreatedType]    = useState("all");
  const [createdParam,   setCreatedParam]   = useState("2");
  const [createdFrom,    setCreatedFrom]    = useState("");
  const [createdTo,      setCreatedTo]      = useState("");
  const [valueMin,       setValueMin]       = useState("");
  const [valueMax,       setValueMax]       = useState("");
  const [companyFilter,  setCompanyFilter]  = useState("");
  const [showAdvanced,   setShowAdvanced]   = useState(false);
  const [modType,        setModType]        = useState("all");
  const [modParam,       setModParam]       = useState("2");
  const [modFrom,        setModFrom]        = useState("");
  const [modTo,          setModTo]          = useState("");
  const [statusChangeFrom,  setStatusChangeFrom]  = useState("all");
  const [statusChangeTo,    setStatusChangeTo]    = useState("all");
  const [statusChangeType,  setStatusChangeType]  = useState("all");
  const [statusChangeParam, setStatusChangeParam] = useState("2");
  const [statusChangeFromD, setStatusChangeFromD] = useState("");
  const [statusChangeToD,   setStatusChangeToD]   = useState("");
  const [activityType,      setActivityType]      = useState("all");
  const [hasActivityDays,   setHasActivityDays]   = useState("");
  const [noActivityDays,    setNoActivityDays]    = useState("");
  const [sortField,         setSortField]         = useState("created_at");
  const [sortOrder,         setSortOrder]         = useState<"asc" | "desc">("desc");
  // Archived (old, terminal) leads live out of the active list; toggle to view.
  const [showArchived, setShowArchived] = useState(false);
  const [archivedCount, setArchivedCount] = useState(0);
  const [showModal,      setShowModal]      = useState(false);
  const [editingLead,    setEditingLead]    = useState<any>(null);
  const [teamMembers,    setTeamMembers]    = useState<{ id: number; name: string }[]>([]);
  const [selectedIds,    setSelectedIds]    = useState<number[]>([]);
  const [showBulkAssign, setShowBulkAssign] = useState(false);
  const [showBulkUpdate, setShowBulkUpdate] = useState(false);
  const [bulkUpdateStatus, setBulkUpdateStatus] = useState("");
  const [bulkUpdateSource, setBulkUpdateSource] = useState("");
  const [bulkUpdateProduct, setBulkUpdateProduct] = useState("");
  const [bulkUpdateAssignee, setBulkUpdateAssignee] = useState("");
  const [bulkUpdateCampaign, setBulkUpdateCampaign] = useState("");
  const [showBulkWa, setShowBulkWa] = useState(false);
  const [waMode, setWaMode] = useState<"text" | "template">("template");
  const [waText, setWaText] = useState("Hi {{first_name}}, ");
  const [waTemplate, setWaTemplate] = useState("");
  const [waLang, setWaLang] = useState("en_US");
  const [waVars, setWaVars] = useState("");
  const [waSending, setWaSending] = useState(false);
  const [isUploading,    setIsUploading]    = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  // View lead modal
  const [viewLead,       setViewLead]       = useState<any>(null);
  const [leadHistory,    setLeadHistory]    = useState<any[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  // Lead-linked tasks in view modal
  const [leadTasks,      setLeadTasks]      = useState<any[]>([]);
  const [tasksLoading,   setTasksLoading]   = useState(false);
  const [leadCalls,      setLeadCalls]      = useState<any[]>([]);
  const [callsLoading,   setCallsLoading]   = useState(false);
  const [leadAttachments,     setLeadAttachments]     = useState<any[]>([]);
  const [attachmentsLoading,  setAttachmentsLoading]  = useState(false);
  const [attachmentUploading, setAttachmentUploading] = useState(false);
  const [newModalNote, setNewModalNote] = useState("");
  const [addingModalNote, setAddingModalNote] = useState(false);
  const [newEditNote, setNewEditNote] = useState("");
  const attachmentFileRef = useRef<HTMLInputElement>(null);
  const [previewFile, setPreviewFile] = useState<{ url: string; name: string } | null>(null);

  // Pending tasks to create when saving a lead
  const [pendingTasks,   setPendingTasks]   = useState<PendingTask[]>([]);
  const blankPendingTask: Omit<PendingTask, "_key"> = { title: "", priority: "medium", due_date: "", due_time: "", assignee_id: "" };

  const blank = { first_name: "", last_name: "", email: "", phone: "", company: "", district: "", installation_location: "", source: "manual", status: "new", value: "0", notes: "", assigned_to: "", product: "" };
  const [form, setForm] = useState(blank);
  const [currentUser, setCurrentUser] = useState<any>(null);
  // ─── Dynamic lead statuses (standard + tenant custom) ──────────────────────
  const { statusMeta, statusOptions } = useLeadStatuses(domain);
  // The districts Settings configured. Typing one by hand would put a value on
  // the lead that an import of the same district would not produce, so the form
  // picks from the same list the import is matched against.
  const { districts: configuredDistricts } = useDistricts();

  useEffect(() => {
    const token = localStorage.getItem(`${domain}_access`);
    if (token) {
      fetch(`${getApiBase(domain)}/api/users/me/`, { headers: { Authorization: `Bearer ${token}` } })
        .then(r => r.json())
        .then(d => setCurrentUser(d))
        .catch(() => {});
    }
  }, [domain]);

  const router = useRouter();
  const searchParams = useSearchParams();

  // A view-only (spectator) account: reads the whole lead book, changes none of
  // it. Every write control below is withheld from it, matching the can_* gates
  // in leads.access that the server enforces.
  const isSpectator = !!currentUser?.read_only;

  // Tele callers add and assign their own leads too; the backend scopes an
  // agent's choices to their own team, and the people picker only lists those.
  const canAssign = !isSpectator && (currentUser?.is_staff || currentUser?.is_general_manager
    || currentUser?.is_manager || currentUser?.role === "tele_caller"
    || currentUser?.role === "leads_manager");

  // A BDE reports through the site visit; the lead status belongs to the tele
  // caller / managers. Mirrors can_edit_lead_status() on the backend.
  const canEditStatus = !isSpectator && (!currentUser || currentUser.role !== "bde");

  // Who can open a campaign page. Mirrors IsAdminOrManager on the campaigns
  // endpoint — for anyone else the request 403s and the page reports "Campaign
  // not found", so the chip is plain text rather than a link into a dead end.
  const canOpenCampaign = !!(currentUser?.is_staff || currentUser?.is_general_manager
    || currentUser?.is_manager || currentUser?.role === "leads_manager");
  // Leads are sourced by the tele-calling side — a BDE only receives them.
  // Mirrors can_add_leads() on the backend.
  const canAddLeads = !isSpectator && (!currentUser || currentUser.role !== "bde");
  // The lead record belongs to the tele-calling side too: a BDE reports through
  // the site visit. Mirrors can_edit_leads() / can_delete_leads().
  const canEditLeads = !isSpectator && (!currentUser || currentUser.role !== "bde");
  const canDeleteLeads = !isSpectator && (!currentUser || currentUser.role !== "bde");
  // CSV template / export and the Archived + Trash views manage the lead book
  // rather than work a lead. Mirrors can_use_lead_tools() on the backend.
  // A spectator keeps these: they only read the book (the Import button inside
  // the group is gated by canAddLeads, and archiving by canEditLeads).
  const canUseLeadTools = !currentUser || currentUser.role !== "bde";
  // The site visit is the BDE's job; a tele caller has nothing to do in it, so
  // the shortcut and its completed badge are hidden from them.
  const showSiteVisit = !currentUser || currentUser.role !== "tele_caller";

  useEffect(() => { fetchLeads(); fetchTeam(); fetchCampaigns(); fetchProducts(); fetchIntegrations(); fetchDistricts(); }, [
    domain, statusFilter, sourceFilter, assigneeFilter, campaignFilter, productFilter, metaIntegrationFilter, stageFilter, districtFilter, search,
    createdType, createdParam, createdFrom, createdTo,
    modType, modParam, modFrom, modTo,
    valueMin, valueMax, companyFilter,
    statusChangeFrom, statusChangeTo, statusChangeType, statusChangeParam, statusChangeFromD, statusChangeToD,
    activityType, hasActivityDays, noActivityDays, page,
    sortField, sortOrder, showArchived
  ]);

  const fetchTeam = async () => {
    const token = localStorage.getItem(`${domain}_access`);
    if (!token) return;
    try {
      // The assignable list, not the directory: it returns exactly the people
      // the backend will accept as an assignee for this user's role.
      const r = await fetch(`${getApiBase(domain)}/api/users/assignable/`, { headers: { Authorization: `Bearer ${token}` } });
      const d = await r.json();
      setTeamMembers((Array.isArray(d) ? d : d.results || []).map((u: any) => ({
        id: u.id,
        name: u.name || `${u.first_name || ""} ${u.last_name || ""}`.trim() || u.username,
      })));
    } catch {}
  };

  // Names only, from an endpoint every role can read — listing the campaigns
  // themselves is admin/manager work, but a tele caller still has to be able to
  // filter their own list by campaign.
  const fetchCampaigns = async () => {
    const token = localStorage.getItem(`${domain}_access`);
    if (!token) return;
    try {
      const r = await fetch(`${getApiBase(domain)}/api/campaigns/options/`, { headers: { Authorization: `Bearer ${token}` } });
      if (!r.ok) return;
      const d = await r.json();
      setCampaignsList((Array.isArray(d) ? d : d.results || []).map((c: any) => ({ id: c.id, name: c.name })));
    } catch {}
  };

  // Meta integrations (one per branch) — used by the "Meta Integration" filter.
  const fetchIntegrations = async () => {
    const token = localStorage.getItem(`${domain}_access`);
    if (!token) return;
    try {
      const r = await fetch(`${getApiBase(domain)}/api/integration-settings/`, { headers: { Authorization: `Bearer ${token}` } });
      if (!r.ok) return;   // non-admins can't list integrations; filter just stays hidden
      const d = await r.json();
      setIntegrationsList((Array.isArray(d) ? d : d.results || [])
        .filter((i: any) => i.name)
        .map((i: any) => ({ id: i.id, name: i.name })));
    } catch {}
  };

  // The districts present on this user's leads. Refetched with the list so a
  // district typed onto a lead a moment ago is already in the filter.
  const fetchDistricts = async () => {
    const token = localStorage.getItem(`${domain}_access`);
    if (!token) return;
    try {
      const r = await fetch(`${getApiBase(domain)}/api/leads/districts/`, { headers: { Authorization: `Bearer ${token}` } });
      if (!r.ok) return;
      const d = await r.json();
      setDistrictsList(Array.isArray(d) ? d : []);
    } catch {}
  };

  const fetchProducts = async () => {
    const token = localStorage.getItem(`${domain}_access`);
    if (!token) return;
    try {
      const r = await fetch(`${getApiBase(domain)}/api/products/`, { headers: { Authorization: `Bearer ${token}` } });
      const d = await r.json();
      setProductsList((Array.isArray(d) ? d : d.results || []).map((p: any) => ({ id: p.id, name: p.name, default_price: p.default_price })));
    } catch {}
  };

  const buildDateParams = (q: URLSearchParams, typeStr: string, paramStr: string, fromStr: string, toStr: string, prefix: string) => {
    if (typeStr === "all") return;
    const now = new Date();
    const toLocalISO = (dt: Date) => `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}`;
    let after = "", before = "";
    if (typeStr === "today") {
      after = toLocalISO(now); before = after;
    } else if (typeStr === "yesterday") {
      const y = new Date(now); y.setDate(y.getDate() - 1);
      after = toLocalISO(y); before = after;
    } else if (typeStr === "this_week") {
      const start = new Date(now);
      const day = start.getDay();
      const diff = start.getDate() - day + (day === 0 ? -6 : 1);
      start.setDate(diff);
      const end = new Date(start); end.setDate(start.getDate() + 6);
      after = toLocalISO(start); before = toLocalISO(end);
    } else if (typeStr === "this_month") {
      after = toLocalISO(new Date(now.getFullYear(), now.getMonth(), 1));
      before = toLocalISO(new Date(now.getFullYear(), now.getMonth() + 1, 0));
    } else if (typeStr === "age_in") {
      const d = new Date(now); d.setDate(d.getDate() - parseInt(paramStr || "0"));
      after = toLocalISO(d); before = after;
    } else if (typeStr === "previous") {
      const d = new Date(now); d.setDate(d.getDate() - parseInt(paramStr || "0"));
      after = toLocalISO(d); before = toLocalISO(now);
    } else if (typeStr === "between") {
      after = fromStr; before = toStr;
    } else if (typeStr === "is_empty" || typeStr === "is_not_empty") {
      q.append(`${prefix}_empty`, typeStr === "is_empty" ? "true" : "false");
    }
    if (after) q.append(`${prefix}_after`, after);
    if (before) q.append(`${prefix}_before`, before);
  };

  const handleSort = (field: string) => {
    if (sortField === field) {
      setSortOrder(sortOrder === "asc" ? "desc" : "asc");
    } else {
      setSortField(field);
      setSortOrder("desc");
    }
    setPage(1);
  };

  // Header button styling — active sort column reads indigo, others stay muted.
  const sortBtnClass = (field: string, extra = "") =>
    `group inline-flex items-center gap-1 font-bold uppercase tracking-widest focus:outline-none transition-colors ${
      sortField === field ? "text-indigo-600" : "text-slate-400 hover:text-indigo-600"
    } ${extra}`;

  const renderSortArrow = (field: string) => {
    if (sortField !== field) {
      // Always-visible affordance so users know the column is sortable.
      return <I.ArrowUpDown className="ml-0.5 text-slate-400 group-hover:text-indigo-500 transition-colors" />;
    }
    return (
      <span className="ml-1 inline-flex items-center justify-center w-[18px] h-[18px] rounded-md bg-indigo-100 text-indigo-700 ring-1 ring-indigo-200 shadow-sm">
        {sortOrder === "asc" ? <I.ArrowUp /> : <I.ArrowDown />}
      </span>
    );
  };

  const buildLeadQuery = () => {
    const q = new URLSearchParams();
    if (statusFilter   !== "all") q.append("status",      statusFilter);
    if (sourceFilter   !== "all") q.append("source",      sourceFilter);
    if (assigneeFilter !== "all") q.append("assigned_to", assigneeFilter);
    if (campaignFilter !== "all") q.append("campaign",    campaignFilter);
    if (productFilter  !== "all") q.append("product",     productFilter);
    if (metaIntegrationFilter !== "all") q.append("meta_integration", metaIntegrationFilter);
    if (stageFilter    !== "all") q.append("stage",       stageFilter);
    if (districtFilter !== "all") q.append("district",    districtFilter);
    if (search)                   q.append("search", search);
    if (valueMin)                 q.append("value_min", valueMin);
    if (valueMax)                 q.append("value_max", valueMax);
    if (companyFilter)            q.append("company", companyFilter);

    if (statusChangeFrom !== "all") q.append("status_change_from", statusChangeFrom);
    if (statusChangeTo !== "all")   q.append("status_change_to", statusChangeTo);

    if (activityType !== "all") q.append("activity_type", activityType);
    if (hasActivityDays) q.append("has_activity_days", hasActivityDays);
    if (noActivityDays) q.append("no_activity_days", noActivityDays);

    buildDateParams(q, createdType, createdParam, createdFrom, createdTo, "created");
    buildDateParams(q, modType, modParam, modFrom, modTo, "modified");
    buildDateParams(q, statusChangeType, statusChangeParam, statusChangeFromD, statusChangeToD, "status_change");

    if (sortField) {
      q.append("ordering", `${sortOrder === "desc" ? "-" : ""}${sortField}`);
    }
    if (showArchived) q.append("archived", "true");
    q.append("page", page.toString());
    return q;
  };

  const fetchLeads = async () => {
    setLoading(true);
    const token = localStorage.getItem(`${domain}_access`);
    if (!token) return;
    const q = buildLeadQuery();
    const url = `${getApiBase(domain)}/api/leads/${q.toString() ? `?${q}` : ""}`;
    try {
      const r = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
      const d = await r.json();
      setLeads(Array.isArray(d) ? d : d.results || []);
      setTotalLeadsCount(d.count || (Array.isArray(d) ? d.length : 0));
      setTotalPages(d.count ? Math.ceil(d.count / 100) : 1);
      setSelectedIds([]);
    } catch {} finally { setLoading(false); }
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]; if (!file) return;
    setIsUploading(true);
    const fd = new FormData(); fd.append("file", file);
    const token = localStorage.getItem(`${domain}_access`);
    try {
      const r = await fetch(`${getApiBase(domain)}/api/leads/bulk_upload/`, { method: "POST", headers: { Authorization: `Bearer ${token}` }, body: fd });
      if (r.ok) {
        fetchLeads();
      } else {
        const err = await r.json().catch(() => ({}));
        alert(err.error || "Upload failed");
      }
    } catch {} finally { setIsUploading(false); if (fileRef.current) fileRef.current.value = ""; }
  };

  const exportCSV = async () => {
    const token = localStorage.getItem(`${domain}_access`);
    const q = buildLeadQuery();
    try {
      const r = await fetch(`${getApiBase(domain)}/api/leads/export_csv/${q.toString() ? `?${q}` : ""}`, { headers: { Authorization: `Bearer ${token}` } });
      const blob = await r.blob();
      const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "leads.csv"; a.click();
    } catch {}
  };

  const downloadTemplate = async () => {
    const token = localStorage.getItem(`${domain}_access`);
    try {
      const r = await fetch(`${getApiBase(domain)}/api/leads/csv_template/`, { headers: { Authorization: `Bearer ${token}` } });
      const blob = await r.blob();
      const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "template.csv"; a.click();
    } catch {}
  };

  const bulkWhatsApp = async () => {
    if (!selectedIds.length) return;
    if (waMode === "template" && !waTemplate.trim()) { alert("Enter a template name."); return; }
    setWaSending(true);
    const token = localStorage.getItem(`${domain}_access`);
    const body: any = { lead_ids: selectedIds, kind: waMode };
    if (waMode === "template") {
      body.template_name = waTemplate.trim();
      body.language = waLang.trim() || "en_US";
      body.variables = waVars.split(",").map(s => s.trim()).filter(Boolean);
    } else {
      body.text = waText;
    }
    try {
      const r = await fetch(`${getApiBase(domain)}/api/whatsapp/bulk/`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify(body),
      });
      const d = await r.json().catch(() => ({}));
      if (r.ok) {
        alert(`Queued ${d.queued} WhatsApp message(s). They will send shortly.`);
        setShowBulkWa(false); setSelectedIds([]);
      } else {
        alert(d.detail || "Failed to queue WhatsApp messages.");
      }
    } catch { alert("Network error."); } finally { setWaSending(false); }
  };

  const bulkDelete = async () => {
    if (!selectedIds.length || !confirm(`Move ${selectedIds.length} leads to Trash? They stay there for 7 days before disappearing forever.`)) return;
    const token = localStorage.getItem(`${domain}_access`);
    await fetch(`${getApiBase(domain)}/api/leads/bulk_delete/`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify({ ids: selectedIds }) });
    setSelectedIds([]); fetchLeads();
  };

  const bulkUpdate = async () => {
    if (!selectedIds.length) return;
    const token = localStorage.getItem(`${domain}_access`);
    const data: any = {};
    if (bulkUpdateStatus) data.status = bulkUpdateStatus;
    if (bulkUpdateSource) data.source = bulkUpdateSource;
    if (bulkUpdateProduct) data.product_id = parseInt(bulkUpdateProduct);
    if (bulkUpdateAssignee) data.assigned_to_id = parseInt(bulkUpdateAssignee);
    if (bulkUpdateCampaign) data.campaign_id = parseInt(bulkUpdateCampaign);
    
    if (Object.keys(data).length === 0) {
      alert("Please select at least one field to update.");
      return;
    }
    
    await fetch(`${getApiBase(domain)}/api/leads/bulk_update/`, { 
      method: "POST", 
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, 
      body: JSON.stringify({ ids: selectedIds, data }) 
    });
    setSelectedIds([]); setShowBulkUpdate(false); fetchLeads();
    setBulkUpdateStatus(""); setBulkUpdateSource("");
    setBulkUpdateProduct(""); setBulkUpdateAssignee(""); setBulkUpdateCampaign("");
  };

  const bulkAssign = async (userId: number) => {
    const token = localStorage.getItem(`${domain}_access`);
    await fetch(`${getApiBase(domain)}/api/leads/bulk_assign/`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify({ ids: selectedIds, user_id: userId }) });
    setSelectedIds([]); setShowBulkAssign(false); fetchLeads();
  };

  const updateStatus = async (id: number, status: string) => {
    // A lead can only be marked Converted after the tele-caller has assigned a BDE.
    if (status === 'converted') {
      const lead = leads.find(l => l.id === id);
      if (lead && !lead.bde) {
        alert("Assign a BDE to this lead before marking it Converted.");
        return;
      }
    }
    const token = localStorage.getItem(`${domain}_access`);
    const r = await fetch(`${getApiBase(domain)}/api/leads/${id}/`, { method: "PATCH", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify({ status }) });
    if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        alert(err.status?.[0] || err.detail || "Failed to update status");
    }
    fetchLeads();
  };

  const deleteLead = async (id: number) => {
    if (!confirm("Move this lead to Trash? It stays there for 7 days before disappearing forever.")) return;
    const token = localStorage.getItem(`${domain}_access`);
    await fetch(`${getApiBase(domain)}/api/leads/${id}/`, { method: "DELETE", headers: { Authorization: `Bearer ${token}` } });
    fetchLeads();
  };

  // ── Trash (soft-deleted leads; auto-purged after 7 days) ──
  type TrashRow = {
    id: number; first_name: string; last_name: string | null; phone: string | null;
    email: string | null; status: string; trashed_at: string | null;
    trashed_by_name: string | null; days_left: number;
  };
  const [showTrash, setShowTrash] = useState(false);
  const [trashRows, setTrashRows] = useState<TrashRow[]>([]);
  const [trashLoading, setTrashLoading] = useState(false);

  const loadArchiveStats = async () => {
    try {
      const token = localStorage.getItem(`${domain}_access`);
      const r = await fetch(`${getApiBase(domain)}/api/leads/archive-stats/`, { headers: { Authorization: `Bearer ${token}` } });
      if (r.ok) { const d = await r.json(); setArchivedCount(d.archived || 0); }
    } catch {}
  };
  useEffect(() => { loadArchiveStats(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const archiveLead = async (id: number, archive: boolean) => {
    const token = localStorage.getItem(`${domain}_access`);
    const r = await fetch(`${getApiBase(domain)}/api/leads/${id}/${archive ? "archive" : "unarchive"}/`, {
      method: "POST", headers: { Authorization: `Bearer ${token}` },
    });
    if (!r.ok) { const e = await r.json().catch(() => ({})); alert(e.error || "Could not update the archive."); return; }
    fetchLeads(); loadArchiveStats();
  };

  const loadTrash = async () => {
    setTrashLoading(true);
    try {
      const token = localStorage.getItem(`${domain}_access`);
      const r = await fetch(`${getApiBase(domain)}/api/leads/trash/`, { headers: { Authorization: `Bearer ${token}` } });
      const d = await r.json().catch(() => ({}));
      setTrashRows(Array.isArray(d.leads) ? d.leads : []);
    } catch { /* keep old rows */ }
    finally { setTrashLoading(false); }
  };

  const openTrash = () => { setShowTrash(true); loadTrash(); };

  const restoreFromTrash = async (id: number) => {
    const token = localStorage.getItem(`${domain}_access`);
    const r = await fetch(`${getApiBase(domain)}/api/leads/${id}/restore-trash/`, { method: "POST", headers: { Authorization: `Bearer ${token}` } });
    if (!r.ok) { const e = await r.json().catch(() => ({})); alert(e.error || "Could not restore."); }
    loadTrash(); fetchLeads();
  };

  // Emptying the Trash is irreversible and covers the whole workspace, so it is
  // a super admin's call — mirrors the check on the endpoint.
  const canEmptyTrash = currentUser?.role === "superadmin";
  const [emptying, setEmptying] = useState(false);

  const emptyTrash = async () => {
    const n = trashRows.length;
    // Two steps on purpose: the second names the count, so a mis-click on a full
    // Trash cannot slip through on muscle memory.
    if (!confirm(`Permanently delete all ${n} lead${n === 1 ? "" : "s"} in the Trash?

This cannot be undone.`)) return;
    if (!confirm(`Last check — ${n} lead${n === 1 ? "" : "s"} will be deleted forever.`)) return;
    setEmptying(true);
    try {
      const token = localStorage.getItem(`${domain}_access`);
      const r = await fetch(`${getApiBase(domain)}/api/leads/empty-trash/`, {
        method: "DELETE", headers: { Authorization: `Bearer ${token}` },
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) { alert(d.error || "Could not empty the Trash."); return; }
      alert(d.message || "Trash emptied.");
      loadTrash(); fetchLeads();
    } catch { alert("Network error while emptying the Trash."); }
    finally { setEmptying(false); }
  };

  const purgeFromTrash = async (id: number) => {
    if (!confirm("Delete this lead forever? This cannot be undone.")) return;
    const token = localStorage.getItem(`${domain}_access`);
    const r = await fetch(`${getApiBase(domain)}/api/leads/${id}/purge/`, { method: "DELETE", headers: { Authorization: `Bearer ${token}` } });
    if (!(r.ok || r.status === 204)) { const e = await r.json().catch(() => ({})); alert(e.error || "Could not delete."); }
    loadTrash();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const token = localStorage.getItem(`${domain}_access`);
    if (!token) return;
    const finalNotes = newEditNote.trim()
      ? (form.notes ? `${form.notes}\n\n${newEditNote.trim()}` : newEditNote.trim())
      : form.notes;

    const payload = {
      ...form,
      notes: finalNotes,
      assigned_to: form.assigned_to ? parseInt(form.assigned_to) : null,
      product: form.product ? parseInt(form.product) : null
    };
    delete (payload as any).value;  // deal value is entered by the BDE during the site visit, not the tele caller
    const method = editingLead ? "PATCH" : "POST";
    const url    = editingLead ? `${getApiBase(domain)}/api/leads/${editingLead.id}/` : `${getApiBase(domain)}/api/leads/`;
    try {
      const r = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify(payload),
      });
      
      if (r.ok) {
        const savedLead = await r.json();
        // Create any pending tasks linked to this lead
        const validTasks = pendingTasks.filter(t => t.title.trim());
        if (validTasks.length > 0) {
          await Promise.allSettled(
            validTasks.map(t =>
              fetch(`${getApiBase(domain)}/api/tasks/`, {
                method: "POST",
                headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
                body: JSON.stringify({
                  title: t.title.trim(),
                  priority: t.priority,
                  due_date: t.due_date || null,
                  due_time: t.due_time || null,
                  assignee: t.assignee_id ? parseInt(t.assignee_id) : null,
                  lead: savedLead.id,
                  status: "todo",
                  description: "",
                  tags: [],
                }),
              })
            )
          );
        }
        setShowModal(false);
        setPendingTasks([]);
        fetchLeads();
      } else {
        const err = await r.json();
        const errMsgs = typeof err === 'object' ? Object.entries(err).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`).join(' | ') : null;
        alert(err.invoice?.[0] || err.error || errMsgs || "Failed to save lead");
      }
    } catch {}
  };

  // ─── Helper: add a blank pending task row ─────────────────────────────────
  const addPendingTask = () =>
    setPendingTasks(prev => [...prev, { ...blankPendingTask, _key: Date.now().toString() }]);

  const updatePendingTask = (key: string, patch: Partial<Omit<PendingTask, "_key">>) =>
    setPendingTasks(prev => prev.map(t => t._key === key ? { ...t, ...patch } : t));

  const removePendingTask = (key: string) =>
    setPendingTasks(prev => prev.filter(t => t._key !== key));

  const openAdd  = () => { setEditingLead(null); setForm(blank); setPendingTasks([]); setNewEditNote(""); setShowModal(true); };
  const openEdit = (lead: any) => {
    setEditingLead(lead);
    setForm({ first_name: lead.first_name || "", last_name: lead.last_name || "", email: lead.email || "", phone: lead.phone || "", company: lead.company || "", district: lead.district || "", installation_location: lead.installation_location || "", source: lead.source || "manual", status: lead.status || "new", value: (lead.value || 0).toString(), notes: lead.notes || "", assigned_to: lead.assigned_to?.toString() || "", product: lead.product?.toString() || "" });
    setPendingTasks([]);
    setNewEditNote("");
    setShowModal(true);
  };

  const openView = async (lead: any) => {
    setViewLead(lead);
    setLeadHistory([]);
    setLeadTasks([]);
    setLeadCalls([]);
    setHistoryLoading(true);
    setTasksLoading(true);
    setCallsLoading(true);
    const token = localStorage.getItem(`${domain}_access`);
    // Opening the quick view counts as seeing the lead, so it drops off the
    // sidebar's Leads badge (the URL doesn't change, so the layout can't tell).
    fetch(`${getApiBase(domain)}/api/leads/${lead.id}/seen/`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ modules: ["leads"] }),
    }).catch(() => {});
    try {
      const [histRes, tasksRes, callsRes] = await Promise.all([
        fetch(`${getApiBase(domain)}/api/leads/${lead.id}/history/`, { headers: { Authorization: `Bearer ${token}` } }),
        fetch(`${getApiBase(domain)}/api/tasks/?lead=${lead.id}`, { headers: { Authorization: `Bearer ${token}` } }),
        fetch(`${getApiBase(domain)}/api/calls/?lead=${lead.id}`, { headers: { Authorization: `Bearer ${token}` } }),
      ]);
      if (histRes.ok) setLeadHistory(await histRes.json());
      if (tasksRes.ok) {
        const td = await tasksRes.json();
        setLeadTasks(Array.isArray(td) ? td : td.results || []);
      }
      if (callsRes.ok) {
        const cd = await callsRes.json();
        setLeadCalls(Array.isArray(cd) ? cd : cd.results || []);
      }
    } catch {} finally { setHistoryLoading(false); setTasksLoading(false); setCallsLoading(false); }

    // Fetch attachments separately
    setAttachmentsLoading(true);
    try {
      const attRes = await fetch(`${getApiBase(domain)}/api/leads/${lead.id}/attachments/`, { headers: { Authorization: `Bearer ${token}` } });
      if (attRes.ok) setLeadAttachments(await attRes.json());
      else setLeadAttachments([]);
    } catch {} finally { setAttachmentsLoading(false); }
  };

  const handleAddModalNote = async () => {
    if (!viewLead || !newModalNote.trim()) return;
    setAddingModalNote(true);
    const token = localStorage.getItem(`${domain}_access`);
    if (!token) { setAddingModalNote(false); return; }

    const existingNotes = viewLead.notes || "";
    const updatedNotes = existingNotes
      ? `${existingNotes}\n\n${newModalNote.trim()}`
      : newModalNote.trim();

    try {
      const res = await fetch(`${getApiBase(domain)}/api/leads/${viewLead.id}/`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ notes: updatedNotes }),
      });
      if (res.ok) {
        const updatedLead = await res.json();
        setViewLead(updatedLead);
        setNewModalNote("");
        fetchLeads();
        
        // Refresh history
        const histRes = await fetch(`${getApiBase(domain)}/api/leads/${viewLead.id}/history/`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        if (histRes.ok) setLeadHistory(await histRes.json());
      } else {
        const err = await res.json();
        alert(err.error || "Failed to add note");
      }
    } catch {
      alert("Network error. Please try again.");
    } finally {
      setAddingModalNote(false);
    }
  };

  const initiateCall = async (leadId: number) => {
    const lead = leads.find(l => l.id === leadId) || viewLead;
    if (!lead?.phone) return alert("Lead does not have a phone number.");
    
    if (!confirm(`Initiate automated call to ${lead.first_name}?`)) return;
    
    const token = localStorage.getItem(`${domain}_access`);
    try {
      const r = await fetch(`${getApiBase(domain)}/api/calls/initiate/`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ lead_id: leadId })
      });
      const d = await r.json();
      if (r.ok) {
        if (d.voxbay_click_to_call_url) {
          window.open(d.voxbay_click_to_call_url, "_blank");
          alert("Redirecting to Voxbay mobile calling app...");
        } else {
          alert(d.status || "Call initiated!");
        }
      } else {
        alert(d.error || "Failed to initiate call");
      }
    } catch { alert("Error connecting to dialer"); }
  };

  const handleAttachmentUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !viewLead) return;
    if (file.size > 50 * 1024 * 1024) { alert("File size exceeds 50MB limit"); return; }
    setAttachmentUploading(true);
    const token = localStorage.getItem(`${domain}_access`);
    try {
      const fd = new FormData(); fd.append("file", file);
      const r = await fetch(`${getApiBase(domain)}/api/leads/${viewLead.id}/attachments/`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: fd
      });
      if (r.ok) {
        const newAtt = await r.json();
        setLeadAttachments(prev => [newAtt, ...prev]);
      } else {
        const err = await r.json();
        alert(err.error || "Upload failed");
      }
    } catch { alert("Error uploading file"); }
    finally { setAttachmentUploading(false); if (attachmentFileRef.current) attachmentFileRef.current.value = ""; }
  };

  const deleteAttachment = async (attachmentId: number, fileName: string) => {
    if (!viewLead) return;
    if (!confirm(`Delete "${fileName}"? This cannot be undone.`)) return;
    const token = localStorage.getItem(`${domain}_access`);
    try {
      const r = await fetch(`${getApiBase(domain)}/api/leads/${viewLead.id}/attachments/${attachmentId}/`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (r.ok || r.status === 204) {
        setLeadAttachments(prev => prev.filter(a => a.id !== attachmentId));
      } else {
        alert("Failed to delete attachment");
      }
    } catch { alert("Error deleting attachment"); }
  };

  const toggleAll = () => setSelectedIds(selectedIds.length === leads.length && leads.length > 0 ? [] : leads.map(l => l.id));
  const toggleOne = (id: number) => setSelectedIds(prev => prev.includes(id) ? prev.filter(i => i !== id) : [...prev, id]);

  const activeFilters = [
    statusFilter !== "all", sourceFilter !== "all", assigneeFilter !== "all", campaignFilter !== "all",
    districtFilter !== "all",
    createdType !== "all", modType !== "all", !!valueMin, !!valueMax, !!companyFilter,
    statusChangeFrom !== "all", statusChangeTo !== "all", statusChangeType !== "all",
    activityType !== "all", !!hasActivityDays, !!noActivityDays
  ].filter(Boolean).length;

  const clearFilters = () => {
    setStatusFilter("all"); setSourceFilter("all"); setAssigneeFilter("all"); setCampaignFilter("all"); setProductFilter("all");
    setDistrictFilter("all");
    setCreatedType("all"); setCreatedParam("2"); setCreatedFrom(""); setCreatedTo("");
    setModType("all"); setModParam("2"); setModFrom(""); setModTo("");
    setValueMin(""); setValueMax(""); setCompanyFilter(""); setSearch("");
    setStatusChangeFrom("all"); setStatusChangeTo("all"); setStatusChangeType("all");
    setStatusChangeParam("2"); setStatusChangeFromD(""); setStatusChangeToD("");
    setActivityType("all"); setHasActivityDays(""); setNoActivityDays("");
    setPage(1);
  };

  // statusOptions & statusMeta come from useLeadStatuses hook (declared above)

  return (
    <div className="min-h-screen bg-[#f4f6fa]">

      {/* ── Header ───────────────────────────────────────────────────────────── */}
      <div className="bg-white border-b border-slate-200/70 sticky top-0 z-20 shadow-sm shadow-slate-100">
        <div className="max-w-[1440px] mx-auto px-4 sm:px-6 xl:px-8">
          {/* Wraps rather than overflows: the six tools here do not shrink,
              and on a narrower window they need a second line. */}
          <div className="flex flex-wrap items-center justify-between gap-3 py-2.5 min-h-[60px]">

            {/* Title */}
            <div className="flex items-center gap-3 min-w-0">
              <div>
                <h1 className="text-[15px] font-bold text-slate-900 leading-none">Leads</h1>
                <p className="text-[11px] text-slate-400 mt-0.5 leading-none">{totalLeadsCount > 0 ? totalLeadsCount : leads.length} total</p>
              </div>
            </div>

            {/* Actions */}
            <div className="flex items-center gap-2 flex-shrink-0">
              <input type="file" accept=".csv" ref={fileRef} className="hidden" onChange={handleUpload} />

              {/* CSV actions grouped */}
              {canUseLeadTools && (
              <div className="hidden sm:flex items-center border border-slate-200 rounded-xl overflow-hidden divide-x divide-slate-200">
                <button onClick={downloadTemplate} title="Download Template"
                  className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium text-slate-600 hover:bg-slate-50 transition-colors">
                  <I.Download /> <span className="hidden md:inline">Template</span>
                </button>
                <button onClick={exportCSV} title="Export CSV"
                  className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium text-slate-600 hover:bg-slate-50 transition-colors">
                  <I.Download /> <span className="hidden md:inline">Export</span>
                </button>
                {/* Import creates leads, so it follows the same rule as New Lead. */}
                {canAddLeads && (
                <button onClick={() => fileRef.current?.click()} disabled={isUploading}
                  className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium text-slate-600 hover:bg-slate-50 transition-colors disabled:opacity-50">
                  <I.Upload /> <span className="hidden md:inline">{isUploading ? "Uploading…" : "Import"}</span>
                </button>
                )}
              </div>
              )}

              {canUseLeadTools && (
              <button onClick={() => { setShowArchived(v => !v); setPage(1); }}
                title="Old, terminal leads kept out of the active list"
                className={`flex items-center gap-1.5 px-4 py-2 border rounded-xl text-sm font-semibold active:scale-[0.97] transition-all shadow-sm ${showArchived ? "bg-indigo-600 border-indigo-600 text-white" : "bg-white border-slate-200 text-slate-600 hover:bg-slate-50"}`}>
                <svg width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><polyline points="21 8 21 21 3 21 3 8" /><rect x="1" y="3" width="22" height="5" /><line x1="10" y1="12" x2="14" y2="12" /></svg>
                <span className="hidden sm:inline">{showArchived ? "Viewing Archived" : "Archived"}</span>
                {archivedCount > 0 && !showArchived && <span className="min-w-[18px] h-[18px] px-1 rounded-full bg-slate-200 text-slate-600 text-[10px] font-bold flex items-center justify-center">{archivedCount > 99 ? "99+" : archivedCount}</span>}
              </button>
              )}

              {canUseLeadTools && (
              <button onClick={openTrash}
                title="Trashed leads — kept for 7 days, then deleted forever"
                className="flex items-center gap-1.5 px-4 py-2 bg-white border border-slate-200 text-slate-600 rounded-xl text-sm font-semibold hover:bg-slate-50 hover:text-rose-600 active:scale-[0.97] transition-all shadow-sm shadow-slate-50">
                <I.Trash /> <span className="hidden sm:inline">Trash</span>
              </button>
              )}

              {canAddLeads && (
              <button onClick={openAdd}
                className="flex items-center gap-1.5 px-4 py-2 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 active:scale-[0.97] transition-all shadow-sm shadow-indigo-200">
                <I.Plus /> <span className="hidden sm:inline">New Lead</span>
              </button>
              )}
            </div>

          </div>
        </div>
      </div>

      {/* ── Toolbar ──────────────────────────────────────────────────────────── */}
      <div className="max-w-[1440px] mx-auto px-4 sm:px-6 xl:px-8 py-4">
        {/* Search sits on its own row.
            Sharing a wrapping row with the filters, it was the only flexible item
            among eight fixed-width ones, so it lost the fight and shrank to the
            width of its own padding — a bare circle with the magnifier in it. How
            many filters appear depends on the role (assignee needs assign rights,
            Meta needs an integration), so a layout that survives any number of
            them is the one to have. */}
        <div className="relative w-full sm:max-w-md mb-2.5">
          <div className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none"><I.Search /></div>
          <input
            type="text"
            placeholder="Search name, email or place…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            onKeyDown={e => e.key === "Enter" && fetchLeads()}
            className="w-full bg-white border border-slate-200 rounded-xl pl-9 pr-4 py-2.5 text-sm text-slate-700 placeholder:text-slate-400 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all shadow-sm shadow-slate-50"
          />
        </div>

        <div className="flex flex-col sm:flex-row gap-2.5 flex-wrap">

          {/* Status filter */}
          <div className="relative flex-shrink-0 w-full sm:w-[180px]">
            <div className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none z-10"><I.Filter /></div>
            <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
              className="dropdown-premium w-full !pl-8">
              <option value="all">All Statuses</option>
              {statusOptions.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>

          {/* Source filter */}
          <div className="flex-shrink-0 w-full sm:w-[150px]">
            <select value={sourceFilter} onChange={e => setSourceFilter(e.target.value)}
              className="dropdown-premium w-full">
              <option value="all">All Sources</option>
              <option value="meta_ads">Meta Ads</option>
              <option value="manual">Manual</option>
              <option value="website">Website</option>
              <option value="linkedin">LinkedIn</option>
              <option value="referral">Referral</option>
            </select>
          </div>

          {/* District filter — the options are the districts actually on the
              leads, since the field is free text off a CSV column or a Meta
              form rather than a fixed list */}
          <div className="flex-shrink-0 w-full sm:w-[160px]">
            <select value={districtFilter} onChange={e => { setDistrictFilter(e.target.value); setPage(1); }}
              className="dropdown-premium w-full">
              <option value="all">All Districts</option>
              <option value="none">No District</option>
              {districtsList.map(d => <option key={d} value={d}>{d}</option>)}
            </select>
          </div>

          {/* Campaign filter */}
          <div className="flex-shrink-0 w-full sm:w-[150px]">
            <select value={campaignFilter} onChange={e => setCampaignFilter(e.target.value)}
              className="dropdown-premium w-full">
              <option value="all">All Campaigns</option>
              <option value="none">No Campaign</option>
              {campaignsList.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </div>

          {/* Meta integration (branch) filter — only useful once one exists */}
          {integrationsList.length > 0 && (
            <div className="flex-shrink-0 w-full sm:w-[170px]">
              <select value={metaIntegrationFilter} onChange={e => { setMetaIntegrationFilter(e.target.value); setPage(1); }}
                className="dropdown-premium w-full">
                <option value="all">All Meta Accounts</option>
                <option value="none">Not from Meta</option>
                {integrationsList.map(i => <option key={i.id} value={i.id}>{i.name}</option>)}
              </select>
            </div>
          )}

          {/* Product filter */}
          <div className="flex-shrink-0 w-full sm:w-[150px]">
            <select value={productFilter} onChange={e => setProductFilter(e.target.value)}
              className="dropdown-premium w-full">
              <option value="all">All Products</option>
              {productsList.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>

          {/* Stage filter */}
          <div className="flex-shrink-0 w-full sm:w-[160px]">
            <select value={stageFilter} onChange={e => setStageFilter(e.target.value)}
              className="dropdown-premium w-full">
              <option value="all">All Stages</option>
              {STAGE_OPTIONS.map(s => <option key={s} value={s}>{STAGE_META[s].label}</option>)}
            </select>
          </div>

          {/* Assignee filter */}
          {canAssign && (
            <div className="flex-shrink-0 w-full sm:w-[160px]">
              <select value={assigneeFilter} onChange={e => setAssigneeFilter(e.target.value)}
                className="dropdown-premium w-full">
                <option value="all">All Assignees</option>
                <option value="unassigned">Unassigned</option>
                {teamMembers.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
              </select>
            </div>
          )}

          {/* Advanced Filter Toggle */}
          <button onClick={() => setShowAdvanced(!showAdvanced)}
            className={`flex-shrink-0 flex items-center gap-1.5 px-3.5 py-2.5 text-xs font-semibold rounded-xl transition-all duration-200 border ${showAdvanced ? "bg-indigo-50 border-indigo-200 text-indigo-700 shadow-sm shadow-indigo-100" : "bg-white border-slate-200 text-slate-600 hover:bg-slate-50 hover:border-slate-300 shadow-sm shadow-slate-50"}`}>
            <I.Filter /> {showAdvanced ? "Hide Advanced" : "Advanced Filters"}
          </button>

          {/* Clear filters — only shown when active */}
          {activeFilters > 0 && (
            <button onClick={clearFilters}
              className="flex-shrink-0 flex items-center gap-1.5 px-3 py-2.5 text-xs font-semibold text-rose-600 bg-rose-50 border border-rose-200 rounded-xl hover:bg-rose-100 transition-all">
              <I.X /> Clear ({activeFilters})
            </button>
          )}
        </div>

        {/* ── Advanced Filters Panel ────────────────────────────────────────────── */}
        {showAdvanced && (
          <div className="mt-3 bg-white border border-slate-200/80 rounded-2xl p-5 shadow-sm shadow-slate-50 relative animate-fade-in-down">
            <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider mb-4 flex items-center gap-2">
              <I.Filter /> Advanced Search Rules
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
              
              {/* Created At */}
              <div>
                <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-1.5">Created On</label>
                <div className="flex flex-col gap-2">
                  <select value={createdType} onChange={e => setCreatedType(e.target.value)} className="dropdown-premium w-full !bg-slate-50">
                    <option value="all">Any time</option>
                    <option value="today">Today</option>
                    <option value="yesterday">Yesterday</option>
                    <option value="this_week">This Week</option>
                    <option value="this_month">This Month</option>
                    <option value="age_in">Age in</option>
                    <option value="previous">Previous</option>
                    <option value="between">Between</option>
                  </select>
                  {(createdType === "age_in" || createdType === "previous") && (
                    <div className="flex items-center gap-2">
                      <input type="number" min="0" value={createdParam} onChange={e => setCreatedParam(e.target.value)} className="w-16 bg-slate-50 border border-slate-200 rounded-lg px-2 py-1.5 text-sm outline-none focus:border-indigo-400" />
                      <span className="text-xs text-slate-500 font-medium">days</span>
                    </div>
                  )}
                  {createdType === "between" && (
                    <div className="flex items-center gap-1.5">
                      <input type="date" value={createdFrom} onChange={e => setCreatedFrom(e.target.value)} className="flex-1 bg-slate-50 border border-slate-200 rounded-lg px-2 py-1.5 text-xs outline-none" />
                      <span className="text-slate-400">-</span>
                      <input type="date" value={createdTo} onChange={e => setCreatedTo(e.target.value)} className="flex-1 bg-slate-50 border border-slate-200 rounded-lg px-2 py-1.5 text-xs outline-none" />
                    </div>
                  )}
                </div>
              </div>

              {/* Modified At */}
              <div>
                <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-1.5">Modified On</label>
                <div className="flex flex-col gap-2">
                  <select value={modType} onChange={e => setModType(e.target.value)} className="dropdown-premium w-full !bg-slate-50">
                    <option value="all">Any time</option>
                    <option value="today">Today</option>
                    <option value="yesterday">Yesterday</option>
                    <option value="this_week">This Week</option>
                    <option value="this_month">This Month</option>
                    <option value="age_in">Age in</option>
                    <option value="previous">Previous</option>
                    <option value="between">Between</option>
                    <option value="is_empty">Is Empty</option>
                    <option value="is_not_empty">Is Not Empty</option>
                  </select>
                  {(modType === "age_in" || modType === "previous") && (
                    <div className="flex items-center gap-2">
                      <input type="number" min="0" value={modParam} onChange={e => setModParam(e.target.value)} className="w-16 bg-slate-50 border border-slate-200 rounded-lg px-2 py-1.5 text-sm outline-none focus:border-indigo-400" />
                      <span className="text-xs text-slate-500 font-medium">days</span>
                    </div>
                  )}
                  {modType === "between" && (
                    <div className="flex items-center gap-1.5">
                      <input type="date" value={modFrom} onChange={e => setModFrom(e.target.value)} className="flex-1 bg-slate-50 border border-slate-200 rounded-lg px-2 py-1.5 text-xs outline-none" />
                      <span className="text-slate-400">-</span>
                      <input type="date" value={modTo} onChange={e => setModTo(e.target.value)} className="flex-1 bg-slate-50 border border-slate-200 rounded-lg px-2 py-1.5 text-xs outline-none" />
                    </div>
                  )}
                </div>
              </div>

              {/* Deal Value */}
              <div>
                <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-1.5">Deal Value (₹)</label>
                <div className="flex items-center gap-2">
                  <input type="number" placeholder="Min" value={valueMin} onChange={e => setValueMin(e.target.value)} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-sm text-slate-700 outline-none focus:border-indigo-400" />
                  <span className="text-slate-300">-</span>
                  <input type="number" placeholder="Max" value={valueMax} onChange={e => setValueMax(e.target.value)} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-sm text-slate-700 outline-none focus:border-indigo-400" />
                </div>
              </div>

              {/* Company */}
              <div>
                <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-1.5">Place</label>
                <input type="text" placeholder="Contains..." value={companyFilter} onChange={e => setCompanyFilter(e.target.value)} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-sm text-slate-700 outline-none focus:border-indigo-400" />
              </div>
              
              {/* Status Change History */}
              <div className="sm:col-span-2 lg:col-span-4 bg-indigo-50/50 border border-indigo-100 rounded-xl p-3">
                <label className="block text-[10px] font-bold text-indigo-700 uppercase tracking-widest mb-2 flex items-center gap-1.5">
                  <I.Activity className="w-3 h-3" /> Status Change History
                </label>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div className="flex gap-2">
                    <select value={statusChangeFrom} onChange={e => setStatusChangeFrom(e.target.value)} className="dropdown-premium flex-1 !text-xs !py-1.5 !px-2 !pr-7 !rounded-lg">
                      <option value="all">From Any Status</option>
                      {statusOptions.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                    </select>
                    <select value={statusChangeTo} onChange={e => setStatusChangeTo(e.target.value)} className="dropdown-premium flex-1 !text-xs !py-1.5 !px-2 !pr-7 !rounded-lg">
                      <option value="all">To Any Status</option>
                      {statusOptions.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                    </select>
                  </div>
                  
                  <div className="sm:col-span-2 flex items-start gap-2">
                    <select value={statusChangeType} onChange={e => setStatusChangeType(e.target.value)} className="dropdown-premium w-40 flex-shrink-0 !text-xs !py-1.5 !px-2 !pr-7 !rounded-lg">
                      <option value="all">At Any Time</option>
                      <option value="today">Today</option>
                      <option value="yesterday">Yesterday</option>
                      <option value="this_week">This Week</option>
                      <option value="this_month">This Month</option>
                      <option value="age_in">Age in</option>
                      <option value="previous">Previous</option>
                      <option value="between">Between</option>
                    </select>
                    
                    {(statusChangeType === "age_in" || statusChangeType === "previous") && (
                      <div className="flex items-center gap-1.5">
                        <input type="number" min="0" value={statusChangeParam} onChange={e => setStatusChangeParam(e.target.value)} className="w-14 bg-white border border-slate-200 rounded-lg px-2 py-1.5 text-xs outline-none focus:border-indigo-400" />
                        <span className="text-xs text-slate-500 font-medium">days</span>
                      </div>
                    )}
                    {statusChangeType === "between" && (
                      <div className="flex flex-wrap items-center gap-1.5">
                        <input type="date" value={statusChangeFromD} onChange={e => setStatusChangeFromD(e.target.value)} className="bg-white border border-slate-200 rounded-lg px-2 py-1.5 text-xs outline-none" />
                        <span className="text-slate-400">-</span>
                        <input type="date" value={statusChangeToD} onChange={e => setStatusChangeToD(e.target.value)} className="bg-white border border-slate-200 rounded-lg px-2 py-1.5 text-xs outline-none" />
                      </div>
                    )}
                  </div>
                </div>
              </div>
              
              {/* Activity Filter */}
              <div className="sm:col-span-2 lg:col-span-4 bg-purple-50/50 border border-purple-100 rounded-xl p-3 mt-2">
                <label className="block text-[10px] font-bold text-purple-700 uppercase tracking-widest mb-2 flex items-center gap-1.5">
                  <I.Activity className="w-3 h-3" /> Activity Filter
                </label>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <select value={activityType} onChange={e => setActivityType(e.target.value)} className="dropdown-premium w-full !text-xs !py-1.5 !px-2 !pr-7 !rounded-lg">
                    <option value="all">Any Activity</option>
                    <option value="note_added">Note Added</option>
                    <option value="lead_status_change">Status Change</option>
                  </select>
                  
                  <div className="flex items-center gap-2">
                    <label className="text-xs text-slate-600 font-medium whitespace-nowrap">Has activity in last</label>
                    <input type="number" min="0" placeholder="days" value={hasActivityDays} onChange={e => { setHasActivityDays(e.target.value); setNoActivityDays(""); }} className="w-16 bg-white border border-slate-200 rounded-lg px-2 py-1.5 text-xs outline-none focus:border-purple-400" />
                  </div>
                  
                  <div className="flex items-center gap-2">
                    <label className="text-xs text-slate-600 font-medium whitespace-nowrap">NO activity in last</label>
                    <input type="number" min="0" placeholder="days" value={noActivityDays} onChange={e => { setNoActivityDays(e.target.value); setHasActivityDays(""); }} className="w-16 bg-white border border-slate-200 rounded-lg px-2 py-1.5 text-xs outline-none focus:border-purple-400" />
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ── Bulk action bar ───────────────────────────────────────────────────── */}
      {showBulkWa && (
        <div className="fixed inset-0 z-50 flex items-center justify-center px-4">
          <div className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm" />
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg relative z-10 overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
              <div>
                <h3 className="font-bold text-lg text-slate-900">💬 Send WhatsApp</h3>
                <p className="text-xs text-slate-400 mt-0.5">{selectedIds.length} lead{selectedIds.length !== 1 ? "s" : ""} selected</p>
              </div>
              <button onClick={() => setShowBulkWa(false)} className="text-slate-400 hover:text-slate-600"><svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12" /></svg></button>
            </div>
            <div className="p-6 space-y-4">
              <select value={waMode} onChange={e => setWaMode(e.target.value as "text" | "template")} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition">
                <option value="template">Approved template (recommended for outreach)</option>
                <option value="text">Free text (only within 24h session window)</option>
              </select>
              {waMode === "template" ? (
                <>
                  <input value={waTemplate} onChange={e => setWaTemplate(e.target.value)} placeholder="Template name (as approved in Meta)" className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition" />
                  <input value={waLang} onChange={e => setWaLang(e.target.value)} placeholder="Language code (e.g. en_US)" className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition" />
                  <input value={waVars} onChange={e => setWaVars(e.target.value)} placeholder="Variable lead fields, comma-separated — e.g. first_name, company" className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition" />
                  <p className="text-xs text-slate-500">{"Each lead's field values fill the template's {{1}}, {{2}}… in order."}</p>
                </>
              ) : (
                <>
                  <textarea value={waText} onChange={e => setWaText(e.target.value)} rows={4} placeholder="Message… supports {{first_name}}" className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition resize-none" />
                  <p className="text-xs text-slate-500">Free text only delivers to people who messaged you in the last 24 hours — otherwise use a template.</p>
                </>
              )}
            </div>
            <div className="px-6 py-4 border-t border-slate-100 flex gap-3">
              <button onClick={() => setShowBulkWa(false)} className="flex-1 px-4 py-2.5 text-slate-600 font-medium hover:bg-slate-50 rounded-xl transition-colors">Cancel</button>
              <button onClick={bulkWhatsApp} disabled={waSending} className="flex-1 bg-emerald-500 hover:bg-emerald-600 text-white font-semibold py-2.5 rounded-xl transition shadow-sm disabled:opacity-50">{waSending ? "Queuing…" : `Send to ${selectedIds.length}`}</button>
            </div>
          </div>
        </div>
      )}

      {selectedIds.length > 0 && (
        <div className="max-w-[1440px] mx-auto px-4 sm:px-6 xl:px-8 pb-3">
          <div className="flex items-center justify-between gap-3 bg-indigo-600 text-white rounded-2xl px-5 py-3 shadow-lg shadow-indigo-200/60">
            <div className="flex items-center gap-3">
              <span className="w-6 h-6 bg-white/20 rounded-md flex items-center justify-center text-[11px] font-bold tabular-nums">{selectedIds.length}</span>
              <span className="text-sm font-medium">lead{selectedIds.length !== 1 ? "s" : ""} selected</span>
            </div>
            <div className="flex items-center gap-2">
              {canAssign && (
                <button onClick={() => setShowBulkAssign(true)}
                  className="flex items-center gap-1.5 bg-white/15 hover:bg-white/25 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all">
                  <I.Users /> Assign
                </button>
              )}
              {canEditLeads && (
              <button onClick={() => setShowBulkUpdate(true)}
                className="flex items-center gap-1.5 bg-white/15 hover:bg-white/25 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all">
                <I.Edit /> Update
              </button>
              )}
              {!isSpectator && (
              <button onClick={() => setShowBulkWa(true)}
                className="flex items-center gap-1.5 bg-emerald-500 hover:bg-emerald-600 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all">
                💬 WhatsApp
              </button>
              )}
              {canDeleteLeads && (
              <button onClick={bulkDelete}
                className="flex items-center gap-1.5 bg-red-500 hover:bg-red-600 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all">
                <I.Trash /> Delete
              </button>
              )}
              <button onClick={() => setSelectedIds([])}
                className="ml-1 text-white/60 hover:text-white text-xs font-semibold transition-colors px-1">
                ✕ Clear
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Table ────────────────────────────────────────────────────────────── */}
      <div className="max-w-[1440px] mx-auto px-4 sm:px-6 xl:px-8 pb-12">
        <div className="bg-white border border-slate-200/60 rounded-2xl shadow-sm overflow-hidden">

          {loading ? (
            <div className="flex flex-col items-center justify-center py-28 gap-3">
              <div className="w-7 h-7 border-[3px] border-indigo-600 border-t-transparent rounded-full animate-spin" />
              <p className="text-sm text-slate-400">Loading leads…</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left min-w-[780px]">
                <thead>
                  <tr className="border-b border-slate-100 bg-slate-50/80">
                    <th className="px-4 py-3 w-10">
                      <Checkbox checked={selectedIds.length === leads.length && leads.length > 0} onChange={toggleAll} />
                    </th>
                    <th className="px-4 py-3 text-[10px] font-bold text-slate-400 uppercase tracking-widest">
                      <button onClick={() => handleSort("first_name")} className={sortBtnClass("first_name")}>
                        Lead {renderSortArrow("first_name")}
                      </button>
                    </th>
                    <th className="px-4 py-3 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Owner</th>
                    <th className="px-4 py-3 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Source</th>
                    <th className="px-4 py-3 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Status</th>
                    <th className="px-4 py-3 text-[10px] font-bold text-slate-400 uppercase tracking-widest">
                      <button onClick={() => handleSort("activity")} className={sortBtnClass("activity")}>
                        Recent Activity {renderSortArrow("activity")}
                      </button>
                    </th>
                    <th className="px-4 py-3 text-[10px] font-bold text-slate-400 uppercase tracking-widest text-right">
                      <button onClick={() => handleSort("value")} className={sortBtnClass("value", "ml-auto")}>
                        Value {renderSortArrow("value")}
                      </button>
                    </th>
                    <th className="w-20" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">

                  {leads.length === 0 && (
                    <tr>
                      <td colSpan={8}>
                        <div className="flex flex-col items-center py-20 text-center">
                          <div className="w-12 h-12 bg-slate-100 rounded-2xl flex items-center justify-center mb-3">
                            <I.Users />
                          </div>
                          <h3 className="text-sm font-semibold text-slate-700 mb-1">No leads found</h3>
                          <p className="text-xs text-slate-400 mb-5">Try adjusting your filters or add a new lead</p>
                          <button onClick={openAdd}
                            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 transition-all">
                            <I.Plus /> Add Lead
                          </button>
                        </div>
                      </td>
                    </tr>
                  )}

                  {leads.map(lead => {
                    const sm   = statusMeta[lead.status] || FALLBACK_STATUS_META;
                    const src  = SOURCE_META[lead.source] || { bg: "bg-slate-100", text: "text-slate-600" };
                    const isSel = selectedIds.includes(lead.id);
                    const initials = `${lead.first_name?.[0] || ""}${lead.last_name?.[0] || ""}`.toUpperCase();
                    return (
                      <tr key={lead.id}
                        onClick={() => openView(lead)}
                        className={`group transition-colors duration-100 cursor-pointer ${isSel ? "bg-indigo-50/50" : "hover:bg-slate-50/60"}`}>

                        {/* Checkbox */}
                        <td className="px-4 py-3.5" onClick={e => e.stopPropagation()}>
                          <Checkbox checked={isSel} onChange={() => toggleOne(lead.id)} />
                        </td>

                        {/* Lead */}
                        <td className="px-4 py-3.5">
                          <div className="flex items-center gap-3">
                            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-100 to-violet-100 flex items-center justify-center text-[11px] font-bold text-indigo-600 flex-shrink-0">
                              {initials || "?"}
                            </div>
                            <div className="min-w-0">
                              <p className="text-[13px] font-semibold text-slate-800 leading-tight">{lead.first_name} {lead.last_name}</p>
                              <p className="text-[11px] text-slate-400 truncate max-w-[180px]">{lead.email || lead.phone || "—"}</p>
                              <div className="mt-1"><StageTag stage={lead.pipeline_stage} /></div>
                              {lead.next_task && <TaskTag task={lead.next_task} />}
                            </div>
                          </div>
                        </td>

                        {/* Owner — a lead handed to a BDE has two: the tele
                            caller who worked it and the BDE who took it on. */}
                        <td className="px-4 py-3.5">
                          <Owners lead={lead} />
                        </td>

                        {/* Source */}
                        <td className="px-4 py-3.5">
                          <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-semibold ${src.bg} ${src.text}`}>
                            {getSourceLabel(lead.source)}
                          </span>
                          {lead.meta_integration_name && (
                            <span className="block mt-1 text-[10px] font-medium text-blue-600 truncate max-w-[140px]">{lead.meta_integration_name}</span>
                          )}
                        </td>

                        {/* Status — dropdown with colored background */}
                        <td className="px-4 py-3.5" onClick={e => e.stopPropagation()}>
                          <div className="relative inline-flex group/status">
                            <span className={`absolute inset-0 rounded-lg pointer-events-none ${sm.bg} transition-all duration-200 group-hover/status:shadow-sm`} />
                            <select
                              value={lead.status}
                              disabled={!canEditStatus}
                              title={canEditStatus ? undefined : "Only the tele caller or a manager can change the lead status."}
                              onChange={e => updateStatus(lead.id, e.target.value)}
                              className={`relative appearance-none pl-2.5 pr-7 py-1.5 rounded-lg text-[11px] font-semibold cursor-pointer outline-none border-0 bg-transparent ${sm.text} min-w-[115px] transition-all duration-200`}
                              style={{ backgroundImage: 'url("data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' width=\'12\' height=\'12\' viewBox=\'0 0 24 24\' fill=\'none\' stroke=\'%2394a3b8\' stroke-width=\'2.5\' stroke-linecap=\'round\' stroke-linejoin=\'round\'%3E%3Cpath d=\'M6 9l6 6 6-6\'/%3E%3C/svg%3E")', backgroundRepeat: 'no-repeat', backgroundPosition: 'right 6px center', backgroundSize: '12px' }}
                            >
                              {statusOptions.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                            </select>
                          </div>
                        </td>

                        {/* Recent Activity */}
                        <td className="px-4 py-3.5">
                          {lead.recent_activity ? (
                            <div className="flex flex-col gap-0.5 max-w-[200px]">
                              <p className="text-[11px] font-medium text-slate-700 truncate" title={lead.recent_activity.description}>
                                {lead.recent_activity.description}
                              </p>
                              <div className="flex items-center gap-1 text-[9px] text-slate-400">
                                <I.Clock />
                                <span>{formatRelativeTime(lead.recent_activity.created_at)}</span>
                              </div>
                            </div>
                          ) : (
                            <span className="text-[11px] text-slate-300 italic">No activity</span>
                          )}
                        </td>

                        {/* Value */}
                        <td className="px-4 py-3.5 text-right">
                          <span className="text-[13px] font-bold text-slate-800 tabular-nums">{formatCurrency(lead.value)}</span>
                        </td>

                        {/* Actions */}
                        <td className="pr-3 py-3.5">
                          <div className="flex items-center justify-end gap-1">
                            {/* Jumps straight to the Site Visit Details section on the
                                lead page, and doubles as the completion indicator. */}
                            {showSiteVisit && (
                            <Link href={`/leads/${lead.id}#site-visit`} onClick={(e) => e.stopPropagation()}
                              className={`flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-[10px] font-bold uppercase tracking-wide whitespace-nowrap border transition-all ${
                                lead.site_visit_complete
                                  ? "bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-100"
                                  : "bg-slate-50 text-slate-500 border-slate-200 hover:bg-indigo-50 hover:text-indigo-600 hover:border-indigo-200"}`}
                              title={lead.site_visit_complete ? "Site visit completed — open the details" : "Open the site visit details"}>
                              {lead.site_visit_complete ? (
                                <>
                                  <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12" /></svg>
                                  Site Visit Completed
                                </>
                              ) : (
                                <>
                                  <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" /><circle cx="12" cy="10" r="3" /></svg>
                                  Site Visit
                                </>
                              )}
                            </Link>
                            )}
                            <Link href={`/leads/${lead.id}`} onClick={(e) => e.stopPropagation()}
                              className="w-7 h-7 flex items-center justify-center rounded-lg text-slate-400 hover:text-sky-600 hover:bg-sky-50 transition-all"
                              title="View Details">
                              <I.Eye />
                            </Link>
                            {canEditLeads && (
                            <button onClick={(e) => { e.stopPropagation(); openEdit(lead); }}
                              className="w-7 h-7 flex items-center justify-center rounded-lg text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 transition-all"
                              title="Edit">
                              <I.Edit />
                            </button>
                            )}
                            {canEditLeads && (
                            <button onClick={(e) => { e.stopPropagation(); archiveLead(lead.id, !showArchived); }}
                              className="w-7 h-7 flex items-center justify-center rounded-lg text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 transition-all"
                              title={showArchived ? "Restore from archive" : "Archive (keep, but hide from active list)"}>
                              {showArchived ? (
                                <svg width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><path d="M3 12a9 9 0 1 0 3-6.7L3 8" /><polyline points="3 3 3 8 8 8" /></svg>
                              ) : (
                                <svg width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><polyline points="21 8 21 21 3 21 3 8" /><rect x="1" y="3" width="22" height="5" /><line x1="10" y1="12" x2="14" y2="12" /></svg>
                              )}
                            </button>
                            )}
                            {!showArchived && canDeleteLeads && (
                            <button onClick={(e) => { e.stopPropagation(); deleteLead(lead.id); }}
                              className="w-7 h-7 flex items-center justify-center rounded-lg text-slate-400 hover:text-red-500 hover:bg-red-50 transition-all"
                              title="Move to Trash">
                              <I.Trash />
                            </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          
          {/* Pagination Controls */}
          {!loading && totalPages > 1 && (
            <div className="flex items-center justify-between px-6 py-4 border-t border-slate-100 bg-slate-50/50">
              <p className="text-xs text-slate-500 font-medium">
                Showing <span className="font-bold text-slate-700">{(page - 1) * 100 + 1}</span> to <span className="font-bold text-slate-700">{Math.min(page * 100, totalLeadsCount)}</span> of <span className="font-bold text-slate-700">{totalLeadsCount}</span> leads
              </p>
              <div className="flex items-center gap-1.5">
                <button
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-xs font-semibold text-slate-600 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-slate-50 transition-colors"
                >
                  Previous
                </button>
                {(() => {
                  // Build a compact page list: 1 … (page-1, page, page+1) … last
                  const nums: (number | string)[] = [];
                  if (totalPages <= 7) {
                    for (let i = 1; i <= totalPages; i++) nums.push(i);
                  } else {
                    nums.push(1);
                    if (page > 3) nums.push("left-ellipsis");
                    const start = Math.max(2, page - 1);
                    const end = Math.min(totalPages - 1, page + 1);
                    for (let i = start; i <= end; i++) nums.push(i);
                    if (page < totalPages - 2) nums.push("right-ellipsis");
                    nums.push(totalPages);
                  }
                  return nums.map((n, i) =>
                    typeof n === "number" ? (
                      <button
                        key={n}
                        onClick={() => setPage(n)}
                        aria-current={n === page ? "page" : undefined}
                        className={`min-w-[32px] px-2.5 py-1.5 rounded-lg border text-xs font-semibold transition-colors ${
                          n === page
                            ? "bg-indigo-600 border-indigo-600 text-white"
                            : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                        }`}
                      >
                        {n}
                      </button>
                    ) : (
                      <span key={`${n}-${i}`} className="px-1 text-xs text-slate-400 select-none">…</span>
                    )
                  );
                })()}
                <button
                  onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                  disabled={page === totalPages}
                  className="px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-xs font-semibold text-slate-600 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-slate-50 transition-colors"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── Trash Modal ───────────────────────────────────────────────────────── */}
      {showTrash && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
          <div className="bg-white w-full max-w-3xl rounded-2xl shadow-2xl max-h-[85vh] overflow-hidden flex flex-col" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 flex-shrink-0">
              <div>
                <h2 className="text-base font-bold text-slate-900">Trash</h2>
                <p className="text-[11px] text-slate-400 mt-0.5">Trashed leads are kept for 7 days, then deleted forever automatically.</p>
              </div>
              <div className="flex items-center gap-2">
                {canEmptyTrash && trashRows.length > 0 && (
                  <button onClick={emptyTrash} disabled={emptying}
                    title="Permanently delete every lead in the Trash"
                    className="px-3 py-1.5 rounded-xl bg-rose-600 text-white text-xs font-bold hover:bg-rose-700 transition disabled:opacity-40">
                    {emptying ? "Emptying…" : "Empty Trash"}
                  </button>
                )}
                <button onClick={() => setShowTrash(false)} className="w-8 h-8 flex items-center justify-center rounded-xl bg-slate-100 text-slate-500 hover:bg-slate-200 transition text-sm">✕</button>
              </div>
            </div>
            <div className="overflow-y-auto flex-1">
              {trashLoading ? (
                <div className="py-14 text-center text-sm text-slate-400">Loading…</div>
              ) : trashRows.length === 0 ? (
                <div className="py-14 text-center text-sm text-slate-400">Trash is empty.</div>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-[10px] font-bold text-slate-400 uppercase tracking-wide border-b border-slate-100 bg-slate-50/60">
                      <th className="px-5 py-3">Lead</th>
                      <th className="px-5 py-3">Trashed</th>
                      <th className="px-5 py-3">Disappears In</th>
                      <th className="px-5 py-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trashRows.map(t => (
                      <tr key={t.id} className="border-b border-slate-50 hover:bg-slate-50/60">
                        <td className="px-5 py-3">
                          <p className="font-semibold text-slate-800">{t.first_name} {t.last_name}</p>
                          <p className="text-[11px] text-slate-400">{t.phone || "—"}{t.email ? ` · ${t.email}` : ""}</p>
                        </td>
                        <td className="px-5 py-3 text-slate-500 text-xs">
                          {t.trashed_at ? new Date(t.trashed_at).toLocaleDateString("en-IN") : "—"}
                          {t.trashed_by_name ? <span className="block text-[11px] text-slate-400">by {t.trashed_by_name}</span> : null}
                        </td>
                        <td className="px-5 py-3">
                          <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${t.days_left <= 2 ? "bg-rose-50 text-rose-600" : "bg-amber-50 text-amber-700"}`}>
                            {t.days_left <= 0 ? "today" : `${t.days_left} day${t.days_left === 1 ? "" : "s"}`}
                          </span>
                        </td>
                        <td className="px-5 py-3">
                          <div className="flex items-center justify-end gap-3">
                            {!isSpectator && (
                            <button onClick={() => restoreFromTrash(t.id)} className="text-[12px] font-semibold text-indigo-600 hover:text-indigo-800">Restore</button>
                            )}
                            <button onClick={() => purgeFromTrash(t.id)} className="text-[12px] font-semibold text-rose-500 hover:text-rose-700">Delete forever</button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── Add / Edit Modal ──────────────────────────────────────────────────── */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/40 backdrop-blur-sm"
          onClick={() => setShowModal(false)}>
          <div className="bg-white w-full sm:max-w-2xl sm:mx-4 rounded-t-2xl sm:rounded-2xl shadow-2xl max-h-[92vh] overflow-hidden flex flex-col"
            onClick={e => e.stopPropagation()}>

            {/* Modal header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 flex-shrink-0">
              <div>
                <h2 className="text-[15px] font-bold text-slate-900">{editingLead ? "Edit Lead" : "New Lead"}</h2>
                <p className="text-xs text-slate-400 mt-0.5">{editingLead ? "Update lead details" : "Add a new lead to your pipeline"}</p>
              </div>
              <button onClick={() => setShowModal(false)}
                className="w-8 h-8 flex items-center justify-center rounded-xl bg-slate-100 text-slate-500 hover:bg-slate-200 transition-all">
                <I.X />
              </button>
            </div>

            {/* Form */}
            <form onSubmit={handleSubmit} className="overflow-y-auto flex-1 px-6 py-5 space-y-4">

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className={LABEL}>First Name <span className="text-red-400 normal-case">*</span></label>
                  <input required value={form.first_name} onChange={e => setForm({ ...form, first_name: e.target.value })} className={FIELD} placeholder="Aarav" />
                </div>
                <div>
                  <label className={LABEL}>Last Name</label>
                  <input value={form.last_name} onChange={e => setForm({ ...form, last_name: e.target.value })} className={FIELD} placeholder="Sharma" />
                </div>
                <div>
                  <label className={LABEL}>Email</label>
                  <input type="email" value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} className={FIELD} placeholder="email@example.com" />
                </div>
                <div>
                  <label className={LABEL}>Phone</label>
                  <input type="tel" value={form.phone} onChange={e => setForm({ ...form, phone: e.target.value })} className={FIELD} placeholder="+91 98765 43210" />
                </div>
                <div>
                  <label className={LABEL}>Location</label>
                  <input value={form.company} onChange={e => setForm({ ...form, company: e.target.value })} className={FIELD} placeholder="e.g. Kochi" />
                </div>
                <div>
                  <label className={LABEL}>District</label>
                  <select value={form.district} onChange={e => setForm({ ...form, district: e.target.value })} className={SELECT_FIELD}>
                    <option value="">— No district —</option>
                    {districtOptions(configuredDistricts, form.district).map(d => (
                      <option key={d} value={d}>{d}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className={LABEL}>Installation Location</label>
                  <input value={form.installation_location} onChange={e => setForm({ ...form, installation_location: e.target.value })} className={FIELD} placeholder="Where the system is installed" />
                </div>
                <div>
                  <label className={LABEL}>Source</label>
                  <div className="relative">
                    <select value={form.source} onChange={e => setForm({ ...form, source: e.target.value })} className={SELECT_FIELD}>
                      <option value="manual">Manual</option>
                      <option value="website">Website</option>
                      <option value="meta_ads">Meta Ads</option>
                      <option value="linkedin">LinkedIn</option>
                      <option value="referral">Referral</option>
                    </select>
                    <div className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none"><I.ChevronDown /></div>
                  </div>
                </div>
                <div>
                  <label className={LABEL}>Status</label>
                  <div className="relative">
                    <select value={form.status} disabled={!canEditStatus} title={canEditStatus ? undefined : "Only the tele caller or a manager can change the lead status."} onChange={e => setForm({ ...form, status: e.target.value })} className={SELECT_FIELD}>
                      {statusOptions.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                    </select>
                    <div className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none"><I.ChevronDown /></div>
                  </div>
                </div>
                <div>
                  <label className={LABEL}>Product</label>
                  <div className="relative">
                    <select value={form.product} onChange={e => setForm({ ...form, product: e.target.value })} className={SELECT_FIELD}>
                      <option value="">None</option>
                      {productsList.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                    </select>
                    <div className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none"><I.ChevronDown /></div>
                  </div>
                </div>
              </div>
              
              {canAssign && (
                <div>
                  <label className={LABEL}>Assigned To</label>
                  <div className="relative">
                    <select value={form.assigned_to} onChange={e => setForm({ ...form, assigned_to: e.target.value })} className={SELECT_FIELD}>
                      <option value="">Unassigned</option>
                      {teamMembers.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
                    </select>
                    <div className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none"><I.ChevronDown /></div>
                  </div>
                </div>
              )}

              <div>
                <label className={LABEL}>Latest Note</label>
                <textarea rows={3} value={getLatestNote(form.notes)} readOnly
                  className={`${FIELD} resize-none bg-slate-50/80 text-slate-500 cursor-not-allowed`} />
              </div>

              <div>
                <label className={LABEL}>Add New Note</label>
                <textarea rows={2} value={newEditNote} onChange={e => setNewEditNote(e.target.value)}
                  placeholder="Add a new comment/follow-up note..."
                  className={`${FIELD} resize-none border-indigo-100 focus:border-indigo-400`} />
              </div>

              {/* ── Tasks Section ────────────────────────────────────────── */}
              <div className="pt-2">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <div className="w-5 h-5 rounded-md bg-violet-100 flex items-center justify-center text-violet-600">
                      <I.Task />
                    </div>
                    <span className="text-[11px] font-bold text-slate-600 uppercase tracking-wide">Tasks</span>
                    {pendingTasks.length > 0 && (
                      <span className="text-[10px] font-bold bg-violet-100 text-violet-600 px-2 py-0.5 rounded-full">{pendingTasks.length}</span>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={addPendingTask}
                    className="flex items-center gap-1 px-2.5 py-1.5 bg-violet-50 text-violet-700 border border-violet-200 rounded-lg text-[11px] font-semibold hover:bg-violet-100 transition-all"
                  >
                    <I.Plus /> Add Task
                  </button>
                </div>

                {pendingTasks.length === 0 && (
                  <div className="border-2 border-dashed border-slate-200 rounded-xl py-5 text-center">
                    <p className="text-xs text-slate-400">No tasks added yet. Click <span className="font-semibold text-violet-600">+ Add Task</span> to create tasks linked to this lead.</p>
                  </div>
                )}

                {pendingTasks.length > 0 && (
                  <div className="space-y-2.5">
                    {pendingTasks.map((task, idx) => (
                      <div key={task._key} className="bg-slate-50 border border-slate-200 rounded-xl p-3.5 relative group">
                        <div className="flex items-start gap-2 mb-2.5">
                          <div className="flex-1">
                            <input
                              type="text"
                              value={task.title}
                              onChange={e => updatePendingTask(task._key, { title: e.target.value })}
                              placeholder={`Task #${idx + 1} — e.g. Follow up call`}
                              className="w-full bg-white border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 outline-none focus:ring-2 focus:ring-violet-500/20 focus:border-violet-400 transition-all"
                            />
                          </div>
                          <button
                            type="button"
                            onClick={() => removePendingTask(task._key)}
                            className="w-7 h-7 flex items-center justify-center rounded-lg text-slate-300 hover:text-red-500 hover:bg-red-50 transition-all flex-shrink-0 mt-0.5"
                          >
                            <I.Trash />
                          </button>
                        </div>
                        <div className="grid grid-cols-4 gap-2">
                          {/* Priority */}
                          <div className="relative">
                            <select
                              value={task.priority}
                              onChange={e => updatePendingTask(task._key, { priority: e.target.value as any })}
                              className="w-full appearance-none bg-white border border-slate-200 rounded-lg pl-2.5 pr-7 py-1.5 text-[11px] font-semibold text-slate-700 outline-none focus:ring-2 focus:ring-violet-500/20 focus:border-violet-400 cursor-pointer transition-all"
                            >
                              <option value="high">🔴 High</option>
                              <option value="medium">🟡 Medium</option>
                              <option value="low">🟢 Low</option>
                            </select>
                            <div className="absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none text-slate-400"><I.ChevronDown /></div>
                          </div>
                          {/* Due Date */}
                          <input
                            type="date"
                            value={task.due_date}
                            onChange={e => updatePendingTask(task._key, { due_date: e.target.value })}
                            className="bg-white border border-slate-200 rounded-lg px-2.5 py-1.5 text-[11px] text-slate-700 outline-none focus:ring-2 focus:ring-violet-500/20 focus:border-violet-400 transition-all"
                          />
                          {/* Due Time */}
                          <input
                            type="time"
                            value={task.due_time}
                            onChange={e => updatePendingTask(task._key, { due_time: e.target.value })}
                            className="bg-white border border-slate-200 rounded-lg px-2.5 py-1.5 text-[11px] text-slate-700 outline-none focus:ring-2 focus:ring-violet-500/20 focus:border-violet-400 transition-all"
                          />
                          {/* Assignee */}
                          <div className="relative">
                            <select
                              value={task.assignee_id}
                              onChange={e => updatePendingTask(task._key, { assignee_id: e.target.value })}
                              className="w-full appearance-none bg-white border border-slate-200 rounded-lg pl-2.5 pr-7 py-1.5 text-[11px] font-medium text-slate-700 outline-none focus:ring-2 focus:ring-violet-500/20 focus:border-violet-400 cursor-pointer transition-all"
                            >
                              <option value="">Unassigned</option>
                              {teamMembers.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
                            </select>
                            <div className="absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none text-slate-400"><I.ChevronDown /></div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </form>

            {/* Footer */}
            <div className="flex items-center gap-3 px-6 py-4 border-t border-slate-100 flex-shrink-0 bg-slate-50/50">
              <button onClick={() => setShowModal(false)}
                className="flex-1 py-2.5 border border-slate-200 rounded-xl text-sm font-semibold text-slate-600 hover:bg-slate-100 transition-all bg-white">
                Cancel
              </button>
              <button onClick={handleSubmit as any}
                className="flex-1 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 transition-all shadow-sm shadow-indigo-200">
                {editingLead ? "Save Changes" : "Create Lead"}
                {pendingTasks.filter(t => t.title.trim()).length > 0 && (
                  <span className="ml-2 bg-white/20 text-white text-[10px] font-bold px-2 py-0.5 rounded-full">
                    +{pendingTasks.filter(t => t.title.trim()).length} task{pendingTasks.filter(t => t.title.trim()).length !== 1 ? "s" : ""}
                  </span>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── View Lead Modal ────────────────────────────────────────────────────── */}
      {viewLead && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
          onClick={() => setViewLead(null)}>
          <div className="bg-white w-full max-w-4xl rounded-2xl shadow-2xl max-h-[90vh] overflow-hidden flex flex-col"
            onClick={e => e.stopPropagation()}>

            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 flex-shrink-0">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-white font-bold text-sm">
                  {(viewLead.first_name?.[0] || "").toUpperCase()}{(viewLead.last_name?.[0] || "").toUpperCase()}
                </div>
                <div>
                  <h2 className="text-[15px] font-bold text-slate-900">{viewLead.first_name} {viewLead.last_name}</h2>
                  <p className="text-[11px] text-slate-400">{viewLead.phone || viewLead.email || "No contact info"}</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => initiateCall(viewLead.id)}
                  className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-emerald-600 text-white text-xs font-bold hover:bg-emerald-700 transition-all shadow-sm shadow-emerald-100"
                >
                  <I.Phone /> Call
                </button>
                <Link href={`/leads/${viewLead.id}`}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-100 text-slate-700 text-xs font-semibold hover:bg-slate-200 border border-slate-200 transition-all">
                  <I.Eye /> Full Screen
                </Link>
                {canEditLeads && (
                <button onClick={() => { setViewLead(null); openEdit(viewLead); }}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-indigo-50 text-indigo-700 text-xs font-semibold hover:bg-indigo-100 transition-all">
                  <I.Edit /> Edit
                </button>
                )}
                <button onClick={() => setViewLead(null)}
                  className="w-8 h-8 flex items-center justify-center rounded-xl bg-slate-100 text-slate-500 hover:bg-slate-200 transition-all">
                  <I.X />
                </button>
              </div>
            </div>

            {/* Body: split panel */}
            <div className="flex flex-col sm:flex-row overflow-hidden flex-1 min-h-0">

              {/* ── Left: Lead Details ── */}
              <div className="sm:w-[340px] flex-shrink-0 border-r border-slate-100 overflow-y-auto p-5 space-y-4">
                {/* Status badge */}
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Current Status</span>
                  <StatusBadge status={viewLead.status} meta={statusMeta} />
                </div>

                {/* Info grid */}
                <div className="grid grid-cols-2 gap-3">
                  {[{ label: "Email",    val: viewLead.email    || "—" },
                    { label: "Phone",    val: viewLead.phone    || "—" },
                    { label: "Place",    val: viewLead.company  || "—" },
                    { label: "District", val: viewLead.district || "—" },
                    { label: "Source",   val: (() => { const s = SOURCE_META[viewLead.source] || { bg: "bg-slate-100", text: "text-slate-600" }; return <span className={`px-2 py-0.5 rounded-md text-[11px] font-semibold ${s.bg} ${s.text}`}>{getSourceLabel(viewLead.source)}</span>; })() },
                    ...(viewLead.meta_integration_name ? [{ label: "Meta Account", val: viewLead.meta_integration_name }] : []),
                    { label: "Value",    val: formatCurrency(viewLead.value) },
                    { label: "Assigned", val: viewLead.assigned_to_name || "Unassigned" },
                  ].map(({ label, val }) => (
                    <div key={label} className="bg-slate-50 rounded-xl p-3">
                      <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide mb-1">{label}</p>
                      <div className="text-[13px] font-semibold text-slate-800 truncate">{val}</div>
                    </div>
                  ))}
                  {viewLead.campaigns && viewLead.campaigns.length > 0 && (
                    <div className="col-span-2 bg-indigo-50/50 rounded-xl p-3 border border-indigo-100/50">
                      <p className="text-[10px] font-semibold text-indigo-400 uppercase tracking-wide mb-2">Campaigns</p>
                      <div className="flex flex-wrap gap-2">
                        {viewLead.campaigns.map((c: any) => (
                          canOpenCampaign ? (
                            <Link key={c.id} href={`/campaigns/${c.id}`} className="px-2 py-1 bg-white text-indigo-600 text-[11px] font-bold rounded-lg border border-indigo-200 hover:bg-indigo-50 transition-colors shadow-sm">
                              {c.name}
                            </Link>
                          ) : (
                            <span key={c.id} className="px-2 py-1 bg-white text-slate-600 text-[11px] font-bold rounded-lg border border-slate-200 shadow-sm">
                              {c.name}
                            </span>
                          )
                        ))}
                      </div>
                    </div>
                  )}
                  {/* Created & Updated — full width so time fits */}
                  {[{ label: "Created", val: viewLead.created_at },
                    { label: "Updated", val: viewLead.updated_at },
                  ].map(({ label, val }) => {
                    const d = new Date(val);
                    const date = d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
                    const time = d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: true });
                    return (
                      <div key={label} className="col-span-2 bg-slate-50 rounded-xl p-3 flex items-center justify-between">
                        <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide">{label}</p>
                        <div className="text-right">
                          <span className="text-[12px] font-semibold text-slate-800">{date}</span>
                          <span className="text-[11px] text-slate-400 ml-2">{time}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>

                {/* Notes */}
                <div className="bg-amber-50/40 border border-amber-100/70 rounded-xl p-3">
                  <p className="text-[10px] font-semibold text-amber-600 uppercase tracking-wide mb-1">Latest Note</p>
                  <p className="text-[12px] text-slate-700 leading-relaxed whitespace-pre-wrap mb-2.5">
                    {getLatestNote(viewLead.notes)}
                  </p>
                  <div className="space-y-2">
                    <textarea
                      rows={2}
                      className="w-full text-xs p-2 border border-amber-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-amber-400 bg-white"
                      placeholder="Type a new note..."
                      value={newModalNote}
                      onChange={(e) => setNewModalNote(e.target.value)}
                    />
                    <button
                      onClick={handleAddModalNote}
                      disabled={addingModalNote || !newModalNote.trim()}
                      className="px-3 py-1 bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white text-[11px] font-bold rounded-lg transition-colors w-full sm:w-auto text-center"
                    >
                      {addingModalNote ? "Adding..." : "Add Note"}
                    </button>
                  </div>
                </div>

                {/* Linked Tasks */}
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <div className="w-5 h-5 rounded-md bg-violet-100 flex items-center justify-center text-violet-600">
                        <I.Task />
                      </div>
                      <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wide">Linked Tasks</span>
                    </div>
                    {!tasksLoading && (
                      <span className="text-[10px] font-bold text-slate-400 bg-slate-100 px-2 py-0.5 rounded-full">{leadTasks.length}</span>
                    )}
                  </div>

                  {tasksLoading && (
                    <div className="flex items-center justify-center py-4">
                      <div className="w-5 h-5 border-2 border-violet-500 border-t-transparent rounded-full animate-spin" />
                    </div>
                  )}

                  {!tasksLoading && leadTasks.length === 0 && (
                    <div className="border-2 border-dashed border-slate-200 rounded-xl py-4 text-center">
                      <p className="text-[11px] text-slate-400">No tasks linked to this lead</p>
                      {canEditLeads && (
                      <button
                        onClick={() => { setViewLead(null); openEdit(viewLead); }}
                        className="mt-2 text-[11px] font-semibold text-violet-600 hover:text-violet-700 transition-colors"
                      >
                        + Add tasks via Edit
                      </button>
                      )}
                    </div>
                  )}

                  {!tasksLoading && leadTasks.length > 0 && (
                    <div className="space-y-2">
                      {leadTasks.map((t: any) => {
                        const taskStatusColors: Record<string, { bg: string; text: string; dot: string }> = {
                          todo:        { bg: "bg-slate-100",   text: "text-slate-600",   dot: "bg-slate-400" },
                          in_progress: { bg: "bg-blue-50",     text: "text-blue-600",    dot: "bg-blue-500" },
                          review:      { bg: "bg-violet-50",   text: "text-violet-600",  dot: "bg-violet-500" },
                          done:        { bg: "bg-emerald-50",  text: "text-emerald-600", dot: "bg-emerald-500" },
                        };
                        const taskStatusLabels: Record<string, string> = { todo: "To Do", in_progress: "In Progress", review: "In Review", done: "Done" };
                        const sc = taskStatusColors[t.status] || taskStatusColors.todo;
                        const priorityColors: Record<string, string> = { high: "text-red-500", medium: "text-amber-500", low: "text-emerald-500" };
                        const pc = priorityColors[t.priority] || "text-slate-500";
                        return (
                          <div
                            key={t.id}
                            role="button"
                            tabIndex={0}
                            onClick={() => router.push(`/tasks?task=${t.id}`)}
                            onKeyDown={(e) => { if (e.key === "Enter") router.push(`/tasks?task=${t.id}`); }}
                            title="Open task"
                            className={`border rounded-xl p-3 cursor-pointer transition-all hover:border-indigo-200 hover:shadow-sm hover:bg-indigo-50/30 ${t.status === "done" ? "opacity-60" : ""} bg-white border-slate-100`}
                          >
                            <div className="flex items-start justify-between gap-2 mb-1">
                              <p className={`text-[12px] font-semibold text-slate-800 leading-snug ${t.status === "done" ? "line-through text-slate-400" : ""}`}>{t.title}</p>
                              <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold flex-shrink-0 ${sc.bg} ${sc.text}`}>
                                <span className={`w-1.5 h-1.5 rounded-full ${sc.dot}`} />
                                {taskStatusLabels[t.status] || t.status}
                              </span>
                            </div>
                            <div className="flex items-center gap-3 mt-1">
                              <span className={`flex items-center gap-1 text-[10px] font-semibold ${pc}`}>
                                <I.Flag level={t.priority} />
                                {t.priority.charAt(0).toUpperCase() + t.priority.slice(1)}
                              </span>
                              {t.due_date && (
                                <span className="flex items-center gap-1 text-[10px] text-slate-400">
                                  <I.Clock />
                                  {new Date(t.due_date).toLocaleDateString("en-IN", { day: "2-digit", month: "short" })}
                                  {t.due_time && ` · ${t.due_time.slice(0, 5)}`}
                                </span>
                              )}
                              {t.assignee_details && (
                                <span className="text-[10px] text-slate-400 truncate">
                                  {`${t.assignee_details.first_name || ""} ${t.assignee_details.last_name || ""}`.trim() || t.assignee_details.username}
                                </span>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>

                {/* Call History */}
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <div className="w-5 h-5 rounded-md bg-emerald-100 flex items-center justify-center text-emerald-600">
                        <I.Phone />
                      </div>
                      <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wide">Recent Call Details</span>
                    </div>
                    {!callsLoading && (
                      <span className="text-[10px] font-bold text-slate-400 bg-slate-100 px-2 py-0.5 rounded-full">{leadCalls.length}</span>
                    )}
                  </div>

                  {callsLoading && (
                    <div className="flex items-center justify-center py-4">
                      <div className="w-5 h-5 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
                    </div>
                  )}

                  {!callsLoading && leadCalls.length === 0 && (
                    <div className="border-2 border-dashed border-slate-200 rounded-xl py-4 text-center">
                      <p className="text-[11px] text-slate-400">No calls recorded yet</p>
                    </div>
                  )}

                  {!callsLoading && leadCalls.length > 0 && (
                    <div className="space-y-2">
                      {leadCalls.map((c: any) => {
                        const outcomeColors: Record<string, string> = {
                          connected: "bg-emerald-50 text-emerald-600 border-emerald-100",
                          completed: "bg-emerald-50 text-emerald-600 border-emerald-100",
                          rnr: "bg-orange-50 text-orange-600 border-orange-100",
                          busy: "bg-blue-50 text-blue-600 border-blue-100",
                          rejected: "bg-blue-50 text-blue-600 border-blue-100",
                          failed: "bg-blue-50 text-blue-600 border-blue-100",
                          cancelled: "bg-rose-50 text-rose-600 border-rose-100",
                          canceled: "bg-rose-50 text-rose-600 border-rose-100",
                        };
                        const oc = outcomeColors[c.outcome] || "bg-slate-50 text-slate-600 border-slate-100";
                        const outcomeLabels: Record<string, string> = {
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
                          <div key={c.id} className="border border-slate-100 bg-white rounded-xl p-3">
                            <div className="flex items-center justify-between mb-1.5">
                              <span className={`px-2 py-0.5 rounded-full text-[9px] font-black uppercase tracking-wider border ${oc}`}>
                                {outcomeLabels[c.outcome] || c.outcome}
                              </span>
                              <span className="text-[10px] text-slate-400 tabular-nums">
                                {Math.floor(c.duration_seconds / 60)}:{(c.duration_seconds % 60).toString().padStart(2, '0')}
                              </span>
                            </div>
                            {c.recording_url && (
                              <audio controls className="h-6 w-full scale-90 origin-left" src={getRecordingUrl(c.recording_url, c.id)} />
                            )}
                            <div className="mt-1.5 flex items-center justify-between">
                              <span className="text-[9px] text-slate-400 uppercase font-bold tracking-tight">
                                {new Date(c.created_at).toLocaleDateString("en-IN", { day: '2-digit', month: 'short' })} at {new Date(c.created_at).toLocaleTimeString("en-IN", { hour: '2-digit', minute: '2-digit' })}
                              </span>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>

                {/* ── Attachments ── */}
                <div className="px-5 pb-4 border-t border-slate-100 pt-4">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <div className="w-5 h-5 rounded-md bg-indigo-100 flex items-center justify-center text-indigo-600">
                        <svg width="11" height="11" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48"/></svg>
                      </div>
                      <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wide">Attachments</span>
                    </div>
                    <div className="flex items-center gap-2">
                      {!attachmentsLoading && (
                        <span className="text-[10px] font-bold text-slate-400 bg-slate-100 px-2 py-0.5 rounded-full">{leadAttachments.length}</span>
                      )}
                      <button
                        onClick={() => attachmentFileRef.current?.click()}
                        disabled={attachmentUploading}
                        className="flex items-center gap-1 px-2.5 py-1 bg-indigo-50 text-indigo-600 hover:bg-indigo-100 text-[10px] font-bold rounded-lg transition-colors disabled:opacity-50"
                      >
                        {attachmentUploading ? (
                          <span className="flex items-center gap-1.5"><div className="w-3 h-3 border border-indigo-400 border-t-transparent rounded-full animate-spin" />Uploading…</span>
                        ) : (
                          <><I.Upload />Upload</>
                        )}
                      </button>
                      <input ref={attachmentFileRef} type="file" className="hidden" onChange={handleAttachmentUpload} />
                    </div>
                  </div>

                  {attachmentsLoading && (
                    <div className="flex items-center justify-center py-3">
                      <div className="w-4 h-4 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
                    </div>
                  )}

                  {!attachmentsLoading && leadAttachments.length === 0 && !viewLead.invoice && (
                    <div
                      onClick={() => attachmentFileRef.current?.click()}
                      className="border-2 border-dashed border-slate-200 hover:border-indigo-300 hover:bg-indigo-50/30 rounded-xl py-4 text-center cursor-pointer transition-all group"
                    >
                      <div className="flex justify-center mb-1 text-slate-300 group-hover:text-indigo-400 transition-colors">
                        <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" viewBox="0 0 24 24"><path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48"/></svg>
                      </div>
                      <p className="text-[11px] text-slate-400 group-hover:text-indigo-600 font-medium transition-colors">Click to attach a file</p>
                      <p className="text-[10px] text-slate-300 mt-0.5">Max 50MB · Any file type</p>
                    </div>
                  )}

                  {!attachmentsLoading && (leadAttachments.length > 0 || viewLead.invoice) && (
                    <div className="space-y-1.5 max-h-[180px] overflow-y-auto pr-0.5">
                      {viewLead.invoice && (
                        <div
                          onClick={() => setPreviewFile({ url: viewLead.invoice, name: "Official Invoice" })}
                          className="flex items-center gap-2.5 p-2.5 rounded-xl bg-fuchsia-50 border border-fuchsia-100 hover:bg-fuchsia-100 hover:border-fuchsia-200 transition-all cursor-pointer group"
                        >
                          <div className="w-7 h-7 rounded-lg bg-white border border-fuchsia-200 flex items-center justify-center text-sm flex-shrink-0 shadow-sm">💰</div>
                          <div className="flex-1 min-w-0">
                            <p className="text-[11px] font-semibold text-fuchsia-900 truncate">Official Invoice</p>
                            <p className="text-[10px] text-fuchsia-600">Required for Converted Status</p>
                          </div>
                          {/* Download */}
                          <a
                            href={viewLead.invoice}
                            target="_blank"
                            rel="noreferrer"
                            onClick={e => e.stopPropagation()}
                            className="w-6 h-6 flex items-center justify-center rounded-lg text-fuchsia-400 hover:text-fuchsia-600 hover:bg-fuchsia-200 transition-colors flex-shrink-0"
                            title="Download"
                          >
                            <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                          </a>
                        </div>
                      )}
                      {leadAttachments.map((att: any) => {
                        const ext = (att.file_name || '').split('.').pop()?.toLowerCase() || '';
                        const icon = ['jpg','jpeg','png','gif','webp'].includes(ext) ? '🖼️' : ext === 'pdf' ? '📄' : '📎';
                        return (
                          <div
                            key={att.id}
                            onClick={() => setPreviewFile({ url: att.file_url, name: att.file_name })}
                            className="flex items-center gap-2.5 p-2.5 rounded-xl bg-slate-50 border border-slate-100 hover:bg-indigo-50 hover:border-indigo-100 transition-all cursor-pointer group"
                          >
                            <div className="w-7 h-7 rounded-lg bg-white border border-slate-200 flex items-center justify-center text-sm flex-shrink-0 shadow-sm">{icon}</div>
                            <div className="flex-1 min-w-0">
                              <p className="text-[11px] font-semibold text-slate-700 truncate">{att.file_name}</p>
                              <p className="text-[10px] text-slate-400">{att.file_size_kb} KB · {new Date(att.uploaded_at).toLocaleDateString('en-IN', { day:'2-digit', month:'short' })}</p>
                            </div>
                            {/* Download */}
                            <a
                              href={att.file_url}
                              target="_blank"
                              rel="noreferrer"
                              onClick={e => e.stopPropagation()}
                              className="w-6 h-6 flex items-center justify-center rounded-lg text-slate-300 hover:text-indigo-500 hover:bg-indigo-100 transition-colors flex-shrink-0"
                              title="Download"
                            >
                              <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                            </a>
                            {/* Delete */}
                            <button
                              onClick={e => { e.stopPropagation(); deleteAttachment(att.id, att.file_name); }}
                              className="w-6 h-6 flex items-center justify-center rounded-lg text-slate-300 hover:text-rose-500 hover:bg-rose-50 transition-colors flex-shrink-0"
                              title="Delete attachment"
                            >
                              <svg width="11" height="11" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4a1 1 0 011-1h4a1 1 0 011 1v2"/></svg>
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>

              {/* ── Right: Lead History ── */}
              <div className="flex-1 overflow-y-auto p-5 min-h-0">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm font-bold text-slate-900">Lead History</h3>
                  <span className="text-[10px] font-semibold text-slate-400 bg-slate-100 px-2 py-1 rounded-md">
                    {historyLoading ? "…" : `${leadHistory.length} events`}
                  </span>
                </div>

                {historyLoading && (
                  <div className="flex items-center justify-center py-16">
                    <div className="w-6 h-6 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
                  </div>
                )}

                {!historyLoading && leadHistory.length === 0 && (
                  <div className="flex flex-col items-center py-16 text-slate-300">
                    <svg width="32" height="32" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24" className="mb-2"><circle cx="12" cy="12" r="10" /><path d="M12 6v6l4 2" /></svg>
                    <p className="text-sm">No history yet</p>
                    <p className="text-xs mt-1">Activity will appear here as this lead progresses</p>
                  </div>
                )}

                {/* Timeline */}
                {!historyLoading && leadHistory.length > 0 && (
                  <div className="relative">
                    {/* vertical line */}
                    <div className="absolute left-4 top-2 bottom-2 w-px bg-slate-100" />
                    <div className="space-y-4">
                      {leadHistory.map((log: any, idx: number) => {
                        const typeConfig: Record<string, { icon: React.ReactNode; bg: string; accent: string; label: string }> = {
                          lead_created:        { label: "Lead Created",       bg: "bg-indigo-100", accent: "text-indigo-600",  icon: <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2" /><circle cx="12" cy="7" r="4" /></svg> },
                          lead_status_change:  { label: "Status Changed",     bg: "bg-amber-100",  accent: "text-amber-600",   icon: <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M17 3l4 4-4 4" /><path d="M7 21l-4-4 4-4" /><path d="M21 7H9a4 4 0 000 8h6" /></svg> },
                          note_added:          { label: "Note Added",         bg: "bg-teal-100",   accent: "text-teal-600",    icon: <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" /><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" /></svg> },
                          task_created:        { label: "Task Created",       bg: "bg-violet-100", accent: "text-violet-600",  icon: <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M16 3v4M8 3v4M3 11h18" /></svg> },
                          task_stage_change:   { label: "Task Stage Changed", bg: "bg-sky-100",    accent: "text-sky-600",    icon: <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" /><path d="M12 6v6l4 2" /></svg> },
                          task_completed:      { label: "Task Completed",     bg: "bg-emerald-100",accent: "text-emerald-600",icon: <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M9 11l3 3 8-8" /><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" /></svg> },
                          meta_import:         { label: "Meta Import",        bg: "bg-violet-100", accent: "text-violet-600",  icon: <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" viewBox="0 0 24 24"><rect x="5" y="2" width="14" height="20" rx="2" /></svg> },
                        };
                        const cfg = typeConfig[log.type] || { label: log.type, bg: "bg-slate-100", accent: "text-slate-500", icon: <I.Clock /> };
                        const ts = new Date(log.timestamp);
                        const dateStr = ts.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
                        const timeStr = ts.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: true });
                        const oldStatus = log.extra?.old_status;
                        const newStatus = log.extra?.new_status;
                        return (
                          <div key={log.id} className="flex gap-4 relative">
                            {/* dot */}
                            <div className={`w-8 h-8 rounded-xl ${cfg.bg} ${cfg.accent} flex items-center justify-center flex-shrink-0 z-10 mt-0.5`}>
                              {cfg.icon}
                            </div>
                            {/* card */}
                            <div className="flex-1 bg-slate-50 rounded-xl p-3.5 border border-slate-100">
                              <div className="flex items-start justify-between gap-2 mb-1.5">
                                <span className={`text-[10px] font-bold uppercase tracking-widest ${cfg.accent}`}>{cfg.label}</span>
                                <span className="text-[10px] text-slate-400 flex-shrink-0">{dateStr}</span>
                              </div>
                              <p className="text-[13px] text-slate-700 font-medium leading-snug">{log.description}</p>
                              {/* Note content block */}
                              {log.extra?.note && (
                                <div className="mt-2 bg-teal-50 border border-teal-100 rounded-lg px-3 py-2">
                                  <p className="text-[12px] text-slate-700 leading-relaxed whitespace-pre-wrap">{log.extra.note}</p>
                                </div>
                              )}
                              {oldStatus && newStatus && (
                                <div className="flex items-center gap-2 mt-2">
                                  <StatusBadge status={oldStatus} meta={statusMeta} />
                                  <svg width="12" height="12" fill="none" stroke="#94a3b8" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M5 12h14M12 5l7 7-7 7" /></svg>
                                  <StatusBadge status={newStatus} meta={statusMeta} />
                                </div>
                              )}
                              <div className="flex items-center gap-1.5 mt-2">
                                {log.actor && (
                                  <span className="text-[10px] font-semibold text-slate-500">{log.actor}</span>
                                )}
                                {log.actor && <span className="text-slate-300">·</span>}
                                <span className="text-[10px] text-slate-400">{timeStr}</span>
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Bulk Assign Modal ─────────────────────────────────────────────────── */}
      {showBulkAssign && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
          onClick={() => setShowBulkAssign(false)}>
          <div className="bg-white w-full max-w-sm mx-4 rounded-2xl shadow-2xl overflow-hidden"
            onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
              <div>
                <h2 className="text-[15px] font-bold text-slate-900">Assign Leads</h2>
                <p className="text-xs text-slate-400 mt-0.5">{selectedIds.length} lead{selectedIds.length !== 1 ? "s" : ""} selected</p>
              </div>
              <button onClick={() => setShowBulkAssign(false)}
                className="w-8 h-8 flex items-center justify-center rounded-xl bg-slate-100 text-slate-500 hover:bg-slate-200 transition-all">
                <I.X />
              </button>
            </div>
            <div className="p-2 max-h-[300px] overflow-y-auto">
              {teamMembers.map(m => (
                <button key={m.id} onClick={() => bulkAssign(m.id)}
                  className="w-full flex items-center gap-3 px-4 py-2.5 rounded-xl hover:bg-indigo-50 transition-colors text-left group">
                  <div className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-xs font-bold text-white flex-shrink-0">
                    {m.name.charAt(0).toUpperCase()}
                  </div>
                  <span className="text-sm font-medium text-slate-700 group-hover:text-indigo-700 transition-colors">{m.name}</span>
                </button>
              ))}
            </div>
            <div className="px-5 py-4 border-t border-slate-100">
              <button onClick={() => setShowBulkAssign(false)}
                className="w-full py-2.5 border border-slate-200 rounded-xl text-sm font-semibold text-slate-600 hover:bg-slate-50 transition-all">
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Bulk Update Modal ─────────────────────────────────────────────────── */}
      {showBulkUpdate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
          onClick={() => setShowBulkUpdate(false)}>
          <div className="bg-white w-full max-w-sm mx-4 rounded-2xl shadow-2xl overflow-hidden"
            onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
              <div>
                <h2 className="text-[15px] font-bold text-slate-900">Bulk Update Leads</h2>
                <p className="text-xs text-slate-400 mt-0.5">{selectedIds.length} lead{selectedIds.length !== 1 ? "s" : ""} selected</p>
              </div>
              <button onClick={() => setShowBulkUpdate(false)}
                className="w-8 h-8 flex items-center justify-center rounded-xl bg-slate-100 text-slate-500 hover:bg-slate-200 transition-all">
                <I.X />
              </button>
            </div>
            <div className="p-5 space-y-4">
              {/* Status is hidden for BDEs — they can still bulk-update the other fields. */}
              {canEditStatus && (
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1.5">Status</label>
                <select value={bulkUpdateStatus} onChange={e => setBulkUpdateStatus(e.target.value)} className="w-full bg-white border border-slate-200 rounded-xl px-3 py-2 text-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none transition-all text-slate-700">
                  <option value="">-- No Change --</option>
                  <option value="new">New</option>
                  <option value="follow_up">Follow Up</option>
                  <option value="positive">Positive</option>
                  <option value="interested">Interested</option>
                  <option value="not_interested">Not Interested</option>
                  <option value="converted">Converted</option>
                </select>
              </div>
              )}
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1.5">Source</label>
                <select value={bulkUpdateSource} onChange={e => setBulkUpdateSource(e.target.value)} className="w-full bg-white border border-slate-200 rounded-xl px-3 py-2 text-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none transition-all text-slate-700">
                  <option value="">-- No Change --</option>
                  <option value="manual">Manual</option>
                  <option value="website">Website</option>
                  <option value="referral">Referral</option>
                  <option value="facebook">Facebook Ads</option>
                  <option value="google">Google Ads</option>
                </select>
              </div>
              {/* Routing leads isn't open to everyone — same rule as the Assign
                  action in the selection bar. */}
              {canAssign && (
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1.5">Assignee</label>
                <select value={bulkUpdateAssignee} onChange={e => setBulkUpdateAssignee(e.target.value)} className="w-full bg-white border border-slate-200 rounded-xl px-3 py-2 text-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none transition-all text-slate-700">
                  <option value="">-- No Change --</option>
                  {teamMembers.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
                </select>
              </div>
              )}
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1.5">Product</label>
                <select value={bulkUpdateProduct} onChange={e => setBulkUpdateProduct(e.target.value)} className="w-full bg-white border border-slate-200 rounded-xl px-3 py-2 text-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none transition-all text-slate-700">
                  <option value="">-- No Change --</option>
                  {productsList.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1.5">Campaign</label>
                <select value={bulkUpdateCampaign} onChange={e => setBulkUpdateCampaign(e.target.value)} className="w-full bg-white border border-slate-200 rounded-xl px-3 py-2 text-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none transition-all text-slate-700">
                  <option value="">-- No Change --</option>
                  {campaignsList.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </div>
            </div>
            <div className="px-5 py-4 border-t border-slate-100 flex gap-3">
              <button onClick={() => setShowBulkUpdate(false)}
                className="flex-1 py-2.5 border border-slate-200 rounded-xl text-sm font-semibold text-slate-600 hover:bg-slate-50 transition-all">
                Cancel
              </button>
              <button onClick={bulkUpdate}
                className="flex-1 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-sm font-semibold transition-all">
                Update
              </button>
            </div>
          </div>
        </div>
      )}

      {/* File Preview Modal */}
      {previewFile && (
        <div className="fixed inset-0 z-[100] flex flex-col bg-black/90 backdrop-blur-md transition-all">
          <div className="flex items-center justify-between px-6 py-4 bg-gradient-to-b from-black/50 to-transparent">
            <h3 className="text-white font-semibold text-sm truncate max-w-[80%]">{previewFile.name}</h3>
            <div className="flex items-center gap-3">
              <a href={previewFile.url} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()} className="px-3 py-1.5 bg-white/10 hover:bg-white/20 text-white rounded-lg text-xs font-semibold flex items-center gap-2 transition-colors">
                <I.Download /> Download
              </a>
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
                <a href={previewFile.url} target="_blank" rel="noreferrer" className="inline-flex px-6 py-2.5 bg-indigo-600 hover:bg-indigo-500 rounded-xl font-bold transition-colors shadow-lg shadow-indigo-500/20">
                  Download File
                </a>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Owners ────────────────────────────────────────────────────────────────
 * A lead starts with one owner, the tele caller. Handing it to a BDE doesn't
 * transfer it — ownership becomes shared, so both are listed with their role.
 * Falls back to whoever the lead is assigned to when neither role is recorded
 * (e.g. a lead sitting with an admin).
 */
function Owners({ lead }: { lead: any }) {
  const people: { name: string; role: string; tint: string }[] = [];
  if (lead.tele_caller_name) {
    people.push({ name: lead.tele_caller_name, role: "Tele Caller", tint: "from-indigo-500 to-violet-600" });
  }
  if (lead.bde_name) {
    people.push({ name: lead.bde_name, role: "BDE", tint: "from-amber-500 to-orange-600" });
  }
  if (people.length === 0 && lead.assigned_to_name) {
    people.push({ name: lead.assigned_to_name, role: "Owner", tint: "from-indigo-500 to-violet-600" });
  }

  if (people.length === 0) {
    return <span className="text-[11px] text-slate-300 italic">Unassigned</span>;
  }

  return (
    <div className="flex flex-col gap-1.5">
      {people.map(p => (
        <div key={p.role} className="flex items-center gap-2" title={`${p.name} · ${p.role}`}>
          <div className={`w-6 h-6 rounded-full bg-gradient-to-br ${p.tint} text-white flex items-center justify-center text-[9px] font-bold flex-shrink-0`}>
            {p.name.charAt(0).toUpperCase()}
          </div>
          <div className="min-w-0 leading-tight">
            <p className="text-[11px] font-medium text-slate-600 truncate max-w-[90px]">{p.name}</p>
            <p className="text-[9px] uppercase tracking-wider text-slate-400">{p.role}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

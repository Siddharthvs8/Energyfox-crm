"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";

import React, { useState, useEffect, useCallback } from "react";

// ─── SVG Icons ────────────────────────────────────────────────────────────────
const Icons = {
  Brain: () => (
    <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" viewBox="0 0 24 24">
      <path d="M12 2a7 7 0 017 7c0 2.38-1.19 4.47-3 5.74V17a3 3 0 01-3 3h-2a3 3 0 01-3-3v-2.26C6.19 13.47 5 11.38 5 9a7 7 0 017-7z" />
      <path d="M9 21v1M15 21v1M12 2v3M8.5 7.5L6 6M15.5 7.5L18 6" />
    </svg>
  ),
  Target: () => (
    <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" viewBox="0 0 24 24">
      <circle cx="12" cy="12" r="10" /><circle cx="12" cy="12" r="6" /><circle cx="12" cy="12" r="2" />
    </svg>
  ),
  Calendar: () => (
    <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" viewBox="0 0 24 24">
      <rect x="3" y="4" width="18" height="18" rx="2" /><path d="M16 2v4M8 2v4M3 10h18" />
    </svg>
  ),
  Users: () => (
    <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" viewBox="0 0 24 24">
      <path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" /><circle cx="9" cy="7" r="4" />
      <path d="M23 21v-2a4 4 0 00-3-3.87" /><path d="M16 3.13a4 4 0 010 7.75" />
    </svg>
  ),
  Clock: () => (
    <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" viewBox="0 0 24 24">
      <circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" />
    </svg>
  ),
  Settings: () => (
    <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" viewBox="0 0 24 24">
      <circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 01-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z" />
    </svg>
  ),
  Plus: () => (
    <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" viewBox="0 0 24 24">
      <path d="M12 5v14M5 12h14" />
    </svg>
  ),
  Alert: () => <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>,
  CheckCircle: () => <svg width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><path d="M22 4L12 14.01l-3-3"/></svg>,
  Edit: () => (
    <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24">
      <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/>
    </svg>
  ),
  Close: () => (
    <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" viewBox="0 0 24 24">
      <path d="M18 6L6 18M6 6l12 12" />
    </svg>
  ),
  Refresh: () => (
    <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24">
      <polyline points="23 4 23 10 17 10" /><path d="M20.49 15a9 9 0 11-2.12-9.36L23 10" />
    </svg>
  ),
  Bell: () => (
    <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" viewBox="0 0 24 24">
      <path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.73 21a2 2 0 01-3.46 0" />
    </svg>
  ),
  Trash: () => (
    <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" viewBox="0 0 24 24">
      <polyline points="3 6 5 6 21 6" /><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6" />
      <path d="M10 11v6M14 11v6M9 6V4a1 1 0 011-1h4a1 1 0 011 1v2" />
    </svg>
  ),
  Zap: () => (
    <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24">
      <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
    </svg>
  ),
  Check: () => (
    <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" viewBox="0 0 24 24">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  ),
  TrendUp: () => (
    <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24">
      <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" /><polyline points="16 7 22 7 22 13" />
    </svg>
  ),
  Sparkle: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
      <path d="M12 3l1.912 5.813a2 2 0 001.275 1.275L21 12l-5.813 1.912a2 2 0 00-1.275 1.275L12 21l-1.912-5.813a2 2 0 00-1.275-1.275L3 12l5.813-1.912a2 2 0 001.275-1.275L12 3z" />
    </svg>
  ),
};

// ─── Circular Progress Ring ───────────────────────────────────────────────────
function ProgressRing({ pct, size = 60, stroke = 5, color = "#6366f1" }: { pct: number; size?: number; stroke?: number; color?: string }) {
  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ - (Math.min(pct, 100) / 100) * circ;
  return (
    <svg width={size} height={size} className="transform -rotate-90">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#f1f5f9" strokeWidth={stroke} />
      <circle
        cx={size / 2} cy={size / 2} r={r} fill="none"
        stroke={color} strokeWidth={stroke}
        strokeDasharray={circ} strokeDashoffset={offset}
        strokeLinecap="round"
        className="transition-all duration-700"
      />
    </svg>
  );
}

// ─── Modal Wrapper ────────────────────────────────────────────────────────────
function Modal({ open, onClose, title, children, width = "max-w-lg" }: any) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className={`bg-white w-full ${width} sm:mx-4 rounded-t-2xl sm:rounded-2xl shadow-2xl max-h-[90vh] flex flex-col overflow-hidden`} onClick={(e: React.MouseEvent) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 flex-shrink-0">
          <h2 className="text-base font-bold text-slate-900">{title}</h2>
          <button onClick={onClose} className="w-8 h-8 flex items-center justify-center rounded-xl bg-slate-100 text-slate-500 hover:bg-slate-200 transition-all">
            <Icons.Close />
          </button>
        </div>
        <div className="overflow-y-auto flex-1 px-6 py-5">{children}</div>
      </div>
    </div>
  );
}

// ─── Month Selector ───────────────────────────────────────────────────────────
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export default function TeamPerformancePage({ params: paramsPromise }: { params: Promise<{ domain: string }> }) {
  const params = React.use(paramsPromise);
  const domain = APP_SLUG;

  const now = new Date();
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [year, setYear] = useState(now.getFullYear());
  const [loading, setLoading] = useState(true);
  const [dashboard, setDashboard] = useState<any>(null);
  const [users, setUsers] = useState<any[]>([]);

  // Modals
  const [showTargetModal, setShowTargetModal] = useState(false);
  const [showHolidayModal, setShowHolidayModal] = useState(false);
  const [showMeetingModal, setShowMeetingModal] = useState(false);
  const [showDailyModal, setShowDailyModal] = useState(false);
  const [showCustomReminderModal, setShowCustomReminderModal] = useState(false);

  // Daily target local state
  const [selectedAgentId, setSelectedAgentId] = useState<number | null>(null);
  const [dailyTargets, setDailyTargets] = useState<any[]>([]);

  // Target form
  const [targetForm, setTargetForm] = useState({ agent: "", target_leads: "", target_amount: "" });
  const [existingTargets, setExistingTargets] = useState<any[]>([]);

  // Holiday form
  const [holidayForm, setHolidayForm] = useState({ date: "", name: "" });

  // Meeting form
  const [meetingForm, setMeetingForm] = useState({ title: "", description: "", scheduled_at: "", duration_minutes: "30", attendees: [] as number[] });

  // Custom Reminder form
  const [customReminderForm, setCustomReminderForm] = useState({ agent_id: "all", title: "", message: "" });

  const token = typeof window !== "undefined" ? localStorage.getItem(`${domain}_access`) : null;
  const api = useCallback((url: string, opts?: any) =>
    fetch(`${getApiBase(domain)}${url}`, {
      ...opts,
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json", ...(opts?.headers || {}) },
    }), [domain, token]);

  // ─── Fetch Dashboard ────────────────────────────────────────────────────────
  const fetchDashboard = useCallback(async () => {
    setLoading(true);
    try {
      const [dashR, usersR, targetsR] = await Promise.all([
        api(`/api/ai-manager/team-performance/?month=${month}&year=${year}`),
        api(`/api/users/`),
        api(`/api/ai-manager/monthly-targets/?month=${month}&year=${year}`),
      ]);
      // /api/users/ and the target list are paginated for larger workspaces —
      // unwrap `results` so the arrays below never get an object.
      const asArray = (d: any) => (Array.isArray(d) ? d : d?.results || []);
      if (dashR.ok) setDashboard(await dashR.json());
      if (usersR.ok) setUsers(asArray(await usersR.json()));
      if (targetsR.ok) setExistingTargets(asArray(await targetsR.json()));
    } catch (e) { console.error(e); }
    setLoading(false);
  }, [api, month, year]);

  useEffect(() => { fetchDashboard(); }, [fetchDashboard]);

  // ─── Realtime refresh ─────────────────────────────────────────────────────────
  // Silently refresh agent progress (connected-call count & call duration) every 15s
  // without flashing the loading spinner.
  const refreshDashboardSilent = useCallback(async () => {
    try {
      const r = await api(`/api/ai-manager/team-performance/?month=${month}&year=${year}`);
      if (r.ok) setDashboard(await r.json());
    } catch {}
  }, [api, month, year]);

  useEffect(() => {
    const id = setInterval(refreshDashboardSilent, 15000);
    return () => clearInterval(id);
  }, [refreshDashboardSilent]);

  // ─── Actions ────────────────────────────────────────────────────────────────
  const saveTarget = async () => {
    if (!targetForm.agent) return;
    // Check if target already exists for this agent/month/year
    const existing = existingTargets.find((t: any) => t.agent == targetForm.agent);
    if (existing) {
      await api(`/api/ai-manager/monthly-targets/${existing.id}/`, {
        method: "PATCH",
        body: JSON.stringify({
          target_leads: parseInt(targetForm.target_leads) || 0,
          target_amount: parseFloat(targetForm.target_amount) || 0,
        }),
      });
    } else {
      await api(`/api/ai-manager/monthly-targets/`, {
        method: "POST",
        body: JSON.stringify({
          agent: parseInt(targetForm.agent),
          month, year,
          target_leads: parseInt(targetForm.target_leads) || 0,
          target_amount: parseFloat(targetForm.target_amount) || 0,
        }),
      });
    }
    setTargetForm({ agent: "", target_leads: "", target_amount: "" });
    fetchDashboard();
  };

  const deleteTarget = async (id: number) => {
    await api(`/api/ai-manager/monthly-targets/${id}/`, { method: "DELETE" });
    fetchDashboard();
  };

  const saveHoliday = async () => {
    if (!holidayForm.date || !holidayForm.name) return;
    await api(`/api/ai-manager/holidays/`, {
      method: "POST",
      body: JSON.stringify(holidayForm),
    });
    setHolidayForm({ date: "", name: "" });
    fetchDashboard();
  };

  const deleteHoliday = async (id: number) => {
    await api(`/api/ai-manager/holidays/${id}/`, { method: "DELETE" });
    fetchDashboard();
  };

  const toggleHoliday = async (day: number) => {
    const dStr = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    const existing = holidays.find((h: any) => h.date === dStr);
    
    if (existing) {
      await api(`/api/ai-manager/holidays/${existing.id}/`, { method: "DELETE" });
    } else {
      let name = prompt("Holiday Name:", "Holiday");
      if (name === null) return;
      if (!name) name = "Holiday";
      await api(`/api/ai-manager/holidays/`, { method: "POST", body: JSON.stringify({ date: dStr, name }) });
    }
    fetchDashboard();
  };

  const openDailyTargets = async (agentId: number) => {
    setSelectedAgentId(agentId);
    setShowDailyModal(true);
    const lastDay = new Date(year, month, 0).getDate();
    const dStrStart = `${year}-${String(month).padStart(2, '0')}-01`;
    const dStrEnd = `${year}-${String(month).padStart(2, '0')}-${String(lastDay).padStart(2, '0')}`;
    const r = await api(`/api/ai-manager/daily-targets/?agent=${agentId}&date_from=${dStrStart}&date_to=${dStrEnd}`);
    if (r.ok) { const d = await r.json(); setDailyTargets(Array.isArray(d) ? d : d?.results || []); }
  };

  const updateDailyTarget = async (id: number, target_leads: string, target_amount: string) => {
    await api(`/api/ai-manager/daily-targets/${id}/`, {
      method: "PATCH",
      body: JSON.stringify({ target_leads: parseInt(target_leads) || 0, target_amount: parseFloat(target_amount) || 0 })
    });
    if (selectedAgentId) {
      const lastDay = new Date(year, month, 0).getDate();
      const dStrStart = `${year}-${String(month).padStart(2, '0')}-01`;
      const dStrEnd = `${year}-${String(month).padStart(2, '0')}-${String(lastDay).padStart(2, '0')}`;
      const r = await api(`/api/ai-manager/daily-targets/?agent=${selectedAgentId}&date_from=${dStrStart}&date_to=${dStrEnd}`);
      if (r.ok) { const d = await r.json(); setDailyTargets(Array.isArray(d) ? d : d?.results || []); }
    }
    fetchDashboard();
  };

  const saveMeeting = async () => {
    if (!meetingForm.title || !meetingForm.scheduled_at) return;
    await api(`/api/ai-manager/meetings/`, {
      method: "POST",
      body: JSON.stringify({
        ...meetingForm,
        duration_minutes: parseInt(meetingForm.duration_minutes) || 30,
      }),
    });
    setMeetingForm({ title: "", description: "", scheduled_at: "", duration_minutes: "30", attendees: [] });
    setShowMeetingModal(false);
    fetchDashboard();
  };

  const sendCustomReminder = async () => {
    if (!customReminderForm.message) return;
    await api(`/api/ai-manager/custom-reminders/`, {
      method: "POST",
      body: JSON.stringify(customReminderForm),
    });
    setCustomReminderForm({ agent_id: "all", title: "", message: "" });
    setShowCustomReminderModal(false);
  };

  const triggerReminders = async (type: string) => {
    await api(`/api/ai-manager/generate-reminders/`, {
      method: "POST",
      body: JSON.stringify({ type, month, year }),
    });
    fetchDashboard();
  };

  // ─── Helpers ────────────────────────────────────────────────────────────────
  const getStatusColor = (pct: number) => {
    if (pct >= 80) return { text: "text-emerald-600", bg: "bg-emerald-50", ring: "#10b981", label: "On Track" };
    if (pct >= 40) return { text: "text-amber-600", bg: "bg-amber-50", ring: "#f59e0b", label: "In Progress" };
    return { text: "text-rose-600", bg: "bg-rose-50", ring: "#f43f5e", label: "Behind" };
  };

  const prevMonth = () => {
    if (month === 1) { setMonth(12); setYear(y => y - 1); }
    else setMonth(m => m - 1);
  };
  const nextMonth = () => {
    if (month === 12) { setMonth(1); setYear(y => y + 1); }
    else setMonth(m => m + 1);
  };

  // ─── Loading ────────────────────────────────────────────────────────────────
  if (loading) return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="text-center">
        <div className="w-10 h-10 border-2 border-violet-600 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
        <p className="text-sm text-slate-400">Loading Team Performance...</p>
      </div>
    </div>
  );

  const summary = dashboard?.summary || {};
  const agents = dashboard?.agents || [];
  const meetings = dashboard?.meetings || [];
  const holidays = dashboard?.holidays || [];
  const config = dashboard?.config || {};

  // Overall progress
  const overallLeadsPct = summary.total_target_leads > 0
    ? Math.round((summary.actual_enrolled / summary.total_target_leads) * 100) : 0;
  const overallAmtPct = summary.total_target_amount > 0
    ? Math.round((summary.actual_revenue / summary.total_target_amount) * 100) : 0;

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-[1400px]" style={{ fontFamily: "'Inter', sans-serif" }}>
      {/* ── Header ── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
        <div className="flex items-center gap-3">
          <div className="w-11 h-11 rounded-2xl bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center shadow-lg shadow-violet-500/30">
            <Icons.Users />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
              Team Performance
            </h1>
            <p className="text-sm text-slate-500">Oversee your team's leads, targets, and scheduled meetings.</p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button onClick={() => setShowCustomReminderModal(true)} className="flex items-center gap-1.5 px-3 py-2 bg-rose-50 text-rose-600 border border-rose-200 rounded-xl text-xs font-semibold hover:bg-rose-100 transition-all">
            <Icons.Alert /> Custom Alert
          </button>
          <button onClick={() => triggerReminders('daily')} className="flex items-center gap-1.5 px-3 py-2 bg-white border border-slate-200 rounded-xl text-xs font-semibold text-slate-700 hover:bg-slate-50 transition-all">
            <Icons.Bell /> Send Reminders
          </button>
        </div>
      </div>

      {/* ── Month Selector ── */}
      <div className="flex items-center gap-3 mb-6">
        <button onClick={prevMonth} className="w-8 h-8 flex items-center justify-center rounded-xl bg-white border border-slate-200 text-slate-600 hover:bg-slate-50 text-sm font-bold">←</button>
        <span className="text-sm font-bold text-slate-800 min-w-[120px] text-center">{MONTHS[month - 1]} {year}</span>
        <button onClick={nextMonth} className="w-8 h-8 flex items-center justify-center rounded-xl bg-white border border-slate-200 text-slate-600 hover:bg-slate-50 text-sm font-bold">→</button>
      </div>

      {/* ── Overview Cards ── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <div className="bg-white border border-slate-100 rounded-2xl p-5 shadow-sm">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-9 h-9 rounded-xl bg-violet-50 flex items-center justify-center text-violet-600"><Icons.Users /></div>
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Active Agents</span>
          </div>
          <p className="text-2xl font-bold text-slate-900">{summary.total_agents || 0}</p>
        </div>
        <div className="bg-white border border-slate-100 rounded-2xl p-5 shadow-sm">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-9 h-9 rounded-xl bg-indigo-50 flex items-center justify-center text-indigo-600"><Icons.Target /></div>
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Target Leads</span>
          </div>
          <p className="text-2xl font-bold text-slate-900">{summary.actual_enrolled || 0} <span className="text-sm text-slate-400 font-medium">/ {summary.total_target_leads || 0}</span></p>
          <div className="w-full h-1.5 bg-slate-100 rounded-full mt-2 overflow-hidden">
            <div className="h-full bg-indigo-500 rounded-full transition-all duration-700" style={{ width: `${Math.min(overallLeadsPct, 100)}%` }} />
          </div>
        </div>
        <div className="bg-white border border-slate-100 rounded-2xl p-5 shadow-sm">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-9 h-9 rounded-xl bg-emerald-50 flex items-center justify-center text-emerald-600"><Icons.TrendUp /></div>
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Revenue</span>
          </div>
          <p className="text-2xl font-bold text-slate-900">₹{(summary.actual_revenue || 0).toLocaleString("en-IN")}</p>
          <p className="text-xs text-slate-400 mt-0.5">of ₹{(summary.total_target_amount || 0).toLocaleString("en-IN")} target</p>
        </div>
        <div className="bg-white border border-slate-100 rounded-2xl p-5 shadow-sm">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-9 h-9 rounded-xl bg-amber-50 flex items-center justify-center text-amber-600"><Icons.Calendar /></div>
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Meetings</span>
          </div>
          <p className="text-2xl font-bold text-slate-900">{meetings.length}</p>
          <p className="text-xs text-slate-400 mt-0.5">upcoming</p>
        </div>
      </div>

      {/* ── Agent Target Cards ── */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
            Agent Targets &amp; Performance
            <span className="inline-flex items-center gap-1 text-[10px] font-bold text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full" title="Connected calls & duration refresh automatically">
              <span className="relative flex h-1.5 w-1.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500" />
              </span>
              LIVE
            </span>
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">Monitor daily &amp; monthly progress for each agent</p>
        </div>
        <button onClick={() => setShowTargetModal(true)} className="flex items-center gap-1.5 px-3 py-2 bg-violet-600 text-white rounded-xl text-xs font-semibold hover:bg-violet-700 transition-all shadow-sm">
          <Icons.Plus /> Set Targets
        </button>
      </div>

      {agents.length === 0 ? (
        <div className="bg-white border border-slate-100 rounded-2xl p-10 text-center mb-8">
          <div className="w-14 h-14 mx-auto rounded-2xl bg-slate-50 flex items-center justify-center text-slate-300 mb-3"><Icons.Users /></div>
          <p className="text-sm text-slate-400">No agents found. Add team members to start managing.</p>
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
          {agents.map((agent: any) => {
            const dp = agent.daily_progress || {};
            const mp = agent.monthly_progress || {};
            const dailyPct = dp.leads_pct || 0;
            const monthlyPct = mp.leads_pct || 0;
            const statusInfo = getStatusColor(monthlyPct);

            return (
              <div key={agent.id} className="bg-white border border-slate-100 rounded-2xl p-5 shadow-sm hover:shadow-md transition-all group">
                {/* Agent header */}
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center text-white text-xs font-bold flex-shrink-0 ring-2 ring-white shadow">
                      {agent.name.charAt(0).toUpperCase()}
                    </div>
                    <div>
                      <p className="text-sm font-bold text-slate-800">{agent.name}</p>
                      <p className="text-[10px] text-slate-400 font-medium uppercase">{agent.role} · {agent.active_leads} active leads</p>
                    </div>
                  </div>
                  {mp.has_target && (
                    <span className={`text-[10px] font-bold px-2 py-1 rounded-lg ${statusInfo.bg} ${statusInfo.text}`}>
                      {statusInfo.label}
                    </span>
                  )}
                </div>

                {mp.has_target ? (
                  <>
                    {/* Monthly progress */}
                    <div className="flex items-center gap-4 mb-4">
                      <div className="relative flex items-center justify-center flex-shrink-0">
                        <ProgressRing pct={monthlyPct} size={56} stroke={5} color={statusInfo.ring} />
                        <span className="absolute text-xs font-bold text-slate-700">{monthlyPct}%</span>
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between mb-1">
                          <div className="flex items-center gap-1.5">
                            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Monthly</span>
                            <button onClick={() => {
                              const existing = existingTargets.find((t: any) => t.agent == agent.id);
                              if (existing) {
                                setTargetForm({agent: String(existing.agent), target_leads: String(existing.target_leads), target_amount: String(existing.target_amount)});
                              } else {
                                setTargetForm({agent: String(agent.id), target_leads: "", target_amount: ""});
                              }
                              setShowTargetModal(true);
                            }} className="text-slate-300 hover:text-violet-600 transition-colors" title="Edit Monthly Target">
                              <Icons.Edit />
                            </button>
                          </div>
                          <span className="text-xs font-semibold text-slate-600">{mp.actual_leads}/{mp.target_leads} leads</span>
                        </div>
                        <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden">
                          <div className="h-full rounded-full transition-all duration-700" style={{ width: `${Math.min(monthlyPct, 100)}%`, backgroundColor: statusInfo.ring }} />
                        </div>
                        <p className="text-[10px] text-slate-400 mt-1">₹{(mp.actual_amount || 0).toLocaleString("en-IN")} / ₹{(mp.target_amount || 0).toLocaleString("en-IN")}</p>
                      </div>
                    </div>

                    {/* Daily progress */}
                    {dp.has_target && (
                      <div className="bg-slate-50 rounded-xl p-3 relative group cursor-pointer hover:bg-slate-100 transition-colors" onClick={() => openDailyTargets(agent.id)}>
                        <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity">
                          <span className="text-[10px] bg-white px-2 py-1 rounded shadow-sm font-bold text-violet-600 flex items-center gap-1"><Icons.Edit /> View Days</span>
                        </div>
                        <div className="flex items-center justify-between mb-1.5">
                          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Today's Target</span>
                          <span className="text-xs font-semibold text-slate-600">{dp.actual_leads}/{dp.target_leads} leads</span>
                        </div>
                        <div className="w-full h-1.5 bg-white rounded-full overflow-hidden">
                          <div className="h-full bg-indigo-500 rounded-full transition-all duration-500" style={{ width: `${Math.min(dailyPct, 100)}%` }} />
                        </div>
                        <p className="text-[10px] text-slate-400 mt-1">₹{(dp.actual_amount || 0).toLocaleString("en-IN")} / ₹{(dp.target_amount || 0).toLocaleString("en-IN")}</p>

                        {/* Connected calls & duration — live from call logs */}
                        {(dp.target_dialed_calls > 0 || dp.target_call_time > 0) && (
                          <div className="grid grid-cols-2 gap-2 mt-2 pt-2 border-t border-slate-200/70">
                            <div>
                              <div className="flex items-center justify-between mb-0.5">
                                <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider">Calls</span>
                                <span className="text-[10px] font-semibold text-slate-600">{dp.achieved_dialed_calls || 0}/{dp.target_dialed_calls || 0}</span>
                              </div>
                              <div className="w-full h-1.5 bg-white rounded-full overflow-hidden">
                                <div className="h-full bg-indigo-500 rounded-full transition-all duration-500" style={{ width: `${Math.min(dp.dialed_calls_pct || 0, 100)}%` }} />
                              </div>
                            </div>
                            <div>
                              <div className="flex items-center justify-between mb-0.5">
                                <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider">Time</span>
                                <span className="text-[10px] font-semibold text-slate-600">{dp.achieved_call_time || 0}/{dp.target_call_time || 0}m</span>
                              </div>
                              <div className="w-full h-1.5 bg-white rounded-full overflow-hidden">
                                <div className="h-full bg-amber-500 rounded-full transition-all duration-500" style={{ width: `${Math.min(dp.call_time_pct || 0, 100)}%` }} />
                              </div>
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </>
                ) : (
                  <div className="bg-slate-50 rounded-xl p-4 text-center">
                    <p className="text-xs text-slate-400">No target set for {MONTHS[month - 1]} {year}</p>
                    <button onClick={() => { setTargetForm({ agent: String(agent.id), target_leads: "", target_amount: "" }); setShowTargetModal(true); }}
                      className="text-[10px] font-bold text-violet-600 hover:underline mt-1">
                      Set Target →
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* ── Middle Row: Meetings + Holidays ── */}
      <div className="grid lg:grid-cols-2 gap-5 mb-8">
        {/* Meetings */}
        <div className="bg-white border border-slate-100 rounded-2xl shadow-sm overflow-hidden">
          <div className="flex items-center justify-between px-5 py-4 border-b border-slate-50">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-xl bg-blue-50 flex items-center justify-center text-blue-600"><Icons.Clock /></div>
              <h2 className="text-sm font-bold text-slate-900">Upcoming Meetings</h2>
            </div>
            <button onClick={() => setShowMeetingModal(true)} className="flex items-center gap-1 px-2.5 py-1.5 bg-blue-600 text-white rounded-lg text-[10px] font-bold hover:bg-blue-700 transition-all">
              <Icons.Plus /> Schedule
            </button>
          </div>
          <div className="p-4 space-y-3 max-h-[280px] overflow-y-auto">
            {meetings.length === 0 ? (
              <div className="text-center py-8">
                <div className="w-10 h-10 mx-auto rounded-xl bg-slate-50 flex items-center justify-center text-slate-300 mb-2"><Icons.Clock /></div>
                <p className="text-xs text-slate-400">No upcoming meetings</p>
              </div>
            ) : meetings.map((m: any) => {
              const dt = new Date(m.scheduled_at);
              return (
                <div key={m.id} className="flex items-start gap-3 p-3 bg-slate-50 rounded-xl hover:bg-blue-50/50 transition-colors">
                  <div className="w-10 h-10 rounded-xl bg-blue-100 flex flex-col items-center justify-center flex-shrink-0">
                    <span className="text-[8px] font-bold text-blue-600 uppercase leading-none">{dt.toLocaleString('en', { month: 'short' })}</span>
                    <span className="text-sm font-bold text-blue-700 leading-none">{dt.getDate()}</span>
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-slate-800 truncate">{m.title}</p>
                    <p className="text-[10px] text-slate-400">
                      {dt.toLocaleTimeString('en', { hour: '2-digit', minute: '2-digit' })} · {m.duration_minutes}min
                      {m.attendee_names?.length > 0 && ` · ${m.attendee_names.map((a: any) => a.name).join(', ')}`}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Holidays Calendar */}
        <div className="bg-white border border-slate-100 rounded-2xl shadow-sm overflow-hidden flex flex-col">
          <div className="flex items-center px-5 py-4 border-b border-slate-50 gap-2">
            <div className="w-8 h-8 rounded-xl bg-rose-50 flex items-center justify-center text-rose-600"><Icons.Calendar /></div>
            <div>
              <h2 className="text-sm font-bold text-slate-900">Working Days & Holidays</h2>
              <p className="text-[10px] text-slate-400">Click a date to toggle holiday</p>
            </div>
          </div>
          <div className="p-4 bg-slate-50/30 flex-1">
            <div className="grid grid-cols-7 gap-1 text-center mb-2">
              {['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'].map(d => (
                <div key={d} className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">{d}</div>
              ))}
            </div>
            <div className="grid grid-cols-7 gap-1">
              {(Array.from({ length: new Date(year, month - 1, 1).getDay() }, () => null) as (number | null)[]).concat(
                Array.from({ length: new Date(year, month, 0).getDate() }, (_, i) => i + 1)
              ).map((day, i) => {
                if (!day) return <div key={`empty-${i}`} className="p-2" />;
                const dStr = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
                const isHoliday = holidays.find((h: any) => h.date === dStr);
                return (
                  <button
                    key={day}
                    onClick={() => toggleHoliday(day as number)}
                    className={`p-2 rounded-xl text-xs font-bold transition-all hover:scale-105 ${
                      isHoliday 
                        ? "bg-rose-100 text-rose-600 ring-1 ring-rose-200" 
                        : "bg-white text-slate-700 hover:bg-slate-100 ring-1 ring-slate-100 shadow-sm"
                    }`}
                  >
                    {day}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* ══════════════ MODALS ══════════════ */}

      {/* ── Set Monthly Target Modal ── */}
      <Modal open={showTargetModal} onClose={() => setShowTargetModal(false)} title="Set Monthly Targets" width="max-w-2xl">
        <div className="space-y-5">
          {/* Existing targets */}
          {existingTargets.length > 0 && (
            <div>
              <p className="text-xs font-bold text-slate-500 mb-2 uppercase tracking-wider">Current Targets — {MONTHS[month - 1]} {year}</p>
              <div className="border border-slate-100 rounded-xl overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full text-left">
                    <thead className="bg-slate-50">
                      <tr className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">
                        <th className="px-4 py-3">Agent</th>
                        <th className="px-4 py-3 text-right">Leads</th>
                        <th className="px-4 py-3 text-right">Amount</th>
                        <th className="px-4 py-3 text-right">Action</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-50">
                      {existingTargets.map((t: any) => (
                        <tr key={t.id} className="hover:bg-slate-50/50">
                          <td className="px-4 py-3 text-sm font-semibold text-slate-800">{t.agent_name}</td>
                          <td className="px-4 py-3 text-right text-sm text-slate-600">{t.target_leads}</td>
                          <td className="px-4 py-3 text-right text-sm text-slate-600">₹{parseFloat(t.target_amount).toLocaleString("en-IN")}</td>
                          <td className="px-4 py-3 text-right">
                            <button onClick={() => setTargetForm({agent: String(t.agent), target_leads: String(t.target_leads), target_amount: String(t.target_amount)})} className="text-violet-500 hover:text-violet-700 transition-colors mr-3 whitespace-nowrap"><Icons.Edit /></button>
                            <button onClick={() => deleteTarget(t.id)} className="text-rose-400 hover:text-rose-600 transition-colors"><Icons.Trash /></button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* Add/update target form */}
          <div className="bg-violet-50/50 rounded-xl p-4 space-y-3">
            <p className="text-xs font-bold text-violet-700 uppercase tracking-wider">Add / Update Target</p>
            <select
              value={targetForm.agent}
              onChange={e => setTargetForm(f => ({ ...f, agent: e.target.value }))}
              className="w-full px-3 py-2.5 text-sm border border-slate-200 rounded-xl bg-white focus:outline-none focus:ring-2 focus:ring-violet-500/20 focus:border-violet-400"
            >
              <option value="">Select Agent</option>
              {users.filter((u: any) => !u.is_staff).map((u: any) => (
                <option key={u.id} value={u.id}>{u.first_name} {u.last_name} ({u.username})</option>
              ))}
            </select>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1 block">Target Leads</label>
                <input
                  type="number" placeholder="e.g. 30"
                  value={targetForm.target_leads}
                  onChange={e => setTargetForm(f => ({ ...f, target_leads: e.target.value }))}
                  className="w-full px-3 py-2.5 text-sm border border-slate-200 rounded-xl bg-white focus:outline-none focus:ring-2 focus:ring-violet-500/20 focus:border-violet-400"
                />
              </div>
              <div>
                <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1 block">Target Amount (₹)</label>
                <input
                  type="number" placeholder="e.g. 500000"
                  value={targetForm.target_amount}
                  onChange={e => setTargetForm(f => ({ ...f, target_amount: e.target.value }))}
                  className="w-full px-3 py-2.5 text-sm border border-slate-200 rounded-xl bg-white focus:outline-none focus:ring-2 focus:ring-violet-500/20 focus:border-violet-400"
                />
              </div>
            </div>
            <button onClick={saveTarget} className="w-full py-2.5 bg-violet-600 text-white rounded-xl text-sm font-bold hover:bg-violet-700 transition-all shadow-sm">
              Save Target
            </button>
          </div>
        </div>
      </Modal>

      {/* ── Add Holiday Modal ── */}
      <Modal open={showHolidayModal} onClose={() => setShowHolidayModal(false)} title="Add Holiday">
        <div className="space-y-4">
          <div>
            <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1 block">Holiday Name</label>
            <input
              type="text" placeholder="e.g. Diwali"
              value={holidayForm.name}
              onChange={e => setHolidayForm(f => ({ ...f, name: e.target.value }))}
              className="w-full px-3 py-2.5 text-sm border border-slate-200 rounded-xl bg-white focus:outline-none focus:ring-2 focus:ring-rose-500/20 focus:border-rose-400"
            />
          </div>
          <div>
            <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1 block">Date</label>
            <input
              type="date"
              value={holidayForm.date}
              onChange={e => setHolidayForm(f => ({ ...f, date: e.target.value }))}
              className="w-full px-3 py-2.5 text-sm border border-slate-200 rounded-xl bg-white focus:outline-none focus:ring-2 focus:ring-rose-500/20 focus:border-rose-400"
            />
          </div>
          <button onClick={() => { saveHoliday(); setShowHolidayModal(false); }} className="w-full py-2.5 bg-rose-600 text-white rounded-xl text-sm font-bold hover:bg-rose-700 transition-all shadow-sm">
            Add Holiday
          </button>
        </div>
      </Modal>

      {/* ── Daily Targets Modal ── */}
      <Modal open={showDailyModal} onClose={() => setShowDailyModal(false)} title={`Daily Targets — ${MONTHS[month - 1]} ${year}`} width="max-w-4xl">
        <div className="space-y-4">
          <p className="text-xs text-slate-500">Edit individual daily targets manually. Auto-calculations will distribute the remaining monthly target across other days automatically.</p>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 max-h-[60vh] overflow-y-auto pr-2">
            {dailyTargets.map((dt: any) => {
              const dObj = new Date(dt.date);
              const isToday = dObj.toDateString() === new Date().toDateString();
              return (
                <div key={dt.id} className={`p-3 rounded-xl border transition-all ${isToday ? "border-violet-300 bg-violet-50/50" : dt.is_manual ? "border-amber-200 bg-amber-50/30" : "border-slate-100 bg-slate-50"}`}>
                  <div className="flex justify-between items-center mb-2">
                    <span className="text-xs font-bold text-slate-700 flex items-center gap-1.5">
                      {dObj.getDate()} {MONTHS[dObj.getMonth()]}
                      {dt.is_manual && <span className="px-1.5 py-0.5 rounded-md bg-amber-100 text-amber-700 text-[9px] uppercase tracking-wider">Manual</span>}
                    </span>
                    <span className="text-[10px] font-semibold text-slate-400">{dObj.toLocaleDateString('en', { weekday: 'short' })}</span>
                  </div>
                  <div className="space-y-2">
                    <div>
                      <label className="text-[10px] font-bold text-slate-500 mb-0.5 block">Leads</label>
                      <input 
                        type="number" 
                        onBlur={(e) => updateDailyTarget(dt.id, e.target.value, String(dt.target_amount))}
                        defaultValue={dt.target_leads} 
                        className="w-full px-2 py-1.5 text-xs border border-slate-200 rounded-lg bg-white focus:outline-none focus:border-violet-400"
                      />
                    </div>
                    <div>
                      <label className="text-[10px] font-bold text-slate-500 mb-0.5 block">Amount (₹)</label>
                      <input 
                        type="number" 
                        onBlur={(e) => updateDailyTarget(dt.id, String(dt.target_leads), e.target.value)}
                        defaultValue={dt.target_amount} 
                        className="w-full px-2 py-1.5 text-xs border border-slate-200 rounded-lg bg-white focus:outline-none focus:border-violet-400"
                      />
                    </div>
                  </div>
                </div>
              );
            })}
            {dailyTargets.length === 0 && (
              <div className="col-span-full py-10 text-center text-sm text-slate-400">
                No targets generated. Ensure the user has a Target set for this month.
              </div>
            )}
          </div>
        </div>
      </Modal>
  

      {/* ── Schedule Meeting Modal ── */}
      <Modal open={showMeetingModal} onClose={() => setShowMeetingModal(false)} title="Schedule Meeting">
        <div className="space-y-4">
          <div>
            <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1 block">Title</label>
            <input
              type="text" placeholder="Daily standup"
              value={meetingForm.title}
              onChange={e => setMeetingForm(f => ({ ...f, title: e.target.value }))}
              className="w-full px-3 py-2.5 text-sm border border-slate-200 rounded-xl bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-400"
            />
          </div>
          <div>
            <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1 block">Description</label>
            <textarea
              placeholder="Meeting agenda..."
              value={meetingForm.description}
              onChange={e => setMeetingForm(f => ({ ...f, description: e.target.value }))}
              className="w-full px-3 py-2.5 text-sm border border-slate-200 rounded-xl bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-400 h-20 resize-none"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1 block">Date & Time</label>
              <input
                type="datetime-local"
                value={meetingForm.scheduled_at}
                onChange={e => setMeetingForm(f => ({ ...f, scheduled_at: e.target.value }))}
                className="w-full px-3 py-2.5 text-sm border border-slate-200 rounded-xl bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-400"
              />
            </div>
            <div>
              <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1 block">Duration (min)</label>
              <input
                type="number" min="5"
                value={meetingForm.duration_minutes}
                onChange={e => setMeetingForm(f => ({ ...f, duration_minutes: e.target.value }))}
                className="w-full px-3 py-2.5 text-sm border border-slate-200 rounded-xl bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-400"
              />
            </div>
          </div>
          <div>
            <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1 block">Attendees</label>
            <div className="flex flex-wrap gap-2 p-3 border border-slate-200 rounded-xl bg-white max-h-32 overflow-y-auto">
              {users.map((u: any) => {
                const selected = meetingForm.attendees.includes(u.id);
                return (
                  <button key={u.id}
                    onClick={() => setMeetingForm(f => ({
                      ...f,
                      attendees: selected ? f.attendees.filter(id => id !== u.id) : [...f.attendees, u.id]
                    }))}
                    className={`text-xs font-semibold px-2.5 py-1.5 rounded-lg transition-all ${selected ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}
                  >
                    {u.first_name} {u.last_name}
                  </button>
                );
              })}
            </div>
          </div>
          <button onClick={saveMeeting} className="w-full py-2.5 bg-blue-600 text-white rounded-xl text-sm font-bold hover:bg-blue-700 transition-all shadow-sm">
            Schedule Meeting
          </button>
        </div>
      </Modal>

      {/* ── Custom Reminder Modal ── */}
      <Modal open={showCustomReminderModal} onClose={() => setShowCustomReminderModal(false)} title="Send Custom Popup Alert">
        <div className="space-y-4">
          <p className="text-xs text-slate-500">This will instantly trigger a full-screen popup alert on the screen of the selected agent(s).</p>
          <div>
            <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1 block">Audience</label>
            <select
              value={customReminderForm.agent_id}
              onChange={e => setCustomReminderForm(f => ({ ...f, agent_id: e.target.value }))}
              className="w-full px-3 py-2.5 text-sm border border-slate-200 rounded-xl bg-white focus:outline-none focus:ring-2 focus:ring-rose-500/20 focus:border-rose-400"
            >
              <option value="all">All Members</option>
              {users.map((u: any) => {
                const name = (u.first_name || u.last_name) ? `${u.first_name || ''} ${u.last_name || ''}`.trim() : u.username;
                const role = u.is_staff ? 'Admin' : (u.is_manager ? 'Manager' : (u.is_general_manager ? 'Gen. Manager' : 'Agent'));
                return (
                  <option key={u.id} value={u.id}>{name} ({role})</option>
                );
              })}
            </select>
          </div>
          <div>
            <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1 block">Popup Title</label>
            <input
              type="text" placeholder="e.g. Urgent Meeting Setup"
              value={customReminderForm.title}
              onChange={e => setCustomReminderForm(f => ({ ...f, title: e.target.value }))}
              className="w-full px-3 py-2.5 text-sm border border-slate-200 rounded-xl bg-white focus:outline-none focus:ring-2 focus:ring-rose-500/20 focus:border-rose-400"
            />
          </div>
          <div>
            <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1 block">Message</label>
            <textarea
              placeholder="Enter your message here..." rows={3}
              value={customReminderForm.message}
              onChange={e => setCustomReminderForm(f => ({ ...f, message: e.target.value }))}
              className="w-full px-3 py-2.5 text-sm border border-slate-200 rounded-xl bg-white focus:outline-none focus:ring-2 focus:ring-rose-500/20 focus:border-rose-400 resize-none"
            />
          </div>
          <button onClick={sendCustomReminder} className="w-full py-2.5 bg-rose-600 text-white rounded-xl text-sm font-bold hover:bg-rose-700 transition-all shadow-sm">
            Send Alert Now
          </button>
        </div>
      </Modal>
    </div>
  );
}

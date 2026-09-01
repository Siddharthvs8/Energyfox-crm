"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";

import React, { useState, useEffect, useCallback, useRef } from "react";

// ─── SVG Icons ────────────────────────────────────────────────────────────────
const I = {
  Target: () => (
    <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" viewBox="0 0 24 24">
      <circle cx="12" cy="12" r="10" /><circle cx="12" cy="12" r="6" /><circle cx="12" cy="12" r="2" />
    </svg>
  ),
  Doc: () => (
    <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" /><polyline points="14 2 14 8 20 8" />
      <polyline points="9 15 11 17 15 13" />
    </svg>
  ),
  TrendUp: () => (
    <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24">
      <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" /><polyline points="16 7 22 7 22 13" />
    </svg>
  ),
  Users: () => (
    <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" viewBox="0 0 24 24">
      <path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" /><circle cx="9" cy="7" r="4" />
    </svg>
  ),
  Clock: () => (
    <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" viewBox="0 0 24 24">
      <circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" />
    </svg>
  ),
  Zap: () => (
    <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24">
      <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
    </svg>
  ),
  Calendar: () => (
    <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" viewBox="0 0 24 24">
      <rect x="3" y="4" width="18" height="18" rx="2" /><path d="M16 2v4M8 2v4M3 10h18" />
    </svg>
  ),
  Award: () => (
    <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" viewBox="0 0 24 24">
      <circle cx="12" cy="8" r="6" /><path d="M15.477 12.89l1.523 8.11-5-3-5 3 1.523-8.11" />
    </svg>
  ),
  Activity: () => (
    <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24">
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
    </svg>
  ),
  ChevronRight: () => (
    <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24">
      <polyline points="9 18 15 12 9 6" />
    </svg>
  ),
  Phone: () => (
    <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" viewBox="0 0 24 24">
      <path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07A19.5 19.5 0 013.07 10a19.79 19.79 0 01-3-8.57A2 2 0 012.11 0h3a2 2 0 012 1.72c.127.96.361 1.903.7 2.81a2 2 0 01-.45 2.11L6.19 7.84a16 16 0 006 6l1.21-1.21a2 2 0 012.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0122 16.92z" />
    </svg>
  ),
  Upload: () => (
    <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" viewBox="0 0 24 24">
      <polyline points="16 16 12 12 8 16" /><line x1="12" y1="12" x2="12" y2="21" />
      <path d="M20.39 18.39A5 5 0 0018 9h-1.26A8 8 0 103 16.3" />
    </svg>
  ),
  Check: () => (
    <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" viewBox="0 0 24 24">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  ),
  X: () => (
    <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24">
      <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  ),
};

// ─── Circular Progress Ring ───────────────────────────────────────────────────
function Ring({ pct, size = 80, stroke = 6, color = "#6366f1" }: { pct: number; size?: number; stroke?: number; color?: string }) {
  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ - (Math.min(pct, 100) / 100) * circ;
  return (
    <svg width={size} height={size} className="transform -rotate-90">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#f1f5f9" strokeWidth={stroke} />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke}
        strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round" className="transition-all duration-700" />
    </svg>
  );
}

// ─── Status Colors ────────────────────────────────────────────────────────────
const STATUS_COLORS: Record<string, { bg: string; text: string; dot: string }> = {
  new_lead: { bg: "bg-blue-50", text: "text-blue-700", dot: "bg-blue-500" },
  contacted: { bg: "bg-cyan-50", text: "text-cyan-700", dot: "bg-cyan-500" },
  follow_up: { bg: "bg-amber-50", text: "text-amber-700", dot: "bg-amber-500" },
  negotiation: { bg: "bg-orange-50", text: "text-orange-700", dot: "bg-orange-500" },
  site_visit_scheduled: { bg: "bg-purple-50", text: "text-purple-700", dot: "bg-purple-500" },
  site_visit_done: { bg: "bg-violet-50", text: "text-violet-700", dot: "bg-violet-500" },
  proposal_sent: { bg: "bg-indigo-50", text: "text-indigo-700", dot: "bg-indigo-500" },
  converted: { bg: "bg-emerald-50", text: "text-emerald-700", dot: "bg-emerald-500" },
  not_interested: { bg: "bg-slate-100", text: "text-slate-500", dot: "bg-slate-400" },
  disqualified: { bg: "bg-red-50", text: "text-red-600", dot: "bg-red-400" },
};

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export default function MyPerformancePage({ params: paramsPromise }: { params: Promise<{ domain: string }> }) {
  const params = React.use(paramsPromise);
  const domain = APP_SLUG;
  const now = new Date();

  const [month, setMonth] = useState(now.getMonth() + 1);
  const [year, setYear] = useState(now.getFullYear());
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<any>(null);

  // Submit Performance Modal
  const [submitModal, setSubmitModal] = useState<any>(null); // holds the DailyTarget object
  const [submitForm, setSubmitForm] = useState({ achieved_dialed_calls: "", achieved_call_time: "" });
  const [submitFiles, setSubmitFiles] = useState<File[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [submitResult, setSubmitResult] = useState<{ ok: boolean; msg: string } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const token = typeof window !== "undefined" ? localStorage.getItem(`${domain}_access`) : null;
  const api = useCallback((url: string, opts?: any) =>
    fetch(`${getApiBase(domain)}${url}`, {
      ...opts,
      headers: { Authorization: `Bearer ${token}`, ...(opts?.skipContentType ? {} : { 'Content-Type': 'application/json' }), ...(opts?.headers || {}) },
    }), [domain, token]);

  const openSubmitModal = (dt: any) => {
    setSubmitModal(dt);
    setSubmitForm({ achieved_dialed_calls: String(dt.achieved_dialed_calls || ""), achieved_call_time: String(dt.achieved_call_time || "") });
    setSubmitFiles([]);
    setSubmitResult(null);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) setSubmitFiles(prev => [...prev, ...Array.from(e.target.files!)]);
  };

  const removeFile = (idx: number) => setSubmitFiles(f => f.filter((_, i) => i !== idx));

  const deleteProof = async (proofId: number) => {
    if (!window.confirm("Delete this proof file? This can't be undone.")) return;
    try {
      const res = await api(`/api/ai-manager/proofs/${proofId}/`, { method: 'DELETE' });
      if (res.ok || res.status === 204) {
        setSubmitModal((m: any) => (m ? { ...m, proofs: (m.proofs || []).filter((p: any) => p.id !== proofId) } : m));
        fetchData();
      } else { alert("Could not delete the proof."); }
    } catch { alert("Network error while deleting."); }
  };

  const submitPerformance = async () => {
    if (!submitModal) return;
    setSubmitting(true);
    setSubmitResult(null);
    try {
      const fd = new FormData();
      fd.append('date', submitModal.date);
      fd.append('achieved_dialed_calls', submitForm.achieved_dialed_calls || '0');
      fd.append('achieved_call_time', submitForm.achieved_call_time || '0');
      submitFiles.forEach(f => fd.append('proofs', f));
      const res = await fetch(`${getApiBase(domain)}/api/ai-manager/submit-performance/`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: fd,
      });
      if (res.ok) {
        setSubmitResult({ ok: true, msg: 'Performance submitted successfully!' });
        fetchData();
        setTimeout(() => setSubmitModal(null), 1500);
      } else {
        const err = await res.json();
        setSubmitResult({ ok: false, msg: err.error || 'Failed to submit.' });
      }
    } catch { setSubmitResult({ ok: false, msg: 'Network error.' }); }
    setSubmitting(false);
  };

  const fetchData = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const r = await api(`/api/ai-manager/my-performance/?month=${month}&year=${year}`);
      if (r.ok) setData(await r.json());
    } catch (e) { console.error(e); }
    if (!silent) setLoading(false);
  }, [api, month, year]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // Realtime polling — connected-call count & duration progress refresh every 15s
  useEffect(() => {
    const id = setInterval(() => fetchData(true), 15000);
    return () => clearInterval(id);
  }, [fetchData]);

  const prevMonth = () => { if (month === 1) { setMonth(12); setYear(y => y - 1); } else setMonth(m => m - 1); };
  const nextMonth = () => { if (month === 12) { setMonth(1); setYear(y => y + 1); } else setMonth(m => m + 1); };

  if (loading) return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="text-center">
        <div className="w-10 h-10 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
        <p className="text-sm text-slate-400">Loading your performance...</p>
      </div>
    </div>
  );

  if (!data) return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <p className="text-sm text-slate-400">Unable to load performance data.</p>
    </div>
  );

  const u = data.user || {};
  const dp = data.daily_progress || {};
  const mp = data.monthly_progress || {};
  const ls = data.lead_stats || {};
  const meetings = data.meetings || [];
  const monthMeetings = data.month_meetings || [];
  const holidays = data.holidays || [];
  const dailyTargets = data.daily_targets || [];
  const recentLeads = data.recent_leads || [];
  const statusBreakdown = ls.status_breakdown || {};

  const dailyLeadPct = dp.leads_pct || 0;
  const monthlyLeadPct = mp.leads_pct || 0;
  const monthlyAmtPct = mp.amount_pct || 0;

  const getColor = (pct: number) => {
    if (pct >= 80) return { ring: "#10b981", text: "text-emerald-600", bg: "bg-emerald-50", label: "Excellent" };
    if (pct >= 50) return { ring: "#6366f1", text: "text-indigo-600", bg: "bg-indigo-50", label: "Good" };
    if (pct >= 25) return { ring: "#f59e0b", text: "text-amber-600", bg: "bg-amber-50", label: "Needs Push" };
    return { ring: "#f43f5e", text: "text-rose-600", bg: "bg-rose-50", label: "Behind" };
  };

  const monthlyColor = getColor(monthlyLeadPct);

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-[1400px]" style={{ fontFamily: "'Inter', sans-serif" }}>
      {/* ── Header ── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
        <div className="flex items-center gap-4">
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-white text-xl font-bold shadow-lg shadow-indigo-500/25 ring-4 ring-white">
            {u.name?.charAt(0)?.toUpperCase() || "?"}
          </div>
          <div>
            <h1 className="text-2xl font-bold text-slate-900">{u.name || "My Performance"}</h1>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="text-xs font-semibold text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded-full">{u.role}</span>
              <span className="text-xs text-slate-400">@{u.username}</span>
            </div>
          </div>
        </div>
        {/* Month selector */}
        <div className="flex items-center gap-3 bg-white border border-slate-200 rounded-xl px-3 py-2">
          <button onClick={prevMonth} className="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-slate-100 text-slate-500 font-bold text-sm">←</button>
          <span className="text-sm font-bold text-slate-800 min-w-[100px] text-center">{MONTHS[month - 1]} {year}</span>
          <button onClick={nextMonth} className="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-slate-100 text-slate-500 font-bold text-sm">→</button>
        </div>
      </div>

      {/* ── Today's Target Highlight ── */}
      {dp.has_target && (
        <div className="bg-gradient-to-r from-indigo-600 via-violet-600 to-purple-600 rounded-2xl p-6 text-white mb-8 shadow-lg shadow-indigo-600/20 relative overflow-hidden">
          <div className="absolute -right-10 -top-10 w-40 h-40 bg-white/5 rounded-full" />
          <div className="absolute right-20 bottom-0 w-24 h-24 bg-white/5 rounded-full" />
          <div className="relative z-10">
            <div className="flex items-center gap-2 mb-4">
              <I.Zap />
              <span className="text-xs font-bold uppercase tracking-widest opacity-80">Today&apos;s Target</span>
              <span className="text-[10px] bg-white/20 px-2 py-0.5 rounded-full font-semibold">{new Date().toLocaleDateString('en-IN', { weekday: 'long', month: 'short', day: 'numeric' })}</span>
              <span className="ml-auto inline-flex items-center gap-1.5 text-[10px] font-bold bg-white/20 px-2 py-0.5 rounded-full" title="Calls & duration update live as you dial">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-white opacity-75" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-white" />
                </span>
                LIVE
              </span>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
              <div>
                <p className="text-white/60 text-[10px] font-bold uppercase tracking-wider mb-1">Lead Target</p>
                <p className="text-3xl font-bold">{dp.actual_leads}<span className="text-lg text-white/50">/{dp.target_leads}</span></p>
              </div>
              <div>
                <p className="text-white/60 text-[10px] font-bold uppercase tracking-wider mb-1">Revenue Target</p>
                <p className="text-3xl font-bold">₹{(dp.actual_amount || 0).toLocaleString("en-IN")}<span className="text-sm text-white/50"> / ₹{(dp.target_amount || 0).toLocaleString("en-IN")}</span></p>
              </div>
              <div>
                <p className="text-white/60 text-[10px] font-bold uppercase tracking-wider mb-1">Lead Progress</p>
                <div className="flex items-center gap-3">
                  <div className="flex-1 h-2.5 bg-white/15 rounded-full overflow-hidden">
                    <div className="h-full bg-white rounded-full transition-all duration-700" style={{ width: `${Math.min(dailyLeadPct, 100)}%` }} />
                  </div>
                  <span className="text-sm font-bold">{dailyLeadPct}%</span>
                </div>
              </div>
              <div>
                <p className="text-white/60 text-[10px] font-bold uppercase tracking-wider mb-1">Revenue Progress</p>
                <div className="flex items-center gap-3">
                  <div className="flex-1 h-2.5 bg-white/15 rounded-full overflow-hidden">
                    <div className="h-full bg-emerald-400 rounded-full transition-all duration-700" style={{ width: `${Math.min(dp.amount_pct || 0, 100)}%` }} />
                  </div>
                  <span className="text-sm font-bold">{dp.amount_pct || 0}%</span>
                </div>
              </div>
            </div>

            {/* Calls & duration — live from connected calls */}
            {(dp.target_dialed_calls > 0 || dp.target_call_time > 0) && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 mt-6 pt-6 border-t border-white/15">
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <p className="text-white/60 text-[10px] font-bold uppercase tracking-wider flex items-center gap-1.5"><I.Phone /> Connected Calls</p>
                    <span className="text-sm font-bold">{dp.dialed_calls_pct || 0}%</span>
                  </div>
                  <p className="text-2xl font-bold mb-2">{dp.achieved_dialed_calls || 0}<span className="text-lg text-white/50">/{dp.target_dialed_calls || 0}</span></p>
                  <div className="h-2.5 bg-white/15 rounded-full overflow-hidden">
                    <div className="h-full bg-white rounded-full transition-all duration-700" style={{ width: `${Math.min(dp.dialed_calls_pct || 0, 100)}%` }} />
                  </div>
                </div>
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <p className="text-white/60 text-[10px] font-bold uppercase tracking-wider flex items-center gap-1.5"><I.Clock /> Call Duration</p>
                    <span className="text-sm font-bold">{dp.call_time_pct || 0}%</span>
                  </div>
                  <p className="text-2xl font-bold mb-2">{dp.achieved_call_time || 0}<span className="text-lg text-white/50">/{dp.target_call_time || 0} min</span></p>
                  <div className="h-2.5 bg-white/15 rounded-full overflow-hidden">
                    <div className="h-full bg-amber-300 rounded-full transition-all duration-700" style={{ width: `${Math.min(dp.call_time_pct || 0, 100)}%` }} />
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Stats Row ── */}
      <div className="grid grid-cols-2 lg:grid-cols-6 gap-4 mb-8">
        <div className="bg-white border border-slate-100 rounded-2xl p-5 shadow-sm">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-8 h-8 rounded-xl bg-blue-50 flex items-center justify-center text-blue-600"><I.Users /></div>
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Total Leads</span>
          </div>
          <p className="text-2xl font-bold text-slate-900">{ls.total_leads || 0}</p>
          <p className="text-[10px] text-slate-400 mt-0.5">{ls.active_leads || 0} active</p>
        </div>
        <div className="bg-white border border-slate-100 rounded-2xl p-5 shadow-sm">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-8 h-8 rounded-xl bg-emerald-50 flex items-center justify-center text-emerald-600"><I.Award /></div>
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Won This Month</span>
          </div>
          <p className="text-2xl font-bold text-slate-900">{ls.enrolled_this_month || 0}</p>
          <p className="text-[10px] text-slate-400 mt-0.5">₹{(ls.revenue_this_month || 0).toLocaleString("en-IN")}</p>
        </div>
        <div className="bg-white border border-slate-100 rounded-2xl p-5 shadow-sm">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-8 h-8 rounded-xl bg-indigo-50 flex items-center justify-center text-indigo-600"><I.Doc /></div>
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Purchase Orders</span>
          </div>
          <p className="text-2xl font-bold text-slate-900">{ls.po_signed_this_month || 0}</p>
          <p className="text-[10px] text-slate-400 mt-0.5">{ls.po_signed_total || 0} all time</p>
        </div>
        <div className="bg-white border border-slate-100 rounded-2xl p-5 shadow-sm">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-8 h-8 rounded-xl bg-violet-50 flex items-center justify-center text-violet-600"><I.TrendUp /></div>
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Win Rate</span>
          </div>
          <p className="text-2xl font-bold text-slate-900">{ls.win_rate || 0}%</p>
        </div>
        <div className="bg-white border border-slate-100 rounded-2xl p-5 shadow-sm">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-8 h-8 rounded-xl bg-amber-50 flex items-center justify-center text-amber-600"><I.Clock /></div>
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Meetings</span>
          </div>
          <p className="text-2xl font-bold text-slate-900">{monthMeetings.length}</p>
          <p className="text-[10px] text-slate-400 mt-0.5">{meetings.length} upcoming</p>
        </div>
        <div className="bg-white border border-slate-100 rounded-2xl p-5 shadow-sm col-span-2 lg:col-span-1">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-8 h-8 rounded-xl bg-rose-50 flex items-center justify-center text-rose-600"><I.Calendar /></div>
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Holidays</span>
          </div>
          <p className="text-2xl font-bold text-slate-900">{holidays.length}</p>
          <p className="text-[10px] text-slate-400 mt-0.5">days off this month</p>
        </div>
      </div>

      {/* ── Monthly Target + Lead Pipeline ── */}
      <div className="grid lg:grid-cols-3 gap-5 mb-8">
        {/* Monthly Target Card */}
        <div className="bg-white border border-slate-100 rounded-2xl p-6 shadow-sm">
          <div className="flex items-center gap-2 mb-5">
            <div className="w-8 h-8 rounded-xl bg-indigo-50 flex items-center justify-center text-indigo-600"><I.Target /></div>
            <h2 className="text-sm font-bold text-slate-900">Monthly Target</h2>
            {mp.has_target && <span className={`ml-auto text-[10px] font-bold px-2 py-1 rounded-lg ${monthlyColor.bg} ${monthlyColor.text}`}>{monthlyColor.label}</span>}
          </div>

          {mp.has_target ? (
            <div className="flex flex-col items-center">
              <div className="relative mb-4">
                <Ring pct={monthlyLeadPct} size={120} stroke={8} color={monthlyColor.ring} />
                <div className="absolute inset-0 flex flex-col items-center justify-center">
                  <span className="text-2xl font-bold text-slate-900">{monthlyLeadPct}%</span>
                  <span className="text-[9px] text-slate-400 font-semibold uppercase">Leads</span>
                </div>
              </div>
              <div className="w-full space-y-3">
                <div>
                  <div className="flex justify-between mb-1">
                    <span className="text-xs text-slate-500">Leads</span>
                    <span className="text-xs font-semibold text-slate-700">{mp.actual_leads}/{mp.target_leads}</span>
                  </div>
                  <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden">
                    <div className="h-full rounded-full transition-all duration-700" style={{ width: `${Math.min(monthlyLeadPct, 100)}%`, backgroundColor: monthlyColor.ring }} />
                  </div>
                </div>
                <div>
                  <div className="flex justify-between mb-1">
                    <span className="text-xs text-slate-500">Revenue</span>
                    <span className="text-xs font-semibold text-slate-700">₹{(mp.actual_amount || 0).toLocaleString("en-IN")} / ₹{(mp.target_amount || 0).toLocaleString("en-IN")}</span>
                  </div>
                  <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden">
                    <div className="h-full bg-emerald-500 rounded-full transition-all duration-700" style={{ width: `${Math.min(monthlyAmtPct, 100)}%` }} />
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="text-center py-8">
              <div className="w-12 h-12 mx-auto rounded-2xl bg-slate-50 flex items-center justify-center text-slate-300 mb-3"><I.Target /></div>
              <p className="text-sm text-slate-400">No target set for {MONTHS[month - 1]} {year}</p>
              <p className="text-[10px] text-slate-400 mt-1">Ask your manager to set monthly targets</p>
            </div>
          )}
        </div>

        {/* Lead Pipeline Breakdown */}
        <div className="bg-white border border-slate-100 rounded-2xl p-6 shadow-sm">
          <div className="flex items-center gap-2 mb-5">
            <div className="w-8 h-8 rounded-xl bg-cyan-50 flex items-center justify-center text-cyan-600"><I.Activity /></div>
            <h2 className="text-sm font-bold text-slate-900">Lead Pipeline</h2>
          </div>
          {Object.keys(statusBreakdown).length === 0 ? (
            <div className="text-center py-8">
              <p className="text-sm text-slate-400">No leads assigned yet</p>
            </div>
          ) : (
            <div className="space-y-2.5 max-h-[280px] overflow-y-auto">
              {Object.entries(statusBreakdown)
                .sort(([, a]: any, [, b]: any) => b - a)
                .map(([status, count]: any) => {
                  const sc = STATUS_COLORS[status] || { bg: "bg-slate-50", text: "text-slate-600", dot: "bg-slate-400" };
                  const pct = ls.total_leads > 0 ? Math.round((count / ls.total_leads) * 100) : 0;
                  return (
                    <div key={status} className="flex items-center gap-3 group">
                      <div className={`w-2 h-2 rounded-full flex-shrink-0 ${sc.dot}`} />
                      <span className="text-xs text-slate-600 flex-1 capitalize truncate">{status.replace(/_/g, ' ')}</span>
                      <span className="text-xs font-bold text-slate-700">{count}</span>
                      <div className="w-16 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                        <div className={`h-full rounded-full ${sc.dot}`} style={{ width: `${pct}%` }} />
                      </div>
                      <span className="text-[10px] text-slate-400 w-8 text-right">{pct}%</span>
                    </div>
                  );
                })}
            </div>
          )}
        </div>

        {/* Daily Targets Breakdown */}
        <div className="bg-white border border-slate-100 rounded-2xl shadow-sm overflow-hidden">
          <div className="flex items-center gap-2 p-6 pb-0 mb-4">
            <div className="w-8 h-8 rounded-xl bg-violet-50 flex items-center justify-center text-violet-600"><I.Calendar /></div>
            <div>
              <h2 className="text-sm font-bold text-slate-900">Daily Targets</h2>
              <p className="text-[10px] text-slate-400">Auto-calculated from monthly target</p>
            </div>
            <span className="ml-auto text-[10px] font-semibold text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded-full">{dailyTargets.length} days</span>
          </div>
          {dailyTargets.length === 0 ? (
            <div className="text-center py-8 px-6">
              <div className="w-12 h-12 mx-auto rounded-2xl bg-slate-50 flex items-center justify-center text-slate-300 mb-3"><I.Calendar /></div>
              <p className="text-sm text-slate-400">No daily targets for this month</p>
              <p className="text-[10px] text-slate-400 mt-1">Targets are auto-generated when your manager sets a monthly target</p>
            </div>
          ) : (
            <div className="max-h-[360px] overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="bg-slate-50 sticky top-0 z-10">
                  <tr>
                    <th className="text-left px-4 py-2 font-semibold text-slate-500">Date</th>
                    <th className="text-left px-4 py-2 font-semibold text-slate-500">Leads</th>
                    <th className="text-left px-4 py-2 font-semibold text-slate-500">Calls / Time</th>
                    <th className="text-left px-4 py-2 font-semibold text-slate-500">Status</th>
                    <th className="text-right px-4 py-2 font-semibold text-slate-500">Submit</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {dailyTargets.map((dt: any) => {
                    const d = new Date(dt.date + 'T12:00:00');
                    const isToday = d.toDateString() === new Date().toDateString();
                    const isPastOrToday = d <= new Date();
                    const sc = dt.status === 'achieved' ? 'bg-emerald-50 text-emerald-600' : dt.status === 'missed' ? 'bg-red-50 text-red-500' : 'bg-slate-50 text-slate-500';
                    return (
                      <tr key={dt.id} className={`transition-colors ${isToday ? 'bg-indigo-50/50 font-semibold' : 'hover:bg-slate-50/50'}`}>
                        <td className="px-4 py-2.5">
                          <div className="flex items-center gap-1.5">
                            {isToday && <span className="w-1.5 h-1.5 rounded-full bg-indigo-600 flex-shrink-0" />}
                            <span className={`font-medium ${isToday ? 'text-indigo-700' : 'text-slate-700'}`}>
                              {d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', weekday: 'short' })}
                            </span>
                          </div>
                        </td>
                        <td className="px-4 py-2.5 font-semibold text-slate-800">{dt.target_leads}</td>
                        <td className="px-4 py-2.5">
                          {(dt.target_dialed_calls > 0 || dt.target_call_time > 0 || dt.achieved_dialed_calls > 0 || dt.achieved_call_time > 0) ? (
                            <div className="space-y-0.5 leading-tight">
                              <div className="text-slate-700">{dt.achieved_dialed_calls}{dt.target_dialed_calls > 0 && <span className="text-slate-400">/{dt.target_dialed_calls}</span>} <span className="text-slate-400 text-[9px]">calls</span></div>
                              <div className="text-slate-700">{dt.achieved_call_time}{dt.target_call_time > 0 && <span className="text-slate-400">/{dt.target_call_time}</span>} <span className="text-slate-400 text-[9px]">min</span></div>
                            </div>
                          ) : <span className="text-slate-300">—</span>}
                        </td>
                        <td className="px-4 py-2.5">
                          <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full ${sc}`}>{dt.status}</span>
                        </td>
                        <td className="px-4 py-2.5 text-right">
                          {isPastOrToday && (
                            <button onClick={() => openSubmitModal(dt)}
                              className="inline-flex items-center gap-1 px-2 py-1 bg-violet-50 text-violet-600 text-[10px] font-bold rounded-lg hover:bg-violet-100 transition-colors">
                              <I.Upload /> Log
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* ── Bottom Row: Meetings + Recent Leads ── */}
      <div className="grid lg:grid-cols-2 gap-5">
        {/* Upcoming Meetings */}
        <div className="bg-white border border-slate-100 rounded-2xl shadow-sm overflow-hidden">
          <div className="flex items-center justify-between px-6 py-4 border-b border-slate-50">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-xl bg-blue-50 flex items-center justify-center text-blue-600"><I.Clock /></div>
              <h2 className="text-sm font-bold text-slate-900">My Meetings</h2>
            </div>
            <span className="text-[10px] font-semibold text-slate-400 bg-slate-50 px-2 py-1 rounded-lg">{meetings.length} upcoming</span>
          </div>
          <div className="p-4 space-y-3 max-h-[320px] overflow-y-auto">
            {meetings.length === 0 ? (
              <div className="text-center py-10">
                <div className="w-12 h-12 mx-auto rounded-2xl bg-slate-50 flex items-center justify-center text-slate-300 mb-3"><I.Clock /></div>
                <p className="text-sm text-slate-400 font-medium">No upcoming meetings</p>
                <p className="text-[10px] text-slate-400 mt-1">You&apos;re all clear! 🎉</p>
              </div>
            ) : meetings.map((m: any) => {
              const dt = new Date(m.scheduled_at);
              const isToday = dt.toDateString() === new Date().toDateString();
              return (
                <div key={m.id} className={`flex items-start gap-3 p-3.5 rounded-xl transition-colors ${isToday ? "bg-blue-50 border border-blue-100" : "bg-slate-50 hover:bg-slate-100/50"}`}>
                  <div className={`w-12 h-12 rounded-xl flex flex-col items-center justify-center flex-shrink-0 ${isToday ? "bg-blue-600 text-white" : "bg-white text-slate-600 border border-slate-200"}`}>
                    <span className="text-[8px] font-bold uppercase leading-none">{dt.toLocaleString('en', { month: 'short' })}</span>
                    <span className="text-base font-bold leading-none">{dt.getDate()}</span>
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-slate-800 truncate">{m.title}</p>
                    <p className="text-[10px] text-slate-400 mt-0.5">
                      {dt.toLocaleTimeString('en', { hour: '2-digit', minute: '2-digit' })} · {m.duration_minutes} min
                    </p>
                    {m.attendee_names?.length > 0 && (
                      <div className="flex items-center gap-1 mt-2">
                        <div className="flex -space-x-1">
                          {m.attendee_names.slice(0, 4).map((a: any, i: number) => (
                            <div key={a.id} className="w-5 h-5 rounded-full bg-indigo-100 text-indigo-600 flex items-center justify-center text-[8px] font-bold ring-1 ring-white">
                              {a.name.charAt(0)}
                            </div>
                          ))}
                        </div>
                        <span className="text-[9px] text-slate-400 ml-1">{m.attendee_names.length} attendee{m.attendee_names.length > 1 ? 's' : ''}</span>
                      </div>
                    )}
                    {isToday && <span className="inline-block mt-2 text-[9px] font-bold text-blue-600 bg-blue-100 px-2 py-0.5 rounded-full">TODAY</span>}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Recent Leads */}
        <div className="bg-white border border-slate-100 rounded-2xl shadow-sm overflow-hidden">
          <div className="flex items-center justify-between px-6 py-4 border-b border-slate-50">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-xl bg-violet-50 flex items-center justify-center text-violet-600"><I.Users /></div>
              <h2 className="text-sm font-bold text-slate-900">Recent Leads</h2>
            </div>
          </div>
          <div className="divide-y divide-slate-50">
            {recentLeads.length === 0 ? (
              <div className="text-center py-10">
                <div className="w-12 h-12 mx-auto rounded-2xl bg-slate-50 flex items-center justify-center text-slate-300 mb-3"><I.Users /></div>
                <p className="text-sm text-slate-400 font-medium">No leads assigned yet</p>
              </div>
            ) : recentLeads.map((l: any) => {
              const sc = STATUS_COLORS[l.status] || STATUS_COLORS.new_lead;
              return (
                <div key={l.id} className="flex items-center gap-3 px-5 py-3.5 hover:bg-slate-50/50 transition-colors">
                  <div className="w-9 h-9 rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-white text-xs font-bold flex-shrink-0">
                    {l.name.charAt(0).toUpperCase()}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-slate-800 truncate">{l.name}</p>
                    <p className="text-[10px] text-slate-400">{l.created_at} · ₹{(l.value || 0).toLocaleString("en-IN")}</p>
                  </div>
                  <span className={`text-[10px] font-bold px-2.5 py-1 rounded-full ${sc.bg} ${sc.text} capitalize whitespace-nowrap`}>
                    {l.status.replace(/_/g, ' ')}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* ── Submit Performance Modal ── */}
      {submitModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" />
          <div className="relative bg-white rounded-3xl shadow-2xl w-full max-w-md overflow-hidden">
            <div className="bg-gradient-to-br from-violet-500 to-indigo-600 px-6 py-5">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-white font-black text-lg">Submit Daily Performance</h2>
                  <p className="text-white/70 text-sm">{new Date(submitModal.date + 'T12:00:00').toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long' })}</p>
                </div>
                <button onClick={() => setSubmitModal(null)} className="text-white/60 hover:text-white transition-colors"><I.X /></button>
              </div>
            </div>
            <div className="p-6 space-y-5">
              {/* Targets summary */}
              {(submitModal.target_dialed_calls > 0 || submitModal.target_call_time > 0) && (
                <div className="grid grid-cols-2 gap-3">
                  {submitModal.target_dialed_calls > 0 && (
                    <div className="bg-indigo-50 rounded-xl p-3 text-center">
                      <p className="text-[10px] text-indigo-400 font-bold uppercase mb-1">Call Target</p>
                      <p className="text-lg font-black text-indigo-700">{submitModal.target_dialed_calls}</p>
                      <p className="text-[10px] text-indigo-400">dialed calls</p>
                    </div>
                  )}
                  {submitModal.target_call_time > 0 && (
                    <div className="bg-violet-50 rounded-xl p-3 text-center">
                      <p className="text-[10px] text-violet-400 font-bold uppercase mb-1">Time Target</p>
                      <p className="text-lg font-black text-violet-700">{submitModal.target_call_time}</p>
                      <p className="text-[10px] text-violet-400">minutes</p>
                    </div>
                  )}
                </div>
              )}

              {/* Achieved inputs */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-500 mb-1.5 uppercase tracking-wide">Dialed Calls Achieved</label>
                  <div className="relative">
                    <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"><I.Phone /></span>
                    <input id="achieved-calls" type="number" min="0" value={submitForm.achieved_dialed_calls}
                      onChange={e => setSubmitForm(f => ({ ...f, achieved_dialed_calls: e.target.value }))}
                      placeholder="0"
                      className="w-full pl-9 pr-3 py-2.5 border border-slate-200 rounded-xl text-sm font-semibold text-slate-800 focus:outline-none focus:ring-2 focus:ring-violet-300" />
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-500 mb-1.5 uppercase tracking-wide">Call Time (mins)</label>
                  <div className="relative">
                    <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"><I.Clock /></span>
                    <input id="achieved-calltime" type="number" min="0" value={submitForm.achieved_call_time}
                      onChange={e => setSubmitForm(f => ({ ...f, achieved_call_time: e.target.value }))}
                      placeholder="0"
                      className="w-full pl-9 pr-3 py-2.5 border border-slate-200 rounded-xl text-sm font-semibold text-slate-800 focus:outline-none focus:ring-2 focus:ring-violet-300" />
                  </div>
                </div>
              </div>

              {/* File Upload */}
              <div>
                <label className="block text-xs font-semibold text-slate-500 mb-1.5 uppercase tracking-wide">Proof Screenshots</label>
                <div
                  onClick={() => fileInputRef.current?.click()}
                  className="border-2 border-dashed border-slate-200 rounded-xl p-5 text-center cursor-pointer hover:border-violet-300 hover:bg-violet-50/50 transition-all flex flex-col items-center gap-2">
                  <div className="w-8 h-8 rounded-xl bg-violet-50 flex items-center justify-center text-violet-500"><I.Upload /></div>
                  <p className="text-xs text-slate-500 font-medium">Click to upload screenshots</p>
                  <p className="text-[10px] text-slate-400">PNG, JPG, PDF — multiple files allowed</p>
                </div>
                <input ref={fileInputRef} type="file" multiple accept="image/*,.pdf" onChange={handleFileChange} className="hidden" />
                {submitFiles.length > 0 && (
                  <div className="mt-2 space-y-1.5 max-h-32 overflow-y-auto">
                    {submitFiles.map((f, i) => (
                      <div key={i} className="flex items-center justify-between bg-slate-50 rounded-lg px-3 py-1.5">
                        <span className="text-xs text-slate-600 truncate flex-1">{f.name}</span>
                        <button onClick={() => removeFile(i)} className="ml-2 text-slate-400 hover:text-rose-500 transition-colors flex-shrink-0"><I.X /></button>
                      </div>
                    ))}
                  </div>
                )}
                {submitModal.proofs?.length > 0 && (
                  <div className="mt-3">
                    <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide mb-1.5">Uploaded ({submitModal.proofs.length})</p>
                    <div className="space-y-1.5 max-h-32 overflow-y-auto">
                      {submitModal.proofs.map((p: any) => {
                        const href = (p.file || "").startsWith("http") ? p.file : `${getApiBase(domain)}${p.file}`;
                        const name = decodeURIComponent((p.file || "").split("/").pop() || "file");
                        return (
                          <div key={p.id} className="flex items-center justify-between bg-emerald-50 rounded-lg px-3 py-1.5">
                            <a href={href} target="_blank" rel="noreferrer" className="text-xs font-semibold text-emerald-700 truncate flex-1 hover:underline" title={name}>{name}</a>
                            <button onClick={() => deleteProof(p.id)} className="ml-2 text-slate-400 hover:text-rose-500 transition-colors flex-shrink-0" title="Delete"><I.X /></button>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>

              {submitResult && (
                <div className={`text-sm font-semibold px-4 py-3 rounded-xl flex items-center gap-2 ${
                  submitResult.ok ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-600'
                }`}>
                  {submitResult.ok ? <I.Check /> : <I.X />}
                  {submitResult.msg}
                </div>
              )}

              <div className="flex gap-3">
                <button onClick={() => setSubmitModal(null)} className="flex-1 py-3 bg-slate-100 text-slate-600 font-bold rounded-xl hover:bg-slate-200 transition-colors text-sm">Cancel</button>
                <button onClick={submitPerformance} disabled={submitting}
                  className="flex-1 py-3 bg-gradient-to-r from-violet-600 to-indigo-600 text-white font-bold rounded-xl hover:opacity-90 disabled:opacity-50 transition-all text-sm flex items-center justify-center gap-2">
                  {submitting ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <I.Check />}
                  {submitting ? 'Submitting…' : 'Submit Performance'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

"use client";
import { APP_SLUG } from "@/lib/config";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { getApiBase } from "@/lib/mock-data";
import { useLeadStatuses } from "@/hooks/useLeadStatuses";

const ModernDashboardCharts = dynamic(() => import("./DashboardCharts"), { ssr: false });
const PipelineChart = dynamic(() => import("./PipelineChart"), { ssr: false });

// ─── Animated Counter ─────────────────────────────────────────────────────────
function AnimatedNumber({ value, prefix = "", suffix = "", isCurrency = false }: { value: number; prefix?: string; suffix?: string; isCurrency?: boolean }) {
  const [display, setDisplay] = useState(0);
  useEffect(() => {
    if (value === 0) { setDisplay(0); return; }
    let start = 0;
    const step = value / (1000 / 16);
    const timer = setInterval(() => {
      start += step;
      if (start >= value) { setDisplay(value); clearInterval(timer); }
      else setDisplay(Math.floor(start));
    }, 16);
    return () => clearInterval(timer);
  }, [value]);
  const formatted = isCurrency
    ? display.toLocaleString("en-IN", { minimumFractionDigits: 0 })
    : display.toLocaleString("en-IN");
  return <>{prefix}{formatted}{suffix}</>;
}

// ─── Stat Card ────────────────────────────────────────────────────────────────
function StatCard({ label, value, prefix = "", isCurrency = false, icon, accent, sub }: any) {
  return (
    <div className="bg-white border border-slate-100 rounded-2xl p-5 shadow-sm hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between mb-4">
        <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ backgroundColor: accent + "15" }}>
          <span style={{ color: accent }}>{icon}</span>
        </div>
        <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-widest">{label}</span>
      </div>
      <p className="text-2xl sm:text-3xl font-bold text-slate-900">
        <AnimatedNumber value={value} prefix={prefix} isCurrency={isCurrency} />
      </p>
      <p className="text-xs text-slate-400 mt-1.5">{sub}</p>
    </div>
  );
}

export default function DashboardPage({ params: paramsPromise }: { params: Promise<{ domain: string }> }) {
  const params = React.use(paramsPromise);
  const domain = APP_SLUG;

  const { statusMeta } = useLeadStatuses(domain);

  const [userName, setUserName] = useState("User");
  const [stats, setStats] = useState<any>(null);
  const [subscription, setSubscription] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [selectedUser, setSelectedUser] = useState<any>(null);
  const [selectedTeam, setSelectedTeam] = useState<any>(null);
  const [modalLoading, setModalLoading] = useState(false);
  const [manager, setManager] = useState<any>(null);

  useEffect(() => {
    const token = localStorage.getItem(`${domain}_access`);
    if (!token) { setLoading(false); return; }
    const name = localStorage.getItem(`${domain}_username`);
    if (name) setUserName(name);
    Promise.all([
      fetch(`${getApiBase(domain)}/api/dashboard-stats/`, { headers: { Authorization: `Bearer ${token}` } }),
      fetch(`${getApiBase(domain)}/api/subscription/`, { headers: { Authorization: `Bearer ${token}` } }),
      fetch(`${getApiBase(domain)}/api/users/me/`, { headers: { Authorization: `Bearer ${token}` } }),
      fetch(`${getApiBase(domain)}/api/teams/`, { headers: { Authorization: `Bearer ${token}` } }),
    ]).then(async ([s, sub, me, teams]) => {
      if (s.ok) setStats(await s.json());
      if (sub.ok) setSubscription(await sub.json());
      // For agents (not admin/GM), surface their team manager.
      if (me.ok && teams.ok) {
        const meData = await me.json();
        const teamsData = await teams.json();
        const teamsArr = Array.isArray(teamsData) ? teamsData : teamsData.results || [];
        const isAdminOrGM = meData.is_staff || meData.is_general_manager || meData.read_only;
        const myTeam = teamsArr.find((t: any) => t.id === meData.team);
        const mgr = myTeam?.manager_detail;
        if (!isAdminOrGM && mgr && mgr.id !== meData.id) setManager(mgr);
      }
    }).catch(console.error).finally(() => setLoading(false));
  }, [domain]);

  const fetchUserPerf = async (id: number) => {
    setModalLoading(true);
    const token = localStorage.getItem(`${domain}_access`);
    try {
      const r = await fetch(`${getApiBase(domain)}/api/users/${id}/performance/`, { headers: { Authorization: `Bearer ${token}` } });
      if (r.ok) setSelectedUser(await r.json());
    } catch (e) { console.error(e); } finally { setModalLoading(false); }
  };

  const fetchTeamPerf = async (id: number) => {
    setModalLoading(true);
    const token = localStorage.getItem(`${domain}_access`);
    try {
      const r = await fetch(`${getApiBase(domain)}/api/teams/${id}/performance/`, { headers: { Authorization: `Bearer ${token}` } });
      if (r.ok) setSelectedTeam(await r.json());
    } catch (e) { console.error(e); } finally { setModalLoading(false); }
  };

  if (loading) return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="text-center">
        <div className="w-8 h-8 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
        <p className="text-sm text-slate-400">Loading dashboard...</p>
      </div>
    </div>
  );

  // All statuses with display labels + colours dynamically resolved from useLeadStatuses hook
  const STATUS_DISPLAY: Record<string, { label: string; color: string }> = {};
  Object.entries(statusMeta).forEach(([k, m]) => {
    STATUS_DISPLAY[k] = { label: m.label, color: m.hex };
  });
  // Build pipeline bars only for statuses that have data
  const pipeline = Object.entries(STATUS_DISPLAY)
    .map(([key, meta]) => ({ key, label: meta.label, color: meta.color, value: stats?.pipeline?.[key] || 0 }))
    .filter(bar => bar.value > 0);
  const maxBar = Math.max(...pipeline.map(d => d.value), 1);
  const activities = stats?.recent_activities || [];

  const activityIcon: Record<string, React.ReactElement> = {
    lead_created:        <svg width="14" height="14" fill="none" stroke="#6366f1" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2" /><circle cx="12" cy="7" r="4" /></svg>,
    lead_status_change:  <svg width="14" height="14" fill="none" stroke="#f59e0b" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M17 3l4 4-4 4" /><path d="M7 21l-4-4 4-4" /><path d="M21 7H9a4 4 0 000 8h6" /></svg>,
    note_added:          <svg width="14" height="14" fill="none" stroke="#0d9488" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" /><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" /></svg>,
    task_created:        <svg width="14" height="14" fill="none" stroke="#8b5cf6" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M16 3v4M8 3v4M3 11h18" /><path d="M12 15v4M10 17h4" /></svg>,
    task_stage_change:   <svg width="14" height="14" fill="none" stroke="#0ea5e9" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" /><path d="M12 6v6l4 2" /></svg>,
    task_completed:      <svg width="14" height="14" fill="none" stroke="#10b981" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M9 11l3 3 8-8" /><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" /></svg>,
    meta_import:         <svg width="14" height="14" fill="none" stroke="#8b5cf6" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><rect x="5" y="2" width="14" height="20" rx="2" /><line x1="12" y1="18" x2="12.01" y2="18" /></svg>,
    user_joined:         <svg width="14" height="14" fill="none" stroke="#06b6d4" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M16 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" /><circle cx="8.5" cy="7" r="4" /><line x1="20" y1="8" x2="20" y2="14" /><line x1="23" y1="11" x2="17" y2="11" /></svg>,
    lead_updated:        <svg width="14" height="14" fill="none" stroke="#f59e0b" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" /><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" /></svg>,
  };
  const activityBg: Record<string, string> = {
    lead_created:       "bg-indigo-50",
    lead_status_change: "bg-amber-50",
    lead_updated:       "bg-amber-50",
    note_added:         "bg-teal-50",
    task_created:       "bg-violet-50",
    task_stage_change:  "bg-sky-50",
    task_completed:     "bg-emerald-50",
    meta_import:        "bg-violet-50",
    user_joined:        "bg-cyan-50",
  };

  const greetHour = new Date().getHours();
  const greeting = greetHour < 12 ? "Good morning" : greetHour < 17 ? "Good afternoon" : "Good evening";

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-[1400px]">
      {/* ── Header ── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">{greeting}, <span className="capitalize">{userName}</span></h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {subscription?.name || "Workspace"} &middot; {subscription?.status === "active" ? <span className="text-emerald-600 font-medium">Active</span> : subscription?.status}
          </p>
        </div>
        <div className="flex gap-3">
          <Link href={`/leads`} className="flex items-center gap-2 px-4 py-2 bg-white border border-slate-200 rounded-xl text-sm font-semibold text-slate-700 hover:bg-slate-50 transition-all">
            <svg width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M23 21v-2a4 4 0 00-3-3.87" /><path d="M16 3.13a4 4 0 010 7.75" /></svg>
            All Leads
          </Link>
          <Link href={`/tasks`} className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 transition-all shadow-sm shadow-indigo-200">
            <svg width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14" /></svg>
            New Task
          </Link>
        </div>
      </div>

      {/* ── Your Manager (agent view) ── */}
      {manager && (
        <div className="bg-white border border-slate-100 rounded-2xl p-5 shadow-sm mb-8 flex items-center gap-4 relative overflow-hidden">
          <div className="absolute left-0 top-0 bottom-0 w-1 bg-gradient-to-b from-indigo-500 to-violet-600" />
          <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-base font-bold text-white shadow-sm flex-shrink-0">
            {(manager.first_name?.[0] || manager.username?.[0] || "?").toUpperCase()}
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-0.5">Your Manager</p>
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="text-sm font-bold text-slate-900 truncate">{manager.first_name} {manager.last_name || manager.username}</h3>
              <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-blue-50 text-blue-700">
                {manager.is_staff ? "Admin" : manager.is_general_manager ? "General Manager" : "Manager"}
              </span>
            </div>
            <p className="text-xs text-slate-400 truncate">
              {manager.email || `@${manager.username}`}
              {(manager.phone || (subscription?.telephony_provider === "voxbay" && manager.voxbay_extension)) && (
                <span className="ml-2 text-indigo-500 font-mono">
                  {manager.phone && `📞 ${manager.phone}`}
                  {manager.phone && subscription?.telephony_provider === "voxbay" && manager.voxbay_extension && " | "}
                  {subscription?.telephony_provider === "voxbay" && manager.voxbay_extension && `Ext: ${manager.voxbay_extension}`}
                </span>
              )}
            </p>
          </div>
          {manager.email && (
            <a href={`mailto:${manager.email}`} className="hidden sm:inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-indigo-50 text-indigo-600 text-xs font-semibold hover:bg-indigo-100 transition-all flex-shrink-0">
              Contact
            </a>
          )}
        </div>
      )}

      {/* ── Stats Grid ── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatCard
          label="Total Leads" value={stats?.total_leads || 0} sub="All time"
          accent="#6366f1"
          icon={<svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M23 21v-2a4 4 0 00-3-3.87" /><path d="M16 3.13a4 4 0 010 7.75" /></svg>}
        />
        <StatCard
          label="Revenue" value={stats?.total_revenue || 0} prefix="₹" isCurrency sub="Closed deals"
          accent="#10b981"
          icon={<svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" viewBox="0 0 24 24"><path d="M12 1v22M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6" /></svg>}
        />
        <StatCard
          label="Pipeline" value={stats?.pipeline_value || 0} prefix="₹" isCurrency sub="Total potential"
          accent="#06b6d4"
          icon={<svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" viewBox="0 0 24 24"><rect x="2" y="7" width="20" height="14" rx="2" /><path d="M16 21V5a2 2 0 00-2-2h-4a2 2 0 00-2 2v16" /></svg>}
        />
        <StatCard
          label="New Today" value={stats?.new_today || 0} sub="Leads added today"
          accent="#f59e0b"
          icon={<svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" /></svg>}
        />
      </div>

      {/* ── Middle: Pipeline + Activity ── */}
      <div className="grid lg:grid-cols-5 gap-5 mb-8">
        {/* Pipeline Chart */}
        <div className="lg:col-span-3 bg-white border border-slate-100 rounded-2xl p-6 shadow-sm flex flex-col min-w-0">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h2 className="text-base font-bold text-slate-900">Lead Pipeline</h2>
              <p className="text-xs text-slate-400 mt-0.5">Current stage distribution</p>
            </div>
            <span className="text-xs font-semibold text-indigo-600 bg-indigo-50 px-3 py-1 rounded-full">
              {Object.values(stats?.pipeline || {}).reduce((a: number, v: any) => a + (v || 0), 0)} total
            </span>
          </div>
          <div className="flex-1 min-h-[220px] w-full pt-2">
            <PipelineChart data={pipeline} />
          </div>
        </div>

        {/* Activity Feed */}
        <div className="lg:col-span-2 bg-white border border-slate-100 rounded-2xl p-6 shadow-sm flex flex-col">
          <div className="flex items-center justify-between mb-5">
            <div>
              <h2 className="text-base font-bold text-slate-900">Recent Activity</h2>
              <p className="text-xs text-slate-400 mt-0.5">Live CRM events stream</p>
            </div>
            <span className="flex items-center gap-1.5 text-xs font-semibold text-emerald-600 bg-emerald-50 px-3 py-1 rounded-full">
              <span className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse" />
              Live
            </span>
          </div>
          <div className="space-y-4 overflow-y-auto flex-1 pr-2 custom-scrollbar max-h-[300px]">
            {activities.length === 0 && (
              <div className="flex flex-col items-center justify-center h-full text-slate-300">
                <svg width="28" height="28" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24" className="mb-2"><circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" /></svg>
                <span className="text-sm">No recent activity</span>
              </div>
            )}
            {activities.map((a: any, idx: number) => {
              // relative timestamp
              const ts = new Date(a.timestamp);
              const diffMs = Date.now() - ts.getTime();
              const diffMin = Math.floor(diffMs / 60000);
              const relTime = diffMin < 1 ? 'just now'
                : diffMin < 60 ? `${diffMin}m ago`
                : diffMin < 1440 ? `${Math.floor(diffMin / 60)}h ago`
                : `${Math.floor(diffMin / 1440)}d ago`;
              return (
              <div key={`${a.type}-${a.id}-${idx}`} className="flex items-start gap-4 group p-2 rounded-xl hover:bg-slate-50 transition-colors">
                <div className={`w-9 h-9 rounded-xl ${activityBg[a.type] || "bg-slate-100"} flex items-center justify-center flex-shrink-0 shadow-sm border border-white`}>
                  {activityIcon[a.type] || <svg width="14" height="14" fill="none" stroke="#94a3b8" strokeWidth="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" /></svg>}
                </div>
                <div className="flex-1 min-w-0 pt-0.5">
                  <p className="text-sm font-medium text-slate-700 leading-snug">{a.description}</p>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-xs font-semibold text-slate-500">{a.user}</span>
                    <span className="w-1 h-1 rounded-full bg-slate-300"></span>
                    <span className="text-[11px] text-slate-400 font-medium">{relTime}</span>
                  </div>
                </div>
              </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* ── Advanced Charts Row ── */}
      <ModernDashboardCharts stats={stats} />

      {/* ── Member Performance Table ── */}
      {(stats?.performance_stats?.length > 0) && (
        <div className="bg-white border border-slate-100 rounded-2xl shadow-sm mb-8 overflow-hidden">
          <div className="flex items-center justify-between px-5 py-4 border-b border-slate-50">
            <div>
              <h2 className="text-base font-bold text-slate-900">Member Performance</h2>
              <p className="text-xs text-slate-400 mt-0.5">Click a member for detailed breakdown</p>
            </div>
            <span className="flex items-center gap-1.5 text-xs font-semibold text-emerald-600">
              <span className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse" />
              Live
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left min-w-[500px]">
              <thead>
                <tr className="text-[10px] font-bold text-slate-400 uppercase tracking-widest bg-slate-50/50">
                  <th className="px-5 py-3.5">Member</th>
                  <th className="px-5 py-3.5 text-right">Converted</th>
                  <th className="px-5 py-3.5 text-right">Revenue</th>
                  <th className="px-5 py-3.5 text-right">Pipeline</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {[...stats.performance_stats].sort((a, b) => b.won_value - a.won_value).map((m: any) => (
                  <tr key={m.id} onClick={() => fetchUserPerf(m.id)} className="group hover:bg-blue-50/30 cursor-pointer transition-colors">
                    <td className="px-5 py-4">
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-xs font-bold text-white flex-shrink-0">
                          {m.name.charAt(0).toUpperCase()}
                        </div>
                        <div>
                          <p className="text-sm font-semibold text-slate-800 group-hover:text-indigo-600 transition-colors">{m.name}</p>
                          <p className="text-[10px] text-slate-400 font-medium uppercase">{m.role}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-5 py-4 text-right">
                      <span className="text-sm font-bold text-slate-700 bg-slate-50 px-2.5 py-1 rounded-lg">{m.won_count}</span>
                    </td>
                    <td className="px-5 py-4 text-right">
                      <span className="text-sm font-bold text-emerald-600">₹{m.won_value.toLocaleString("en-IN")}</span>
                    </td>
                    <td className="px-5 py-4 text-right">
                      <span className="text-sm text-slate-400">₹{m.pipeline_value.toLocaleString("en-IN")}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Team Stats ── */}
      {(stats?.team_stats?.length > 0) && (
        <div className="bg-white border border-slate-100 rounded-2xl p-5 shadow-sm mb-8">
          <div className="flex items-center justify-between mb-5">
            <h2 className="text-base font-bold text-slate-900">Team Performance</h2>
            <p className="text-xs text-slate-400">Aggregated win metrics</p>
          </div>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {stats.team_stats.map((team: any) => {
              const maxW = Math.max(...stats.team_stats.map((t: any) => t.won_value), 1);
              const pct = Math.round((team.won_value / maxW) * 100);
              return (
                <div key={team.id} onClick={() => fetchTeamPerf(team.id)} className="border border-slate-100 rounded-2xl p-4 hover:border-emerald-200 hover:shadow-sm transition-all cursor-pointer">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-sm font-bold text-slate-800 truncate">{team.name}</h3>
                    <svg width="14" height="14" fill="none" stroke="#10b981" strokeWidth="2" viewBox="0 0 24 24"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17" /><polyline points="16 7 22 7 22 13" /></svg>
                  </div>
                  <p className="text-xl font-bold text-emerald-600 mb-1">₹{team.won_value.toLocaleString("en-IN")}</p>
                  <p className="text-xs text-slate-400 mb-3">{team.won_count} converted</p>
                  <div className="w-full h-1.5 bg-slate-100 rounded-full overflow-hidden">
                    <div className="h-full bg-emerald-500 rounded-full" style={{ width: `${pct}%` }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Performance Detail Modal ── */}
      {(selectedUser || selectedTeam || modalLoading) && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/40 backdrop-blur-sm">
          <div className="bg-white w-full sm:max-w-2xl sm:mx-4 rounded-t-2xl sm:rounded-2xl shadow-2xl max-h-[90vh] overflow-hidden flex flex-col" onClick={e => e.stopPropagation()}>
            {modalLoading ? (
              <div className="flex items-center justify-center py-20">
                <div className="w-8 h-8 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
              </div>
            ) : selectedUser ? (
              <>
                {/* User Modal Header */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 flex-shrink-0">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-white font-bold">
                      {selectedUser.user_info.name.charAt(0)}
                    </div>
                    <div>
                      <h2 className="text-base font-bold text-slate-900">{selectedUser.user_info.name}</h2>
                      <p className="text-xs text-slate-400 font-medium">{selectedUser.user_info.role} &middot; Performance</p>
                    </div>
                  </div>
                  <button onClick={() => setSelectedUser(null)} className="w-8 h-8 flex items-center justify-center rounded-xl bg-slate-100 text-slate-500 hover:bg-slate-200 transition-all">
                    <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12" /></svg>
                  </button>
                </div>

                <div className="overflow-y-auto flex-1 px-6 py-5 space-y-6">
                  {/* Summary */}
                  <div className="grid grid-cols-3 gap-3">
                    {[
                      { label: "Converted Revenue", value: `₹${selectedUser.summary.won_value.toLocaleString("en-IN")}`, bg: "bg-emerald-50", text: "text-emerald-700" },
                      { label: "Enroll Rate", value: `${selectedUser.summary.win_rate}%`,                            bg: "bg-indigo-50",  text: "text-indigo-700" },
                      { label: "Total Leads", value: selectedUser.summary.total_leads,                               bg: "bg-slate-50",   text: "text-slate-700" },
                    ].map(s => (
                      <div key={s.label} className={`${s.bg} rounded-xl p-3 text-center`}>
                        <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-1">{s.label}</p>
                        <p className={`text-lg font-bold ${s.text}`}>{s.value}</p>
                      </div>
                    ))}
                  </div>

                  {/* Status bar */}
                  {selectedUser.summary.total_leads > 0 && (
                    <div>
                      <p className="text-xs font-semibold text-slate-500 mb-2">Lead Distribution</p>
                      <div className="flex h-3 rounded-full overflow-hidden gap-0.5">
                        {Object.entries(selectedUser.status_distribution).map(([status, count]: [any, any]) => {
                          const pct = (count / selectedUser.summary.total_leads) * 100;
                          const dotClass = statusMeta[status]?.dot || "bg-slate-300";
                          return <div key={status} className={`${dotClass} rounded-full`} style={{ width: `${pct}%` }} title={`${status}: ${count}`} />;
                        })}
                      </div>
                      <div className="flex flex-wrap gap-3 mt-2">
                        {Object.entries(selectedUser.status_distribution).map(([s, c]: [any, any]) => {
                          const dotClass = statusMeta[s]?.dot || "bg-slate-300";
                          const displayLabel = statusMeta[s]?.label || s;
                          return <div key={s} className="flex items-center gap-1.5"><div className={`w-2 h-2 rounded-full ${dotClass}`} /><span className="text-[10px] font-medium text-slate-500">{displayLabel} ({c})</span></div>;
                        })}
                      </div>
                    </div>
                  )}

                  {/* Recent leads */}
                  <div>
                    <p className="text-xs font-semibold text-slate-500 mb-3">Recent Leads</p>
                    <div className="border border-slate-100 rounded-xl overflow-hidden">
                      <table className="w-full text-left">
                        <thead className="bg-slate-50">
                          <tr className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">
                            <th className="px-4 py-3">Lead</th>
                            <th className="px-4 py-3">Date</th>
                            <th className="px-4 py-3 text-right">Value</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-50">
                          {selectedUser.recent_leads.length === 0 && (
                            <tr><td colSpan={3} className="py-8 text-center text-sm text-slate-400">No recent leads</td></tr>
                          )}
                          {selectedUser.recent_leads.map((l: any) => {
                            const statusCls = statusMeta[l.status]
                              ? `${statusMeta[l.status].text} ${statusMeta[l.status].bg}`
                              : "text-slate-500 bg-slate-50";
                            const statusLabel = statusMeta[l.status]?.label || l.status;
                            return (
                              <tr key={l.id} className="hover:bg-slate-50/50">
                                <td className="px-4 py-3">
                                  <p className="text-sm font-semibold text-slate-800">{l.name}</p>
                                  <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-md ${statusCls}`}>{statusLabel}</span>
                                </td>
                                <td className="px-4 py-3 text-xs text-slate-400">{l.date}</td>
                                <td className="px-4 py-3 text-right text-sm font-bold text-slate-700">₹{l.value.toLocaleString()}</td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>

                <div className="px-6 py-4 border-t border-slate-50 flex-shrink-0">
                  <button onClick={() => setSelectedUser(null)} className="w-full py-2.5 border border-slate-200 rounded-xl text-sm font-semibold text-slate-600 hover:bg-slate-50 transition-all">Close</button>
                </div>
              </>
            ) : selectedTeam ? (
              <>
                {/* Team Modal Header */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 flex-shrink-0">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-400 to-teal-500 flex items-center justify-center text-white font-bold">
                      <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M23 21v-2a4 4 0 00-3-3.87" /><path d="M16 3.13a4 4 0 010 7.75" /></svg>
                    </div>
                    <div>
                      <h2 className="text-base font-bold text-slate-900">{selectedTeam.team_info.name}</h2>
                      <p className="text-xs text-slate-400 font-medium">{selectedTeam.team_info.description || "Team Performance"}</p>
                    </div>
                  </div>
                  <button onClick={() => setSelectedTeam(null)} className="w-8 h-8 flex items-center justify-center rounded-xl bg-slate-100 text-slate-500 hover:bg-slate-200 transition-all">
                    <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12" /></svg>
                  </button>
                </div>

                <div className="overflow-y-auto flex-1 px-6 py-5 space-y-6">
                  {/* Summary */}
                  <div className="grid grid-cols-3 gap-3">
                    {[
                      { label: "Converted Revenue", value: `₹${selectedTeam.summary.won_value.toLocaleString("en-IN")}`, bg: "bg-emerald-50", text: "text-emerald-700" },
                      { label: "Enroll Rate", value: `${selectedTeam.summary.win_rate}%`,                            bg: "bg-indigo-50",  text: "text-indigo-700" },
                      { label: "Total Leads", value: selectedTeam.summary.total_leads,                               bg: "bg-slate-50",   text: "text-slate-700" },
                    ].map(s => (
                      <div key={s.label} className={`${s.bg} rounded-xl p-3 text-center`}>
                        <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-1">{s.label}</p>
                        <p className={`text-lg font-bold ${s.text}`}>{s.value}</p>
                      </div>
                    ))}
                  </div>

                  {/* Leaderboard */}
                  <div>
                    <h3 className="text-xs font-semibold text-slate-500 mb-3 flex items-center gap-2">
                       <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" /></svg>
                       Leaderboard
                    </h3>
                    <div className="border border-slate-100 rounded-xl overflow-hidden bg-white">
                      <table className="w-full text-left">
                        <thead className="bg-slate-50">
                          <tr className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">
                            <th className="px-4 py-3">Member</th>
                            <th className="px-4 py-3 text-right">Converted</th>
                            <th className="px-4 py-3 text-right">Revenue</th>
                            <th className="px-4 py-3 text-right">Pipeline</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-50">
                          {selectedTeam.leaderboard.length === 0 && (
                            <tr><td colSpan={4} className="py-8 text-center text-sm text-slate-400">No members with leads</td></tr>
                          )}
                          {selectedTeam.leaderboard.map((m: any, i: number) => (
                            <tr key={m.id} className="hover:bg-slate-50/50">
                              <td className="px-4 py-3">
                                <div className="flex items-center gap-2">
                                  {i === 0 && <span className="w-5 h-5 rounded flex items-center justify-center bg-amber-100 text-amber-600 font-bold text-[10px]">1</span>}
                                  {i === 1 && <span className="w-5 h-5 rounded flex items-center justify-center bg-slate-200 text-slate-600 font-bold text-[10px]">2</span>}
                                  {i === 2 && <span className="w-5 h-5 rounded flex items-center justify-center bg-orange-100 text-orange-700 font-bold text-[10px]">3</span>}
                                  {i > 2 && <span className="w-5 h-5 rounded flex items-center justify-center bg-slate-50 text-slate-400 font-bold text-[10px]">{i+1}</span>}
                                  <p className="text-sm font-semibold text-slate-800">{m.name}</p>
                                </div>
                              </td>
                              <td className="px-4 py-3 text-right text-sm font-semibold text-slate-700">{m.won_count}</td>
                              <td className="px-4 py-3 text-right text-sm font-bold text-emerald-600">₹{m.won_value.toLocaleString()}</td>
                              <td className="px-4 py-3 text-right text-sm text-slate-400">₹{m.pipeline_value.toLocaleString()}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  {/* Status bar */}
                  {selectedTeam.summary.total_leads > 0 && (
                    <div>
                      <p className="text-xs font-semibold text-slate-500 mb-2">Team Lead Distribution</p>
                      <div className="flex h-3 rounded-full overflow-hidden gap-0.5">
                        {Object.entries(selectedTeam.status_distribution).map(([status, count]: [any, any]) => {
                          const pct = (count / selectedTeam.summary.total_leads) * 100;
                          const dotClass = statusMeta[status]?.dot || "bg-slate-300";
                          return <div key={status} className={`${dotClass} rounded-full`} style={{ width: `${pct}%` }} title={`${status}: ${count}`} />;
                        })}
                      </div>
                      <div className="flex flex-wrap gap-3 mt-2">
                        {Object.entries(selectedTeam.status_distribution).map(([s, c]: [any, any]) => {
                          const dotClass = statusMeta[s]?.dot || "bg-slate-300";
                          const displayLabel = statusMeta[s]?.label || s;
                          return <div key={s} className="flex items-center gap-1.5"><div className={`w-2 h-2 rounded-full ${dotClass}`} /><span className="text-[10px] font-medium text-slate-500">{displayLabel} ({c})</span></div>;
                        })}
                      </div>
                    </div>
                  )}

                  {/* Recent leads */}
                  {(selectedTeam.recent_leads?.length > 0) && (
                    <div>
                      <p className="text-xs font-semibold text-slate-500 mb-3">Team Recent Leads</p>
                      <div className="border border-slate-100 rounded-xl overflow-hidden">
                        <table className="w-full text-left">
                          <thead className="bg-slate-50">
                            <tr className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">
                              <th className="px-4 py-3">Lead</th>
                              <th className="px-4 py-3">Agent</th>
                              <th className="px-4 py-3 text-right">Value</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-50">
                            {selectedTeam.recent_leads.map((l: any) => {
                              const statusCls = statusMeta[l.status]
                                ? `${statusMeta[l.status].text} ${statusMeta[l.status].bg}`
                                : "text-slate-500 bg-slate-50";
                              const statusLabel = statusMeta[l.status]?.label || l.status;
                              return (
                                <tr key={l.id} className="hover:bg-slate-50/50">
                                  <td className="px-4 py-3">
                                    <p className="text-sm font-semibold text-slate-800">{l.name}</p>
                                    <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-md ${statusCls}`}>{statusLabel}</span>
                                  </td>
                                  <td className="px-4 py-3 text-xs text-slate-400">{l.agent}</td>
                                  <td className="px-4 py-3 text-right text-sm font-bold text-slate-700">₹{l.value.toLocaleString()}</td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>

                <div className="px-6 py-4 border-t border-slate-50 flex-shrink-0">
                  <button onClick={() => setSelectedTeam(null)} className="w-full py-2.5 border border-slate-200 rounded-xl text-sm font-semibold text-slate-600 hover:bg-slate-50 transition-all">Close</button>
                </div>
              </>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}

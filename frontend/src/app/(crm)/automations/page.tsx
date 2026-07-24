"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import AutomationBuilder from "./components/AutomationBuilder";

const PRIORITY_MAP: Record<number, { label: string; color: string; border: string }> = {
  1: { label: "Critical", color: "bg-rose-500/10 text-rose-500", border: "border-rose-500/20" },
  2: { label: "High", color: "bg-amber-500/10 text-amber-500", border: "border-amber-500/20" },
  3: { label: "Normal", color: "bg-blue-500/10 text-blue-500", border: "border-blue-500/20" },
  4: { label: "Low", color: "bg-slate-500/10 text-slate-500", border: "border-slate-500/20" },
};

const TRIGGER_ICONS: Record<string, string> = {
  lead_created: "⚡",
  lead_status_changed: "🔄",
  lead_updated: "✏️",
  lead_converted: "🏆",
  lead_lost: "💔",
  lead_inactive: "😴",
  pushed_to_documentation: "🤝",
  payment_partially_paid: "🪙",
  payment_fully_paid: "💰",
  project_completed: "🏗️",
  doc_stage2_completed: "📄",
  warranty_completed: "🛡️",
  liasoning_completed: "🏛️",
  discom_approved: "🟢",
  discom_not_approved: "🔴",
  maintenance_scheduled: "🔧",
  task_created: "📋",
  task_completed: "✅",
  campaign_lead_added: "📢",
  call_logged: "📞",
  whatsapp_received: "💬",
};

export default function AutomationsPage({ params: paramsPromise }: { params: Promise<{ domain: string }> }) {
  const params = React.use(paramsPromise);
  const router = useRouter();
  const domain = APP_SLUG;
  const [rules, setRules] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showBuilder, setShowBuilder] = useState(false);
  const [editingRule, setEditingRule] = useState<any>(null);
  const [toggling, setToggling] = useState<number | null>(null);
  const [testing, setTesting] = useState<number | null>(null);
  const [bulkRunning, setBulkRunning] = useState<number | null>(null);
  const [testResult, setTestResult] = useState<any>(null);
  const [metaOptions, setMetaOptions] = useState<any>(null);
  const [templates, setTemplates] = useState<any[]>([]);
  const [showTemplates, setShowTemplates] = useState(false);

  useEffect(() => {
    fetchRules();
    fetchMetadata();
    fetchTemplates();
  }, [domain]);

  const fetchTemplates = async () => {
    const token = localStorage.getItem(`${domain}_access`);
    if (!token) return;
    try {
      const res = await fetch(`${getApiBase(domain)}/api/automations/templates/`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setTemplates(await res.json());
    } catch {}
  };

  const useTemplate = (t: any) => {
    // Prefill the builder with the recipe (no id ⇒ saved as a new rule).
    setEditingRule({ ...t.rule });
    setShowTemplates(false);
    setShowBuilder(true);
  };

  const TEMPLATE_ICONS: Record<string, string> = {
    shuffle: "🔀", alarm: "⏰", fire: "🔥", mail: "✉️", "phone-missed": "📵", copy: "🧬",
  };

  const fetchRules = async () => {
    const token = localStorage.getItem(`${domain}_access`);
    if (!token) return;
    try {
      const res = await fetch(`${getApiBase(domain)}/api/automations/`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setRules(data.results || data);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const fetchMetadata = async () => {
    const token = localStorage.getItem(`${domain}_access`);
    if (!token) return;
    try {
      const res = await fetch(`${getApiBase(domain)}/api/automations/metadata_options/`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setMetaOptions(await res.json());
    } catch {}
  };

  const handleToggle = async (id: number) => {
    const token = localStorage.getItem(`${domain}_access`);
    if (!token) return;
    setToggling(id);
    try {
      const res = await fetch(`${getApiBase(domain)}/api/automations/${id}/toggle/`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setRules((prev) =>
          prev.map((r) => (r.id === id ? { ...r, is_active: data.is_active } : r))
        );
      }
    } catch {} finally {
      setToggling(null);
    }
  };

  const handleTest = async (id: number) => {
    const token = localStorage.getItem(`${domain}_access`);
    if (!token) return;
    setTesting(id);
    setTestResult(null);
    try {
      const res = await fetch(`${getApiBase(domain)}/api/automations/${id}/test/`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      setTestResult({ ruleId: id, ...data });
    } catch (e: any) {
      setTestResult({ ruleId: id, error: e.message });
    } finally {
      setTesting(null);
    }
  };

  const handleBulkRun = async (id: number) => {
    if (!confirm("Are you sure? This will execute this automation against up to 500 existing records simultaneously. This action cannot be undone.")) return;
    const token = localStorage.getItem(`${domain}_access`);
    if (!token) return;
    setBulkRunning(id);
    setTestResult(null);
    try {
      const res = await fetch(`${getApiBase(domain)}/api/automations/${id}/bulk_run/`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      setTestResult({ 
          ruleId: id, 
          message: data.message, 
          log: { 
              status: data.failed > data.success ? 'skipped' : 'success', 
              error_message: `Success: ${data.success} | Skipped: ${data.skipped} | Failed: ${data.failed}` 
          } 
      });
      fetchRules(); // Refresh stats
    } catch (e: any) {
      setTestResult({ ruleId: id, error: e.message });
    } finally {
      setBulkRunning(null);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Delete this automation rule? This cannot be undone.")) return;
    const token = localStorage.getItem(`${domain}_access`);
    if (!token) return;
    try {
      await fetch(`${getApiBase(domain)}/api/automations/${id}/`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      setRules((prev) => prev.filter((r) => r.id !== id));
    } catch {}
  };

  const handleEdit = (rule: any) => {
    setEditingRule(rule);
    setShowBuilder(true);
  };

  const successRate = (r: any) => {
    if (r.execution_count === 0) return null;
    return Math.round((r.success_count / r.execution_count) * 100);
  };

  const timeAgo = (dt: string | null) => {
    if (!dt) return "Never";
    const diff = Date.now() - new Date(dt).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "Just now";
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    const days = Math.floor(hrs / 24);
    return `${days}d ago`;
  };

  return (
    <div className="min-h-screen bg-[#0A0A0B] text-slate-200 font-sans selection:bg-indigo-500/30">
      {/* Premium Background Effects */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none z-0">
        <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] rounded-full bg-indigo-900/20 blur-[120px]" />
        <div className="absolute bottom-[-10%] right-[-5%] w-[30%] h-[50%] rounded-full bg-violet-900/10 blur-[150px]" />
        <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI0IiBoZWlnaHQ9IjQiPgoJPHJlY3Qgd2lkdGg9IjQiIGhlaWdodD0iNCIgZmlsbD0iI2ZmZiIgZmlsbC1vcGFjaXR5PSIwLjAxIi8+Cjwvc3ZnPg==')] opacity-50 z-0"></div>
      </div>

      <div className="relative z-10 flex flex-col h-screen overflow-hidden">
        {/* Header */}
        <header className="flex-shrink-0 border-b border-white/5 bg-black/40 backdrop-blur-xl">
          <div className="max-w-[1600px] mx-auto px-6 h-24 flex items-center justify-between">
            <div className="flex flex-col gap-1">
              <h1 className="text-3xl font-extrabold tracking-tight text-white flex items-center gap-3">
                <span className="p-2 bg-gradient-to-br from-indigo-500/20 to-violet-500/20 text-indigo-400 rounded-xl border border-indigo-500/20 shadow-[0_0_15px_rgba(99,102,241,0.2)]">
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
                </span>
                Automations
              </h1>
              <p className="text-sm font-medium text-slate-400 pl-14">
                Design and deploy intelligent event-driven workflows.
              </p>
            </div>
            
            <div className="flex items-center gap-3">
            <button
              onClick={() => setShowTemplates(true)}
              className="flex items-center gap-2 px-5 py-3 bg-white/5 border border-white/10 text-white rounded-xl font-bold transition-all hover:bg-white/10 active:scale-95"
            >
              <span className="text-base">✨</span>
              <span className="tracking-wide text-xs font-extrabold uppercase">Templates</span>
            </button>
            <button
              onClick={() => { setEditingRule(null); setShowBuilder(true); }}
              className="group relative flex items-center gap-2 px-6 py-3 bg-white text-black rounded-xl font-bold transition-all hover:scale-[1.02] active:scale-95 overflow-hidden shadow-[0_0_20px_rgba(255,255,255,0.15)]"
            >
              <div className="absolute inset-0 bg-gradient-to-r from-red-200 via-violet-200 to-indigo-200 opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
              <div className="absolute inset-0 opacity-0 group-hover:opacity-20 transition-opacity duration-300 bg-[url('data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI4IiBoZWlnaHQ9IjgiPgoJPHJlY3Qgd2lkdGg9IjgiIGhlaWdodD0iOCIgZmlsbD0iI2ZmZiIgZmlsbC1vcGFjaXR5PSIwLjI1Ii8+Cjwvc3ZnPg==')]" />
              <svg className="relative z-10 w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>
              <span className="relative z-10 tracking-wide text-sm font-extrabold uppercase">New Pipeline</span>
            </button>
            </div>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto w-full max-w-[1600px] mx-auto px-6 py-10 scrollbar-hide">
          {/* Stats Row */}
          {!loading && rules.length > 0 && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-10">
              {[
                { label: "Active Pipelines", value: rules.filter(r => r.is_active).length, acc: "bg-emerald-500/20 text-emerald-400 border-emerald-500/20" },
                { label: "Total Executions", value: rules.reduce((a, r) => a + r.execution_count, 0).toLocaleString(), acc: "bg-indigo-500/20 text-indigo-400 border-indigo-500/20" },
                { label: "Total Configured", value: rules.length, acc: "bg-slate-700/50 text-slate-300 border-white/5" },
                { label: "Global Success Rate", value: (() => {
                    const total = rules.reduce((a, r) => a + r.execution_count, 0);
                    const success = rules.reduce((a, r) => a + r.success_count, 0);
                    return total > 0 ? `${Math.round((success / total) * 100)}%` : "—";
                  })(), acc: "bg-violet-500/20 text-violet-400 border-violet-500/20" }
              ].map((stat, i) => (
                <div key={i} className="relative group p-6 rounded-2xl bg-white/[0.02] border border-white/5 backdrop-blur-sm overflow-hidden hover:bg-white/[0.04] transition-colors">
                  <div className={`absolute top-0 right-0 w-32 h-32 bg-gradient-to-br from-white/5 to-transparent rounded-full blur-2xl -mr-16 -mt-16 transition-opacity opacity-50 group-hover:opacity-100`} />
                  <div className="relative z-10">
                    <div className="flex items-center gap-3 mb-2">
                      <div className={`w-2.5 h-2.5 rounded-full ${stat.acc.split(' ')[0]}`} />
                      <div className="text-xs font-bold text-slate-500 uppercase tracking-widest">{stat.label}</div>
                    </div>
                    <div className={`text-4xl font-black tracking-tight ${stat.acc.split(' ')[1]}`}>{stat.value}</div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Rules List */}
          {loading ? (
            <div className="flex justify-center py-32">
              <div className="relative flex items-center justify-center w-16 h-16">
                 <div className="absolute inset-0 bg-indigo-500/30 rounded-full blur-xl animate-pulse"></div>
                 <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-r-2 border-indigo-400 relative z-10"></div>
              </div>
            </div>
          ) : rules.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-32 text-center bg-white/[0.02] border border-white/5 rounded-3xl backdrop-blur-sm shadow-2xl">
              <div className="w-24 h-24 bg-gradient-to-br from-indigo-500/20 to-violet-500/20 border border-white/10 rounded-full flex items-center justify-center mb-8 shadow-[0_0_30px_rgba(99,102,241,0.15)] glow-pulse">
                <span className="text-4xl">⚡</span>
              </div>
              <h3 className="text-2xl font-bold text-white mb-3">Your workspace lacks automation</h3>
              <p className="text-slate-400 mb-8 max-w-md mx-auto leading-relaxed">
                Start building visual pipelines to streamline your lead follow-ups, handle state changes automatically, and supercharge your team's efficiency out-of-the-box.
              </p>
              <button
                onClick={() => { setEditingRule(null); setShowBuilder(true); }}
                className="group relative px-8 py-3.5 bg-indigo-600 text-white rounded-xl font-bold transition-all hover:bg-indigo-500 shadow-[0_0_20px_rgba(79,70,229,0.3)] hover:shadow-[0_0_30px_rgba(79,70,229,0.5)] active:scale-95"
              >
                Assemble First Pipeline
              </button>
            </div>
          ) : (
            <div className="flex flex-col gap-4">
              {rules.map((rule) => {
                const pr = PRIORITY_MAP[rule.priority] || PRIORITY_MAP[3];
                const rate = successRate(rule);
                const isActive = rule.is_active;
                
                return (
                  <div
                    key={rule.id}
                    className={`group relative flex flex-col bg-white/[0.02] backdrop-blur-md border rounded-2xl transition-all duration-300 hover:bg-white/[0.04] ${
                      isActive ? "border-white/[0.08] shadow-lg shadow-black/20" : "border-white/[0.03] opacity-60 hover:opacity-100"
                    }`}
                  >
                    <div className="flex items-center p-6 gap-6">
                      
                      {/* Toggle */}
                      <button
                        onClick={() => handleToggle(rule.id)}
                        disabled={toggling === rule.id}
                        className={`relative w-12 h-6 rounded-full transition-all duration-300 flex-shrink-0 border focus:outline-none ${
                          isActive ? "bg-indigo-600 border-indigo-500/50 shadow-[0_0_15px_rgba(79,70,229,0.4)]" : "bg-slate-800 border-slate-700 hover:bg-slate-700"
                        }`}
                      >
                        <span className={`absolute top-[2px] left-[2px] w-4 h-4 bg-white rounded-full shadow-sm transition-transform duration-300 ${
                          isActive ? "translate-x-6" : "translate-x-0"
                        }`} />
                      </button>

                      {/* Info core */}
                      <div className="flex-1 min-w-0 pr-6 border-r border-white/5">
                        <div className="flex items-center gap-3 mb-2">
                           <span className="text-xl opacity-80 filter drop-shadow-[0_0_8px_rgba(255,255,255,0.3)]">
                             {TRIGGER_ICONS[rule.trigger_event] || "⚡"}
                           </span>
                           <h3
                            className="text-lg font-bold text-white truncate cursor-pointer hover:text-indigo-400 transition-colors"
                            onClick={() => handleEdit(rule)}
                           >
                            {rule.name}
                           </h3>
                           <div className={`px-2.5 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wider border ${pr.color} ${pr.border}`}>
                             {pr.label}
                           </div>
                        </div>
                        {rule.description && (
                          <p className="text-sm text-slate-400 line-clamp-1 mb-3">{rule.description}</p>
                        )}
                        
                        {/* Pipeline visualizer preview */}
                        <div className="flex items-center text-xs font-semibold text-slate-500">
                          <span className="bg-white/5 px-2.5 py-1 rounded-md text-slate-300 border border-white/5 flex items-center gap-2">
                             <div className="w-1.5 h-1.5 rounded-full bg-blue-500"></div> Trigger
                          </span>
                          <div className="w-4 h-px bg-white/10 mx-1"></div>
                          <span className="bg-white/5 px-2.5 py-1 rounded-md text-slate-300 border border-white/5 flex items-center gap-2">
                            <div className="w-1.5 h-1.5 rounded-full bg-amber-500"></div> {(rule.conditions || []).length} Condition{(rule.conditions || []).length !== 1 ? "s" : ""}
                          </span>
                          <div className="w-4 h-px bg-white/10 mx-1"></div>
                          <span className="bg-white/5 px-2.5 py-1 rounded-md text-slate-300 border border-white/5 flex items-center gap-2">
                            <div className="w-1.5 h-1.5 rounded-full bg-emerald-500"></div> {(rule.actions || []).length} Action{(rule.actions || []).length !== 1 ? "s" : ""}
                          </span>
                        </div>
                      </div>

                      {/* Performance Metrics */}
                      <div className="flex items-center gap-8 pl-4 flex-shrink-0">
                         <div className="flex flex-col items-center">
                            <span className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-1">Runs</span>
                            <span className="text-lg font-black text-white">{rule.execution_count}</span>
                         </div>
                         {rate !== null && (
                          <div className="flex flex-col items-center">
                             <span className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-1">Success</span>
                             <span className={`text-lg font-black ${rate >= 80 ? "text-emerald-400" : rate >= 50 ? "text-amber-400" : "text-rose-400"}`}>
                               {rate}%
                             </span>
                          </div>
                         )}
                         <div className="flex flex-col items-center w-24">
                            <span className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-1">Last Sync</span>
                            <span className="text-sm font-semibold text-slate-300">{timeAgo(rule.last_executed_at)}</span>
                         </div>
                      </div>

                      {/* Operations */}
                      <div className="flex items-center gap-2 pl-4 flex-shrink-0">
                        <button
                          onClick={() => handleTest(rule.id)}
                          disabled={testing === rule.id}
                          className="w-10 h-10 flex items-center justify-center rounded-xl bg-white/[0.03] text-slate-400 border border-white/[0.05] hover:bg-indigo-500/20 hover:text-indigo-300 hover:border-indigo-500/30 transition-all shadow-sm"
                          title="Run Test Pipeline"
                        >
                          {testing === rule.id ? (
                            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-indigo-400"></div>
                          ) : (
                            <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                          )}
                        </button>
                        <button
                          onClick={() => handleBulkRun(rule.id)}
                          disabled={bulkRunning === rule.id}
                          className="w-10 h-10 flex items-center justify-center rounded-xl bg-white/[0.03] text-slate-400 border border-white/[0.05] hover:bg-emerald-500/20 hover:text-emerald-300 hover:border-emerald-500/30 transition-all shadow-sm"
                          title="Run Retroactively (Bulk)"
                        >
                          {bulkRunning === rule.id ? (
                            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-emerald-400"></div>
                          ) : (
                            <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
                          )}
                        </button>
                        <button
                          onClick={() => handleEdit(rule)}
                          className="w-10 h-10 flex items-center justify-center rounded-xl bg-white/[0.03] text-slate-400 border border-white/[0.05] hover:bg-blue-500/20 hover:text-blue-300 hover:border-blue-500/30 transition-all shadow-sm"
                          title="Edit Canvas"
                        >
                          <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                        </button>
                        <button
                          onClick={() => router.push(`/automations/${rule.id}`)}
                          className="w-10 h-10 flex items-center justify-center rounded-xl bg-white/[0.03] text-slate-400 border border-white/[0.05] hover:bg-slate-700 hover:text-white transition-all shadow-sm"
                          title="View Execution Logs"
                        >
                          <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
                        </button>
                        <button
                          onClick={() => handleDelete(rule.id)}
                          className="w-10 h-10 flex items-center justify-center rounded-xl bg-white/[0.03] text-slate-400 border border-white/[0.05] hover:bg-rose-500/20 hover:text-rose-300 hover:border-rose-500/30 transition-all shadow-sm group-hover:opacity-100 opacity-60"
                          title="Destroy"
                        >
                          <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>
                        </button>
                      </div>
                    </div>

                    {/* Test result banner */}
                    {testResult && testResult.ruleId === rule.id && (
                      <div className={`px-6 py-3 border-t border-white/[0.05] flex items-center justify-between shadow-inner ${
                        testResult.error ? "bg-rose-900/20 text-rose-300" :
                        testResult.log?.status === 'success' ? "bg-emerald-900/20 text-emerald-300" :
                        testResult.log?.status === 'skipped' ? "bg-amber-900/20 text-amber-300" :
                        "bg-blue-900/20 text-blue-300"
                      }`}>
                        <span className="text-sm font-semibold flex items-center gap-2">
                          {testResult.error ? `❌ ${testResult.error}` :
                            `${testResult.log?.status === 'success' ? '✅' : testResult.log?.status === 'skipped' ? '⏭️' : '⚠️'} ${testResult.message} — ${testResult.log?.status || 'unknown'} pipeline trace`}
                          {testResult.log?.error_message && ` — ${testResult.log.error_message}`}
                        </span>
                        <button onClick={() => setTestResult(null)} className="text-current opacity-60 hover:opacity-100 transition-opacity">
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </main>

        {/* Builder Modal / Canvas Fullscreen Wrapper */}
        {showTemplates && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm" onClick={() => setShowTemplates(false)}>
            <div className="bg-[#0d0d11] border border-white/10 rounded-3xl w-full max-w-3xl max-h-[85vh] overflow-hidden flex flex-col shadow-2xl" onClick={e => e.stopPropagation()}>
              <div className="px-6 py-5 border-b border-white/10 flex items-center justify-between flex-shrink-0">
                <div>
                  <h2 className="text-xl font-black text-white flex items-center gap-2">✨ Automation Templates</h2>
                  <p className="text-sm text-slate-400 mt-0.5">Install a prebuilt recipe, then tweak it for your team.</p>
                </div>
                <button onClick={() => setShowTemplates(false)} className="w-9 h-9 rounded-xl bg-white/5 border border-white/10 text-slate-400 hover:text-white flex items-center justify-center transition-colors">✕</button>
              </div>
              <div className="overflow-y-auto p-6 grid sm:grid-cols-2 gap-4">
                {templates.length === 0 && (
                  <p className="text-slate-500 text-sm col-span-full text-center py-8">No templates available.</p>
                )}
                {templates.map((t) => (
                  <button key={t.key} onClick={() => useTemplate(t)} className="text-left p-5 bg-[#16161a] border border-white/10 rounded-2xl hover:border-indigo-500/40 hover:bg-white/[0.04] transition-all group">
                    <div className="flex items-center gap-3 mb-2">
                      <span className="w-10 h-10 rounded-xl bg-indigo-500/15 border border-indigo-500/20 flex items-center justify-center text-xl flex-shrink-0">{TEMPLATE_ICONS[t.icon] || "⚡"}</span>
                      <h3 className="font-bold text-white text-sm group-hover:text-indigo-300 transition-colors">{t.name}</h3>
                    </div>
                    <p className="text-xs text-slate-400 leading-relaxed mb-3">{t.description}</p>
                    <div className="flex flex-wrap gap-1.5">
                      {(t.rule?.actions || []).slice(0, 5).map((a: any, i: number) => (
                        <span key={i} className="text-[10px] font-semibold px-2 py-0.5 rounded-md bg-white/5 border border-white/10 text-slate-400">
                          {a.type === "wait" ? `wait ${a.params?.amount || ""}${(a.params?.unit || "d")[0]}` : a.type.replace(/_/g, " ")}
                        </span>
                      ))}
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {showBuilder && (
          <AutomationBuilder
            domain={domain}
            metaOptions={metaOptions}
            editingRule={editingRule}
            onClose={() => { setShowBuilder(false); setEditingRule(null); }}
            onSuccess={() => { setShowBuilder(false); setEditingRule(null); fetchRules(); }}
          />
        )}
      </div>
    </div>
  );
}


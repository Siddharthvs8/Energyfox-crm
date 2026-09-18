"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";

const STATUS_COLORS: Record<string, string> = {
  success: "bg-emerald-100 text-emerald-700",
  partial: "bg-amber-100 text-amber-700",
  failed: "bg-red-100 text-red-700",
  skipped: "bg-slate-100 text-slate-500",
};
const STATUS_ICONS: Record<string, string> = {
  success: "✅", partial: "⚠️", failed: "❌", skipped: "⏭️",
};

const TRIGGER_LABELS: Record<string, string> = {
  lead_created: "Lead Created", lead_status_changed: "Lead Status Changed",
  lead_updated: "Lead Updated", lead_converted: "Lead Converted",
  lead_lost: "Deal Marked Lost", lead_inactive: "Lead Inactive",
  pushed_to_documentation: "Closed Deal (Pushed to Documentation)",
  payment_partially_paid: "Payment Verified — Partially Paid",
  payment_fully_paid: "Payment Fully Paid (moves to Purchase)",
  project_completed: "Project Completed",
  doc_stage2_completed: "Documentation Stage 2 Completed",
  warranty_completed: "Warranty Completed",
  liasoning_completed: "Liasoning & Service Completed",
  discom_approved: "Discom Approval — Approved",
  discom_not_approved: "Discom Approval — Not Approved",
  maintenance_scheduled: "Periodic Maintenance Scheduled",
  task_created: "Task Created",
  task_completed: "Task Completed", campaign_lead_added: "Lead Added to Campaign",
  call_logged: "Call Logged", whatsapp_received: "WhatsApp Reply Received",
};

const ACTION_LABELS: Record<string, string> = {
  assign_lead: "Assign Lead", change_status: "Change Status", create_task: "Create Task",
  add_to_campaign: "Add to Campaign", send_webhook: "Send Webhook",
  send_notification: "Send Notification", update_field: "Update Field",
  add_note: "Add Note", duplicate_check: "Duplicate Check",
};

export default function AutomationDetailPage({
  params: paramsPromise,
}: {
  params: Promise<{ domain: string; id: string }>;
}) {
  const params = React.use(paramsPromise);
  const router = useRouter();
  const { id } = params;
  const domain = APP_SLUG;
  const [rule, setRule] = useState<any>(null);
  const [logs, setLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedLog, setExpandedLog] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<"overview" | "logs">("overview");

  useEffect(() => {
    fetchData();
  }, [domain, id]);

  const fetchData = async () => {
    const token = localStorage.getItem(`${domain}_access`);
    if (!token) return;
    try {
      const [ruleRes, logsRes] = await Promise.all([
        fetch(`${getApiBase(domain)}/api/automations/${id}/`, { headers: { Authorization: `Bearer ${token}` } }),
        fetch(`${getApiBase(domain)}/api/automations/${id}/logs/`, { headers: { Authorization: `Bearer ${token}` } }),
      ]);
      if (ruleRes.ok) setRule(await ruleRes.json());
      if (logsRes.ok) setLogs(await logsRes.json());
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleToggle = async () => {
    const token = localStorage.getItem(`${domain}_access`);
    if (!token || !rule) return;
    try {
      const res = await fetch(`${getApiBase(domain)}/api/automations/${id}/toggle/`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setRule({ ...rule, is_active: data.is_active });
      }
    } catch {}
  };

  const handleDelete = async () => {
    if (!confirm("Delete this automation? This action cannot be undone.")) return;
    const token = localStorage.getItem(`${domain}_access`);
    if (!token) return;
    try {
      await fetch(`${getApiBase(domain)}/api/automations/${id}/`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      router.push(`/automations`);
    } catch {}
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-[#f5f7fb] flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
      </div>
    );
  }

  if (!rule) {
    return (
      <div className="min-h-screen bg-[#f5f7fb] flex items-center justify-center">
        <div className="text-center">
          <p className="text-slate-500 text-lg mb-4">Automation not found</p>
          <button onClick={() => router.push(`/automations`)} className="text-indigo-600 font-bold hover:underline">
            ← Back to Automations
          </button>
        </div>
      </div>
    );
  }

  const successRate = rule.execution_count > 0 ? Math.round((rule.success_count / rule.execution_count) * 100) : null;

  return (
    <div className="min-h-screen bg-[#f5f7fb]">
      {/* Header */}
      <header className="bg-white border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-20 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => router.push(`/automations`)}
              className="p-2 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-all"
            >
              <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M19 12H5"/><path d="M12 19l-7-7 7-7"/></svg>
            </button>
            <div>
              <h1 className="text-xl font-black text-slate-800 tracking-tight flex items-center gap-2.5">
                <span>⚡</span> {rule.name}
              </h1>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-0.5">
                <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider whitespace-nowrap flex-shrink-0 ${rule.is_active ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>
                  {rule.is_active ? "● Active" : "○ Paused"}
                </span>
                <span className="text-xs text-slate-400">Created {new Date(rule.created_at).toLocaleDateString('en-IN', { month: 'short', day: 'numeric', year: 'numeric' })}</span>
                {rule.created_by_name && (
                  <span className="text-xs text-slate-400">by {rule.created_by_name}</span>
                )}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button onClick={handleToggle} className={`px-4 py-2 rounded-xl font-bold text-sm transition-all ${rule.is_active ? "bg-amber-50 text-amber-600 hover:bg-amber-100" : "bg-emerald-50 text-emerald-600 hover:bg-emerald-100"}`}>
              {rule.is_active ? "Pause" : "Enable"}
            </button>
            <button onClick={handleDelete} className="px-4 py-2 rounded-xl font-bold text-sm bg-red-50 text-red-600 hover:bg-red-100 transition-all">
              Delete
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Stats */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">
          <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm">
            <div className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">Total Runs</div>
            <div className="text-3xl font-black text-slate-800">{rule.execution_count}</div>
          </div>
          <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm">
            <div className="text-xs font-bold text-emerald-500 uppercase tracking-wider mb-1">Successes</div>
            <div className="text-3xl font-black text-emerald-600">{rule.success_count}</div>
          </div>
          <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm">
            <div className="text-xs font-bold text-red-400 uppercase tracking-wider mb-1">Failures</div>
            <div className="text-3xl font-black text-red-500">{rule.failure_count}</div>
          </div>
          <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm">
            <div className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">Success Rate</div>
            <div className={`text-3xl font-black ${successRate !== null ? (successRate >= 80 ? "text-emerald-600" : successRate >= 50 ? "text-amber-600" : "text-red-500") : "text-slate-300"}`}>
              {successRate !== null ? `${successRate}%` : "—"}
            </div>
          </div>
          <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm">
            <div className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">Last Run</div>
            <div className="text-sm font-bold text-slate-600 mt-1">
              {rule.last_executed_at ? new Date(rule.last_executed_at).toLocaleString('en-IN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : "Never"}
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 bg-slate-100 rounded-xl p-1 mb-6 w-fit">
          <button onClick={() => setActiveTab("overview")} className={`px-5 py-2 rounded-lg text-sm font-bold transition-all ${activeTab === "overview" ? "bg-white shadow text-slate-800" : "text-slate-500 hover:text-slate-700"}`}>
            Overview
          </button>
          <button onClick={() => setActiveTab("logs")} className={`px-5 py-2 rounded-lg text-sm font-bold transition-all ${activeTab === "logs" ? "bg-white shadow text-slate-800" : "text-slate-500 hover:text-slate-700"}`}>
            Execution Logs ({logs.length})
          </button>
        </div>

        {/* Overview Tab */}
        {activeTab === "overview" && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Trigger */}
            <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm">
              <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-4">Trigger</h3>
              <div className="flex items-center gap-3 mb-3">
                <div className="w-10 h-10 bg-indigo-100 rounded-xl flex items-center justify-center text-xl">
                  {({lead_created:"🆕",lead_status_changed:"🔄",lead_updated:"✏️",task_created:"📋",task_completed:"✅",campaign_lead_added:"📢"} as any)[rule.trigger_event] || "⚡"}
                </div>
                <div>
                  <div className="font-bold text-slate-800">{TRIGGER_LABELS[rule.trigger_event] || rule.trigger_event}</div>
                  {rule.trigger_config && Object.keys(rule.trigger_config).length > 0 && (
                    <div className="text-xs text-slate-500">
                      {rule.trigger_config.from_status && `From: ${rule.trigger_config.from_status}`}
                      {rule.trigger_config.from_status && rule.trigger_config.to_status && " → "}
                      {rule.trigger_config.to_status && `To: ${rule.trigger_config.to_status}`}
                    </div>
                  )}
                </div>
              </div>
              <div className="text-xs text-slate-400 space-y-1 mt-4 pt-4 border-t border-slate-100">
                <div className="flex justify-between"><span>Rate Limit</span><span className="font-semibold text-slate-600">{rule.max_executions_per_hour}/hr</span></div>
                <div className="flex justify-between"><span>Cooldown</span><span className="font-semibold text-slate-600">{rule.cooldown_seconds}s</span></div>
              </div>
            </div>

            {/* Conditions */}
            <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm">
              <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-4">
                Conditions {rule.conditions?.length > 0 && <span className="text-indigo-500 ml-1">({rule.condition_logic.toUpperCase()})</span>}
              </h3>
              {(rule.conditions || []).length === 0 ? (
                <p className="text-sm text-slate-400 italic">No conditions — fires on every trigger</p>
              ) : (
                <div className="space-y-2">
                  {rule.conditions.map((c: any, i: number) => (
                    <div key={i} className="flex items-center gap-2">
                      {i > 0 && (
                        <span className="text-[10px] font-black text-indigo-500 bg-indigo-50 px-2 py-0.5 rounded-full">
                          {rule.condition_logic === 'all' ? 'AND' : 'OR'}
                        </span>
                      )}
                      <div className="flex-1 bg-slate-50 rounded-lg px-3 py-2 text-sm">
                        <span className="font-semibold text-slate-700">{c.field}</span>{" "}
                        <span className="text-indigo-600 font-medium">{c.operator}</span>{" "}
                        {c.value && <span className="text-slate-600">&quot;{c.value}&quot;</span>}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Actions */}
            <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm md:col-span-2">
              <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-4">Action Pipeline</h3>
              <div className="flex flex-wrap gap-3">
                {(rule.actions || []).map((a: any, i: number) => (
                  <React.Fragment key={i}>
                    <div className="bg-slate-50 rounded-xl p-4 border border-slate-100 min-w-[200px]">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="w-6 h-6 bg-indigo-100 text-indigo-600 rounded-full flex items-center justify-center text-[10px] font-bold">{i + 1}</span>
                        <span className="font-bold text-sm text-slate-700">{ACTION_LABELS[a.type] || a.type}</span>
                      </div>
                      {a.params && Object.keys(a.params).length > 0 && (
                        <div className="text-xs text-slate-400 space-y-0.5">
                          {Object.entries(a.params).filter(([,v]) => v !== undefined && v !== '' && v !== null).map(([k, v]) => (
                            <div key={k}><span className="text-slate-500">{k}:</span> <span className="text-slate-700 font-medium">{String(v)}</span></div>
                          ))}
                        </div>
                      )}
                    </div>
                    {i < (rule.actions || []).length - 1 && (
                      <div className="flex items-center text-slate-300">
                        <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M5 12h14"/><path d="M12 5l7 7-7 7"/></svg>
                      </div>
                    )}
                  </React.Fragment>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Logs Tab */}
        {activeTab === "logs" && (
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
            {logs.length === 0 ? (
              <div className="text-center py-16">
                <div className="w-16 h-16 bg-slate-50 rounded-full flex items-center justify-center mx-auto mb-4">
                  <svg width="24" height="24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-slate-300" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" strokeLinecap="round"/></svg>
                </div>
                <p className="text-slate-400 font-medium">No execution logs yet</p>
                <p className="text-sm text-slate-400 mt-1">Logs will appear here when this automation runs</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-200">
                      <th className="px-5 py-3.5 text-xs font-bold text-slate-500 uppercase tracking-wider">Status</th>
                      <th className="px-5 py-3.5 text-xs font-bold text-slate-500 uppercase tracking-wider">Trigger</th>
                      <th className="px-5 py-3.5 text-xs font-bold text-slate-500 uppercase tracking-wider">Object</th>
                      <th className="px-5 py-3.5 text-xs font-bold text-slate-500 uppercase tracking-wider">Conditions</th>
                      <th className="px-5 py-3.5 text-xs font-bold text-slate-500 uppercase tracking-wider">Time</th>
                      <th className="px-5 py-3.5 text-xs font-bold text-slate-500 uppercase tracking-wider">Timestamp</th>
                      <th className="px-5 py-3.5 text-xs font-bold text-slate-500 uppercase tracking-wider w-10"></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {logs.map((log) => (
                      <React.Fragment key={log.id}>
                        <tr
                          className="hover:bg-slate-50 transition-colors cursor-pointer"
                          onClick={() => setExpandedLog(expandedLog === log.id ? null : log.id)}
                        >
                          <td className="px-5 py-3.5">
                            <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-bold uppercase tracking-wider ${STATUS_COLORS[log.status] || "bg-slate-100 text-slate-500"}`}>
                              {STATUS_ICONS[log.status]} {log.status}
                            </span>
                          </td>
                          <td className="px-5 py-3.5 text-sm text-slate-600">{TRIGGER_LABELS[log.trigger_event] || log.trigger_event}</td>
                          <td className="px-5 py-3.5 text-sm text-slate-600">
                            <span className="bg-slate-100 px-2 py-0.5 rounded text-xs font-mono">
                              {log.trigger_object_type} #{log.trigger_object_id}
                            </span>
                          </td>
                          <td className="px-5 py-3.5 text-sm">
                            {log.conditions_matched ? (
                              <span className="text-emerald-600 font-medium">✓ Matched</span>
                            ) : (
                              <span className="text-slate-400">✗ No match</span>
                            )}
                          </td>
                          <td className="px-5 py-3.5 text-sm text-slate-500">{log.execution_time_ms}ms</td>
                          <td className="px-5 py-3.5 text-xs text-slate-400">
                            {new Date(log.created_at).toLocaleString('en-IN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                          </td>
                          <td className="px-5 py-3.5">
                            <svg
                              width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"
                              viewBox="0 0 24 24"
                              className={`text-slate-400 transition-transform ${expandedLog === log.id ? "rotate-180" : ""}`}
                            >
                              <path d="M6 9l6 6 6-6"/>
                            </svg>
                          </td>
                        </tr>
                        {expandedLog === log.id && (
                          <tr>
                            <td colSpan={7} className="px-5 pb-5">
                              <div className="bg-slate-50 rounded-xl p-4 space-y-4">
                                {/* Error message */}
                                {log.error_message && (
                                  <div className="bg-red-50 border border-red-100 rounded-lg px-4 py-3 text-sm text-red-700">
                                    <span className="font-bold">Error:</span> {log.error_message}
                                  </div>
                                )}
                                {/* Actions executed */}
                                {log.actions_executed && log.actions_executed.length > 0 && (
                                  <div>
                                    <div className="text-xs font-bold text-slate-400 uppercase mb-2">Actions Executed</div>
                                    <div className="space-y-1.5">
                                      {log.actions_executed.map((a: any, i: number) => (
                                        <div key={i} className={`flex items-center gap-3 px-3 py-2 rounded-lg ${a.status === 'success' ? 'bg-emerald-50' : 'bg-red-50'}`}>
                                          <span className="text-xs">{a.status === 'success' ? '✅' : '❌'}</span>
                                          <span className="text-sm font-medium text-slate-700">{ACTION_LABELS[a.type] || a.type}</span>
                                          <span className="text-xs text-slate-500 ml-auto">{a.detail}</span>
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                )}
                                {/* Trigger data */}
                                {log.trigger_data && Object.keys(log.trigger_data).length > 0 && (
                                  <details>
                                    <summary className="text-xs font-bold text-slate-400 uppercase cursor-pointer hover:text-slate-600">Trigger Data Snapshot</summary>
                                    <pre className="mt-2 bg-white rounded-lg p-3 text-xs text-slate-600 overflow-x-auto border border-slate-200">
                                      {JSON.stringify(log.trigger_data, null, 2)}
                                    </pre>
                                  </details>
                                )}
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}

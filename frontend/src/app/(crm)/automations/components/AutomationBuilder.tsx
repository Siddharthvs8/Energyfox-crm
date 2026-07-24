"use client";
import { getApiBase } from "@/lib/mock-data";
import { useLeadStatuses } from "@/hooks/useLeadStatuses";

import React, { useState, useEffect, useRef } from "react";

interface Props {
  domain: string;
  metaOptions: any;
  editingRule: any | null;
  onClose: () => void;
  onSuccess: () => void;
}

const ACTION_LABELS: Record<string, string> = {
  ai_auto_assign: "🤖 AI Auto-Assign (Smart)",
  assign_lead: "Assign to Specific User", change_status: "Change Status", create_task: "Create Task",
  add_to_campaign: "Add to Campaign", send_webhook: "Send Webhook",
  send_notification: "Send Notification", update_field: "Update Field",
  add_note: "Add Note", duplicate_check: "Duplicate Check",
  reassign_employee_leads: "Reassign Employee Leads",
  send_email: "Send Email", escalate_to_manager: "Escalate to Manager",
  notify_assignee: "Notify Lead Owner", wait: "⏳ Wait / Delay",
  send_whatsapp: "Send WhatsApp",
};
const ACTION_ICONS: Record<string, string> = {
  ai_auto_assign: "🤖",
  assign_lead: "👤", change_status: "🔄", create_task: "📋",
  add_to_campaign: "📢", send_webhook: "🔗", send_notification: "🔔",
  update_field: "✏️", add_note: "📝", duplicate_check: "🔍",
  reassign_employee_leads: "🔀",
  send_email: "✉️", escalate_to_manager: "🚨", notify_assignee: "🛎️", wait: "⏳",
  send_whatsapp: "💬",
};

export default function AutomationBuilder({ domain, metaOptions, editingRule, onClose, onSuccess }: Props) {
  const { statusOptions } = useLeadStatuses(domain);

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  // Visual Pipeline State
  const [drawerOpen, setDrawerOpen] = useState<'settings'|'trigger'|'conditions'|'action'>('settings');
  const [drawerActionIndex, setDrawerActionIndex] = useState<number | null>(null);

  // Form state
  const [name, setName] = useState(editingRule?.name || "");
  const [description, setDescription] = useState(editingRule?.description || "");
  const [priority, setPriority] = useState(editingRule?.priority || 3);
  const [triggerEvent, setTriggerEvent] = useState(editingRule?.trigger_event || "lead_created");
  const [triggerConfig, setTriggerConfig] = useState<any>(editingRule?.trigger_config || {});
  const [conditionLogic, setConditionLogic] = useState(editingRule?.condition_logic || "all");
  const [conditions, setConditions] = useState<any[]>(editingRule?.conditions || []);
  const [actions, setActions] = useState<any[]>(editingRule?.actions || []);
  const [maxExec, setMaxExec] = useState(editingRule?.max_executions_per_hour || 100);
  const [cooldown, setCooldown] = useState(editingRule?.cooldown_seconds || 0);

  // Users and campaigns for dropdowns
  const [users, setUsers] = useState<any[]>([]);
  const [teams, setTeams] = useState<any[]>([]);
  const [campaigns, setCampaigns] = useState<any[]>([]);

  useEffect(() => {
    const token = localStorage.getItem(`${domain}_access`);
    if (!token) return;
    Promise.all([
      fetch(`${getApiBase(domain)}/api/users/`, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.ok ? r.json() : []),
      fetch(`${getApiBase(domain)}/api/teams/`, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.ok ? r.json() : []),
      fetch(`${getApiBase(domain)}/api/campaigns/`, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.ok ? r.json() : []),
    ]).then(([u, t, c]) => {
      setUsers(Array.isArray(u) ? u : u.results || []);
      setTeams(Array.isArray(t) ? t : t.results || []);
      setCampaigns(Array.isArray(c) ? c : c.results || []);
    });
  }, [domain]);

  const triggers = metaOptions?.triggers || [
    { value: "lead_created", label: "Lead Created" },
    { value: "lead_status_changed", label: "Lead Status Changed" },
    { value: "lead_updated", label: "Lead Updated" },
    { value: "lead_converted", label: "Lead Converted" },
    { value: "lead_lost", label: "Deal Marked Lost" },
    { value: "lead_inactive", label: "Lead Inactive (no activity)" },
    { value: "pushed_to_documentation", label: "Closed Deal (Pushed to Documentation)" },
    { value: "payment_partially_paid", label: "Payment Verified — Partially Paid" },
    { value: "payment_fully_paid", label: "Payment Fully Paid (moves to Purchase)" },
    { value: "project_completed", label: "Project Completed (installation done)" },
    { value: "doc_stage2_completed", label: "Documentation Stage 2 Completed" },
    { value: "warranty_completed", label: "Warranty Completed" },
    { value: "liasoning_completed", label: "Liasoning & Service Completed" },
    { value: "discom_approved", label: "Discom Approval — Approved" },
    { value: "discom_not_approved", label: "Discom Approval — Not Approved" },
    { value: "maintenance_scheduled", label: "Periodic Maintenance Scheduled" },
    { value: "task_created", label: "Task Created" },
    { value: "task_completed", label: "Task Completed" },
    { value: "campaign_lead_added", label: "Lead Added to Campaign" },
    { value: "call_logged", label: "Call Logged" },
  ];

  const operators = metaOptions?.operators || [
    { value: "equals", label: "Equals" }, { value: "not_equals", label: "Not Equals" },
    { value: "contains", label: "Contains" }, { value: "greater_than", label: "Greater Than" },
    { value: "less_than", label: "Less Than" }, { value: "is_empty", label: "Is Empty" },
    { value: "is_not_empty", label: "Is Not Empty" },
  ];

  const conditionFields = metaOptions?.condition_fields || [
    { value: "source", label: "Source", type: "text" },
    { value: "status", label: "Status", type: "select" },
    { value: "value", label: "Deal Value", type: "number" },
    { value: "first_name", label: "First Name", type: "text" },
    { value: "email", label: "Email", type: "text" },
    { value: "company", label: "Company", type: "text" },
  ];

  const addCondition = () => setConditions([...conditions, { field: "source", operator: "equals", value: "" }]);
  const removeCondition = (i: number) => setConditions(conditions.filter((_, idx) => idx !== i));
  const updateCondition = (i: number, key: string, val: any) => {
    setConditions(conditions.map((c, idx) => idx === i ? { ...c, [key]: val } : c));
  };

  const addAction = (type: string) => {
     const newActions = [...actions, { type, params: {} }];
     setActions(newActions);
     setDrawerActionIndex(newActions.length - 1);
     setDrawerOpen('action');
  };
  const removeAction = (i: number, e: React.MouseEvent) => {
     e.stopPropagation();
     setActions(actions.filter((_, idx) => idx !== i));
     if (drawerOpen === 'action' && drawerActionIndex === i) setDrawerOpen('settings');
  };
  const updateActionParam = (i: number, key: string, val: any) => {
    setActions(actions.map((a, idx) => idx === i ? { ...a, params: { ...a.params, [key]: val } } : a));
  };

  const handleSave = async () => {
    if (!name.trim()) { setError("Please enter a name for the automation."); return; }
    if (actions.length === 0) { setError("Please add at least one action."); return; }
    setError("");
    setSaving(true);
    const token = localStorage.getItem(`${domain}_access`);
    if (!token) return;

    const body = {
      name, description, priority, trigger_event: triggerEvent,
      trigger_config: triggerConfig, condition_logic: conditionLogic,
      conditions, actions,
      max_executions_per_hour: maxExec, cooldown_seconds: cooldown,
    };

    try {
      // Key on the id, not truthiness — a template prefill passes a config
      // object without an id and must be created (POST), not updated.
      const url = editingRule?.id
        ? `${getApiBase(domain)}/api/automations/${editingRule.id}/`
        : `${getApiBase(domain)}/api/automations/`;
      const res = await fetch(url, {
        method: editingRule?.id ? "PUT" : "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (res.ok) {
        onSuccess();
      } else {
        const data = await res.json();
        setError(JSON.stringify(data));
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const PipelineNode = ({ title, icon, subtitle, color, isActive, onClick, onRemove }: any) => (
    <div className="relative group flex justify-center w-full max-w-[400px]">
      <div 
        onClick={onClick}
        className={`w-full flex items-center p-4 rounded-2xl border transition-all duration-300 cursor-pointer backdrop-blur-md hover:scale-[1.02] ${
          isActive 
            ? `bg-${color}-500/20 border-${color}-500 shadow-[0_0_30px_rgba(var(--${color}-rgb),0.3)]` 
            : "bg-[#111] border-white/10 hover:border-white/30 hover:bg-[#1a1a1a]"
        }`}
      >
        <div className={`flex items-center justify-center w-12 h-12 rounded-xl text-xl mr-4 flex-shrink-0 bg-${color}-500/20 text-${color}-400 border border-${color}-500/30`}>
          {icon}
        </div>
        <div className="flex-1 min-w-0">
           <h4 className="text-white font-bold text-sm truncate">{title}</h4>
           {subtitle && <p className="text-xs text-slate-400 mt-0.5 truncate">{subtitle}</p>}
        </div>
        {onRemove && (
           <button onClick={onRemove} className="opacity-0 group-hover:opacity-100 p-2 text-slate-500 hover:text-red-400 transition-colors">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
           </button>
        )}
      </div>
    </div>
  );

  const Connector = () => (
    <div className="flex justify-center h-8 my-1 w-full max-w-[400px]">
      <svg width="2" height="100%" className="overflow-visible">
         <line x1="1" y1="0" x2="1" y2="32" stroke="rgba(255,255,255,0.2)" strokeWidth="2" strokeDasharray="4 4" className="animate-[dash_20s_linear_infinite]" />
      </svg>
    </div>
  );

  return (
    <div className="fixed inset-0 z-[100] flex text-slate-200 font-sans selection:bg-indigo-500/30">
      <style>{`
        :root { --blue-rgb: 59, 130, 246; --amber-rgb: 245, 158, 11; --emerald-rgb: 16, 185, 129; --indigo-rgb: 99, 102, 241; --purple-rgb: 168, 85, 247; }
        @keyframes dash { to { stroke-dashoffset: -1000; } }
        @keyframes fadeUp { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes slideInRight { from { opacity: 0; transform: translateX(40px); } to { opacity: 1; transform: translateX(0); } }
      `}</style>
      
      {/* Background layer */}
      <div className="absolute inset-0 bg-[#060608]">
         {/* Dot Matrix Pattern */}
         <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyMCIgaGVpZ2h0PSIyMCI+CiAgPGNpcmNsZSBjeD0iMiIgY3k9IjIiIHI9IjEiIGZpbGw9IiNmZmYiIGZpbGwtb3BhY2l0eT0iMC4wNSIvPgo8L3N2Zz4=')]"></div>
      </div>

      <div className="relative z-10 flex w-full h-full">
         
         {/* Main Canvas Area */}
         <div className="flex-1 flex flex-col items-center pt-24 pb-32 px-6 overflow-y-auto" onClick={() => setDrawerOpen('settings')}>
            <div className="w-full max-w-4xl flex items-center justify-between absolute top-0 left-0 right-0 px-8 py-6 pointer-events-none">
               <button onClick={onClose} className="px-5 py-2.5 bg-white/5 border border-white/10 text-white rounded-xl font-bold backdrop-blur-md pointer-events-auto hover:bg-white/10 transition-colors flex items-center gap-2">
                  <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
                  Exit Builder
               </button>
               <button onClick={handleSave} disabled={saving} className="px-6 py-2.5 bg-indigo-600 text-white rounded-xl font-bold backdrop-blur-md pointer-events-auto shadow-[0_0_20px_rgba(99,102,241,0.4)] hover:bg-indigo-500 disabled:opacity-50 transition-all flex items-center gap-2 relative overflow-hidden group">
                  <div className="absolute inset-0 bg-white/20 translate-y-full group-hover:translate-y-0 transition-transform duration-300"></div>
                  <span className="relative">{saving ? "Deploying..." : "Publish Pipeline"}</span>
                  <svg className="relative" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
               </button>
            </div>

            <div className="text-center mb-12 animate-[fadeUp_0.4s_ease-out_forwards]">
               <h2 className="text-3xl font-black text-white px-4 py-2 border-b-2 border-transparent hover:border-white/20 transition-colors inline-block cursor-pointer outline-none" onClick={(e) => { e.stopPropagation(); setDrawerOpen('settings'); }}>
                  {name || "Untitled Pipeline"}
               </h2>
               <p className="text-slate-400 mt-2 font-medium">{actions.length} action{actions.length !== 1 ? 's' : ''} configured</p>
            </div>

            {/* Pipeline Visual UI */}
            <div className="flex flex-col items-center w-full animate-[fadeUp_0.5s_ease-out_forwards]" onClick={e => e.stopPropagation()}>
               
               {/* 1. Trigger */}
               <PipelineNode 
                  title={triggers.find((t:any) => t.value === triggerEvent)?.label || "Select Trigger"}
                  subtitle="When this event happens"
                  icon="⚡"
                  color="blue"
                  isActive={drawerOpen === 'trigger'}
                  onClick={() => setDrawerOpen('trigger')}
               />

               <Connector />

               {/* 2. Conditions */}
               <PipelineNode 
                  title="Conditions & Routing"
                  subtitle={`${conditions.length} rule${conditions.length !== 1 ? 's' : ''} applied`}
                  icon="🛤️"
                  color="amber"
                  isActive={drawerOpen === 'conditions'}
                  onClick={() => setDrawerOpen('conditions')}
               />

               <Connector />

               {/* 3. Actions */}
               <div className="flex flex-col items-center w-full gap-2">
                  {actions.map((action, i) => (
                     <React.Fragment key={i}>
                        <PipelineNode 
                           title={ACTION_LABELS[action.type] || action.type}
                           subtitle={`Step ${i + 1}`}
                           icon={ACTION_ICONS[action.type] || "⚙️"}
                           color="emerald"
                           isActive={drawerOpen === 'action' && drawerActionIndex === i}
                           onClick={() => { setDrawerActionIndex(i); setDrawerOpen('action'); }}
                           onRemove={(e: any) => removeAction(i, e)}
                        />
                        <Connector />
                     </React.Fragment>
                  ))}
                  
                  {/* Add action button */}
                  <div className="w-[400px] border border-dashed border-white/20 rounded-2xl p-4 flex flex-col items-center justify-center cursor-pointer hover:border-indigo-400 hover:bg-indigo-500/5 transition-colors gap-2" onClick={() => { setDrawerActionIndex(null); setDrawerOpen('action'); }}>
                     <div className="w-10 h-10 rounded-full bg-white/5 flex items-center justify-center text-xl text-white">
                        +
                     </div>
                     <span className="text-sm font-bold text-slate-400">Add Action Step</span>
                  </div>
               </div>

            </div>
         </div>

         {/* Configuration Drawer */}
         <div className="w-[450px] flex-shrink-0 bg-[#0e0e11]/90 backdrop-blur-2xl border-l border-white/10 h-full p-8 overflow-y-auto flex flex-col shadow-[-20px_0_40px_rgba(0,0,0,0.5)] animate-[slideInRight_0.4s_ease-out_forwards]">
            
            {drawerOpen === 'settings' && (
               <div className="space-y-6">
                  <div className="mb-8">
                     <div className="w-10 h-10 rounded-xl bg-purple-500/20 border border-purple-500/30 flex items-center justify-center text-xl mb-4">⚙️</div>
                     <h3 className="text-2xl font-black text-white">Pipeline Settings</h3>
                     <p className="text-sm text-slate-400 mt-1">Configure global properties for this automation.</p>
                  </div>

                  <div>
                     <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Automation Name</label>
                     <input value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Inbound Lead Router" className="w-full px-4 py-3 bg-[#16161a] border border-white/10 rounded-xl text-sm text-white focus:outline-none focus:border-indigo-500 transition-colors" />
                  </div>
                  <div>
                     <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Description</label>
                     <textarea value={description} onChange={e => setDescription(e.target.value)} placeholder="Brief description..." rows={3} className="w-full px-4 py-3 bg-[#16161a] border border-white/10 rounded-xl text-sm text-white resize-none focus:outline-none focus:border-indigo-500 transition-colors" />
                  </div>
                  <div>
                     <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Priority Level</label>
                     <select value={priority} onChange={e => setPriority(Number(e.target.value))} className="w-full px-4 py-3 bg-[#16161a] border border-white/10 rounded-xl text-sm text-white focus:outline-none focus:border-indigo-500">
                        <option value={1}>Critical</option>
                        <option value={2}>High</option>
                        <option value={3}>Normal</option>
                        <option value={4}>Low</option>
                     </select>
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                     <div>
                        <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Rate Limit (/hr)</label>
                        <input type="number" value={maxExec} onChange={e => setMaxExec(Number(e.target.value))} className="w-full px-4 py-3 bg-[#16161a] border border-white/10 rounded-xl text-sm text-white focus:outline-none focus:border-indigo-500 transition-colors" />
                     </div>
                     <div>
                        <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Cooldown (s)</label>
                        <input type="number" value={cooldown} onChange={e => setCooldown(Number(e.target.value))} className="w-full px-4 py-3 bg-[#16161a] border border-white/10 rounded-xl text-sm text-white focus:outline-none focus:border-indigo-500 transition-colors" />
                     </div>
                  </div>
                  {error && <div className="p-4 bg-red-500/10 border border-red-500/20 text-red-400 rounded-xl text-sm font-medium">{error}</div>}
               </div>
            )}

            {drawerOpen === 'trigger' && (
               <div className="space-y-6">
                  <div className="mb-8">
                     <div className="w-10 h-10 rounded-xl bg-blue-500/20 border border-blue-500/30 flex items-center justify-center text-xl text-blue-400 mb-4">⚡</div>
                     <h3 className="text-2xl font-black text-white">Trigger Event</h3>
                     <p className="text-sm text-slate-400 mt-1">What initiates this pipeline?</p>
                  </div>

                  <div className="space-y-3">
                     {triggers.map((t: any) => (
                        <div key={t.value} onClick={() => setTriggerEvent(t.value)} className={`p-4 rounded-xl border flex items-center gap-4 cursor-pointer transition-colors ${triggerEvent === t.value ? "bg-blue-500/10 border-blue-500 text-white" : "bg-[#16161a] border-white/10 text-slate-400 hover:bg-[#1a1a1f]"}`}>
                           <div className={`w-4 h-4 rounded-full border-2 flex items-center justify-center ${triggerEvent === t.value ? "border-blue-500" : "border-slate-600"}`}>
                              {triggerEvent === t.value && <div className="w-2 h-2 bg-blue-500 rounded-full"/>}
                           </div>
                           <span className="font-bold text-sm tracking-wide">{t.label}</span>
                        </div>
                     ))}
                  </div>

                  {triggerEvent === "lead_status_changed" && (
                     <div className="mt-8 pt-6 border-t border-white/10 space-y-4">
                        <div className="text-xs font-bold text-slate-500 uppercase tracking-wider">Status Transition Filters</div>
                        <div className="grid grid-cols-2 gap-4">
                           <div>
                              <label className="text-xs text-slate-400 mb-2 block">From Status</label>
                              <select value={triggerConfig.from_status || ""} onChange={e => setTriggerConfig({...triggerConfig, from_status: e.target.value})} className="w-full px-3 py-2.5 bg-[#16161a] border border-white/10 rounded-lg text-sm text-white">
                                 <option value="">Any State</option>
                                 {statusOptions.map(opt => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
                              </select>
                           </div>
                           <div>
                              <label className="text-xs text-slate-400 mb-2 block">To Status</label>
                              <select value={triggerConfig.to_status || ""} onChange={e => setTriggerConfig({...triggerConfig, to_status: e.target.value})} className="w-full px-3 py-2.5 bg-[#16161a] border border-white/10 rounded-lg text-sm text-white">
                                 <option value="">Any State</option>
                                 {statusOptions.map(opt => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
                              </select>
                           </div>
                        </div>
                     </div>
                  )}
               </div>
            )}

            {drawerOpen === 'conditions' && (
               <div className="space-y-6">
                  <div className="mb-8">
                     <div className="w-10 h-10 rounded-xl bg-amber-500/20 border border-amber-500/30 flex items-center justify-center text-xl text-amber-400 mb-4">🛤️</div>
                     <h3 className="text-2xl font-black text-white">Conditions</h3>
                     <p className="text-sm text-slate-400 mt-1">Filters that must be met to proceed.</p>
                  </div>

                  {conditions.length > 0 && (
                     <div className="flex bg-[#16161a] border border-white/10 rounded-lg p-1.5 mb-6">
                        <button onClick={() => setConditionLogic('all')} className={`flex-1 py-1.5 rounded-md text-xs font-bold transition-all ${conditionLogic === 'all' ? 'bg-amber-500 text-black' : 'text-slate-400 hover:text-white'}`}>AND (All Match)</button>
                        <button onClick={() => setConditionLogic('any')} className={`flex-1 py-1.5 rounded-md text-xs font-bold transition-all ${conditionLogic === 'any' ? 'bg-amber-500 text-black' : 'text-slate-400 hover:text-white'}`}>OR (Any Match)</button>
                     </div>
                  )}

                  <div className="space-y-4">
                     {conditions.map((cond, i) => {
                        const selectedField = conditionFields.find((f: any) => f.value === cond.field);
                        const isNoValueOp = ['is_empty', 'is_not_empty'].includes(cond.operator);
                        return (
                           <div key={i} className="bg-[#16161a] border border-white/10 rounded-xl p-4 relative group">
                              <button onClick={() => removeCondition(i)} className="absolute -top-3 -right-3 w-6 h-6 bg-red-500 text-white rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity shadow-lg">✕</button>
                              <div className="space-y-3">
                                 <select value={cond.field} onChange={e => updateCondition(i, 'field', e.target.value)} className="w-full px-3 py-2 bg-black/50 border border-white/10 rounded-lg text-sm text-white">
                                    {conditionFields.map((f: any) => <option key={f.value} value={f.value}>{f.label}</option>)}
                                 </select>
                                 <select value={cond.operator} onChange={e => updateCondition(i, 'operator', e.target.value)} className="w-full px-3 py-2 bg-black/50 border border-white/10 rounded-lg text-sm text-white text-emerald-400 font-bold">
                                    {operators.map((o: any) => <option key={o.value} value={o.value}>{o.label}</option>)}
                                 </select>
                                 {!isNoValueOp && (
                                    selectedField?.type === 'select' || cond.field === 'status' ? (
                                       <select value={cond.value} onChange={e => updateCondition(i, 'value', e.target.value)} className="w-full px-3 py-2 bg-black/50 border border-white/10 rounded-lg text-sm text-white">
                                          <option value="">Select value...</option>
                                          {statusOptions.map(opt => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
                                       </select>
                                    ) : (
                                       <input value={cond.value} onChange={e => updateCondition(i, 'value', e.target.value)} placeholder="Filter value" type={selectedField?.type === 'number' ? 'number' : 'text'} className="w-full px-3 py-2 bg-black/50 border border-white/10 rounded-lg text-sm text-white" />
                                    )
                                 )}
                              </div>
                           </div>
                        );
                     })}
                     <button onClick={addCondition} className="w-full py-3.5 border border-dashed border-white/20 rounded-xl text-sm font-bold text-amber-500 hover:bg-amber-500/10 hover:border-amber-500/50 transition-colors">
                        + Add Condition Block
                     </button>
                  </div>
               </div>
            )}

            {drawerOpen === 'action' && (
               <div className="space-y-6 flex-1 flex flex-col">
                  {drawerActionIndex === null ? (
                     <>
                        <div className="mb-6">
                           <div className="w-10 h-10 rounded-xl bg-emerald-500/20 border border-emerald-500/30 flex items-center justify-center text-xl text-emerald-400 mb-4">⚙️</div>
                           <h3 className="text-2xl font-black text-white">Add Action</h3>
                           <p className="text-sm text-slate-400 mt-1">Choose an operation for the pipeline to execute.</p>
                        </div>
                        <div className="grid gap-2">
                           {Object.entries(ACTION_LABELS).map(([key, label]) => (
                              <button key={key} onClick={() => addAction(key)} className="flex items-center gap-4 px-4 py-3.5 bg-[#16161a] border border-white/5 rounded-xl text-sm font-bold text-white hover:border-emerald-500/50 hover:bg-emerald-500/10 transition-colors text-left group">
                                 <span className="text-xl group-hover:scale-110 transition-transform">{ACTION_ICONS[key]}</span>
                                 <span>{label}</span>
                              </button>
                           ))}
                        </div>
                     </>
                  ) : (
                     <>
                     {(() => {
                        const action = actions[drawerActionIndex];
                        if (!action) return null;
                        return (
                           <div className="space-y-6">
                              <div className="mb-8">
                                 <div className="w-10 h-10 rounded-xl bg-emerald-500/20 border border-emerald-500/30 flex items-center justify-center text-xl text-emerald-400 mb-4">{ACTION_ICONS[action.type]}</div>
                                 <h3 className="text-2xl font-black text-white">{ACTION_LABELS[action.type]}</h3>
                                 <p className="text-sm text-slate-400 mt-1">Configure action parameters.</p>
                              </div>

                              <div className="space-y-4">
                              {action.type === "ai_auto_assign" && (
                                 <div className="space-y-4">
                                    <div className="p-4 bg-indigo-500/10 border border-indigo-500/20 rounded-xl">
                                       <div className="flex items-start gap-3">
                                          <span className="text-2xl">🤖</span>
                                          <div>
                                             <p className="text-sm font-bold text-indigo-300">AI Manager Auto-Assign</p>
                                             <p className="text-xs text-slate-400 mt-1">Uses your configured strategy (Workload Balanced or Round Robin) from AI Manager settings to pick the best available agent automatically.</p>
                                          </div>
                                       </div>
                                    </div>
                                    <div className="p-4 bg-[#16161a] border border-white/10 rounded-xl">
                                       <label className="flex items-center gap-3 text-sm font-bold text-white cursor-pointer">
                                          <input type="checkbox" checked={action.params.force || false} onChange={e => updateActionParam(drawerActionIndex, 'force', e.target.checked)} className="w-4 h-4 rounded text-indigo-500 focus:ring-indigo-500 bg-black border-white/20" />
                                          Force Override (re-assign even if already assigned)
                                       </label>
                                    </div>
                                 </div>
                              )}
                              {action.type === "send_whatsapp" && (
                                 <div className="space-y-4">
                                    <select value={action.params.mode || "text"} onChange={e => updateActionParam(drawerActionIndex, 'mode', e.target.value)} className="w-full px-4 py-3 bg-[#16161a] border border-white/10 rounded-xl text-sm text-white">
                                       <option value="text">Text message (24h session window)</option>
                                       <option value="template">Approved template (business-initiated)</option>
                                    </select>
                                    {(action.params.mode || "text") === "template" ? (
                                       <>
                                          <input value={action.params.template_name || ""} onChange={e => updateActionParam(drawerActionIndex, 'template_name', e.target.value)} placeholder="Template name (as approved in Meta)" className="w-full px-4 py-3 bg-[#16161a] border border-white/10 rounded-xl text-sm text-white" />
                                          <input value={action.params.language || "en_US"} onChange={e => updateActionParam(drawerActionIndex, 'language', e.target.value)} placeholder="Language code (e.g. en_US)" className="w-full px-4 py-3 bg-[#16161a] border border-white/10 rounded-xl text-sm text-white" />
                                          <input value={(action.params.variables || []).join(", ")} onChange={e => updateActionParam(drawerActionIndex, 'variables', e.target.value.split(",").map((s: string) => s.trim()).filter(Boolean))} placeholder="Body variables, comma-separated — e.g. {{first_name}}, {{company}}" className="w-full px-4 py-3 bg-[#16161a] border border-white/10 rounded-xl text-sm text-white" />
                                          <p className="text-xs text-slate-500">{"Variables fill {{1}}, {{2}}… in order. Use {{first_name}} to insert lead data."}</p>
                                       </>
                                    ) : (
                                       <>
                                          <textarea value={action.params.text || ""} onChange={e => updateActionParam(drawerActionIndex, 'text', e.target.value)} placeholder="Message text…" rows={4} className="w-full px-4 py-3 bg-[#16161a] border border-white/10 rounded-xl text-sm text-white resize-none" />
                                          <p className="text-xs text-slate-500">{"Supports {{first_name}}. Free-text only delivers inside the 24-hour customer window — otherwise use a template."}</p>
                                       </>
                                    )}
                                 </div>
                              )}
                              {action.type === "wait" && (
                                 <div className="space-y-3">
                                    <div className="grid grid-cols-2 gap-3">
                                       <input type="number" min={1} value={action.params.amount || 1} onChange={e => updateActionParam(drawerActionIndex, 'amount', Number(e.target.value))} placeholder="Amount" className="w-full px-4 py-3 bg-[#16161a] border border-white/10 rounded-xl text-sm text-white" />
                                       <select value={action.params.unit || "days"} onChange={e => updateActionParam(drawerActionIndex, 'unit', e.target.value)} className="w-full px-4 py-3 bg-[#16161a] border border-white/10 rounded-xl text-sm text-white">
                                          <option value="minutes">Minutes</option>
                                          <option value="hours">Hours</option>
                                          <option value="days">Days</option>
                                       </select>
                                    </div>
                                    <p className="text-xs text-slate-500">Steps after this run later — a scheduler resumes the sequence when the wait elapses.</p>
                                 </div>
                              )}
                              {action.type === "send_email" && (
                                 <div className="space-y-4">
                                    <input value={action.params.to || ""} onChange={e => updateActionParam(drawerActionIndex, 'to', e.target.value)} placeholder="To (leave blank to use the lead's email)" className="w-full px-4 py-3 bg-[#16161a] border border-white/10 rounded-xl text-sm text-white" />
                                    <input value={action.params.subject || ""} onChange={e => updateActionParam(drawerActionIndex, 'subject', e.target.value)} placeholder="Subject — supports {{first_name}}" className="w-full px-4 py-3 bg-[#16161a] border border-white/10 rounded-xl text-sm text-white" />
                                    <textarea value={action.params.body || ""} onChange={e => updateActionParam(drawerActionIndex, 'body', e.target.value)} placeholder="Email body…" rows={4} className="w-full px-4 py-3 bg-[#16161a] border border-white/10 rounded-xl text-sm text-white resize-none" />
                                    <p className="text-xs text-slate-500">{"Use placeholders like {{first_name}}, {{company}} — replaced with the lead's data."}</p>
                                 </div>
                              )}
                              {action.type === "escalate_to_manager" && (
                                 <div className="space-y-4">
                                    <div className="p-4 bg-[#16161a] border border-white/10 rounded-xl">
                                       <label className="flex items-center gap-3 text-sm font-bold text-white cursor-pointer">
                                          <input type="checkbox" checked={action.params.reassign !== false} onChange={e => updateActionParam(drawerActionIndex, 'reassign', e.target.checked)} className="w-4 h-4 rounded text-rose-500 focus:ring-rose-500 bg-black border-white/20" />
                                          Reassign the lead to the manager
                                       </label>
                                    </div>
                                    <input value={action.params.message || ""} onChange={e => updateActionParam(drawerActionIndex, 'message', e.target.value)} placeholder="Notification message to the manager" className="w-full px-4 py-3 bg-[#16161a] border border-white/10 rounded-xl text-sm text-white" />
                                 </div>
                              )}
                              {action.type === "notify_assignee" && (
                                 <input value={action.params.message || ""} onChange={e => updateActionParam(drawerActionIndex, 'message', e.target.value)} placeholder="Message to the lead's owner" className="w-full px-4 py-3 bg-[#16161a] border border-white/10 rounded-xl text-sm text-white" />
                              )}
                              {action.type === "assign_lead" && (
                                 <>
                                    <div className="p-4 bg-[#16161a] border border-white/10 rounded-xl">
                                       <label className="flex items-center gap-3 text-sm font-bold text-white cursor-pointer">
                                          <input type="checkbox" checked={action.params.round_robin || false} onChange={e => updateActionParam(drawerActionIndex, 'round_robin', e.target.checked)} className="w-4 h-4 rounded text-emerald-500 focus:ring-emerald-500 bg-black border-white/20" />
                                          Use Team Round Robin
                                       </label>
                                    </div>
                                    <div className="space-y-2">
                                       <label className="text-xs font-bold text-slate-500 uppercase">{action.params.round_robin ? "Select Team" : "Select User Agent"}</label>
                                       {action.params.round_robin ? (
                                          <select value={action.params.team_id || ""} onChange={e => updateActionParam(drawerActionIndex, 'team_id', Number(e.target.value))} className="w-full px-4 py-3 bg-[#16161a] border border-white/10 rounded-xl text-sm text-white">
                                             <option value="">Select Team...</option>
                                             {teams.map((t: any) => <option key={t.id} value={t.id}>{t.name}</option>)}
                                          </select>
                                       ) : (
                                          <select value={action.params.user_id || ""} onChange={e => updateActionParam(drawerActionIndex, 'user_id', Number(e.target.value))} className="w-full px-4 py-3 bg-[#16161a] border border-white/10 rounded-xl text-sm text-white">
                                             <option value="">Select User...</option>
                                             {users.map((u: any) => <option key={u.id} value={u.id}>{u.first_name} {u.last_name}</option>)}
                                          </select>
                                       )}
                                    </div>
                                 </>
                              )}
                              {action.type === "change_status" && (
                                 <select value={action.params.status || ""} onChange={e => updateActionParam(drawerActionIndex, 'status', e.target.value)} className="w-full px-4 py-3 bg-[#16161a] border border-white/10 rounded-xl text-sm text-white">
                                    <option value="">Select New Status...</option>
                                    {statusOptions.map(opt => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
                                 </select>
                              )}
                              {action.type === "create_task" && (
                                 <div className="space-y-4">
                                    <input value={action.params.title || ""} onChange={e => updateActionParam(drawerActionIndex, 'title', e.target.value)} placeholder="Task descriptor" className="w-full px-4 py-3 bg-[#16161a] border border-white/10 rounded-xl text-sm text-white" />
                                    <select value={action.params.priority || "medium"} onChange={e => updateActionParam(drawerActionIndex, 'priority', e.target.value)} className="w-full px-4 py-3 bg-[#16161a] border border-white/10 rounded-xl text-sm text-white">
                                       <option value="low">Low Priority</option>
                                       <option value="medium">Medium Priority</option>
                                       <option value="high">High Priority</option>
                                    </select>
                                    <div className="grid grid-cols-2 gap-3">
                                       <input type="number" value={action.params.due_days || 1} onChange={e => updateActionParam(drawerActionIndex, 'due_days', Number(e.target.value))} placeholder="Due in (days)" className="w-full px-4 py-3 bg-[#16161a] border border-white/10 rounded-xl text-sm text-white" min={1} />
                                       <select value={action.params.assignee_id || ""} onChange={e => updateActionParam(drawerActionIndex, 'assignee_id', Number(e.target.value) || "")} className="w-full px-4 py-3 bg-[#16161a] border border-white/10 rounded-xl text-sm text-white">
                                          <option value="">Dynamic Assign</option>
                                          {users.map((u: any) => <option key={u.id} value={u.id}>{u.first_name} {u.last_name}</option>)}
                                       </select>
                                    </div>
                                 </div>
                              )}
                              {action.type === "add_to_campaign" && (
                                 <select value={action.params.campaign_id || ""} onChange={e => updateActionParam(drawerActionIndex, 'campaign_id', Number(e.target.value))} className="w-full px-4 py-3 bg-[#16161a] border border-white/10 rounded-xl text-sm text-white">
                                    <option value="">Enroll in Campaign...</option>
                                    {campaigns.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}
                                 </select>
                              )}
                              {action.type === "send_webhook" && (
                                 <div className="space-y-4">
                                    <select value={action.params.method || "POST"} onChange={e => updateActionParam(drawerActionIndex, 'method', e.target.value)} className="w-full px-4 py-3 bg-[#16161a] border border-white/10 rounded-xl text-sm text-white">
                                       <option>POST</option><option>GET</option><option>PUT</option>
                                    </select>
                                    <input value={action.params.url || ""} onChange={e => updateActionParam(drawerActionIndex, 'url', e.target.value)} placeholder="Endpoint URL: https://" className="w-full px-4 py-3 bg-[#16161a] border border-white/10 rounded-xl text-sm text-white" />
                                 </div>
                              )}
                              {action.type === "send_notification" && (
                                 <div className="space-y-4">
                                    <select value={action.params.user_id || ""} onChange={e => updateActionParam(drawerActionIndex, 'user_id', Number(e.target.value))} className="w-full px-4 py-3 bg-[#16161a] border border-white/10 rounded-xl text-sm text-white">
                                       <option value="">Select Recipient...</option>
                                       {users.map((u: any) => <option key={u.id} value={u.id}>{u.first_name} {u.last_name}</option>)}
                                    </select>
                                    <input value={action.params.message || ""} onChange={e => updateActionParam(drawerActionIndex, 'message', e.target.value)} placeholder="Push notification message" className="w-full px-4 py-3 bg-[#16161a] border border-white/10 rounded-xl text-sm text-white" />
                                 </div>
                              )}
                              {action.type === "update_field" && (
                                 <div className="space-y-4">
                                    <select value={action.params.field || ""} onChange={e => updateActionParam(drawerActionIndex, 'field', e.target.value)} className="w-full px-4 py-3 bg-[#16161a] border border-white/10 rounded-xl text-sm text-white">
                                       <option value="">Property Name</option>
                                       {conditionFields.map((f: any) => <option key={f.value} value={f.value}>{f.label}</option>)}
                                    </select>
                                    <input value={action.params.value || ""} onChange={e => updateActionParam(drawerActionIndex, 'value', e.target.value)} placeholder="Set to value..." className="w-full px-4 py-3 bg-[#16161a] border border-white/10 rounded-xl text-sm text-white" />
                                 </div>
                              )}
                              {action.type === "add_note" && (
                                 <textarea value={action.params.note || ""} onChange={e => updateActionParam(drawerActionIndex, 'note', e.target.value)} placeholder="Log note..." rows={4} className="w-full px-4 py-3 bg-[#16161a] border border-white/10 rounded-xl text-sm text-white resize-none" />
                              )}
                              {action.type === "duplicate_check" && (
                                 <div className="p-4 bg-[#16161a] border border-white/10 rounded-xl text-slate-400 text-sm">
                                    Automatically scans and merges duplicate records based on strict matching identifiers. Minimal configuration needed.
                                 </div>
                              )}
                              {action.type === "reassign_employee_leads" && (
                                 <div className="space-y-4">
                                    <div className="p-4 bg-[#16161a] border border-white/10 rounded-xl space-y-4">
                                       <div>
                                          <label className="text-xs font-bold text-slate-500 uppercase">From Employee</label>
                                          <select value={action.params.from_user_id || ""} onChange={e => updateActionParam(drawerActionIndex, 'from_user_id', Number(e.target.value))} className="w-full mt-1 px-4 py-3 bg-black/50 border border-white/10 rounded-xl text-sm text-white">
                                             <option value="">Select Employee...</option>
                                             {users.map((u: any) => <option key={u.id} value={u.id}>{u.first_name} {u.last_name}</option>)}
                                          </select>
                                       </div>
                                       <div>
                                          <label className="text-xs font-bold text-slate-500 uppercase">Filter by Lead Status (Optional)</label>
                                          <select value={action.params.lead_status || ""} onChange={e => updateActionParam(drawerActionIndex, 'lead_status', e.target.value)} className="w-full mt-1 px-4 py-3 bg-black/50 border border-white/10 rounded-xl text-sm text-white">
                                             <option value="">All Statuses</option>
                                             {statusOptions.map(opt => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
                                          </select>
                                       </div>
                                    </div>

                                    <div className="p-4 bg-[#16161a] border border-white/10 rounded-xl space-y-4">
                                       <label className="flex items-center gap-3 text-sm font-bold text-white cursor-pointer">
                                          <input type="checkbox" checked={action.params.round_robin || false} onChange={e => updateActionParam(drawerActionIndex, 'round_robin', e.target.checked)} className="w-4 h-4 rounded text-emerald-500 focus:ring-emerald-500 bg-black border-white/20" />
                                          Assign to Team (Round Robin)
                                       </label>
                                       <div>
                                          <label className="text-xs font-bold text-slate-500 uppercase">{action.params.round_robin ? "To Team" : "To Employee"}</label>
                                          {action.params.round_robin ? (
                                             <select value={action.params.team_id || ""} onChange={e => updateActionParam(drawerActionIndex, 'team_id', Number(e.target.value))} className="w-full mt-1 px-4 py-3 bg-black/50 border border-white/10 rounded-xl text-sm text-white">
                                                <option value="">Select Team...</option>
                                                {teams.map((t: any) => <option key={t.id} value={t.id}>{t.name}</option>)}
                                             </select>
                                          ) : (
                                             <select value={action.params.to_user_id || ""} onChange={e => updateActionParam(drawerActionIndex, 'to_user_id', Number(e.target.value))} className="w-full mt-1 px-4 py-3 bg-black/50 border border-white/10 rounded-xl text-sm text-white">
                                                <option value="">Select Employee...</option>
                                                {users.map((u: any) => <option key={u.id} value={u.id}>{u.first_name} {u.last_name}</option>)}
                                             </select>
                                          )}
                                       </div>
                                       <div>
                                          <label className="text-xs font-bold text-slate-500 uppercase">Change Lead Status To (Optional)</label>
                                          <select value={action.params.new_status || ""} onChange={e => updateActionParam(drawerActionIndex, 'new_status', e.target.value)} className="w-full mt-1 px-4 py-3 bg-black/50 border border-white/10 rounded-xl text-sm text-white">
                                             <option value="">Keep Current Status</option>
                                             {statusOptions.map(opt => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
                                          </select>
                                       </div>
                                    </div>
                                 </div>
                              )}
                              </div>
                           </div>
                        );
                     })()}
                     </>
                  )}
               </div>
            )}
         </div>
      </div>
    </div>
  );
}

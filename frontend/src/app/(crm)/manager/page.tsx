"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";

import React, { useEffect, useState, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import { BarChart, Bar, XAxis, YAxis, Tooltip as RechartsTooltip, ResponsiveContainer, CartesianGrid, Legend } from "recharts";
import { jsPDF } from "jspdf";
import autoTable from "jspdf-autotable";
import * as htmlToImage from "html-to-image";

// ─── Types ─────────────────────────────────────────────────────────────────────
interface User { id: number; username: string; first_name: string; last_name: string; email: string; is_staff: boolean; is_manager: boolean; is_general_manager: boolean; team: number | null; }
interface Agent { id: number; name: string; role: string; active_leads: number; total_leads: number; daily_progress: any; monthly_progress: any; }
interface MonthlyTarget { id: number; agent: number; month: number; year: number; target_leads: number; target_amount: string; target_dialed_calls: number; target_call_time: number; }
interface DailyTarget { id: number; agent: number; date: string; target_leads: number; target_amount: string; target_dialed_calls: number; target_call_time: number; achieved_dialed_calls: number; achieved_call_time: number; status: string; is_manual: boolean; }
interface Holiday { id: number; date: string; name: string; }

const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

// ─── Icons ─────────────────────────────────────────────────────────────────────
const Icons = {
  Target: () => <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg>,
  Chart: () => <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" viewBox="0 0 24 24"><path d="M18 20V10M12 20V4M6 20v-6"/></svg>,
  Users: () => <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75"/></svg>,
  Bell: () => <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" viewBox="0 0 24 24"><path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 01-3.46 0"/></svg>,
  Calendar: () => <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>,
  Close: () => <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg>,
  Check: () => <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5"/></svg>,
  Edit: () => <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>,
  Back: () => <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M19 12H5M12 5l-7 7 7 7"/></svg>,
  Send: () => <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>,
  Phone: () => <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" viewBox="0 0 24 24"><path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07A19.5 19.5 0 013.07 10a19.79 19.79 0 01-3-8.57A2 2 0 012.11 0h3a2 2 0 012 1.72c.127.96.361 1.903.7 2.81a2 2 0 01-.45 2.11L6.19 7.84a16 16 0 006 6l1.21-1.21a2 2 0 012.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0122 16.92z"/></svg>,
};

// ─── Progress Ring ─────────────────────────────────────────────────────────────
function ProgressRing({ pct, size = 56, color = "#6366f1" }: { pct: number; size?: number; color?: string }) {
  const r = (size - 8) / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ - (Math.min(pct, 100) / 100) * circ;
  return (
    <svg width={size} height={size}>
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="#e2e8f0" strokeWidth="6" />
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeWidth="6"
        strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round"
        transform={`rotate(-90 ${size/2} ${size/2})`} style={{ transition: "stroke-dashoffset 0.6s ease" }} />
      <text x="50%" y="50%" textAnchor="middle" dy="0.35em" fontSize={size < 50 ? 9 : 11} fontWeight="700" fill="#1e293b">{Math.round(pct)}%</text>
    </svg>
  );
}

// ─── Agent Card ────────────────────────────────────────────────────────────────
function AgentCard({ agent, onSelect, onSetTarget, onEditDaily }: { agent: Agent; onSelect: () => void; onSetTarget: () => void; onEditDaily: () => void }) {
  const dp = agent.daily_progress;
  const mp = agent.monthly_progress;
  const roleColor = agent.role === "Admin" ? "bg-rose-50 text-rose-600" : agent.role === "General Manager" ? "bg-violet-50 text-violet-600" : agent.role === "Manager" ? "bg-blue-50 text-blue-600" : "bg-slate-50 text-slate-500";
  return (
    <div className="bg-white rounded-2xl border border-slate-100 shadow-sm hover:shadow-md transition-all hover:-translate-y-0.5 p-5">
      <div className="flex items-start justify-between mb-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-white text-sm font-bold">
              {agent.name.charAt(0)}
            </div>
            <div>
              <p className="font-semibold text-slate-800 text-sm leading-tight">{agent.name}</p>
              <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${roleColor}`}>{agent.role}</span>
            </div>
          </div>
        </div>
        <div className="flex flex-col items-end gap-1">
          <span className="text-xs text-slate-400">{agent.active_leads} active leads</span>
          <span className="text-xs text-slate-400">{agent.total_leads} total</span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 mb-4">
        <div className="bg-slate-50 rounded-xl p-3 text-center relative">
          <p className="text-[10px] text-slate-400 font-medium mb-1">Today</p>
          {dp?.has_target ? (
            <div className="flex flex-col items-center">
              <ProgressRing pct={dp.leads_pct || 0} size={48} color={dp.leads_pct >= 100 ? "#10b981" : "#6366f1"} />
              <p className="text-[10px] text-slate-500 mt-1">{dp.actual_leads}/{dp.target_leads} leads</p>
              {dp.is_manual && <span className="text-[8px] font-bold bg-amber-100 text-amber-600 px-1 py-0.5 rounded mt-0.5">Edited</span>}
            </div>
          ) : <p className="text-xs text-slate-400 mt-2">No target</p>}
          {dp?.has_target && (
            <button onClick={(e) => { e.stopPropagation(); onEditDaily(); }} className="absolute top-2 right-2 w-5 h-5 flex items-center justify-center rounded-md bg-white shadow-sm border border-slate-100 text-slate-400 hover:text-indigo-600 hover:border-indigo-200 transition-all" title="Edit today's target">
              <Icons.Edit />
            </button>
          )}
        </div>
        <div className="bg-slate-50 rounded-xl p-3 text-center">
          <p className="text-[10px] text-slate-400 font-medium mb-1">This Month</p>
          {mp?.has_target ? (
            <div className="flex flex-col items-center">
              <ProgressRing pct={mp.leads_pct || 0} size={48} color={mp.leads_pct >= 100 ? "#10b981" : "#f59e0b"} />
              <p className="text-[10px] text-slate-500 mt-1">{mp.actual_leads}/{mp.target_leads} leads</p>
            </div>
          ) : <p className="text-xs text-slate-400 mt-2">No target</p>}
        </div>
      </div>

      <div className="flex gap-2">
        <button onClick={onSetTarget} className="flex-1 py-2 text-xs font-semibold text-indigo-600 bg-indigo-50 hover:bg-indigo-100 rounded-xl transition-colors flex items-center justify-center gap-1">
          <Icons.Target /> Set Target
        </button>
        {dp?.has_target && (
          <button onClick={onEditDaily} className="flex-1 py-2 text-xs font-semibold text-amber-600 bg-amber-50 hover:bg-amber-100 rounded-xl transition-colors flex items-center justify-center gap-1">
            <Icons.Edit /> Edit Daily
          </button>
        )}
        <button onClick={onSelect} className="flex-1 py-2 text-xs font-semibold text-slate-600 bg-slate-50 hover:bg-slate-100 rounded-xl transition-colors flex items-center justify-center gap-1">
          <Icons.Chart /> Report
        </button>
      </div>
    </div>
  );
}

// ─── Main Page ─────────────────────────────────────────────────────────────────
export default function ManagerPage({ params: paramsPromise }: { params: Promise<{ domain: string }> }) {
  const resolvedParams = React.use(paramsPromise);
  const domain = APP_SLUG;
  const router = useRouter();

  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [allUsers, setAllUsers] = useState<User[]>([]);
  const [monthlyTargets, setMonthlyTargets] = useState<MonthlyTarget[]>([]);
  const [activeTab, setActiveTab] = useState<"overview" | "targets" | "input_params" | "report" | "broadcast" | "holidays">("overview");
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [agentReport, setAgentReport] = useState<any>(null);
  const [agentDailyTargets, setAgentDailyTargets] = useState<DailyTarget[]>([]);
  const [loadingReport, setLoadingReport] = useState(false);
  const [generatingPdf, setGeneratingPdf] = useState(false);
  const [showPdfModal, setShowPdfModal] = useState(false);
  const [pdfDateFrom, setPdfDateFrom] = useState("");
  const [pdfDateTo, setPdfDateTo] = useState("");
  const [reportDateFrom, setReportDateFrom] = useState("");
  const [reportDateTo, setReportDateTo] = useState("");
  const reportRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<HTMLDivElement>(null);

  // Targets tab: expanded agent daily targets
  const [expandedAgentId, setExpandedAgentId] = useState<number | null>(null);
  const [expandedDailyTargets, setExpandedDailyTargets] = useState<DailyTarget[]>([]);
  const [loadingExpanded, setLoadingExpanded] = useState(false);

  // Month/Year selector
  const now = new Date();
  const [selMonth, setSelMonth] = useState(now.getMonth() + 1);
  const [selYear, setSelYear] = useState(now.getFullYear());

  // Set Target Modal
  const [targetModal, setTargetModal] = useState<{ agent: Agent | null; existing: MonthlyTarget | null }>({ agent: null, existing: null });
  const [targetForm, setTargetForm] = useState({ target_leads: "", target_amount: "", target_dialed_calls: "", target_call_time: "" });
  const [savingTarget, setSavingTarget] = useState(false);

  // Daily Target Override Modal
  const [dailyModal, setDailyModal] = useState<{ target: DailyTarget | null }>({ target: null });
  const [dailyForm, setDailyForm] = useState({ target_leads: "", target_amount: "" });
  const [savingDaily, setSavingDaily] = useState(false);

  // Broadcast Notification
  const [broadcastForm, setBroadcastForm] = useState({ agent_id: "all", title: "", message: "" });
  const [broadcasting, setBroadcasting] = useState(false);
  const [broadcastResult, setBroadcastResult] = useState<string | null>(null);

  // Input Parameters tab (daily)
  const todayStr = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;
  const [paramsDate, setParamsDate] = useState(todayStr);
  const [paramsDailyTargets, setParamsDailyTargets] = useState<DailyTarget[]>([]);
  const [loadingParams, setLoadingParams] = useState(false);
  const [paramsForms, setParamsForms] = useState<Record<number, { dialed_calls: string; call_time: string }>>({}); 
  const [savingParams, setSavingParams] = useState<number | null>(null);
  const [paramsSaved, setParamsSaved] = useState<number | null>(null);
  const [globalParams, setGlobalParams] = useState({ dialed_calls: "", call_time: "" });
  const [savingAllParams, setSavingAllParams] = useState(false);

  // Holidays
  const [holidays, setHolidays] = useState<Holiday[]>([]);
  const [holidayName, setHolidayName] = useState("");
  const [savingHoliday, setSavingHoliday] = useState(false);

  const token = () => localStorage.getItem(`${domain}_access`) || "";
  const api = (path: string) => `${getApiBase(domain)}${path}`;

  // ── Auth + Load ─────────────────────────────────────────────────────────────
  useEffect(() => {
    const tk = localStorage.getItem(`${domain}_access`);
    if (!tk) { router.push(`/login`); return; }
    fetch(api("/api/users/me/"), { headers: { Authorization: `Bearer ${tk}` } })
      .then(r => { if (!r.ok) throw new Error("unauth"); return r.json(); })
      .then(d => {
        if (!d.is_staff && !d.is_general_manager && !d.is_manager) { router.push(`/`); return; }
        setCurrentUser(d);
        setLoading(false);
      })
      .catch(() => router.push(`/login`));
  }, [domain, router]);

  // ── Load Dashboard Data ─────────────────────────────────────────────────────
  const loadDashboard = useCallback(async () => {
    const tk = token();
    if (!currentUser) return;
    try {
      const ts = Date.now();
      // Choose right endpoint based on role
      const endpoint = (currentUser.is_staff || currentUser.is_general_manager)
        ? api(`/api/ai-manager/dashboard/?month=${selMonth}&year=${selYear}&_t=${ts}`)
        : api(`/api/ai-manager/team-performance/?month=${selMonth}&year=${selYear}&_t=${ts}`);
      const [dashR, usersR, mtR] = await Promise.all([
        fetch(endpoint, { headers: { Authorization: `Bearer ${tk}` } }),
        fetch(api(`/api/users/?_t=${ts}`), { headers: { Authorization: `Bearer ${tk}` } }),
        fetch(api(`/api/ai-manager/monthly-targets/?month=${selMonth}&year=${selYear}&_t=${ts}`), { headers: { Authorization: `Bearer ${tk}` } }),
      ]);
      if (dashR.ok) {
        const d = await dashR.json();
        setAgents(d.agents || []);
      }
      if (usersR.ok) { const d = await usersR.json(); setAllUsers(Array.isArray(d) ? d : d.results || []); }
      if (mtR.ok) { const d = await mtR.json(); setMonthlyTargets(Array.isArray(d) ? d : d.results || []); }
    } catch {}
  }, [currentUser, selMonth, selYear, domain]);

  useEffect(() => { loadDashboard(); }, [loadDashboard]);

  // ── Load Agent Detailed Report ──────────────────────────────────────────────
  const loadAgentReport = async (agent: Agent, from?: string, to?: string) => {
    setSelectedAgent(agent);
    setActiveTab("report");
    
    let dFrom = from;
    let dTo = to;
    if (!dFrom || !dTo) {
      const lastDay = new Date(selYear, selMonth, 0).getDate();
      dFrom = `${selYear}-${String(selMonth).padStart(2,'0')}-01`;
      dTo = `${selYear}-${String(selMonth).padStart(2,'0')}-${lastDay}`;
    }
    setReportDateFrom(dFrom);
    setReportDateTo(dTo);
    
    setLoadingReport(true);
    try {
      const tk = token();
      const ts = Date.now();
      const [perfR, dtR] = await Promise.all([
        fetch(api(`/api/users/${agent.id}/performance/?date_from=${dFrom}&date_to=${dTo}&_t=${ts}`), { headers: { Authorization: `Bearer ${tk}` } }),
        fetch(api(`/api/ai-manager/daily-targets/?agent=${agent.id}&date_from=${dFrom}&date_to=${dTo}&_t=${ts}`), { headers: { Authorization: `Bearer ${tk}` } }),
      ]);
      if (perfR.ok) setAgentReport(await perfR.json());
      if (dtR.ok) { const d = await dtR.json(); setAgentDailyTargets(Array.isArray(d) ? d : d.results || []); }
    } catch {}
    setLoadingReport(false);
  };

  const generatePdfWithDates = async () => {
    if (!reportRef.current || !selectedAgent || !pdfDateFrom || !pdfDateTo) return;
    setGeneratingPdf(true);
    try {
      // 1. Fetch data for selected dates
      const tk = token();
      const ts = Date.now();
      const [perfR, dtR] = await Promise.all([
        fetch(api(`/api/users/${selectedAgent.id}/performance/?date_from=${pdfDateFrom}&date_to=${pdfDateTo}&_t=${ts}`), { headers: { Authorization: `Bearer ${tk}` } }),
        fetch(api(`/api/ai-manager/daily-targets/?agent=${selectedAgent.id}&date_from=${pdfDateFrom}&date_to=${pdfDateTo}&_t=${ts}`), { headers: { Authorization: `Bearer ${tk}` } }),
      ]);
      
      let newReport: any = null;
      let newDaily: DailyTarget[] = [];
      if (perfR.ok) newReport = await perfR.json();
      if (dtR.ok) { const d = await dtR.json(); newDaily = Array.isArray(d) ? d : d.results || []; }

      setAgentReport(newReport);
      setAgentDailyTargets(newDaily);
      
      // Wait a moment for React to render chart animations
      await new Promise(r => setTimeout(r, 600));

      const doc = new jsPDF('p', 'pt', 'a4');
      const pageWidth = doc.internal.pageSize.getWidth();

      // HEADER
      doc.setFontSize(22);
      doc.setTextColor(30, 41, 59); // slate-800
      doc.text("Performance Report", 40, 50);

      doc.setFontSize(12);
      doc.setTextColor(100, 116, 139); // slate-500
      doc.text(`Employee: ${selectedAgent.name} (${selectedAgent.role})`, 40, 75);
      doc.text(`Period: ${pdfDateFrom} to ${pdfDateTo}`, 40, 95);

      let currentY = 130;

      // SUMMARY METRICS
      if (newReport?.summary) {
        doc.setFontSize(14);
        doc.setTextColor(30, 41, 59);
        doc.text("Summary Metrics", 40, currentY);
        currentY += 15;

        autoTable(doc, {
          startY: currentY,
          head: [['Pipeline Value', 'Won Value', 'Conversion Rate']],
          body: [[
            `Rs. ${(newReport.summary.pipeline_value || 0).toLocaleString('en-IN')}`,
            `Rs. ${(newReport.summary.won_value || 0).toLocaleString('en-IN')}`,
            `${newReport.summary.win_rate || 0}%`
          ]],
          theme: 'grid',
          headStyles: { fillColor: [99, 102, 241], textColor: [255, 255, 255], fontStyle: 'bold' },
          styles: { fontSize: 11, halign: 'center', cellPadding: 8 }
        });
        currentY = (doc as any).lastAutoTable.finalY + 35;
      }

      // DAILY PERFORMANCE CHART
      if (chartRef.current && newDaily.length > 0) {
        const chartImg = await htmlToImage.toPng(chartRef.current, { backgroundColor: '#ffffff', pixelRatio: 2 });
        const chartW = pageWidth - 80;
        const aspect = chartRef.current.offsetHeight / chartRef.current.offsetWidth;
        const chartH = chartW * aspect;

        doc.setFontSize(14);
        doc.setTextColor(30, 41, 59);
        doc.text("Daily Performance Trends", 40, currentY);
        currentY += 15;
        
        doc.addImage(chartImg, 'PNG', 40, currentY, chartW, chartH);
        currentY += chartH + 35;
      }

      // DAILY METRICS TABLE
      if (newDaily.length > 0) {
        if (currentY > doc.internal.pageSize.getHeight() - 100) {
           doc.addPage();
           currentY = 40;
        }

        doc.setFontSize(14);
        doc.setTextColor(30, 41, 59);
        doc.text("Daily Targets & Achievement", 40, currentY);
        currentY += 15;

        const tableData = newDaily.map(dt => {
           return [
             new Date(dt.date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' }),
             `${dt.achieved_dialed_calls} / ${dt.target_dialed_calls > 0 ? dt.target_dialed_calls : 'no target'}`,
             `${dt.achieved_call_time} / ${dt.target_call_time > 0 ? dt.target_call_time : 'no target'}`,
             dt.status
           ];
        });

        autoTable(doc, {
          startY: currentY,
          head: [['Date', 'Dialed Calls (Achieved / Target)', 'Call Time (Achieved / Target)', 'Status']],
          body: tableData,
          theme: 'striped',
          headStyles: { fillColor: [241, 245, 249], textColor: [100, 116, 139], fontStyle: 'bold' },
          styles: { fontSize: 10, cellPadding: 6 }
        });
        currentY = (doc as any).lastAutoTable.finalY + 35;
      }

      // RECENT LEADS
      if (newReport?.recent_leads && newReport.recent_leads.length > 0) {
        if (currentY > doc.internal.pageSize.getHeight() - 100) {
           doc.addPage();
           currentY = 40;
        }

        doc.setFontSize(14);
        doc.setTextColor(30, 41, 59);
        doc.text("Recent Leads Activity", 40, currentY);
        currentY += 15;

        const leadsData = newReport.recent_leads.map((l: any) => [
          l.name,
          l.date,
          l.status,
          `Rs. ${l.value.toLocaleString('en-IN')}`
        ]);

        autoTable(doc, {
          startY: currentY,
          head: [['Lead Name', 'Date', 'Status', 'Value']],
          body: leadsData,
          theme: 'striped',
          headStyles: { fillColor: [241, 245, 249], textColor: [100, 116, 139], fontStyle: 'bold' },
          styles: { fontSize: 10, cellPadding: 6 }
        });
      }

      doc.save(`${selectedAgent.name.replace(/\s+/g, '_')}_Report_${pdfDateFrom}_to_${pdfDateTo}.pdf`);
      
      setShowPdfModal(false);
      loadAgentReport(selectedAgent); // Revert back to original data
    } catch (err: any) {
      console.error("PDF generation failed", err);
      alert("Failed to generate PDF. Error: " + (err?.message || err));
      loadAgentReport(selectedAgent); // Revert back on error too
    }
    setGeneratingPdf(false);
  };

  // ── Toggle daily targets expansion in Targets tab ──────────────────────────
  const toggleDailyExpand = async (agentId: number) => {
    if (expandedAgentId === agentId) { setExpandedAgentId(null); return; }
    setExpandedAgentId(agentId);
    setLoadingExpanded(true);
    try {
      const tk = token();
      const ts = Date.now();
      const r = await fetch(api(`/api/ai-manager/daily-targets/?agent=${agentId}&date_from=${selYear}-${String(selMonth).padStart(2,'0')}-01&date_to=${selYear}-${String(selMonth).padStart(2,'0')}-${new Date(selYear, selMonth, 0).getDate()}&_t=${ts}`), { headers: { Authorization: `Bearer ${tk}` } });
      if (r.ok) { const d = await r.json(); setExpandedDailyTargets(Array.isArray(d) ? d : d.results || []); }
    } catch {}
    setLoadingExpanded(false);
  };

  // Refresh expanded daily targets after edit
  const refreshExpanded = async () => {
    if (!expandedAgentId) return;
    try {
      const tk = token();
      const ts = Date.now();
      const r = await fetch(api(`/api/ai-manager/daily-targets/?agent=${expandedAgentId}&date_from=${selYear}-${String(selMonth).padStart(2,'0')}-01&date_to=${selYear}-${String(selMonth).padStart(2,'0')}-${new Date(selYear, selMonth, 0).getDate()}&_t=${ts}`), { headers: { Authorization: `Bearer ${tk}` } });
      if (r.ok) { const d = await r.json(); setExpandedDailyTargets(Array.isArray(d) ? d : d.results || []); }
    } catch {}
  };

  // ── Open Target Modal ───────────────────────────────────────────────────────
  const openTargetModal = (agent: Agent) => {
    const existing = monthlyTargets.find(mt => mt.agent === agent.id && mt.month === selMonth && mt.year === selYear) || null;
    setTargetModal({ agent, existing });
    setTargetForm({ 
      target_leads: existing ? String(existing.target_leads) : "", 
      target_amount: existing ? existing.target_amount : "",
      target_dialed_calls: existing ? String(existing.target_dialed_calls) : "",
      target_call_time: existing ? String(existing.target_call_time) : ""
    });
  };

  // ── Save Monthly Target ─────────────────────────────────────────────────────
  const saveTarget = async () => {
    if (!targetModal.agent) return;
    setSavingTarget(true);
    const tk = token();
    const body = { 
        agent: targetModal.agent.id, 
        month: selMonth, 
        year: selYear, 
        target_leads: parseInt(targetForm.target_leads) || 0, 
        target_amount: parseFloat(targetForm.target_amount) || 0,
        target_dialed_calls: parseInt(targetForm.target_dialed_calls) || 0,
        target_call_time: parseInt(targetForm.target_call_time) || 0
    };
    const isUpdate = !!targetModal.existing;
    const url = isUpdate ? api(`/api/ai-manager/monthly-targets/${targetModal.existing!.id}/`) : api("/api/ai-manager/monthly-targets/");
    
    try {
        const res = await fetch(url, { method: isUpdate ? "PUT" : "POST", headers: { Authorization: `Bearer ${tk}`, "Content-Type": "application/json" }, body: JSON.stringify(body) });
        setSavingTarget(false);
        if (!res.ok) {
            alert("Failed to save target. Server responded with: " + await res.text());
            return;
        }
        setTargetModal({ agent: null, existing: null });
        loadDashboard();
        // Refresh expanded daily targets if this agent was expanded
        if (expandedAgentId === targetModal.agent?.id) {
          setTimeout(() => toggleDailyExpand(targetModal.agent!.id), 500);
        }
    } catch (e) {
        setSavingTarget(false);
        alert("Network error. Could not save target.");
    }
  };

  // ── Save Daily Target Override ──────────────────────────────────────────────
  const saveDailyTarget = async () => {
    if (!dailyModal.target) return;
    if (!dailyModal.target.id) {
        alert("Cannot edit this target because it lacks an ID. Please refresh the page.");
        return;
    }
    setSavingDaily(true);
    const tk = token();
    try {
        const res = await fetch(api(`/api/ai-manager/daily-targets/${dailyModal.target.id}/`), {
          method: "PATCH",
          headers: { Authorization: `Bearer ${tk}`, "Content-Type": "application/json" },
          body: JSON.stringify({ target_leads: parseInt(dailyForm.target_leads) || 0, target_amount: parseFloat(dailyForm.target_amount) || 0 }),
        });
        setSavingDaily(false);
        if (!res.ok) {
            alert("Failed to save target. Server responded with: " + await res.text());
            return;
        }
        setDailyModal({ target: null });
        if (selectedAgent) loadAgentReport(selectedAgent);
        refreshExpanded();
        loadDashboard();
    } catch (e) {
        setSavingDaily(false);
        alert("Network error. Could not save target.");
    }
  };

  // ── Broadcast Notification ──────────────────────────────────────────────────
  const sendBroadcast = async () => {
    if (!broadcastForm.message) return;
    setBroadcasting(true);
    const tk = token();
    const r = await fetch(api("/api/ai-manager/custom-reminders/"), {
      method: "POST",
      headers: { Authorization: `Bearer ${tk}`, "Content-Type": "application/json" },
      body: JSON.stringify({ agent_id: broadcastForm.agent_id, title: broadcastForm.title || "Notice from Manager", message: broadcastForm.message }),
    });
    if (r.ok) {
      const d = await r.json();
      setBroadcastResult(`✅ Sent to ${d.created} recipient(s) successfully`);
      setBroadcastForm({ agent_id: "all", title: "", message: "" });
    } else {
      setBroadcastResult("❌ Failed to send notification");
    }
    setBroadcasting(false);
    setTimeout(() => setBroadcastResult(null), 4000);
  };

  // ── Load Holidays ──────────────────────────────────────────────────────────
  const loadHolidays = useCallback(async () => {
    try {
      const tk = token();
      const r = await fetch(api(`/api/ai-manager/holidays/?month=${selMonth}&year=${selYear}`), { headers: { Authorization: `Bearer ${tk}` } });
      if (r.ok) { const d = await r.json(); setHolidays(Array.isArray(d) ? d : d.results || []); }
    } catch {}
  }, [selMonth, selYear, domain]);

  useEffect(() => { loadHolidays(); }, [loadHolidays]);

  const addHoliday = async (dateStr: string, name: string) => {
    if (!name.trim()) return;
    setSavingHoliday(true);
    const tk = token();
    const r = await fetch(api("/api/ai-manager/holidays/"), {
      method: "POST",
      headers: { Authorization: `Bearer ${tk}`, "Content-Type": "application/json" },
      body: JSON.stringify({ date: dateStr, name: name.trim() }),
    });
    if (r.ok) { loadHolidays(); loadDashboard(); }
    setSavingHoliday(false);
  };

  const removeHoliday = async (id: number) => {
    const tk = token();
    await fetch(api(`/api/ai-manager/holidays/${id}/`), { method: "DELETE", headers: { Authorization: `Bearer ${tk}` } });
    loadHolidays();
    loadDashboard();
  };

  // ── Load daily targets for Input Parameters tab ──
  const loadParamsDailyTargets = useCallback(async (dateStr: string) => {
    setLoadingParams(true);
    setParamsForms({});
    try {
      const tk = token();
      const ts = Date.now();
      const r = await fetch(api(`/api/ai-manager/daily-targets/?date_from=${dateStr}&date_to=${dateStr}&_t=${ts}`), { headers: { Authorization: `Bearer ${tk}` } });
      if (r.ok) { const d = await r.json(); setParamsDailyTargets(Array.isArray(d) ? d : d.results || []); }
      else setParamsDailyTargets([]);
    } catch { setParamsDailyTargets([]); }
    setLoadingParams(false);
  }, [domain]);

  useEffect(() => { if (activeTab === 'input_params') loadParamsDailyTargets(paramsDate); }, [activeTab, paramsDate]);

  // ── Silent realtime refresh of achieved call metrics ──
  // Pulls only the latest achieved call count & duration without clearing in-progress
  // target edits (paramsForms) or flashing the loading spinner.
  const refreshParamsAchieved = useCallback(async (dateStr: string) => {
    try {
      const tk = token();
      const ts = Date.now();
      const r = await fetch(api(`/api/ai-manager/daily-targets/?date_from=${dateStr}&date_to=${dateStr}&_t=${ts}`), { headers: { Authorization: `Bearer ${tk}` } });
      if (r.ok) { const d = await r.json(); setParamsDailyTargets(Array.isArray(d) ? d : d.results || []); }
    } catch {}
  }, [domain]);

  // Poll every 15s while the Input Parameters tab is open so connected-call count and
  // call duration stay live against their targets.
  useEffect(() => {
    if (activeTab !== 'input_params') return;
    const id = setInterval(() => refreshParamsAchieved(paramsDate), 15000);
    return () => clearInterval(id);
  }, [activeTab, paramsDate, refreshParamsAchieved]);

  if (loading) return <div className="flex items-center justify-center min-h-screen"><div className="w-8 h-8 border-4 border-indigo-600/30 border-t-indigo-600 rounded-full animate-spin" /></div>;

  const role = currentUser?.is_staff ? "Admin" : currentUser?.is_general_manager ? "General Manager" : "Manager";
  const roleGradient = currentUser?.is_staff ? "from-rose-500 to-pink-600" : currentUser?.is_general_manager ? "from-violet-500 to-purple-600" : "from-indigo-500 to-blue-600";

  // Stats
  const totalAgents = agents.length;
  const agentsWithTarget = agents.filter(a => a.monthly_progress?.has_target).length;
  const avgMonthPct = agents.filter(a => a.monthly_progress?.leads_pct).reduce((acc, a) => acc + (a.monthly_progress.leads_pct || 0), 0) / (agents.filter(a => a.monthly_progress?.leads_pct).length || 1);

  const getParamsVal = (agentId: number, field: 'dialed_calls' | 'call_time') => {
    if (paramsForms[agentId]) return paramsForms[agentId][field];
    const dt = paramsDailyTargets.find(d => d.agent === agentId);
    if (!dt) return "";
    return field === 'dialed_calls' ? String(dt.target_dialed_calls || "") : String(dt.target_call_time || "");
  };
  const setParamsField = (agentId: number, field: 'dialed_calls' | 'call_time', val: string) => {
    setParamsForms(prev => ({ ...prev, [agentId]: { dialed_calls: getParamsVal(agentId, 'dialed_calls'), call_time: getParamsVal(agentId, 'call_time'), [field]: val } }));
  };

  const saveInputParams = async (agent: Agent) => {
    const dt = paramsDailyTargets.find(d => d.agent === agent.id);
    if (!dt) { alert(`No daily target exists for ${agent.name} on this date. Set a monthly target first.`); return; }
    setSavingParams(agent.id);
    const tk = token();
    try {
      const res = await fetch(api(`/api/ai-manager/daily-targets/${dt.id}/`), {
        method: "PATCH",
        headers: { Authorization: `Bearer ${tk}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          target_dialed_calls: parseInt(getParamsVal(agent.id, 'dialed_calls')) || 0,
          target_call_time: parseInt(getParamsVal(agent.id, 'call_time')) || 0,
        }),
      });
      if (res.ok) {
        setParamsSaved(agent.id);
        setTimeout(() => setParamsSaved(null), 2000);
        loadParamsDailyTargets(paramsDate);
      } else {
        alert("Failed to save: " + await res.text());
      }
    } catch { alert("Network error"); }
    setSavingParams(null);
  };

  const applyGlobalParams = () => {
    const dCalls = globalParams.dialed_calls;
    const cTime = globalParams.call_time;
    if (!dCalls && !cTime) return;
    setParamsForms(prev => {
      const next = { ...prev };
      agents.forEach(agent => {
        const dt = paramsDailyTargets.find(d => d.agent === agent.id);
        if (dt) {
           next[agent.id] = { 
             dialed_calls: dCalls || getParamsVal(agent.id, 'dialed_calls'), 
             call_time: cTime || getParamsVal(agent.id, 'call_time')
           };
        }
      });
      return next;
    });
  };

  const saveAllInputParams = async () => {
    setSavingAllParams(true);
    const tk = token();
    const promises = agents.map(agent => {
      const dt = paramsDailyTargets.find(d => d.agent === agent.id);
      if (!dt) return null;
      const dCalls = parseInt(getParamsVal(agent.id, 'dialed_calls'));
      const cTime = parseInt(getParamsVal(agent.id, 'call_time'));
      if(isNaN(dCalls) && isNaN(cTime)) return null; 
      return fetch(api(`/api/ai-manager/daily-targets/${dt.id}/`), {
        method: "PATCH",
        headers: { Authorization: `Bearer ${tk}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          target_dialed_calls: dCalls || 0,
          target_call_time: cTime || 0,
        }),
      });
    });
    
    await Promise.all(promises.filter(Boolean));
    await loadParamsDailyTargets(paramsDate);
    setSavingAllParams(false);
  };

  const tabs = [
    { id: "overview", label: "Team Overview", icon: <Icons.Users /> },
    { id: "targets", label: "Set Targets", icon: <Icons.Target /> },
    { id: "input_params", label: "Input Parameters", icon: <Icons.Phone /> },
    { id: "holidays", label: "Holidays", icon: <Icons.Calendar /> },
    { id: "report", label: "Employee Report", icon: <Icons.Chart /> },
    { id: "broadcast", label: "Broadcast", icon: <Icons.Bell /> },
  ];

  return (
    <div className="min-h-screen bg-[#f5f7fb]" style={{ fontFamily: "'Inter', sans-serif" }}>
      {/* ── Header ── */}
      <div className={`bg-gradient-to-r ${roleGradient} px-8 py-8`}>
        <div className="max-w-7xl mx-auto">
          <div className="flex items-center justify-between flex-wrap gap-4">
            <div>
              <div className="flex items-center gap-3 mb-1">
                <span className="bg-white/20 text-white text-xs font-bold px-3 py-1 rounded-full">{role}</span>
              </div>
              <h1 className="text-2xl font-black text-white">Manager Module</h1>
              <p className="text-white/70 text-sm mt-1">Manage targets, view reports, and broadcast notifications</p>
            </div>
            {/* Month/Year Selector */}
            <div className="flex items-center gap-2 bg-white/20 backdrop-blur-sm rounded-2xl px-4 py-2">
              <select value={selMonth} onChange={e => setSelMonth(parseInt(e.target.value))} className="bg-transparent text-white font-semibold text-sm outline-none cursor-pointer">
                {MONTHS.map((m, i) => <option key={i} value={i+1} className="text-slate-800">{m}</option>)}
              </select>
              <select value={selYear} onChange={e => setSelYear(parseInt(e.target.value))} className="bg-transparent text-white font-semibold text-sm outline-none cursor-pointer">
                {[2024, 2025, 2026, 2027].map(y => <option key={y} value={y} className="text-slate-800">{y}</option>)}
              </select>
            </div>
          </div>

          {/* Stats Row */}
          <div className="grid grid-cols-3 gap-4 mt-6">
            {[
              { label: "Total Members", value: totalAgents, sub: "in scope" },
              { label: "With Targets", value: agentsWithTarget, sub: `of ${totalAgents}` },
              { label: "Avg Achievement", value: `${Math.round(avgMonthPct)}%`, sub: "this month" },
            ].map(s => (
              <div key={s.label} className="bg-white/15 backdrop-blur-sm rounded-2xl p-4">
                <p className="text-white/60 text-xs font-medium mb-1">{s.label}</p>
                <p className="text-white font-black text-2xl">{s.value}</p>
                <p className="text-white/50 text-xs">{s.sub}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── Tabs ── */}
      <div className="max-w-7xl mx-auto px-8">
        <div className="flex gap-1 bg-white rounded-2xl shadow-sm border border-slate-100 p-1.5 mt-6 w-fit">
          {tabs.map(t => (
            <button key={t.id} onClick={() => { setActiveTab(t.id as any); if (t.id !== "report") setSelectedAgent(null); }}
              className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold transition-all ${activeTab === t.id ? "bg-indigo-600 text-white shadow-md shadow-indigo-200" : "text-slate-500 hover:text-slate-700 hover:bg-slate-50"}`}>
              {t.icon} {t.label}
            </button>
          ))}
        </div>

        <div className="mt-6 pb-10">
          {/* ── OVERVIEW TAB ── */}
          {activeTab === "overview" && (
            <div>
              <div className="flex items-center justify-between mb-5">
                <h2 className="text-lg font-bold text-slate-800">Team Performance — {MONTHS[selMonth - 1]} {selYear}</h2>
                <span className="text-xs text-slate-400">{agents.length} members</span>
              </div>
              {agents.length === 0 ? (
                <div className="bg-white rounded-2xl border border-slate-100 py-20 flex flex-col items-center justify-center">
                  <div className="w-16 h-16 rounded-2xl bg-slate-50 flex items-center justify-center text-slate-300 mb-4 text-2xl">👥</div>
                  <p className="font-semibold text-slate-500">No team members found</p>
                  <p className="text-xs text-slate-400 mt-1">Members will appear here once added to the team</p>
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                  {agents.map(agent => (
                    <AgentCard key={agent.id} agent={agent} onSelect={() => loadAgentReport(agent)} onSetTarget={() => { openTargetModal(agent); setActiveTab("targets"); }} onEditDaily={() => { const dp = agent.daily_progress; if (dp?.has_target && dp.id) { setDailyModal({ target: { id: dp.id, agent: agent.id, date: dp.date, target_leads: dp.target_leads, target_amount: String(dp.target_amount), status: dp.status, is_manual: dp.is_manual } as any }); setDailyForm({ target_leads: String(dp.target_leads), target_amount: String(dp.target_amount) }); }}} />
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ── TARGETS TAB ── */}
          {activeTab === "targets" && (
            <div>
              <div className="flex items-center justify-between mb-5">
                <h2 className="text-lg font-bold text-slate-800">Monthly Targets — {MONTHS[selMonth - 1]} {selYear}</h2>
                <p className="text-xs text-slate-400">Click a row to view auto-calculated daily targets. Edit any day inline.</p>
              </div>
              <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-slate-50 border-b border-slate-100">
                      <tr>
                        <th className="text-left px-5 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Employee</th>
                        <th className="text-left px-5 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Role</th>
                        <th className="text-left px-5 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Monthly Leads</th>
                        <th className="text-left px-5 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Monthly Amount</th>
                        <th className="text-left px-5 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Daily (Auto)</th>
                        <th className="text-left px-5 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Achievement</th>
                        <th className="text-right px-5 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Action</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-50">
                      {agents.map(agent => {
                        const mt = monthlyTargets.find(m => m.agent === agent.id);
                        const mp = agent.monthly_progress;
                        const isExpanded = expandedAgentId === agent.id;
                        // Estimate daily = monthly / ~22 working days
                        const estDaily = mt ? Math.ceil(mt.target_leads / 22) : 0;
                        return (
                          <React.Fragment key={agent.id}>
                          <tr onClick={() => mt && toggleDailyExpand(agent.id)} className={`hover:bg-slate-50/50 transition-colors ${mt ? 'cursor-pointer' : ''} ${isExpanded ? 'bg-indigo-50/40' : ''}`}>
                            <td className="px-5 py-4">
                              <div className="flex items-center gap-3">
                                <div className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-white text-xs font-bold">{agent.name.charAt(0)}</div>
                                <div>
                                  <span className="font-semibold text-slate-800">{agent.name}</span>
                                  {mt && <span className="ml-2 text-slate-400 text-[10px]">{isExpanded ? '▲' : '▼'}</span>}
                                </div>
                              </div>
                            </td>
                            <td className="px-5 py-4"><span className="text-xs font-semibold text-slate-500">{agent.role}</span></td>
                            <td className="px-5 py-4">
                              {mt ? <span className="font-bold text-slate-800">{mt.target_leads}</span> : <span className="text-slate-300">—</span>}
                            </td>
                            <td className="px-5 py-4">
                              {mt ? <span className="font-bold text-slate-800">₹{parseFloat(mt.target_amount).toLocaleString('en-IN')}</span> : <span className="text-slate-300">—</span>}
                            </td>
                            <td className="px-5 py-4">
                              {mt ? <span className="text-xs font-semibold text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded-full">~{estDaily}/day</span> : <span className="text-slate-300">—</span>}
                            </td>
                            <td className="px-5 py-4">
                              {mp?.has_target ? (
                                <div className="flex items-center gap-2">
                                  <div className="flex-1 max-w-[80px] h-2 bg-slate-100 rounded-full">
                                    <div className="h-full rounded-full transition-all" style={{ width: `${Math.min(mp.leads_pct, 100)}%`, background: mp.leads_pct >= 100 ? "#10b981" : "#6366f1" }} />
                                  </div>
                                  <span className="text-xs font-semibold text-slate-600">{Math.round(mp.leads_pct)}%</span>
                                </div>
                              ) : <span className="text-slate-300 text-xs">No target set</span>}
                            </td>
                            <td className="px-5 py-4 text-right">
                              <button onClick={(e) => { e.stopPropagation(); openTargetModal(agent); }} className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-indigo-50 text-indigo-600 text-xs font-semibold rounded-lg hover:bg-indigo-100 transition-colors">
                                <Icons.Edit /> {mt ? "Edit" : "Set"}
                              </button>
                            </td>
                          </tr>
                          {/* ── Expanded Daily Targets ── */}
                          {isExpanded && (
                            <tr>
                              <td colSpan={7} className="p-0">
                                <div className="bg-gradient-to-b from-indigo-50/60 to-white px-6 py-4 border-t border-indigo-100">
                                  <div className="flex items-center justify-between mb-3">
                                    <div className="flex items-center gap-2">
                                      <Icons.Calendar />
                                      <h4 className="font-bold text-slate-700 text-sm">Daily Targets — {agent.name}</h4>
                                      <span className="text-[10px] bg-indigo-100 text-indigo-600 font-bold px-2 py-0.5 rounded-full">Auto-calculated from monthly</span>
                                    </div>
                                    <span className="text-[10px] text-slate-400">{expandedDailyTargets.length} days</span>
                                  </div>
                                  {loadingExpanded ? (
                                    <div className="flex justify-center py-6"><div className="w-5 h-5 border-2 border-indigo-600/30 border-t-indigo-600 rounded-full animate-spin" /></div>
                                  ) : expandedDailyTargets.length === 0 ? (
                                    <p className="text-xs text-slate-400 text-center py-4">No daily targets generated yet. Set a monthly target first.</p>
                                  ) : (
                                    <div className="bg-white rounded-xl border border-slate-100 overflow-hidden max-h-64 overflow-y-auto">
                                      <table className="w-full text-xs">
                                        <thead className="bg-slate-50 sticky top-0">
                                          <tr>
                                            <th className="text-left px-3 py-2 font-semibold text-slate-500">Date</th>
                                            <th className="text-left px-3 py-2 font-semibold text-slate-500">Leads</th>
                                            <th className="text-left px-3 py-2 font-semibold text-slate-500">Amount</th>
                                            <th className="text-left px-3 py-2 font-semibold text-slate-500">Status</th>
                                            <th className="text-right px-3 py-2 font-semibold text-slate-500">Edit</th>
                                          </tr>
                                        </thead>
                                        <tbody className="divide-y divide-slate-50">
                                          {expandedDailyTargets.map(dt => {
                                            const sc = dt.status === 'achieved' ? 'bg-emerald-50 text-emerald-600' : dt.status === 'missed' ? 'bg-red-50 text-red-500' : 'bg-slate-50 text-slate-500';
                                            return (
                                              <tr key={dt.id} className={`hover:bg-slate-50/50 ${dt.is_manual ? 'bg-amber-50/30' : ''}`}>
                                                <td className="px-3 py-2">
                                                  <span className="font-medium text-slate-700">{new Date(dt.date + 'T12:00:00').toLocaleDateString('en-IN', { day: 'numeric', month: 'short', weekday: 'short' })}</span>
                                                  {dt.is_manual && <span className="ml-1 text-[9px] font-bold bg-amber-100 text-amber-600 px-1 py-0.5 rounded">Manual</span>}
                                                </td>
                                                <td className="px-3 py-2 font-semibold text-slate-800">{dt.target_leads}</td>
                                                <td className="px-3 py-2 font-semibold text-slate-800">₹{parseFloat(dt.target_amount).toLocaleString('en-IN')}</td>
                                                <td className="px-3 py-2"><span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full ${sc}`}>{dt.status}</span></td>
                                                <td className="px-3 py-2 text-right">
                                                  <button onClick={(e) => { e.stopPropagation(); setDailyModal({ target: dt }); setDailyForm({ target_leads: String(dt.target_leads), target_amount: dt.target_amount }); }}
                                                    className="inline-flex items-center gap-1 px-2 py-0.5 bg-indigo-50 text-indigo-600 text-[10px] font-semibold rounded hover:bg-indigo-100 transition-colors">
                                                    <Icons.Edit /> Edit
                                                  </button>
                                                </td>
                                              </tr>
                                            );
                                          })}
                                        </tbody>
                                      </table>
                                    </div>
                                  )}
                                </div>
                              </td>
                            </tr>
                          )}
                          </React.Fragment>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* ── REPORT TAB ── */}
          {activeTab === "report" && (
            <div>
              {!selectedAgent ? (
                <div>
                  <h2 className="text-lg font-bold text-slate-800 mb-5">Select Employee to View Report</h2>
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                    {agents.map(agent => (
                      <button key={agent.id} onClick={() => loadAgentReport(agent)} className="bg-white rounded-2xl border border-slate-100 shadow-sm hover:shadow-md hover:-translate-y-0.5 transition-all p-5 text-left">
                        <div className="flex items-center gap-3 mb-3">
                          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-white font-bold">{agent.name.charAt(0)}</div>
                          <div>
                            <p className="font-semibold text-slate-800 text-sm">{agent.name}</p>
                            <p className="text-xs text-slate-400">{agent.role}</p>
                          </div>
                        </div>
                        <div className="flex gap-4 text-xs text-slate-500">
                          <span>🎯 {agent.monthly_progress?.actual_leads || 0} enrolled</span>
                          <span>📂 {agent.total_leads} leads</span>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                <div>
                  <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between mb-5 gap-4">
                    <button onClick={() => setSelectedAgent(null)} className="flex items-center gap-2 text-slate-500 hover:text-slate-800 text-sm font-semibold transition-colors">
                      <Icons.Back /> Back to All Employees
                    </button>
                    
                    <div className="flex flex-wrap items-center gap-3">
                      <div className="flex items-center gap-2 bg-white border border-slate-200 rounded-xl px-3 py-2 shadow-sm">
                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">From</span>
                        <input type="date" value={reportDateFrom} onChange={e => loadAgentReport(selectedAgent!, e.target.value, reportDateTo)} className="text-xs font-semibold text-slate-700 bg-transparent outline-none cursor-pointer" />
                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider ml-1">To</span>
                        <input type="date" value={reportDateTo} onChange={e => loadAgentReport(selectedAgent!, reportDateFrom, e.target.value)} className="text-xs font-semibold text-slate-700 bg-transparent outline-none cursor-pointer" />
                      </div>

                      <button onClick={() => {
                          setPdfDateFrom(reportDateFrom);
                          setPdfDateTo(reportDateTo);
                          setShowPdfModal(true);
                        }} disabled={generatingPdf} className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white px-4 py-2 rounded-xl text-sm font-bold shadow-sm shadow-indigo-200 transition-all">
                        <Icons.Chart />
                        Download PDF
                      </button>
                    </div>
                  </div>
                  {loadingReport ? (
                    <div className="flex items-center justify-center py-20"><div className="w-8 h-8 border-4 border-indigo-600/30 border-t-indigo-600 rounded-full animate-spin" /></div>
                  ) : agentReport && (
                    <div ref={reportRef} className="space-y-6 pb-6 bg-[#f5f7fb]">
                      {/* Header */}
                      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-6">
                        <div className="flex items-center justify-between flex-wrap gap-4">
                          <div className="flex items-center gap-4">
                            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-white text-2xl font-black">{selectedAgent.name.charAt(0)}</div>
                            <div>
                              <h2 className="text-xl font-black text-slate-800">{selectedAgent.name}</h2>
                              <p className="text-slate-500 text-sm">{selectedAgent.role} · {agentReport.user_info?.id ? `ID #${agentReport.user_info.id}` : ""}</p>
                            </div>
                          </div>
                          <div className="flex gap-3">
                            <div className="text-center">
                              <p className="text-2xl font-black text-slate-800">{agentReport.summary?.won_count || 0}</p>
                              <p className="text-xs text-slate-400">Enrolled</p>
                            </div>
                            <div className="text-center">
                              <p className="text-2xl font-black text-slate-800">{agentReport.summary?.total_leads || 0}</p>
                              <p className="text-xs text-slate-400">Total Leads</p>
                            </div>
                            <div className="text-center">
                              <p className="text-2xl font-black text-emerald-600">{agentReport.summary?.win_rate || 0}%</p>
                              <p className="text-xs text-slate-400">Win Rate</p>
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* Monthly Progress */}
                      {selectedAgent.monthly_progress?.has_target && (
                        <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-6">
                          <h3 className="font-bold text-slate-800 mb-4">Monthly Target — {MONTHS[selMonth - 1]} {selYear}</h3>
                          <div className="grid grid-cols-2 gap-4">
                            <div className="bg-indigo-50 rounded-xl p-4 flex items-center gap-4">
                              <ProgressRing pct={selectedAgent.monthly_progress.leads_pct} size={64} color="#6366f1" />
                              <div>
                                <p className="text-sm font-bold text-slate-800">{selectedAgent.monthly_progress.actual_leads}/{selectedAgent.monthly_progress.target_leads} Leads</p>
                                <p className="text-xs text-slate-500">Converted this month</p>
                              </div>
                            </div>
                            <div className="bg-emerald-50 rounded-xl p-4 flex items-center gap-4">
                              <ProgressRing pct={selectedAgent.monthly_progress.amount_pct} size={64} color="#10b981" />
                              <div>
                                <p className="text-sm font-bold text-slate-800">₹{(selectedAgent.monthly_progress.actual_amount || 0).toLocaleString('en-IN')}</p>
                                <p className="text-xs text-slate-500">of ₹{(selectedAgent.monthly_progress.target_amount || 0).toLocaleString('en-IN')}</p>
                              </div>
                            </div>
                          </div>
                        </div>
                      )}

                      {/* Charts Section */}
                      {agentDailyTargets.length > 0 && (
                        <div ref={chartRef} className="bg-white rounded-2xl border border-slate-100 shadow-sm p-6">
                          <h3 className="font-bold text-slate-800 mb-4">Daily Performance Trends</h3>
                          <div className="h-[300px] w-full">
                            <ResponsiveContainer width="100%" height="100%">
                              <BarChart data={agentDailyTargets.map(dt => ({ name: new Date(dt.date).getDate().toString(), Calls: dt.achieved_dialed_calls, Time: dt.achieved_call_time, Leads: dt.target_leads }))} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                                <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: '#94a3b8' }} />
                                <YAxis yAxisId="left" axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: '#94a3b8' }} />
                                <YAxis yAxisId="right" orientation="right" axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: '#94a3b8' }} />
                                <RechartsTooltip contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)' }} cursor={{ fill: '#f8fafc' }} />
                                <Legend wrapperStyle={{ fontSize: '12px', fontWeight: 600, color: '#64748b' }} />
                                <Bar yAxisId="left" dataKey="Calls" fill="#6366f1" radius={[4, 4, 0, 0]} name="Calls Made" />
                                <Bar yAxisId="left" dataKey="Time" fill="#f59e0b" radius={[4, 4, 0, 0]} name="Call Time (min)" />
                                <Bar yAxisId="right" dataKey="Leads" fill="#10b981" radius={[4, 4, 0, 0]} name="Target Leads" />
                              </BarChart>
                            </ResponsiveContainer>
                          </div>
                        </div>
                      )}

                      {/* Daily Targets Table with Input Parameters */}
                      {agentDailyTargets.length > 0 && (
                        <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
                          <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
                            <div>
                              <h3 className="font-bold text-slate-800">Daily Performance — {MONTHS[selMonth - 1]} {selYear}</h3>
                              <p className="text-[10px] text-slate-400 mt-0.5">Leads, dialed calls, and call time tracked per day</p>
                            </div>
                            <span className="text-xs text-slate-400">{agentDailyTargets.length} days</span>
                          </div>
                          <div className="overflow-x-auto max-h-96 overflow-y-auto">
                            <table className="w-full text-sm">
                              <thead className="bg-slate-50 sticky top-0">
                                <tr>
                                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500">Date</th>
                                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500">Leads</th>
                                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500">Dialed Calls</th>
                                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500">Call Time</th>
                                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500">Status</th>
                                  <th className="text-right px-4 py-2.5 text-xs font-semibold text-slate-500">Override</th>
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-slate-50">
                                {agentDailyTargets.map(dt => {
                                  const dateStr = dt.date;
                                  const statusColor = dt.status === "achieved" ? "bg-emerald-50 text-emerald-600" : dt.status === "missed" ? "bg-red-50 text-red-500" : "bg-slate-50 text-slate-500";
                                  const callPct = dt.target_dialed_calls > 0 ? Math.round((dt.achieved_dialed_calls / dt.target_dialed_calls) * 100) : 0;
                                  const timePct = dt.target_call_time > 0 ? Math.round((dt.achieved_call_time / dt.target_call_time) * 100) : 0;
                                  return (
                                    <tr key={dt.id} className={`hover:bg-slate-50/50 transition-colors ${dt.is_manual ? "bg-amber-50/30" : ""}`}>
                                      <td className="px-4 py-3">
                                        <span className="font-medium text-slate-700">{new Date(dateStr + "T12:00:00").toLocaleDateString('en-IN', { day: 'numeric', month: 'short', weekday: 'short' })}</span>
                                        {dt.is_manual && <span className="ml-2 text-[10px] font-bold bg-amber-100 text-amber-600 px-1.5 py-0.5 rounded">Manual</span>}
                                      </td>
                                      <td className="px-4 py-3">
                                        <span className="font-semibold text-slate-800">{dt.target_leads}</span>
                                        <span className="text-slate-400 text-xs ml-1">target</span>
                                      </td>
                                      <td className="px-4 py-3">
                                        {dt.target_dialed_calls > 0 ? (
                                          <div>
                                            <div className="flex items-center gap-1.5">
                                              <span className="font-bold text-slate-800">{dt.achieved_dialed_calls}</span>
                                              <span className="text-slate-400 text-xs">/ {dt.target_dialed_calls}</span>
                                            </div>
                                            <div className="w-16 h-1.5 bg-slate-100 rounded-full mt-1">
                                              <div className="h-full rounded-full transition-all" style={{ width: `${Math.min(callPct, 100)}%`, background: callPct >= 100 ? "#10b981" : "#6366f1" }} />
                                            </div>
                                          </div>
                                        ) : (
                                          <div className="flex items-center gap-1.5">
                                            <span className="font-bold text-slate-800">{dt.achieved_dialed_calls}</span>
                                            <span className="text-slate-400 text-[10px]">no target</span>
                                          </div>
                                        )}
                                      </td>
                                      <td className="px-4 py-3">
                                        {dt.target_call_time > 0 ? (
                                          <div>
                                            <div className="flex items-center gap-1.5">
                                              <span className="font-bold text-slate-800">{dt.achieved_call_time}</span>
                                              <span className="text-slate-400 text-xs">/ {dt.target_call_time} min</span>
                                            </div>
                                            <div className="w-16 h-1.5 bg-slate-100 rounded-full mt-1">
                                              <div className="h-full rounded-full transition-all" style={{ width: `${Math.min(timePct, 100)}%`, background: timePct >= 100 ? "#10b981" : "#f59e0b" }} />
                                            </div>
                                          </div>
                                        ) : (
                                          <div className="flex items-center gap-1.5">
                                            <span className="font-bold text-slate-800">{dt.achieved_call_time}</span>
                                            <span className="text-slate-400 text-[10px]">no target</span>
                                          </div>
                                        )}
                                      </td>
                                      <td className="px-4 py-3">
                                        <span className={`text-[11px] font-bold px-2 py-0.5 rounded-full ${statusColor}`}>{dt.status}</span>
                                      </td>
                                      <td className="px-4 py-3 text-right">
                                        <button onClick={() => { setDailyModal({ target: dt }); setDailyForm({ target_leads: String(dt.target_leads), target_amount: dt.target_amount }); }}
                                          className="inline-flex items-center gap-1 px-2 py-1 bg-indigo-50 text-indigo-600 text-xs font-semibold rounded-lg hover:bg-indigo-100 transition-colors">
                                          <Icons.Edit /> Edit
                                        </button>
                                      </td>
                                    </tr>
                                  );
                                })}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      )}

                      {/* Status Breakdown */}
                      {agentReport.summary && (
                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                          <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5">
                            <p className="text-xs font-medium text-slate-400 mb-2">Pipeline Value</p>
                            <p className="text-2xl font-black text-slate-800">₹{(agentReport.summary.pipeline_value || 0).toLocaleString('en-IN')}</p>
                          </div>
                          <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5">
                            <p className="text-xs font-medium text-slate-400 mb-2">Won Value</p>
                            <p className="text-2xl font-black text-emerald-600">₹{(agentReport.summary.won_value || 0).toLocaleString('en-IN')}</p>
                          </div>
                          <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5">
                            <p className="text-xs font-medium text-slate-400 mb-2">Conversion Rate</p>
                            <p className="text-2xl font-black text-indigo-600">{agentReport.summary.win_rate || 0}%</p>
                          </div>
                        </div>
                      )}

                      {/* Recent Activity */}
                      {agentReport.recent_leads?.length > 0 && (
                        <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
                          <div className="px-6 py-4 border-b border-slate-100">
                            <h3 className="font-bold text-slate-800">Recent Leads</h3>
                          </div>
                          <div className="divide-y divide-slate-50">
                            {agentReport.recent_leads.map((l: any) => (
                              <div key={l.id} className="px-6 py-3 flex items-center justify-between">
                                <div>
                                  <p className="font-semibold text-slate-800 text-sm">{l.name}</p>
                                  <p className="text-xs text-slate-400">{l.date}</p>
                                </div>
                                <div className="text-right">
                                  <span className="text-xs font-semibold px-2 py-1 bg-slate-50 rounded-lg text-slate-600">{l.status}</span>
                                  <p className="text-xs text-slate-400 mt-1">₹{(l.value || 0).toLocaleString('en-IN')}</p>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* ── BROADCAST TAB ── */}
          {activeTab === "broadcast" && (
            <div className="max-w-2xl">
              <h2 className="text-lg font-bold text-slate-800 mb-5">Broadcast Notification</h2>
              <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-6 space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-500 mb-1.5 uppercase tracking-wide">Send To</label>
                  <select value={broadcastForm.agent_id} onChange={e => setBroadcastForm(f => ({ ...f, agent_id: e.target.value }))} className="w-full border border-slate-200 rounded-xl px-4 py-2.5 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-300">
                    <option value="all">📢 All Team Members</option>
                    {agents.map(a => <option key={a.id} value={a.id}>👤 {a.name}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-500 mb-1.5 uppercase tracking-wide">Title</label>
                  <input value={broadcastForm.title} onChange={e => setBroadcastForm(f => ({ ...f, title: e.target.value }))} placeholder="Notice from Manager" className="w-full border border-slate-200 rounded-xl px-4 py-2.5 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-300" />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-500 mb-1.5 uppercase tracking-wide">Message <span className="text-rose-500">*</span></label>
                  <textarea value={broadcastForm.message} onChange={e => setBroadcastForm(f => ({ ...f, message: e.target.value }))} rows={4} placeholder="Type your message here…" className="w-full border border-slate-200 rounded-xl px-4 py-2.5 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-300 resize-none" />
                </div>
                {broadcastResult && (
                  <div className={`text-sm font-semibold px-4 py-3 rounded-xl ${broadcastResult.startsWith("✅") ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-600"}`}>{broadcastResult}</div>
                )}
                <button onClick={sendBroadcast} disabled={broadcasting || !broadcastForm.message} className="w-full py-3 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white font-bold rounded-xl transition-all flex items-center justify-center gap-2">
                  {broadcasting ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <Icons.Send />}
                  {broadcasting ? "Sending…" : "Send Notification"}
                </button>
              </div>
            </div>
          )}

          {/* ── INPUT PARAMETERS TAB (Daily) ── */}
          {activeTab === "input_params" && (
            <div>
              <div className="flex items-center justify-between mb-5 flex-wrap gap-4">
                <div>
                  <h2 className="text-lg font-bold text-slate-800">Daily Input Parameters</h2>
                  <p className="text-xs text-slate-400 mt-0.5">Set dialed calls &amp; call time targets — connected calls and duration update live as agents dial</p>
                </div>
                <div className="flex items-center gap-3 bg-white border border-slate-200 rounded-xl px-4 py-2">
                  <Icons.Calendar />
                  <input type="date" value={paramsDate} onChange={e => setParamsDate(e.target.value)}
                    className="text-sm font-semibold text-slate-800 outline-none cursor-pointer bg-transparent" />
                  <button onClick={() => setParamsDate(todayStr)} className="text-[10px] font-bold text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded-full hover:bg-indigo-100 transition-colors">Today</button>
                </div>
              </div>

              {loadingParams ? (
                <div className="flex justify-center py-20"><div className="w-6 h-6 border-2 border-indigo-600/30 border-t-indigo-600 rounded-full animate-spin" /></div>
              ) : (
                <div className="space-y-6">
                  {/* Assign to All Widget */}
                  <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5 flex flex-wrap items-end gap-4">
                    <div>
                      <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">Set All Dialed Calls</label>
                      <input type="number" min="0" placeholder="e.g. 50" value={globalParams.dialed_calls} onChange={e => setGlobalParams(p => ({ ...p, dialed_calls: e.target.value }))} className="w-32 border border-slate-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300" />
                    </div>
                    <div>
                      <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">Set All Call Time (min)</label>
                      <input type="number" min="0" placeholder="e.g. 120" value={globalParams.call_time} onChange={e => setGlobalParams(p => ({ ...p, call_time: e.target.value }))} className="w-32 border border-slate-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300" />
                    </div>
                    <button onClick={applyGlobalParams} className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm font-bold rounded-xl transition-colors">Apply to Inputs</button>
                    <div className="flex-1" />
                    <button onClick={saveAllInputParams} disabled={savingAllParams} className="flex items-center gap-2 px-5 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-sm font-bold rounded-xl shadow-sm transition-colors">
                      {savingAllParams ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <Icons.Check />}
                      {savingAllParams ? "Saving..." : "Save All"}
                    </button>
                  </div>

                  {/* Agents Table */}
                  <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
                  <div className="px-5 py-3 border-b border-slate-100 bg-slate-50 flex items-center justify-between">
                    <span className="text-xs font-semibold text-slate-500">
                      {new Date(paramsDate + 'T12:00:00').toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
                    </span>
                    <div className="flex items-center gap-3">
                      <span className="inline-flex items-center gap-1.5 text-[10px] font-bold text-emerald-600" title="Connected calls & duration refresh automatically">
                        <span className="relative flex h-2 w-2">
                          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                          <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
                        </span>
                        LIVE
                      </span>
                      <span className="text-[10px] font-semibold text-slate-400">{paramsDailyTargets.length} target(s) found</span>
                    </div>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead className="bg-slate-50 border-b border-slate-100">
                        <tr>
                          <th className="text-left px-5 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Employee</th>
                          <th className="text-left px-5 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Role</th>
                          <th className="text-left px-5 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Dialed Calls Target</th>
                          <th className="text-left px-5 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Call Time Target (mins)</th>
                          <th className="text-left px-5 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Achieved (Live)</th>
                          <th className="text-right px-5 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Action</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-50">
                        {agents.map(agent => {
                          const dt = paramsDailyTargets.find(d => d.agent === agent.id);
                          const isSaving = savingParams === agent.id;
                          const isSaved = paramsSaved === agent.id;
                          return (
                            <tr key={agent.id} className={`hover:bg-slate-50/50 transition-colors ${!dt ? 'opacity-50' : ''}`}>
                              <td className="px-5 py-4">
                                <div className="flex items-center gap-3">
                                  <div className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-white text-xs font-bold">{agent.name.charAt(0)}</div>
                                  <span className="font-semibold text-slate-800">{agent.name}</span>
                                </div>
                              </td>
                              <td className="px-5 py-4"><span className="text-xs font-semibold text-slate-500">{agent.role}</span></td>
                              <td className="px-5 py-4">
                                {dt ? (
                                  <input
                                    type="number" min="0" placeholder="e.g. 25"
                                    value={getParamsVal(agent.id, 'dialed_calls')}
                                    onChange={e => setParamsField(agent.id, 'dialed_calls', e.target.value)}
                                    className="w-28 border border-slate-200 rounded-lg px-3 py-2 text-sm font-semibold text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-300 transition-all"
                                  />
                                ) : <span className="text-xs text-slate-300">No target</span>}
                              </td>
                              <td className="px-5 py-4">
                                {dt ? (
                                  <input
                                    type="number" min="0" placeholder="e.g. 60"
                                    value={getParamsVal(agent.id, 'call_time')}
                                    onChange={e => setParamsField(agent.id, 'call_time', e.target.value)}
                                    className="w-28 border border-slate-200 rounded-lg px-3 py-2 text-sm font-semibold text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-300 transition-all"
                                  />
                                ) : <span className="text-xs text-slate-300">No target</span>}
                              </td>
                              <td className="px-5 py-4">
                                {dt ? (() => {
                                  const callPct = dt.target_dialed_calls > 0 ? Math.round((dt.achieved_dialed_calls / dt.target_dialed_calls) * 100) : 0;
                                  const timePct = dt.target_call_time > 0 ? Math.round((dt.achieved_call_time / dt.target_call_time) * 100) : 0;
                                  return (
                                    <div className="space-y-2 min-w-[140px]">
                                      {/* Connected calls → dialed calls target */}
                                      <div>
                                        <div className="flex items-center justify-between gap-2 mb-0.5">
                                          <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide">Calls</span>
                                          <span className="text-xs font-bold text-slate-700">
                                            {dt.achieved_dialed_calls}{dt.target_dialed_calls > 0 && <span className="text-slate-400 font-normal">/{dt.target_dialed_calls}</span>}
                                          </span>
                                        </div>
                                        {dt.target_dialed_calls > 0 && (
                                          <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                                            <div className={`h-full rounded-full transition-all duration-500 ${callPct >= 100 ? 'bg-emerald-500' : 'bg-indigo-500'}`} style={{ width: `${Math.min(callPct, 100)}%` }} />
                                          </div>
                                        )}
                                      </div>
                                      {/* Connected call duration → call time target */}
                                      <div>
                                        <div className="flex items-center justify-between gap-2 mb-0.5">
                                          <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide">Time</span>
                                          <span className="text-xs font-bold text-slate-700">
                                            {dt.achieved_call_time}m{dt.target_call_time > 0 && <span className="text-slate-400 font-normal">/{dt.target_call_time}m</span>}
                                          </span>
                                        </div>
                                        {dt.target_call_time > 0 && (
                                          <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                                            <div className={`h-full rounded-full transition-all duration-500 ${timePct >= 100 ? 'bg-emerald-500' : 'bg-amber-500'}`} style={{ width: `${Math.min(timePct, 100)}%` }} />
                                          </div>
                                        )}
                                      </div>
                                    </div>
                                  );
                                })() : <span className="text-xs text-slate-300">—</span>}
                              </td>
                              <td className="px-5 py-4 text-right">
                                {dt ? (
                                  <button
                                    onClick={() => saveInputParams(agent)}
                                    disabled={isSaving}
                                    className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg transition-all ${
                                      isSaved ? 'bg-emerald-50 text-emerald-600' : 'bg-indigo-50 text-indigo-600 hover:bg-indigo-100'
                                    } disabled:opacity-50`}
                                  >
                                    {isSaving ? <div className="w-3.5 h-3.5 border-2 border-indigo-600/30 border-t-indigo-600 rounded-full animate-spin" /> : isSaved ? <Icons.Check /> : <Icons.Edit />}
                                    {isSaving ? 'Saving...' : isSaved ? 'Saved!' : 'Save'}
                                  </button>
                                ) : <span className="text-[10px] text-slate-300">Set monthly target first</span>}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
              )}
            </div>
          )}

          {/* ── HOLIDAYS TAB ── */}
          {activeTab === "holidays" && (
            <div className="max-w-4xl">
              <div className="flex items-center justify-between mb-5">
                <div>
                  <h2 className="text-lg font-bold text-slate-800">Holiday Calendar — {MONTHS[selMonth - 1]} {selYear}</h2>
                  <p className="text-xs text-slate-400 mt-0.5">Mark holidays to exclude them from daily target calculations</p>
                </div>
                <span className="text-xs font-semibold text-rose-600 bg-rose-50 px-3 py-1 rounded-full">{holidays.length} holiday{holidays.length !== 1 ? 's' : ''}</span>
              </div>

              <div className="grid lg:grid-cols-5 gap-5">
                {/* Calendar */}
                <div className="lg:col-span-3 bg-white rounded-2xl border border-slate-100 shadow-sm p-6">
                  <div className="grid grid-cols-7 gap-1 mb-2">
                    {['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map(d => (
                      <div key={d} className="text-[10px] font-bold text-slate-400 text-center py-1 uppercase">{d}</div>
                    ))}
                  </div>
                  <div className="grid grid-cols-7 gap-1">
                    {(() => {
                      const firstDay = new Date(selYear, selMonth - 1, 1).getDay();
                      const offset = firstDay === 0 ? 6 : firstDay - 1;
                      const daysInMonth = new Date(selYear, selMonth, 0).getDate();
                      const holidayMap = new Map(holidays.map(h => [h.date, h]));
                      const today = new Date();
                      const todayStr = `${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}-${String(today.getDate()).padStart(2,'0')}`;

                      const cells = [];
                      for (let i = 0; i < offset; i++) cells.push(<div key={`pad-${i}`} />);
                      for (let d = 1; d <= daysInMonth; d++) {
                        const dateStr = `${selYear}-${String(selMonth).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
                        const hol = holidayMap.get(dateStr);
                        const isSunday = new Date(selYear, selMonth - 1, d).getDay() === 0;
                        const isToday = dateStr === todayStr;

                        let bg = 'bg-slate-50 text-slate-600 hover:bg-indigo-50 hover:text-indigo-600 cursor-pointer';
                        if (isSunday) bg = 'bg-orange-50 text-orange-400';
                        if (hol) bg = 'bg-rose-500 text-white shadow-sm shadow-rose-200 ring-2 ring-rose-200';
                        if (isToday && !hol) bg += ' ring-2 ring-indigo-300';

                        cells.push(
                          <button key={d} onClick={() => {
                            if (hol) { removeHoliday(hol.id); }
                            else if (!isSunday) {
                              const name = prompt(`Holiday name for ${MONTHS[selMonth-1]} ${d}, ${selYear}:`);
                              if (name) { addHoliday(dateStr, name); }
                            }
                          }}
                            className={`w-full aspect-square flex flex-col items-center justify-center rounded-xl text-xs font-bold transition-all ${bg}`}
                            title={hol ? `${hol.name} (click to remove)` : isSunday ? 'Sunday' : 'Click to mark holiday'}
                          >
                            <span>{d}</span>
                            {hol && <span className="text-[7px] font-medium truncate max-w-full px-0.5 leading-tight">{hol.name.length > 5 ? hol.name.slice(0,5)+'..' : hol.name}</span>}
                          </button>
                        );
                      }
                      return cells;
                    })()}
                  </div>
                  <div className="flex items-center gap-4 mt-4 pt-3 border-t border-slate-50">
                    <div className="flex items-center gap-1.5"><div className="w-3 h-3 rounded bg-slate-50 border border-slate-200" /><span className="text-[9px] text-slate-400">Working Day</span></div>
                    <div className="flex items-center gap-1.5"><div className="w-3 h-3 rounded bg-rose-500" /><span className="text-[9px] text-slate-400">Holiday</span></div>
                    <div className="flex items-center gap-1.5"><div className="w-3 h-3 rounded bg-orange-50 border border-orange-200" /><span className="text-[9px] text-slate-400">Sunday</span></div>
                  </div>
                </div>

                {/* Holiday List */}
                <div className="lg:col-span-2 bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
                  <div className="px-5 py-4 border-b border-slate-100">
                    <h3 className="font-bold text-slate-800 text-sm">Marked Holidays</h3>
                    <p className="text-[10px] text-slate-400">Click a holiday on calendar to remove it</p>
                  </div>
                  {holidays.length === 0 ? (
                    <div className="text-center py-12">
                      <div className="w-12 h-12 mx-auto rounded-2xl bg-slate-50 flex items-center justify-center text-slate-300 mb-3 text-xl">🏖️</div>
                      <p className="text-sm text-slate-400 font-medium">No holidays marked</p>
                      <p className="text-[10px] text-slate-400 mt-1">Click any date on the calendar to add</p>
                    </div>
                  ) : (
                    <div className="divide-y divide-slate-50 max-h-[400px] overflow-y-auto">
                      {holidays.sort((a,b) => a.date.localeCompare(b.date)).map(h => (
                        <div key={h.id} className="flex items-center justify-between px-5 py-3 hover:bg-slate-50/50 transition-colors group">
                          <div className="flex items-center gap-3">
                            <div className="w-10 h-10 rounded-xl bg-rose-50 flex flex-col items-center justify-center text-rose-600">
                              <span className="text-[8px] font-bold uppercase leading-none">{MONTHS[parseInt(h.date.split('-')[1])-1]}</span>
                              <span className="text-sm font-bold leading-none">{parseInt(h.date.split('-')[2])}</span>
                            </div>
                            <div>
                              <p className="font-semibold text-slate-800 text-sm">{h.name}</p>
                              <p className="text-[10px] text-slate-400">{new Date(h.date + 'T12:00:00').toLocaleDateString('en-IN', { weekday: 'long' })}</p>
                            </div>
                          </div>
                          <button onClick={() => removeHoliday(h.id)} className="opacity-0 group-hover:opacity-100 p-1.5 text-slate-400 hover:text-rose-500 hover:bg-rose-50 rounded-lg transition-all" title="Remove">
                            <Icons.Close />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── Set Monthly Target Modal ── */}
      {targetModal.agent && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={() => setTargetModal({ agent: null, existing: null })} />
          <div className="relative bg-white rounded-3xl shadow-2xl w-full max-w-md overflow-hidden animate-fadeIn">
            <div className="bg-gradient-to-br from-indigo-500 to-violet-600 px-6 py-5">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-white font-black text-lg">Set Monthly Target</h2>
                  <p className="text-white/70 text-sm">{targetModal.agent.name} · {MONTHS[selMonth - 1]} {selYear}</p>
                </div>
                <button onClick={() => setTargetModal({ agent: null, existing: null })} className="text-white/60 hover:text-white transition-colors"><Icons.Close /></button>
              </div>
            </div>
            <div className="p-6 space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-500 mb-1.5 uppercase tracking-wide">Target Leads (Conversions)</label>
                <input type="number" min="0" value={targetForm.target_leads} onChange={e => setTargetForm(f => ({ ...f, target_leads: e.target.value }))} placeholder="e.g. 20" className="w-full border border-slate-200 rounded-xl px-4 py-2.5 text-sm font-semibold text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-300" />
                <p className="text-xs text-slate-400 mt-1">Daily targets will be auto-calculated from this</p>
                {targetForm.target_leads && parseInt(targetForm.target_leads) > 0 && (
                  <div className="mt-2 bg-indigo-50 rounded-lg px-3 py-2 flex items-center gap-2">
                    <Icons.Calendar />
                    <span className="text-xs font-semibold text-indigo-700">≈ {Math.ceil(parseInt(targetForm.target_leads) / 22)} leads/day</span>
                    <span className="text-[10px] text-indigo-400">(~22 working days, weighted by history)</span>
                  </div>
                )}
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-500 mb-1.5 uppercase tracking-wide">Target Revenue (₹)</label>
                <input type="number" min="0" value={targetForm.target_amount} onChange={e => setTargetForm(f => ({ ...f, target_amount: e.target.value }))} placeholder="e.g. 100000" className="w-full border border-slate-200 rounded-xl px-4 py-2.5 text-sm font-semibold text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-300" />
                {targetForm.target_amount && parseFloat(targetForm.target_amount) > 0 && (
                  <div className="mt-2 bg-emerald-50 rounded-lg px-3 py-2 flex items-center gap-2">
                    <Icons.Target />
                    <span className="text-xs font-semibold text-emerald-700">≈ ₹{Math.ceil(parseFloat(targetForm.target_amount) / 22).toLocaleString('en-IN')}/day</span>
                  </div>
                )}
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-500 mb-1.5 uppercase tracking-wide">Total Dialed Calls</label>
                  <input type="number" min="0" value={targetForm.target_dialed_calls} onChange={e => setTargetForm(f => ({ ...f, target_dialed_calls: e.target.value }))} placeholder="e.g. 500" className="w-full border border-slate-200 rounded-xl px-4 py-2.5 text-sm font-semibold text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-300" />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-500 mb-1.5 uppercase tracking-wide">Total Call Time (mins)</label>
                  <input type="number" min="0" value={targetForm.target_call_time} onChange={e => setTargetForm(f => ({ ...f, target_call_time: e.target.value }))} placeholder="e.g. 1200" className="w-full border border-slate-200 rounded-xl px-4 py-2.5 text-sm font-semibold text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-300" />
                </div>
              </div>
              <div className="flex gap-3 pt-2">
                <button onClick={() => setTargetModal({ agent: null, existing: null })} className="flex-1 py-3 bg-slate-100 text-slate-600 font-bold rounded-xl hover:bg-slate-200 transition-colors">Cancel</button>
                <button onClick={saveTarget} disabled={savingTarget || !targetForm.target_leads} className="flex-1 py-3 bg-indigo-600 text-white font-bold rounded-xl hover:bg-indigo-700 disabled:opacity-50 transition-colors flex items-center justify-center gap-2">
                  {savingTarget ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <Icons.Check />}
                  {targetModal.existing ? "Update Target" : "Set Target"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Daily Target Override Modal ── */}
      {dailyModal.target && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={() => setDailyModal({ target: null })} />
          <div className="relative bg-white rounded-3xl shadow-2xl w-full max-w-sm p-6">
            <div className="flex items-center justify-between mb-5">
              <div>
                <h2 className="font-black text-slate-800 text-lg">Override Daily Target</h2>
                <p className="text-xs text-slate-400">{new Date(dailyModal.target.date + "T12:00:00").toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long' })}</p>
              </div>
              <button onClick={() => setDailyModal({ target: null })} className="text-slate-400 hover:text-slate-600"><Icons.Close /></button>
            </div>
            <div className="space-y-3 mb-5">
              <div>
                <label className="block text-xs font-semibold text-slate-500 mb-1">Target Leads</label>
                <input type="number" min="0" value={dailyForm.target_leads} onChange={e => setDailyForm(f => ({ ...f, target_leads: e.target.value }))} className="w-full border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300" />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-500 mb-1">Target Amount (₹)</label>
                <input type="number" min="0" value={dailyForm.target_amount} onChange={e => setDailyForm(f => ({ ...f, target_amount: e.target.value }))} className="w-full border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300" />
              </div>
            </div>
            <div className="flex gap-3">
              <button onClick={() => setDailyModal({ target: null })} className="flex-1 py-2.5 bg-slate-100 text-slate-600 font-bold rounded-xl hover:bg-slate-200 transition-colors text-sm">Cancel</button>
              <button onClick={saveDailyTarget} disabled={savingDaily} className="flex-1 py-2.5 bg-amber-500 text-white font-bold rounded-xl hover:bg-amber-600 disabled:opacity-50 transition-colors text-sm flex items-center justify-center gap-2">
                {savingDaily ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <Icons.Check />}
                Override
              </button>
            </div>
          </div>
        </div>
      )}

      {/* PDF Generate Modal */}
      {showPdfModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl shadow-xl w-full max-w-md overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-100 flex justify-between items-center bg-slate-50/50">
              <h3 className="font-bold text-slate-800">Generate PDF Report</h3>
              <button onClick={() => setShowPdfModal(false)} className="text-slate-400 hover:text-slate-600"><Icons.Close /></button>
            </div>
            <div className="p-6">
              <p className="text-sm text-slate-600 mb-4">Select the date range for the report data.</p>
              <div className="grid grid-cols-2 gap-4 mb-6">
                <div>
                  <label className="block text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">From Date</label>
                  <input type="date" value={pdfDateFrom} onChange={e => setPdfDateFrom(e.target.value)} className="w-full bg-slate-50 border border-slate-200 text-slate-800 text-sm rounded-xl px-3 py-2.5 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500" />
                </div>
                <div>
                  <label className="block text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">To Date</label>
                  <input type="date" value={pdfDateTo} onChange={e => setPdfDateTo(e.target.value)} className="w-full bg-slate-50 border border-slate-200 text-slate-800 text-sm rounded-xl px-3 py-2.5 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500" />
                </div>
              </div>
              <button onClick={generatePdfWithDates} disabled={generatingPdf} className="w-full py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-sm font-bold transition-all disabled:opacity-50 flex items-center justify-center gap-2">
                {generatingPdf ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <Icons.Check />}
                {generatingPdf ? "Generating..." : "Generate & Download"}
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}

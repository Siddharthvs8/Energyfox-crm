"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";

import React, { useState, useEffect } from "react";
import { use } from "react";
import Link from "next/link";
import { Skeleton, SkeletonRegion } from "@/components/Skeleton";

const I = {
  Phone: () => <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6 19.79 19.79 0 01-3.07-8.67A2 2 0 014.11 2h3a2 2 0 012 1.72 12.84 12.84 0 00.7 2.81 2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l2.27-2.27a2 2 0 012.11-.45 12.84 12.84 0 002.81.7A2 2 0 0122 16.92z" /></svg>,
  Clock: () => <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" /><path d="M12 6v6l4 2" /></svg>,
  Search:() => <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8" /><path d="M21 21l-4.35-4.35" /></svg>,
  User:  () => <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2" /><circle cx="12" cy="7" r="4" /></svg>,
  Filter:() => <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" /></svg>,
  Calendar:() => <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="18" rx="2" ry="2" /><line x1="16" y1="2" x2="16" y2="6" /><line x1="8" y1="2" x2="8" y2="6" /><line x1="3" y1="10" x2="21" y2="10" /></svg>,
};

const OUTCOME_OPTIONS = [
  { value: "", label: "All Outcomes" },
  { value: "connected", label: "Connected" },
  { value: "rnr", label: "RNR" },
  { value: "busy", label: "Busy" },
  { value: "cancelled", label: "Cancelled" },
  { value: "initiated", label: "Initiated" },
];

const DIRECTION_OPTIONS = [
  { value: "", label: "All Directions" },
  { value: "inbound", label: "Inbound" },
  { value: "outbound", label: "Outbound" },
];

export default function CallsPage({ params: paramsPromise }: { params: Promise<{ domain: string }> }) {
  const params = use(paramsPromise);
  const domain = APP_SLUG;

  const [calls, setCalls] = useState<any[]>([]);
  const [users, setUsers] = useState<any[]>([]);
  const [currentUser, setCurrentUser] = useState<any>(null);
  const [selectedUserId, setSelectedUserId] = useState<string>("");
  const [selectedOutcome, setSelectedOutcome] = useState<string>("");
  const [selectedDirection, setSelectedDirection] = useState<string>("");
  const [dateFrom, setDateFrom] = useState<string>("");
  const [dateTo, setDateTo] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");

  const canFilterByUser = currentUser && (currentUser.is_staff || currentUser.is_general_manager || currentUser.is_manager);

  const getRoleLabel = () => {
    if (!currentUser) return '';
    if (currentUser.is_staff) return 'Admin';
    if (currentUser.is_general_manager) return 'General Manager';
    if (currentUser.is_manager) return 'Manager';
    return 'Agent';
  };

  const fetchCurrentUser = async () => {
    const token = localStorage.getItem(`${domain}_access`);
    if (!token) return;
    try {
      const r = await fetch(`${getApiBase(domain)}/api/users/me/`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      const d = await r.json();
      setCurrentUser(d);
    } catch {}
  };

  const fetchUsers = async () => {
    const token = localStorage.getItem(`${domain}_access`);
    if (!token) return;
    try {
      const r = await fetch(`${getApiBase(domain)}/api/users/`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      const d = await r.json();
      setUsers(Array.isArray(d) ? d : (d.results || []));
    } catch {}
  };

  const fetchCalls = async () => {
    setLoading(true);
    const token = localStorage.getItem(`${domain}_access`);
    if (!token) return;
    try {
      const qp = new URLSearchParams();
      if (selectedUserId) qp.set('user', selectedUserId);
      if (selectedOutcome) qp.set('outcome', selectedOutcome);
      if (selectedDirection) qp.set('direction', selectedDirection);
      if (dateFrom) qp.set('date_from', dateFrom);
      if (dateTo) qp.set('date_to', dateTo);
      const qs = qp.toString();
      const url = `${getApiBase(domain)}/api/calls/${qs ? `?${qs}` : ''}`;
      const r = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` }
      });
      const d = await r.json();
      setCalls(Array.isArray(d) ? d : (d.results || []));
    } catch {} finally { setLoading(false); }
  };

  useEffect(() => {
    fetchCurrentUser();
    fetchUsers();
  }, []);

  useEffect(() => {
    fetchCalls();
  }, [selectedUserId, selectedOutcome, selectedDirection, dateFrom, dateTo]);

  const formatDuration = (sec: number) => {
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${m}:${s < 10 ? '0' : ''}${s}`;
  };

  const getRecordingUrl = (url: string, id: number) => {
    if (!url) return "";
    if (url.includes("exotel") || url.includes("recordings.exotel")) {
      const token = localStorage.getItem(`${domain}_access`);
      return `${getApiBase(domain)}/api/calls/${id}/recording_proxy/${token ? `?token=${token}` : ''}`;
    }
    return url;
  };

  const filteredCalls = calls.filter(c => 
    (c.lead_name || "").toLowerCase().includes(search.toLowerCase()) ||
    (c.outcome || "").toLowerCase().includes(search.toLowerCase())
  );

  const getStatusColor = (status: string) => {
    switch ((status || '').toLowerCase()) {
      case 'connected':  return 'bg-emerald-50 text-emerald-700 border-emerald-100';
      case 'rnr':        return 'bg-orange-50 text-orange-700 border-orange-100';
      case 'busy':       return 'bg-blue-50 text-blue-700 border-blue-100';
      case 'cancelled':
      case 'canceled':   return 'bg-rose-50 text-rose-700 border-rose-100';
      case 'initiated':  return 'bg-violet-50 text-violet-700 border-violet-100';
      default:           return 'bg-slate-50 text-slate-700 border-slate-100';
    }
  };

  const getOutcomeLabel = (outcome: string) => {
    switch ((outcome || '').toLowerCase()) {
      case 'connected': return 'Connected';
      case 'rnr':       return 'RNR';
      case 'busy':      return 'Busy';
      case 'cancelled':
      case 'canceled':  return 'Cancelled';
      case 'initiated': return 'Initiated';
      // Legacy / rejected mapping fallbacks
      case 'completed': return 'Connected';
      case 'no-answer': return 'RNR';
      case 'failed':    return 'Busy';
      case 'rejected':  return 'Busy';
      default:          return outcome;
    }
  };

  const hasActiveFilters = selectedOutcome || selectedUserId || selectedDirection || dateFrom || dateTo;

  const clearAllFilters = () => {
    setSelectedUserId("");
    setSelectedOutcome("");
    setSelectedDirection("");
    setDateFrom("");
    setDateTo("");
    setSearch("");
  };

  return (
    <div className="p-4 sm:p-6 lg:p-10 space-y-5 sm:space-y-8 animate-[fadeIn_0.4s_ease-out]">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-black text-slate-800 tracking-tight">Call Tracking</h1>
          <p className="text-slate-500 text-sm mt-1">
            {currentUser ? (
              <>
                {getRoleLabel() === 'Agent' 
                  ? 'Viewing your call logs' 
                  : getRoleLabel() === 'Manager' 
                    ? "Viewing your team's call logs"
                    : 'Viewing all call logs'}
                <span className="ml-2 px-2 py-0.5 rounded-full text-[9px] font-black uppercase tracking-wider bg-indigo-50 text-indigo-600 border border-indigo-100">
                  {getRoleLabel()}
                </span>
              </>
            ) : 'Automatic logs and recordings of client communications'}
          </p>
        </div>
      </div>

      {/* Filter Bar */}
      <div className="bg-white rounded-3xl sm:rounded-[2rem] border border-slate-100 shadow-sm p-3.5 sm:p-5">
        {/* Six controls wrap to five rows on a phone, so below `lg` they are one
            row that scrolls — the filters stay one thumb-swipe apart. */}
        <div className="flex items-center gap-3 overflow-x-auto no-scrollbar pb-1 lg:flex-wrap lg:overflow-visible lg:pb-0 [&>*]:flex-shrink-0">
          {/* User Filter — only visible to Admin, GM, Manager */}
          {canFilterByUser && (
            <select 
              value={selectedUserId}
              onChange={e => setSelectedUserId(e.target.value)}
              className="px-4 py-2.5 bg-white border border-slate-200 rounded-2xl text-sm outline-none focus:ring-4 focus:ring-indigo-500/10 focus:border-indigo-500 transition-all shadow-sm"
            >
              <option value="">All Users</option>
              {users.map(u => (
                <option key={u.id} value={u.id}>
                  {`${u.first_name} ${u.last_name}`.trim() || u.username}
                </option>
              ))}
            </select>
          )}

          {/* Outcome Filter */}
          <div className="relative">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none">
              <I.Filter />
            </span>
            <select 
              value={selectedOutcome}
              onChange={e => setSelectedOutcome(e.target.value)}
              className="pl-9 pr-4 py-2.5 bg-white border border-slate-200 rounded-2xl text-sm outline-none focus:ring-4 focus:ring-indigo-500/10 focus:border-indigo-500 transition-all shadow-sm appearance-none cursor-pointer min-w-[140px]"
            >
              {OUTCOME_OPTIONS.map(o => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>

          {/* Direction Filter */}
          <div className="relative">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none">
              <I.Filter />
            </span>
            <select 
              value={selectedDirection}
              onChange={e => setSelectedDirection(e.target.value)}
              className="pl-9 pr-4 py-2.5 bg-white border border-slate-200 rounded-2xl text-sm outline-none focus:ring-4 focus:ring-indigo-500/10 focus:border-indigo-500 transition-all shadow-sm appearance-none cursor-pointer min-w-[140px]"
            >
              {DIRECTION_OPTIONS.map(d => (
                <option key={d.value} value={d.value}>{d.label}</option>
              ))}
            </select>
          </div>


          {/* Date From */}
          <div className="relative">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none">
              <I.Calendar />
            </span>
            <input
              type="date"
              value={dateFrom}
              onChange={e => setDateFrom(e.target.value)}
              className="pl-9 pr-3 py-2.5 bg-white border border-slate-200 rounded-2xl text-sm outline-none focus:ring-4 focus:ring-indigo-500/10 focus:border-indigo-500 transition-all shadow-sm cursor-pointer min-w-[140px]"
              title="From date"
            />
          </div>

          {/* Date To */}
          <div className="relative">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none">
              <I.Calendar />
            </span>
            <input
              type="date"
              value={dateTo}
              onChange={e => setDateTo(e.target.value)}
              className="pl-9 pr-3 py-2.5 bg-white border border-slate-200 rounded-2xl text-sm outline-none focus:ring-4 focus:ring-indigo-500/10 focus:border-indigo-500 transition-all shadow-sm cursor-pointer min-w-[140px]"
              title="To date"
            />
          </div>

          {/* Search */}
          <div className="relative group flex-1 !flex-shrink w-[200px] min-w-[180px]">
             <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 group-focus-within:text-indigo-500 transition-colors">
               <I.Search />
             </span>
             <input 
               type="text" 
               placeholder="Search leads..." 
               value={search}
               onChange={e => setSearch(e.target.value)}
               className="pl-9 pr-4 py-2.5 bg-white border border-slate-200 rounded-2xl text-sm w-full outline-none focus:ring-4 focus:ring-indigo-500/10 focus:border-indigo-500 transition-all shadow-sm"
             />
          </div>

          {/* Clear All */}
          {hasActiveFilters && (
            <button
              onClick={clearAllFilters}
              className="px-4 py-2.5 text-xs font-bold text-rose-500 hover:text-white hover:bg-rose-500 border border-rose-200 rounded-2xl transition-all"
            >
              Clear All
            </button>
          )}
        </div>

        {/* Active Filters Indicator */}
        {hasActiveFilters && (
          <div className="flex items-center gap-2 mt-3 pt-3 border-t border-slate-50 flex-wrap">
            <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">Active filters:</span>
            {selectedOutcome && (
              <span className={`px-2.5 py-0.5 rounded-full text-[9px] font-black uppercase border tracking-widest ${getStatusColor(selectedOutcome)} flex items-center gap-1`}>
                {getOutcomeLabel(selectedOutcome)}
                <button onClick={() => setSelectedOutcome("")} className="ml-0.5 hover:text-rose-500">✕</button>
              </span>
            )}
            {selectedDirection && (
              <span className="px-2.5 py-0.5 rounded-full text-[9px] font-black uppercase tracking-widest bg-violet-50 text-violet-600 border border-violet-100 flex items-center gap-1">
                {selectedDirection === "inbound" ? "Inbound" : "Outbound"}
                <button onClick={() => setSelectedDirection("")} className="ml-0.5 hover:text-rose-500">✕</button>
              </span>
            )}

            {selectedUserId && (
              <span className="px-2.5 py-0.5 rounded-full text-[9px] font-black uppercase tracking-widest bg-indigo-50 text-indigo-600 border border-indigo-100 flex items-center gap-1">
                {(() => { const u = users.find(u => String(u.id) === selectedUserId); return u ? `${u.first_name} ${u.last_name}`.trim() || u.username : 'User'; })()}
                <button onClick={() => setSelectedUserId("")} className="ml-0.5 hover:text-rose-500">✕</button>
              </span>
            )}
            {dateFrom && (
              <span className="px-2.5 py-0.5 rounded-full text-[9px] font-black uppercase tracking-widest bg-cyan-50 text-cyan-600 border border-cyan-100 flex items-center gap-1">
                From: {dateFrom}
                <button onClick={() => setDateFrom("")} className="ml-0.5 hover:text-rose-500">✕</button>
              </span>
            )}
            {dateTo && (
              <span className="px-2.5 py-0.5 rounded-full text-[9px] font-black uppercase tracking-widest bg-cyan-50 text-cyan-600 border border-cyan-100 flex items-center gap-1">
                To: {dateTo}
                <button onClick={() => setDateTo("")} className="ml-0.5 hover:text-rose-500">✕</button>
              </span>
            )}
          </div>
        )}
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 sm:gap-6">
        {[
          { label: "Connected", val: calls.filter(c => c.outcome === 'connected' || c.outcome === 'completed').length, color: "emerald" },
          { label: "RNR", val: calls.filter(c => c.outcome === 'rnr' || c.outcome === 'no-answer').length, color: "orange" },
          { label: "Busy", val: calls.filter(c => c.outcome === 'busy' || c.outcome === 'rejected' || c.outcome === 'failed').length, color: "blue" },
          { label: "Cancelled", val: calls.filter(c => c.outcome === 'cancelled' || c.outcome === 'canceled').length, color: "rose" },
        ].map((s, idx) => (
          <div key={idx} className="bg-white p-4 sm:p-6 rounded-3xl sm:rounded-[2rem] border border-slate-100 shadow-sm hover:shadow-xl hover:shadow-indigo-500/5 transition-all group">
            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1 group-hover:text-indigo-500 transition-colors">{s.label}</p>
            <p className="text-2xl sm:text-3xl font-black text-slate-800 tracking-tighter">{s.val}</p>
          </div>
        ))}
      </div>

      {/* Table */}
      <div className="bg-white rounded-3xl sm:rounded-[2.5rem] border border-slate-100 shadow-sm overflow-hidden min-h-[400px]">
        {loading ? (
          <SkeletonRegion label="Loading call logs">
            {/* Phone: the same card, recording player included. */}
            <div className="lg:hidden p-3 space-y-2.5">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="record-card">
                  <div className="flex items-start gap-3">
                    <Skeleton className="w-10 h-10 rounded-2xl flex-shrink-0" />
                    <div className="flex-1 space-y-2">
                      <Skeleton className="h-3.5 w-1/2 rounded-md" />
                      <Skeleton className="h-2.5 w-1/3 rounded-full" />
                    </div>
                    <Skeleton className="h-8 w-14 rounded-md flex-shrink-0" />
                  </div>
                  <div className="flex gap-1.5 mt-2.5">
                    <Skeleton className="h-5 w-24 rounded-full" />
                    <Skeleton className="h-5 w-20 rounded-full" />
                  </div>
                  {i % 2 === 0 && <Skeleton className="h-9 w-full rounded-lg mt-2.5" />}
                </div>
              ))}
            </div>
            <div className="hidden lg:block">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="flex items-center gap-6 px-6 py-5 border-b border-slate-50">
                  <div className="flex items-center gap-3 w-56 flex-shrink-0">
                    <Skeleton className="w-10 h-10 rounded-2xl flex-shrink-0" />
                    <div className="flex-1 space-y-2">
                      <Skeleton className="h-3 w-full rounded-md" />
                      <Skeleton className="h-2 w-2/3 rounded-full" />
                    </div>
                  </div>
                  {Array.from({ length: 5 }).map((_, c) => <Skeleton key={c} className="h-4 flex-1 rounded-md" />)}
                </div>
              ))}
            </div>
          </SkeletonRegion>
        ) : filteredCalls.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-32 text-center">
            <div className="w-16 h-16 bg-slate-50 flex items-center justify-center rounded-3xl text-slate-300 mb-4 ring-8 ring-slate-50/50">
              <I.Phone />
            </div>
            <h3 className="text-slate-800 font-bold mb-1">No call logs found</h3>
            <p className="text-slate-400 text-xs px-10">
              {hasActiveFilters 
                ? 'No calls match your current filters. Try adjusting or clearing them.' 
                : 'Records will appear here automatically as soon as agents start calling leads.'}
            </p>
          </div>
        ) : (
          <>
          {/* ── Mobile: one card per call ──
              Six columns do not fit a phone, and the recording player was the
              first thing to fall off the right edge. Stacked, it is the widest
              control on the card. */}
          <div className="lg:hidden p-3 space-y-2.5">
            {filteredCalls.map(call => {
              const isAutoCreatedInbound = call.lead_source === 'inbound_call' || (!call.lead && call.direction === 'inbound');
              const named = call.lead && !isAutoCreatedInbound;
              const Body = (
                <>
                  <div className="flex items-start gap-3">
                    <div className={`w-10 h-10 rounded-2xl flex items-center justify-center flex-shrink-0 ${named ? "bg-indigo-50 text-indigo-600" : "bg-teal-50 text-teal-600"}`}>
                      {named ? <I.User /> : <I.Phone />}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-bold text-slate-800 truncate">
                        {named ? call.lead_name : (call.lead_phone || call.lead_name || 'Unknown Caller')}
                      </p>
                      <p className="text-[10px] text-slate-400 font-medium truncate">
                        {named
                          ? `Logged by ${call.user_name}`
                          : `${call.direction === 'inbound' ? 'Inbound call' : 'Logged by'} ${call.user_name}`}
                      </p>
                    </div>
                    <div className="text-right flex-shrink-0">
                      <p className="text-[11px] font-bold text-slate-700">
                        {new Date(call.created_at).toLocaleDateString("en-IN", { day: '2-digit', month: 'short' })}
                      </p>
                      <p className="text-[10px] text-slate-400">
                        {new Date(call.created_at).toLocaleTimeString("en-IN", { hour: '2-digit', minute: '2-digit' })}
                      </p>
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-1.5 mt-2.5">
                    <span className={`px-2.5 py-0.5 rounded-full text-[9px] font-black uppercase border tracking-widest ${getStatusColor(call.outcome)}`}>
                      {getOutcomeLabel(call.outcome)}
                    </span>
                    <span className={`px-2 py-0.5 rounded-full text-[9px] font-black uppercase border ${call.direction === 'inbound' ? "bg-teal-50 text-teal-600 border-teal-100" : "bg-indigo-50 text-indigo-600 border-indigo-100"}`}>
                      {call.direction === 'inbound' ? 'Inbound' : 'Outbound'}
                    </span>
                    <span className="flex items-center gap-1 text-slate-500 font-mono text-[11px] ml-auto">
                      <I.Clock />{formatDuration(call.duration_seconds)}
                    </span>
                  </div>

                  {call.recording_url && (
                    <audio controls className="w-full h-9 mt-2.5" src={getRecordingUrl(call.recording_url, call.id)}>
                      Your browser does not support the audio element.
                    </audio>
                  )}
                </>
              );
              return named ? (
                <Link key={call.id} href={`/leads/${call.lead}`} className="record-card block">{Body}</Link>
              ) : (
                <div key={call.id} className="record-card">{Body}</div>
              );
            })}
          </div>

          <div className="hidden lg:block overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-slate-50/50 border-b border-slate-100">
                  <th className="px-6 py-5 text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">Call Details</th>
                  <th className="px-6 py-5 text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">Direction</th>
                  <th className="px-6 py-5 text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">Status</th>
                  <th className="px-6 py-5 text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">Duration</th>
                  <th className="px-6 py-5 text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">Recording</th>
                  <th className="px-6 py-5 text-right text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">Timestamp</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {filteredCalls.map(call => (
                  <tr key={call.id} className="hover:bg-slate-50/30 transition-colors group">
                    <td className="px-6 py-4">
                      {(() => {
                        const isAutoCreatedInbound = call.lead_source === 'inbound_call' || (!call.lead && call.direction === 'inbound');
                        
                        if (call.lead && !isAutoCreatedInbound) {
                          // Real lead — clickable link to lead page
                          return (
                            <Link href={`/leads/${call.lead}`} className="flex items-center gap-3 hover:opacity-85 transition-opacity">
                              <div className="w-10 h-10 rounded-2xl bg-indigo-50 flex items-center justify-center text-indigo-600 flex-shrink-0 group-hover:scale-110 transition-transform">
                                <I.User />
                              </div>
                              <div>
                                <p className="text-sm font-bold text-slate-800 group-hover:text-indigo-600 transition-colors">{call.lead_name}</p>
                                <p className="text-[10px] text-slate-400 font-medium">Logged by {call.user_name}</p>
                              </div>
                            </Link>
                          );
                        } else {
                          // Inbound call from unknown/auto-created lead — show phone, no link
                          return (
                            <div className="flex items-center gap-3">
                              <div className="w-10 h-10 rounded-2xl bg-teal-50 flex items-center justify-center text-teal-600 flex-shrink-0">
                                <I.Phone />
                              </div>
                              <div>
                                <p className="text-sm font-bold text-slate-800">{call.lead_phone || call.lead_name || 'Unknown Caller'}</p>
                                <p className="text-[10px] text-slate-400 font-medium">
                                  {call.direction === 'inbound' ? 'Inbound call' : 'Logged by'} {call.user_name}
                                </p>
                              </div>
                            </div>
                          );
                        }
                      })()}
                    </td>
                    <td className="px-6 py-4">
                      {call.direction === 'inbound' ? (
                        <span className="px-2 py-0.5 rounded-full text-[9px] font-black uppercase bg-teal-50 text-teal-600 border border-teal-100">Inbound</span>
                      ) : (
                        <span className="px-2 py-0.5 rounded-full text-[9px] font-black uppercase bg-indigo-50 text-indigo-600 border border-indigo-100">Outbound</span>
                      )}
                    </td>
                    <td className="px-6 py-4">
                      <span className={`px-3 py-1 rounded-full text-[10px] font-black uppercase border tracking-widest ${getStatusColor(call.outcome)}`}>
                        {getOutcomeLabel(call.outcome)}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-1.5 text-slate-600 font-mono text-xs">
                        <I.Clock />
                        {formatDuration(call.duration_seconds)}
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      {call.recording_url ? (
                        <div className="flex items-center gap-2 max-w-[200px]">
                           <audio controls className="h-8 max-w-full scale-90 origin-left" src={getRecordingUrl(call.recording_url, call.id)}>
                             Your browser does not support the audio element.
                           </audio>
                        </div>
                      ) : (
                        <span className="text-[10px] text-slate-300 italic">No recording</span>
                      )}
                    </td>
                    <td className="px-6 py-4 text-right">
                       <p className="text-xs font-bold text-slate-700">
                         {new Date(call.created_at).toLocaleDateString("en-IN", { day: '2-digit', month: 'short' })}
                       </p>
                       <p className="text-[10px] text-slate-400">
                         {new Date(call.created_at).toLocaleTimeString("en-IN", { hour: '2-digit', minute: '2-digit' })}
                       </p>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          </>
        )}
      </div>

      <style jsx global>{`
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
      `}</style>
    </div>
  );
}

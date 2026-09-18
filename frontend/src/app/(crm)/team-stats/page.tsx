"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { isSpectator } from "@/lib/spectator";

type TeamData = { team_lead: string; this_month: number; series: { label: string; count: number }[] };
type Stats = { structure: TeamData; electrical: TeamData; can_edit: boolean };

export default function TeamStatsPage() {
  const domain = APP_SLUG;
  const router = useRouter();
  const [authChecked, setAuthChecked] = useState(false);
  const [allowed, setAllowed] = useState(false);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [structureLead, setStructureLead] = useState("");
  const [electricalLead, setElectricalLead] = useState("");
  const [savingLeads, setSavingLeads] = useState(false);

  const token = () => localStorage.getItem(`${domain}_access`);
  const url = `${getApiBase(domain)}/api/leads/team-stats/`;

  useEffect(() => {
    const t = token();
    if (!t) { router.push("/login"); return; }
    fetch(`${getApiBase(domain)}/api/users/me/`, { headers: { Authorization: `Bearer ${t}` } })
      .then(r => r.json())
      .then(d => {
        const ok = isSpectator(d) || d.role === "project_manager" || d.is_staff || d.is_general_manager;
        setAllowed(ok); setAuthChecked(true);
        if (!ok) router.replace("/");
      })
      .catch(() => setAuthChecked(true));
  }, [domain, router]);

  const loadStats = () => {
    fetch(url, { headers: { Authorization: `Bearer ${token()}` } })
      .then(r => (r.ok ? r.json() : null))
      .then(d => { if (d) { setStats(d); setStructureLead(d.structure.team_lead || ""); setElectricalLead(d.electrical.team_lead || ""); } })
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { if (allowed) loadStats(); }, [allowed]); // eslint-disable-line react-hooks/exhaustive-deps

  const saveLeads = async () => {
    setSavingLeads(true);
    try {
      const r = await fetch(url, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token()}` },
        body: JSON.stringify({ structure_team_lead: structureLead, electrical_team_lead: electricalLead }),
      });
      if (r.ok) { loadStats(); alert("Team leads updated."); }
      else alert("Failed to update team leads.");
    } catch { alert("Network error."); }
    finally { setSavingLeads(false); }
  };

  if (!authChecked) return <div className="flex items-center justify-center min-h-[60vh]"><div className="w-8 h-8 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" /></div>;
  if (!allowed) return null;

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-[1100px]">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Team Stats</h1>
        <p className="text-sm text-slate-500 mt-1">Monthly work completion for the structure and electrical teams (from project work dates).</p>
      </div>

      {loading || !stats ? (
        <div className="py-16 text-center text-sm text-slate-400">Loading…</div>
      ) : (
        <>
          <div className="grid md:grid-cols-2 gap-5">
            <TeamCard title="Structure" accent="indigo" data={stats.structure} />
            <TeamCard title="Electrical" accent="amber" data={stats.electrical} />
          </div>

          {stats.can_edit && (
            <div className="mt-6 bg-white border border-slate-200 rounded-2xl shadow-sm p-5">
              <h2 className="text-sm font-bold text-slate-900 mb-3">Team Leads</h2>
              <div className="grid sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wide mb-1.5">Structure Team Lead</label>
                  <input value={structureLead} onChange={e => setStructureLead(e.target.value)} placeholder="Name" className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400" />
                </div>
                <div>
                  <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wide mb-1.5">Electrical Team Lead</label>
                  <input value={electricalLead} onChange={e => setElectricalLead(e.target.value)} placeholder="Name" className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400" />
                </div>
              </div>
              <button onClick={saveLeads} disabled={savingLeads} className="mt-4 px-5 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 disabled:opacity-50 transition">{savingLeads ? "Saving…" : "Save Team Leads"}</button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function TeamCard({ title, accent, data }: { title: string; accent: "indigo" | "amber"; data: TeamData }) {
  const max = Math.max(1, ...data.series.map(s => s.count));
  const barColor = accent === "indigo" ? "bg-indigo-500" : "bg-amber-500";
  const chipColor = accent === "indigo" ? "text-indigo-700 bg-indigo-50" : "text-amber-700 bg-amber-50";
  return (
    <div className="bg-white border border-slate-200 rounded-2xl shadow-sm p-5">
      <div className="flex items-center justify-between mb-1">
        <h2 className="text-base font-bold text-slate-900">{title}</h2>
        <span className={`text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full ${chipColor}`}>This month: {data.this_month}</span>
      </div>
      <p className="text-xs text-slate-500 mb-4">Team Lead: <span className="font-semibold text-slate-700">{data.team_lead || "—"}</span></p>

      <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wide mb-2">Monthly Work Completion</p>
      <div className="flex items-end gap-2 h-32">
        {data.series.map((s, i) => (
          <div key={i} className="flex-1 flex flex-col items-center justify-end gap-1">
            <span className="text-[10px] font-semibold text-slate-500">{s.count}</span>
            <div className={`w-full rounded-t-md ${barColor} transition-all`} style={{ height: `${Math.max(4, (s.count / max) * 100)}%` }} title={`${s.label}: ${s.count}`} />
            <span className="text-[10px] text-slate-400">{s.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

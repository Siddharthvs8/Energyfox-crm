"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";

import React, { useState, useEffect } from "react";
import Link from "next/link";

// ─── Animated Counter ─────────────────────────────────────────────────────────
function AnimatedNumber({ value, prefix = "", suffix = "", isCurrency = false }: { value: number; prefix?: string; suffix?: string; isCurrency?: boolean }) {
  const [display, setDisplay] = useState(0);
  useEffect(() => {
    if (value === 0) { setDisplay(0); return; }
    let start = 0;
    const step = value / (800 / 16); // ~800ms animation
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

// ─── Trophy Icon ──────────────────────────────────────────────────────────────
const Trophy = ({ rank, color = "currentColor" }: { rank: number; color?: string }) => {
  if (rank === 1) return (
    <div className="relative">
      <svg width="24" height="24" fill="none" stroke="#f59e0b" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M6 9H4.5a1.5 1.5 0 010-3H6m0 3V4a1 1 0 011-1h10a1 1 0 011 1v16a1 1 0 01-1 1H7a1 1 0 01-1-1v-5m0-6V9m12-3v12M14 6v12" /><path d="M18 9h1.5a1.5 1.5 0 000-3H18" /></svg>
      <span className="absolute -top-1 -right-1 text-[8px] font-black bg-amber-400 text-white rounded-full w-4 h-4 flex items-center justify-center border-2 border-white shadow-sm">1</span>
    </div>
  );
  if (rank === 2) return (
    <div className="relative">
      <svg width="24" height="24" fill="none" stroke="#94a3b8" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M6 9H4.5a1.5 1.5 0 010-3H6m0 3V4a1 1 0 011-1h10a1 1 0 011 1v16a1 1 0 01-1 1H7a1 1 0 01-1-1v-5m0-6V9m12-3v12M14 6v12" /><path d="M18 9h1.5a1.5 1.5 0 000-3H18" /></svg>
      <span className="absolute -top-1 -right-1 text-[8px] font-black bg-slate-400 text-white rounded-full w-4 h-4 flex items-center justify-center border-2 border-white shadow-sm">2</span>
    </div>
  );
  if (rank === 3) return (
    <div className="relative">
      <svg width="24" height="24" fill="none" stroke="#b45309" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M6 9H4.5a1.5 1.5 0 010-3H6m0 3V4a1 1 0 011-1h10a1 1 0 011 1v16a1 1 0 01-1 1H7a1 1 0 01-1-1v-5m0-6V9m12-3v12M14 6v12" /><path d="M18 9h1.5a1.5 1.5 0 000-3H18" /></svg>
      <span className="absolute -top-1 -right-1 text-[8px] font-black bg-orange-600 text-white rounded-full w-4 h-4 flex items-center justify-center border-2 border-white shadow-sm">3</span>
    </div>
  );
  return <span className="text-sm font-black text-slate-300 w-6 text-center">{rank}</span>;
}

export default function LeaderboardPage({ params: paramsPromise }: { params: Promise<{ domain: string }> }) {
  const params = React.use(paramsPromise);
  const domain = APP_SLUG;

  const [period, setPeriod] = useState("all_time");
  const [data, setData] = useState<any>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchLeaderboard = async () => {
      setLoading(true);
      const token = localStorage.getItem(`${domain}_access`);
      if (!token) { setLoading(false); return; }
      try {
        const response = await fetch(`${getApiBase(domain)}/api/leaderboard/?period=${period}`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        if (response.ok) {
          const result = await response.json();
          setData(result.leaderboard || []);
        }
      } catch (err) {
        console.error("Leaderboard fetch error:", err);
      } finally {
        setLoading(false);
      }
    };
    fetchLeaderboard();
  }, [domain, period]);

  const periods = [
    { id: "daily", label: "Today" },
    { id: "monthly", label: "This Month" },
    { id: "all_time", label: "All Time" },
  ];

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-[1200px] mx-auto min-h-screen">
      {/* ── Header ── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-6 mb-10">
        <div>
          <h1 className="text-3xl font-black text-slate-900 tracking-tight flex items-center gap-3">
             <span className="text-4xl">🏆</span> Sales Leaderboard
          </h1>
          <p className="text-sm text-slate-500 mt-1 font-medium">Rankings based on closed sales and revenue</p>
        </div>

        <div className="flex p-1 bg-white border border-slate-100 rounded-2xl shadow-sm self-start sm:self-center">
          {periods.map((p) => (
            <button
              key={p.id}
              onClick={() => setPeriod(p.id)}
              className={`px-5 py-2 rounded-xl text-xs font-bold transition-all ${
                period === p.id 
                  ? "bg-indigo-600 text-white shadow-lg shadow-indigo-600/20" 
                  : "text-slate-500 hover:bg-slate-50"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="flex flex-col items-center justify-center py-20 grayscale opacity-50">
          <div className="w-10 h-10 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin mb-4" />
          <p className="text-sm font-bold text-slate-400">Updating Rankings...</p>
        </div>
      ) : data.length === 0 ? (
        <div className="bg-white border border-slate-100 rounded-[2rem] p-16 text-center shadow-sm">
          <div className="w-20 h-20 bg-slate-50 rounded-3xl flex items-center justify-center mx-auto mb-6">
            <svg width="40" height="40" fill="none" stroke="#94a3b8" strokeWidth="1.5" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" /></svg>
          </div>
          <h3 className="text-xl font-bold text-slate-800">No Sales Recorded</h3>
          <p className="text-slate-400 text-sm mt-2 max-w-xs mx-auto">No users have closed any sales in this time period yet. Time to hustle!</p>
        </div>
      ) : (
        <div className="grid gap-4">
          {/* ── Rankings List ── */}
          <div className="bg-white border border-slate-100 rounded-[2rem] shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="bg-slate-50/50 border-b border-slate-50 text-[10px] font-black text-slate-400 uppercase tracking-widest">
                    <th className="px-8 py-5 w-20">Rank</th>
                    <th className="px-6 py-5">Sales Agent</th>
                    <th className="px-6 py-5 text-center">Closed Sales</th>
                    <th className="px-8 py-5 text-right">Total Revenue</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {data.map((user: any, index: number) => {
                    const rank = index + 1;
                    return (
                      <tr key={user.id} className="group hover:bg-slate-50/30 transition-all">
                        <td className="px-8 py-6">
                           <Trophy rank={rank} />
                        </td>
                        <td className="px-6 py-6">
                          <div className="flex items-center gap-4">
                            <div className={`w-12 h-12 rounded-2xl flex items-center justify-center text-white font-black text-lg shadow-sm ${
                              rank === 1 ? "bg-gradient-to-br from-amber-400 to-orange-500 shadow-amber-200" :
                              rank === 2 ? "bg-gradient-to-br from-slate-400 to-slate-600 shadow-slate-200" :
                              rank === 3 ? "bg-gradient-to-br from-orange-700 to-orange-900 shadow-orange-200" :
                              "bg-indigo-500/10 text-indigo-600"
                            }`}>
                              {user.name.charAt(0).toUpperCase()}
                            </div>
                            <div>
                               <p className="text-base font-bold text-slate-900 group-hover:text-indigo-600 transition-colors">{user.name}</p>
                               <p className="text-[10px] font-black text-slate-400 uppercase tracking-wide">{user.role}</p>
                            </div>
                          </div>
                        </td>
                        <td className="px-6 py-6 text-center">
                           <div className="inline-flex items-center justify-center w-10 h-10 bg-slate-50 rounded-xl">
                              <span className="text-base font-black text-slate-800">
                                <AnimatedNumber value={user.closed_sales} />
                              </span>
                           </div>
                        </td>
                        <td className="px-8 py-6 text-right">
                           <p className={`text-xl font-black ${user.revenue > 0 ? "text-emerald-500" : "text-slate-300"}`}>
                             <AnimatedNumber value={user.revenue} prefix="₹" isCurrency />
                           </p>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* ── Summary Stats ── */}
          <div className="grid sm:grid-cols-2 gap-4 mt-4">
             <div className="bg-indigo-600 rounded-[2rem] p-8 text-white relative overflow-hidden shadow-xl shadow-indigo-100">
                <div className="absolute -right-6 -bottom-6 w-32 h-32 bg-white/10 rounded-full blur-2xl" />
                <p className="text-[10px] font-black uppercase tracking-[0.2em] opacity-60 mb-2">Total Sales Force Revenue</p>
                <p className="text-4xl font-black">
                  <AnimatedNumber value={data.reduce((acc: any, curr: any) => acc + curr.revenue, 0)} prefix="₹" isCurrency />
                </p>
                <div className="mt-4 flex items-center gap-2">
                   <span className="text-[10px] font-bold bg-white/20 px-3 py-1 rounded-full">{data.length} Sales Agents</span>
                </div>
             </div>
             <div className="bg-white border border-slate-100 rounded-[2rem] p-8 shadow-sm">
                <p className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] mb-2">Achievement Milestone</p>
                <p className="text-4xl font-black text-slate-900">
                  <AnimatedNumber value={data.reduce((acc: any, curr: any) => acc + curr.closed_sales, 0)} />
                </p>
                <p className="text-sm font-bold text-slate-400 mt-2">Total Combined Closed Sales</p>
             </div>
          </div>
        </div>
      )}

      <style jsx global>{`
        @keyframes slideIn {
          from { opacity: 0; transform: translateY(10px); }
          to { opacity: 1; transform: translateY(0); }
        }
        tr { animation: slideIn 0.3s ease-out forwards; }
      `}</style>
    </div>
  );
}

"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import CampaignFormModal from "./components/CampaignFormModal";
import { isSpectator } from "@/lib/spectator";

export default function CampaignsPage({ params: paramsPromise }: { params: Promise<{ domain: string }> }) {
  const params = React.use(paramsPromise);
  const router = useRouter();
  const domain = APP_SLUG;
  const [campaigns, setCampaigns] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [currentUser, setCurrentUser] = useState<any>(null);
  const [authChecked, setAuthChecked] = useState(false);

  // Auth guard: block agents (users who are not staff, not GM, not manager)
  useEffect(() => {
    const token = localStorage.getItem(`${domain}_access`);
    if (!token) return;
    fetch(`${getApiBase(domain)}/api/users/me/`, {
      headers: { Authorization: `Bearer ${token}` },
    }).then(r => r.json()).then(d => {
      setCurrentUser(d);
      setAuthChecked(true);
      // A spectator reads every module; the API agrees (CampaignAccess admits
      // `watches_everything`).
      if (!isSpectator(d) && !d.is_staff && !d.is_general_manager && !d.is_manager
          && d.role !== "leads_manager") {
        router.replace(`/`);
      }
    }).catch(() => setAuthChecked(true));
  }, [domain, router]);

  useEffect(() => {
    if (!authChecked) return;
    if (currentUser && !currentUser.is_staff && !currentUser.is_general_manager && !currentUser.is_manager && currentUser.role !== "leads_manager") return;
    fetchCampaigns();
  }, [domain, authChecked, currentUser]);

  const fetchCampaigns = async () => {
    const token = localStorage.getItem(`${domain}_access`);
    if (!token) return;
    try {
      const res = await fetch(`${getApiBase(domain)}/api/campaigns/`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setCampaigns(data.results || data);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'active': return <span className="px-3 py-1.5 bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 rounded-xl text-xs font-bold uppercase tracking-wider shadow-[0_0_15px_rgba(16,185,129,0.3)]">Active</span>;
      case 'completed': return <span className="px-3 py-1.5 bg-blue-500/20 text-blue-400 border border-blue-500/30 rounded-xl text-xs font-bold uppercase tracking-wider">Completed</span>;
      case 'inactive': return <span className="px-3 py-1.5 bg-slate-500/20 text-slate-400 border border-slate-500/30 rounded-xl text-xs font-bold uppercase tracking-wider">Inactive</span>;
      default: return <span className="px-3 py-1.5 bg-amber-500/20 text-amber-400 border border-amber-500/30 rounded-xl text-xs font-bold uppercase tracking-wider">Planning</span>;
    }
  };

  if (!authChecked) return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="text-center"><div className="w-8 h-8 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin mx-auto mb-3" /><p className="text-sm text-slate-400">Loading...</p></div>
    </div>
  );
  if (currentUser && !currentUser.is_staff && !currentUser.is_general_manager && !currentUser.is_manager && currentUser.role !== "leads_manager") return null;

  return (
    <div className="min-h-screen bg-[#060608] text-slate-200 font-sans selection:bg-indigo-500/30 relative">
      {/* Fixed dark backdrop: keeps the viewport dark below short content and on
          over-scroll, so the light app background never shows through. */}
      <div className="fixed inset-0 bg-[#060608] -z-10 pointer-events-none" />
      {/* Background layer */}
      <div className="absolute inset-0 z-0">
         <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyMCIgaGVpZ2h0PSIyMCI+CiAgPGNpcmNsZSBjeD0iMiIgY3k9IjIiIHI9IjEiIGZpbGw9IiNmZmYiIGZpbGwtb3BhY2l0eT0iMC4wNSIvPgo8L3N2Zz4=')] opacity-50"></div>
         <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-indigo-600/20 blur-[120px] rounded-full mix-blend-screen"></div>
         <div className="absolute bottom-[-10%] right-[-10%] w-[30%] h-[30%] bg-purple-600/10 blur-[120px] rounded-full mix-blend-screen"></div>
      </div>

      <div className="relative z-10">
        <header className="border-b border-white/10 bg-[#060608]/80 backdrop-blur-xl sticky-under-topbar z-20">
          <div className="max-w-7xl mx-auto px-6 h-20 flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-black text-white tracking-tight flex items-center gap-3">
                 <span className="text-3xl">📢</span> Campaigns
              </h1>
            </div>
            <button
              onClick={() => setIsModalOpen(true)}
              className="group relative flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white px-6 py-2.5 rounded-xl font-bold transition-all active:scale-95 shadow-[0_0_20px_rgba(99,102,241,0.4)] overflow-hidden"
            >
              <div className="absolute inset-0 bg-white/20 translate-y-full group-hover:translate-y-0 transition-transform duration-300"></div>
              <svg className="relative z-10" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>
              <span className="relative z-10">New Campaign</span>
            </button>
          </div>
        </header>

        <main className="max-w-7xl mx-auto px-6 py-10">
          {loading ? (
            <div className="flex justify-center py-32">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-500"></div>
            </div>
          ) : campaigns.length === 0 ? (
            <div className="text-center bg-[#111116]/80 backdrop-blur-2xl rounded-3xl border border-white/5 shadow-2xl px-6 py-24 relative overflow-hidden group hover:border-white/10 transition-colors">
              <div className="absolute inset-0 bg-gradient-to-b from-white/[0.02] to-transparent"></div>
              <div className="w-24 h-24 bg-indigo-500/10 border border-indigo-500/20 rounded-2xl flex items-center justify-center mx-auto mb-8 transform -rotate-6 group-hover:rotate-0 transition-transform duration-500">
                <span className="text-5xl drop-shadow-[0_0_15px_rgba(99,102,241,0.5)]">📢</span>
              </div>
              <h3 className="text-2xl font-black text-white mb-3">No campaigns deployed</h3>
              <p className="text-slate-400 mb-8 max-w-sm mx-auto text-sm">Launch your first marketing initiative to track leads and analyze outbound performance.</p>
              <button
                onClick={() => setIsModalOpen(true)}
                className="bg-white/10 border border-white/20 text-white font-bold px-8 py-3 rounded-xl hover:bg-white/20 transition-all shadow-[0_0_15px_rgba(255,255,255,0.1)] active:scale-95"
              >
                Plan Campaign
              </button>
            </div>
          ) : (
            <div className="bg-[#111116]/80 backdrop-blur-2xl border border-white/10 rounded-3xl overflow-hidden shadow-2xl relative">
              <div className="absolute inset-0 bg-gradient-to-br from-white/[0.02] to-transparent pointer-events-none"></div>
              <div className="overflow-x-auto relative z-10">
                <table className="w-full text-left border-collapse whitespace-nowrap">
                  <thead>
                    <tr className="border-b border-white/10 bg-white/5">
                      <th className="px-8 py-5 text-xs font-bold text-slate-400 uppercase tracking-wider">Initiative</th>
                      <th className="px-8 py-5 text-xs font-bold text-slate-400 uppercase tracking-wider">Vector</th>
                      <th className="px-8 py-5 text-xs font-bold text-slate-400 uppercase tracking-wider">Status</th>
                      <th className="px-8 py-5 text-xs font-bold text-slate-400 uppercase tracking-wider">Est. Value</th>
                      <th className="px-8 py-5 text-xs font-bold text-slate-400 uppercase tracking-wider">Enrollment</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {campaigns.map((c) => (
                      <tr key={c.id} className="hover:bg-white/5 transition-colors group cursor-pointer" onClick={() => router.push(`/campaigns/${c.id}`)}>
                        <td className="px-8 py-6">
                          <div className="font-bold text-white text-base group-hover:text-indigo-400 transition-colors">{c.name}</div>
                          {c.start_date && (
                            <div className="text-xs text-slate-500 mt-1 font-medium">{c.start_date} {c.end_date ? `→ ${c.end_date}` : ''}</div>
                          )}
                        </td>
                        <td className="px-8 py-6 text-sm text-slate-400 capitalize font-medium">
                          {c.campaign_type.replace('_', ' ')}
                        </td>
                        <td className="px-8 py-6">
                          {getStatusBadge(c.status)}
                        </td>
                        <td className="px-8 py-6 text-sm font-black text-slate-300">
                          ${parseFloat(c.expected_revenue).toLocaleString()}
                        </td>
                        <td className="px-8 py-6">
                          <div className="inline-flex items-center gap-2 px-3 py-1.5 bg-white/5 border border-white/10 text-slate-300 rounded-xl text-xs font-bold">
                            <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" /><circle cx="9" cy="7" r="4" /></svg>
                            {c.leads_count}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </main>
      </div>

      {isModalOpen && (
        <CampaignFormModal
          domain={domain}
          onClose={() => setIsModalOpen(false)}
          onSuccess={() => {
            setIsModalOpen(false);
            fetchCampaigns();
          }}
        />
      )}
    </div>
  );
}

"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import CampaignFormModal from "../components/CampaignFormModal";

export default function CampaignDetailsPage({ params: paramsPromise }: { params: Promise<{ domain: string, id: string }> }) {
  const params = React.use(paramsPromise);
  const router = useRouter();
  const { id } = params;
  const domain = APP_SLUG;
  const [campaign, setCampaign] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [isLeadModalOpen, setIsLeadModalOpen] = useState(false);
  const [leads, setLeads] = useState<any[]>([]);
  const [availableLeads, setAvailableLeads] = useState<any[]>([]);
  const [selectedLeadIds, setSelectedLeadIds] = useState<string[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const fileRef = React.useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetchCampaign();
    fetchLeads();
  }, [domain, id]);

  const fetchCampaign = async () => {
    const token = localStorage.getItem(`${domain}_access`);
    if (!token) return;
    try {
      const res = await fetch(`${getApiBase(domain)}/api/campaigns/${id}/`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        setCampaign(await res.json());
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const fetchLeads = async () => {
    const token = localStorage.getItem(`${domain}_access`);
    if (!token) return;
    try {
      const res = await fetch(`${getApiBase(domain)}/api/leads/?all=true`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        const allLeads = data.results || data;
        setLeads(allLeads.filter((l: any) => campaign && campaign.leads ? campaign.leads.includes(l.id) : false));
        setAvailableLeads(allLeads.filter((l: any) => campaign && campaign.leads ? !campaign.leads.includes(l.id) : true));
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleAddLead = async () => {
    if (selectedLeadIds.length === 0) return;
    const token = localStorage.getItem(`${domain}_access`);
    try {
      const res = await fetch(`${getApiBase(domain)}/api/campaigns/${id}/add_leads/`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ lead_ids: selectedLeadIds.map(val => parseInt(val)) })
      });
      if (res.ok) {
        setIsLeadModalOpen(false);
        setSelectedLeadIds([]);
        fetchCampaign();
      } else {
        alert("Failed to add leads to campaign.");
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]; if (!file) return;
    setIsUploading(true);
    const fd = new FormData(); 
    fd.append("file", file);
    fd.append("campaign_id", id);
    
    const token = localStorage.getItem(`${domain}_access`);
    try {
      const r = await fetch(`${getApiBase(domain)}/api/leads/bulk_upload/`, { method: "POST", headers: { Authorization: `Bearer ${token}` }, body: fd });
      if (r.ok) {
        fetchCampaign(); // Refresh list to show imported leads
      } else {
        const err = await r.json().catch(() => ({}));
        alert(err.error || "Upload failed");
      }
    } catch {} finally { setIsUploading(false); if (fileRef.current) fileRef.current.value = ""; }
  };

  const removeLead = async (leadId: number) => {
    if (!confirm("Remove this lead from the campaign?")) return;
    const token = localStorage.getItem(`${domain}_access`);
    try {
      const res = await fetch(`${getApiBase(domain)}/api/campaigns/${id}/remove_leads/`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ lead_ids: [leadId] })
      });
      if (res.ok) {
        fetchCampaign();
      }
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    if (campaign && campaign.leads) {
      fetchLeads();
    }
  }, [campaign]);

  const handleDelete = async () => {
    if (!confirm("Are you sure you want to delete this campaign?")) return;
    const token = localStorage.getItem(`${domain}_access`);
    try {
      const res = await fetch(`${getApiBase(domain)}/api/campaigns/${id}/`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        router.push(`/campaigns`);
      }
    } catch (err) {
      console.error(err);
    }
  };

  if (loading) return (
    <div className="min-h-screen bg-[#060608] flex justify-center items-center">
      <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-500"></div>
    </div>
  );
  if (!campaign) return <div className="min-h-screen bg-[#060608] flex justify-center items-center text-slate-500">Campaign not found</div>;

  return (
    <div className="min-h-screen bg-[#060608] text-slate-200 font-sans selection:bg-indigo-500/30 relative">
      {/* Background layer */}
      <div className="absolute inset-0 z-0">
         <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyMCIgaGVpZ2h0PSIyMCI+CiAgPGNpcmNsZSBjeD0iMiIgY3k9IjIiIHI9IjEiIGZpbGw9IiNmZmYiIGZpbGwtb3BhY2l0eT0iMC4wNSIvPgo8L3N2Zz4=')] opacity-50"></div>
         <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-indigo-600/10 blur-[120px] rounded-full mix-blend-screen pointer-events-none"></div>
      </div>

      <div className="relative z-10">
        <header className="border-b border-white/10 bg-[#060608]/80 backdrop-blur-xl sticky top-0 z-20">
          <div className="max-w-7xl mx-auto px-6 h-20 flex items-center justify-between">
            <div className="flex items-center gap-6">
              <button onClick={() => router.push(`/campaigns`)} className="p-2.5 rounded-xl bg-white/5 border border-white/10 hover:bg-white/10 text-slate-300 transition-colors">
                <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
              </button>
              <div>
                <h1 className="text-2xl font-black text-white tracking-tight leading-none mb-1.5">{campaign.name}</h1>
                <div className="flex items-center gap-3 text-sm">
                  <span className="text-slate-400 capitalize font-medium">{campaign.campaign_type.replace('_', ' ')}</span>
                  <span className="w-1 h-1 rounded-full bg-slate-600"></span>
                  <span className={`font-bold uppercase tracking-wider text-[10px] px-2.5 py-0.5 rounded-full ${campaign.status === 'active' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 shadow-[0_0_10px_rgba(16,185,129,0.2)]' : 'bg-slate-800 text-slate-400 border border-slate-700'}`}>
                    {campaign.status}
                  </span>
                </div>
              </div>
            </div>
            <div className="flex gap-3">
              <button onClick={() => setIsEditModalOpen(true)} className="px-5 py-2.5 bg-white/5 border border-white/10 text-white font-bold rounded-xl hover:bg-white/10 transition-colors shadow-sm">
                Edit Protocol
              </button>
              <button onClick={handleDelete} className="px-5 py-2.5 bg-red-500/10 border border-red-500/20 text-red-400 font-bold rounded-xl hover:bg-red-500/20 transition-colors shadow-sm">
                Terminate
              </button>
            </div>
          </div>
        </header>

        <main className="max-w-7xl mx-auto px-6 py-10">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
            <div className="lg:col-span-2 space-y-8">
              <div className="bg-[#111116]/80 backdrop-blur-2xl rounded-3xl border border-white/10 p-8 relative overflow-hidden shadow-2xl">
                <div className="absolute inset-0 bg-gradient-to-b from-white/[0.02] to-transparent pointer-events-none"></div>
                <h2 className="text-xl font-bold text-white mb-6 relative z-10 flex items-center gap-2">
                  <span className="text-indigo-400">⚡</span> Operations Center
                </h2>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-6 mb-8 relative z-10">
                  <div className="p-4 rounded-2xl bg-white/5 border border-white/5 relative group overflow-hidden">
                    <div className="absolute bottom-0 right-0 w-16 h-16 bg-emerald-500/10 blur-xl group-hover:bg-emerald-500/20 transition-colors"></div>
                    <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-2">Est. Revenue</div>
                    <div className="text-2xl font-black text-emerald-400">${parseFloat(campaign.expected_revenue).toLocaleString()}</div>
                  </div>
                  <div className="p-4 rounded-2xl bg-white/5 border border-white/5 relative group overflow-hidden">
                    <div className="absolute bottom-0 right-0 w-16 h-16 bg-amber-500/10 blur-xl group-hover:bg-amber-500/20 transition-colors"></div>
                    <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-2">Budget</div>
                    <div className="text-2xl font-black text-amber-400">${parseFloat(campaign.budgeted_cost).toLocaleString()}</div>
                  </div>
                  <div className="p-4 rounded-2xl bg-white/5 border border-white/5 relative group overflow-hidden">
                    <div className="absolute bottom-0 right-0 w-16 h-16 bg-red-500/10 blur-xl group-hover:bg-red-500/20 transition-colors"></div>
                    <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-2">Actual Cost</div>
                    <div className="text-2xl font-black text-white">${parseFloat(campaign.actual_cost).toLocaleString()}</div>
                  </div>
                  <div className="p-4 rounded-2xl bg-white/5 border border-white/5 relative group overflow-hidden">
                    <div className="absolute bottom-0 right-0 w-16 h-16 bg-blue-500/10 blur-xl group-hover:bg-blue-500/20 transition-colors"></div>
                    <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-2">Total Leads</div>
                    <div className="text-2xl font-black text-white">{campaign.leads_count}</div>
                  </div>
                </div>
                
                {campaign.description && (
                  <div className="relative z-10 mt-6 pt-6 border-t border-white/5">
                    <div className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3">Briefing</div>
                    <p className="text-sm text-slate-300 leading-relaxed bg-[#16161a] border border-white/5 p-5 rounded-2xl">{campaign.description}</p>
                  </div>
                )}
              </div>

              <div className="bg-[#111116]/80 backdrop-blur-2xl rounded-3xl border border-white/10 overflow-hidden shadow-2xl relative">
                <div className="px-8 py-6 border-b border-white/5 flex items-center justify-between relative z-10">
                  <h2 className="text-xl font-bold text-white flex items-center gap-2">
                    <span className="text-purple-400">👥</span> Lead Vector
                  </h2>
                  <div className="flex items-center gap-4">
                    <input type="file" accept=".csv" ref={fileRef} className="hidden" onChange={handleUpload} />
                    <button onClick={() => fileRef.current?.click()} disabled={isUploading} className="text-sm font-bold text-white hover:text-emerald-300 bg-emerald-600/20 border border-emerald-500/30 px-4 py-2 rounded-xl flex items-center gap-2 transition-colors disabled:opacity-50">
                      <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" /><polyline points="17 8 12 3 7 8" /><line x1="12" y1="3" x2="12" y2="15" /></svg> 
                      {isUploading ? "Importing..." : "Import CSV"}
                    </button>
                    <button onClick={() => setIsLeadModalOpen(true)} className="text-sm font-bold text-white hover:text-indigo-300 bg-indigo-600/20 border border-indigo-500/30 px-4 py-2 rounded-xl flex items-center gap-2 transition-colors">
                      <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg> Add Targets
                    </button>
                    <Link href={`/leads`} className="text-sm font-bold text-slate-400 hover:text-white hidden sm:block transition-colors">View All Leads →</Link>
                  </div>
                </div>
                
                <div className="relative z-10">
                  {leads.length === 0 ? (
                    <div className="p-10 text-center">
                      <div className="w-16 h-16 bg-white/5 rounded-2xl flex items-center justify-center mx-auto mb-4 text-2xl text-slate-500">🎯</div>
                      <p className="text-slate-400 text-sm">No leads are currently targeted by this campaign.</p>
                    </div>
                  ) : (
                    <ul className="divide-y divide-white/5">
                      {leads.map(lead => (
                        <li key={lead.id} className="p-6 hover:bg-white/5 transition-colors flex items-center justify-between group">
                          <div className="flex items-center gap-4">
                            <div className="w-10 h-10 rounded-full border border-white/10 bg-[#1a1a1f] flex items-center justify-center font-bold text-indigo-400 shadow-[0_0_10px_rgba(99,102,241,0.1)]">
                              {lead.first_name[0]}{lead.last_name[0]}
                            </div>
                            <div>
                              <Link href={`/leads/${lead.id}`} className="font-bold text-white hover:text-indigo-400 transition-colors text-base">
                                {lead.first_name} {lead.last_name}
                              </Link>
                              <div className="text-xs text-slate-500 mt-0.5">{lead.email || lead.phone || "No signal"}</div>
                            </div>
                          </div>
                          <div className="flex items-center gap-4">
                            <div className={`px-2.5 py-1 rounded-lg text-[10px] font-bold uppercase tracking-wider border 
                              ${lead.status === 'converted' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 'bg-white/5 text-slate-400 border-white/5'}`
                            }>
                              {lead.status.replace('_', ' ')}
                            </div>
                            <button onClick={() => removeLead(lead.id)} className="text-slate-500 hover:text-red-400 opacity-0 group-hover:opacity-100 p-2 rounded-lg transition-all" title="Remove from campaign">
                              <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg>
                            </button>
                          </div>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            </div>

            <div className="space-y-8">
              <div className="bg-[#111116]/80 backdrop-blur-2xl rounded-3xl border border-white/10 p-8 shadow-2xl relative overflow-hidden">
                <div className="absolute top-0 right-0 w-32 h-32 bg-indigo-500/10 blur-[50px]"></div>
                <h2 className="text-sm font-bold text-white mb-6 uppercase tracking-widest">Metadata</h2>
                <div className="space-y-6 relative z-10">
                  <div className="flex justify-between items-center pb-4 border-b border-white/5">
                    <span className="text-sm text-slate-400 font-medium">Launch Date</span>
                    <span className="text-sm font-bold text-white px-3 py-1 bg-white/5 rounded-lg border border-white/5">{campaign.start_date || 'TBD'}</span>
                  </div>
                  <div className="flex justify-between items-center pb-4 border-b border-white/5">
                    <span className="text-sm text-slate-400 font-medium">Conclusion</span>
                    <span className="text-sm font-bold text-white px-3 py-1 bg-white/5 rounded-lg border border-white/5">{campaign.end_date || 'TBD'}</span>
                  </div>
                  <div className="flex justify-between items-center pb-4 border-b border-white/5">
                    <span className="text-sm text-slate-400 font-medium">Sent</span>
                    <span className="text-sm font-bold text-indigo-400">{campaign.number_sent}</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-slate-400 font-medium">Expected Yield</span>
                    <span className="text-sm font-bold text-emerald-400">{campaign.expected_response}%</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </main>
      </div>

      {isEditModalOpen && (
        <CampaignFormModal
          domain={domain}
          initialData={campaign}
          onClose={() => setIsEditModalOpen(false)}
          onSuccess={() => {
            setIsEditModalOpen(false);
            fetchCampaign();
          }}
        />
      )}

      {isLeadModalOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm"></div>
          <div className="relative bg-[#0e0e11] border border-white/10 rounded-3xl shadow-[0_0_50px_rgba(0,0,0,0.5)] w-full max-w-md overflow-hidden animate-[slideUp_0.3s_cubic-bezier(0.16,1,0.3,1)]">
            <div className="px-8 py-6 border-b border-white/5 flex items-center justify-between">
              <h2 className="text-xl font-bold text-white">Assign Target</h2>
              <button onClick={() => setIsLeadModalOpen(false)} className="p-2 text-slate-500 hover:text-white hover:bg-white/5 rounded-xl transition-colors">
                <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg>
              </button>
            </div>
            <div className="p-8">
              <div className="flex justify-between items-end mb-3">
                <label className="block text-xs font-bold text-slate-400 uppercase tracking-wider">Select Leads</label>
                <button 
                  onClick={() => setSelectedLeadIds(selectedLeadIds.length === availableLeads.length ? [] : availableLeads.map(l => l.id.toString()))}
                  className="text-[10px] font-bold text-indigo-400 hover:text-indigo-300 uppercase tracking-wider"
                >
                  {selectedLeadIds.length === availableLeads.length ? "Deselect All" : "Select All"}
                </button>
              </div>
              <div className="max-h-60 overflow-y-auto space-y-2 bg-[#16161a] border border-white/10 rounded-xl p-3">
                {availableLeads.length === 0 && <p className="text-slate-500 text-sm p-2 text-center">No available leads to add.</p>}
                {availableLeads.map((l: any) => (
                  <label key={l.id} className="flex items-center gap-3 p-2 hover:bg-white/5 rounded-lg cursor-pointer transition-colors">
                    <input 
                      type="checkbox" 
                      checked={selectedLeadIds.includes(l.id.toString())}
                      onChange={(e) => {
                        if (e.target.checked) setSelectedLeadIds([...selectedLeadIds, l.id.toString()]);
                        else setSelectedLeadIds(selectedLeadIds.filter(id => id !== l.id.toString()));
                      }}
                      className="w-4 h-4 rounded bg-[#060608] border-white/20 text-indigo-500 focus:ring-indigo-500/50"
                    />
                    <span className="text-white text-sm font-medium">{l.first_name} {l.last_name}</span>
                  </label>
                ))}
              </div>

              <div className="mt-10 flex justify-end gap-3">
                <button type="button" onClick={() => setIsLeadModalOpen(false)} className="px-5 py-2.5 text-sm font-bold text-slate-400 hover:text-white border border-transparent hover:border-white/10 rounded-xl transition-colors">
                  Cancel
                </button>
                <button type="button" onClick={handleAddLead} disabled={selectedLeadIds.length === 0} className="px-6 py-2.5 text-sm font-bold text-white bg-indigo-600 rounded-xl hover:bg-indigo-500 transition-colors shadow-[0_0_15px_rgba(99,102,241,0.3)] disabled:opacity-50 disabled:shadow-none">
                  Assign Leads ({selectedLeadIds.length})
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

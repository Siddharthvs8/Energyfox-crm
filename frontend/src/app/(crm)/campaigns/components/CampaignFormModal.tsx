import { getApiBase } from "@/lib/mock-data";
import React, { useState } from 'react';

export default function CampaignFormModal({ domain, onClose, onSuccess, initialData = null }: any) {
  const [formData, setFormData] = useState({
    name: initialData?.name || '',
    campaign_type: initialData?.campaign_type || 'email',
    status: initialData?.status || 'planning',
    start_date: initialData?.start_date || '',
    end_date: initialData?.end_date || '',
    expected_revenue: initialData?.expected_revenue || '0.00',
    budgeted_cost: initialData?.budgeted_cost || '0.00',
    expected_response: initialData?.expected_response || '0.00',
    description: initialData?.description || ''
  });
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    const tk = localStorage.getItem(`${domain}_access`);
    try {
      const url = initialData 
        ? `${getApiBase(domain)}/api/campaigns/${initialData.id}/` 
        : `${getApiBase(domain)}/api/campaigns/`;
      const method = initialData ? 'PUT' : 'POST';

      // Clean empty dates
      const payload = { ...formData };
      if (!payload.start_date) delete payload.start_date;
      if (!payload.end_date) delete payload.end_date;

      const res = await fetch(url, {
        method,
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${tk}`
        },
        body: JSON.stringify(payload)
      });
      if (res.ok) {
        onSuccess();
      } else {
        console.error(await res.text());
        alert("Failed to save campaign");
      }
    } catch (err) {
      console.error(err);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[100] flex items-center justify-center p-4">
      <div className="bg-[#0e0e11] border border-white/10 rounded-3xl shadow-[0_0_50px_rgba(0,0,0,0.5)] w-full max-w-2xl overflow-hidden animate-[slideUp_0.3s_cubic-bezier(0.16,1,0.3,1)]">
        <div className="px-8 py-6 border-b border-white/5 flex items-center justify-between">
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <span className="text-indigo-400">📝</span> {initialData ? 'Update Protocol' : 'Deploy Campaign'}
          </h2>
          <button onClick={onClose} className="p-2 text-slate-500 hover:text-white hover:bg-white/5 rounded-xl transition-colors">
            <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg>
          </button>
        </div>
        
        <form onSubmit={handleSubmit} className="p-8 max-h-[80vh] overflow-y-auto">
          <div className="grid grid-cols-2 gap-6">
            <div className="col-span-2">
              <label className="block text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">Campaign Identifier <span className="text-red-500">*</span></label>
              <input required type="text" value={formData.name} onChange={e => setFormData({...formData, name: e.target.value})} className="w-full bg-[#16161a] border border-white/10 rounded-xl px-4 py-3.5 text-sm focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all font-medium text-white placeholder-slate-600" placeholder="e.g. Q3 Summer Promo" />
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">Vector</label>
              <select value={formData.campaign_type} onChange={e => setFormData({...formData, campaign_type: e.target.value})} className="w-full bg-[#16161a] border border-white/10 rounded-xl px-4 py-3.5 text-sm focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all font-medium text-white">
                <option value="email">Email</option>
                <option value="webinar">Webinar</option>
                <option value="conference">Conference</option>
                <option value="trade_show">Trade Show</option>
                <option value="advertisement">Advertisement</option>
                <option value="telemarketing">Telemarketing</option>
                <option value="others">Others</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">Status</label>
              <select value={formData.status} onChange={e => setFormData({...formData, status: e.target.value})} className="w-full bg-[#16161a] border border-white/10 rounded-xl px-4 py-3.5 text-sm focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all font-medium text-white">
                <option value="planning">Planning</option>
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
                <option value="completed">Completed</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">Launch Target</label>
              <input type="date" value={formData.start_date} onChange={e => setFormData({...formData, start_date: e.target.value})} className="w-full bg-[#16161a] border border-white/10 rounded-xl px-4 py-3.5 text-sm focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all font-medium text-white color-scheme-dark" />
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">Conclusion Target</label>
              <input type="date" value={formData.end_date} onChange={e => setFormData({...formData, end_date: e.target.value})} className="w-full bg-[#16161a] border border-white/10 rounded-xl px-4 py-3.5 text-sm focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all font-medium text-white color-scheme-dark" />
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">Est. Revenue ($)</label>
              <input type="number" step="0.01" value={formData.expected_revenue} onChange={e => setFormData({...formData, expected_revenue: e.target.value})} className="w-full bg-[#16161a] border border-white/10 rounded-xl px-4 py-3.5 text-sm focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all font-medium text-white" />
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">Budget Allocation ($)</label>
              <input type="number" step="0.01" value={formData.budgeted_cost} onChange={e => setFormData({...formData, budgeted_cost: e.target.value})} className="w-full bg-[#16161a] border border-white/10 rounded-xl px-4 py-3.5 text-sm focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all font-medium text-white" />
            </div>
            
            <div className="col-span-2">
              <label className="block text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">Briefing</label>
              <textarea rows={3} value={formData.description} onChange={e => setFormData({...formData, description: e.target.value})} className="w-full bg-[#16161a] border border-white/10 rounded-xl px-4 py-3.5 text-sm focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all font-medium text-white resize-none"></textarea>
            </div>
          </div>

          <div className="mt-10 flex justify-end gap-3 pt-6 border-t border-white/5">
            <button type="button" onClick={onClose} className="px-5 py-2.5 text-sm font-bold text-slate-400 hover:text-white border border-transparent hover:border-white/10 rounded-xl transition-colors">
              Cancel
            </button>
            <button type="submit" disabled={saving} className="px-6 py-2.5 text-sm font-bold text-white bg-indigo-600 rounded-xl hover:bg-indigo-500 transition-all shadow-[0_0_15px_rgba(99,102,241,0.3)] disabled:opacity-50 disabled:shadow-none flex items-center gap-2">
              {saving ? 'Processing...' : 'Confirm Pipeline'}
              {!saving && <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" viewBox="0 0 24 24"><path d="M5 12h14M12 5l7 7-7 7"/></svg>}
            </button>
          </div>
        </form>
        <style>{`
          .color-scheme-dark { color-scheme: dark; }
        `}</style>
      </div>
    </div>
  );
}

"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase, formatCurrency } from "@/lib/mock-data";

import React, { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import DocumentationStage1Section from "./DocumentationStage1Section";

import ActivityTimeline from "@/components/ActivityTimeline";
import { DetailSkeleton } from "@/components/Skeleton";
type Attachment = { label: string; url: string; is_image: boolean };
type DocDetail = {
  id: number;
  first_name: string; last_name: string | null;
  phone: string | null; email: string | null;
  location: string | null; installation_location: string | null;
  product_name: string | null; value: number; status: string;
  bde_name: string | null;
  documentation_staff: number | null;
  documentation_staff_name: string | null;
  pushed_at: string | null;
  can_assign: boolean;
  site_visit: Record<string, any> | null;
  can_edit_stage1: boolean;
  can_reopen_stage1: boolean;
  attachments: Attachment[];
};

// Site-visit text/choice fields worth showing (files are listed under Attachments).
const SV_LABELS: { key: string; label: string }[] = [
  { key: "roof_type", label: "Roof Type" },
  { key: "rcc_roof_types", label: "RCC Roof Type" },
  { key: "connection_type", label: "Connection Type" },
  { key: "connected_load", label: "Connected Load" },
  { key: "consumer_number", label: "Consumer Number" },
  { key: "current_bill", label: "Current Bill" },
  { key: "phase", label: "Phase" },
  { key: "building_height", label: "Building Height" },
  { key: "panel_to_inverter_distance", label: "Panel→Inverter Distance" },
  { key: "kseb_section", label: "KSEB Section" },
  { key: "feasible_capacity", label: "Feasible Capacity" },
  { key: "plant_capacity", label: "Plant Capacity" },
  { key: "transformer_feasibility", label: "Transformer Feasibility" },
  { key: "neutral_link", label: "Neutral Link" },
  { key: "roof_access", label: "Access to Roof" },
  { key: "parapet_height", label: "Parapet Height" },
  { key: "structure_type", label: "Structure Type" },
  { key: "custom_structure_height", label: "Custom Structure Height" },
  { key: "cable_panel_to_dc_db", label: "Cable: Panel→DC DB" },
  { key: "cable_inverter_to_ac_db", label: "Cable: Inverter→AC DB" },
  { key: "earthing_cable_length", label: "Earthing Cable Length" },
  { key: "lightning_conductor_length", label: "Lightning Conductor Length" },
  { key: "earthing_surface", label: "Earthing Surface" },
  { key: "anchoring_allowed", label: "Anchoring Allowed" },
  { key: "name_change", label: "Name Change" },
  { key: "loan", label: "Loan" },
  { key: "loan_amount", label: "Required Loan Amount" },
  { key: "load_enhancement", label: "Load Enhancement" },
  { key: "email_linked_to_itr", label: "Email linked to ITR" },
];

export default function DocumentationDetailPage({ params: paramsPromise }: { params: Promise<{ id: string }> }) {
  const params = React.use(paramsPromise);
  const id = params.id;
  const domain = APP_SLUG;
  const router = useRouter();

  const [data, setData] = useState<DocDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [docStaff, setDocStaff] = useState<{ id: number; name: string; branch_name: string | null }[]>([]);
  const [selectedStaff, setSelectedStaff] = useState("");
  const [assigning, setAssigning] = useState(false);

  const token = () => localStorage.getItem(`${domain}_access`);

  const load = useCallback(async () => {
    const t = token();
    if (!t) { router.push("/login"); return; }
    try {
      const r = await fetch(`${getApiBase(domain)}/api/leads/${id}/documentation-detail/`, { headers: { Authorization: `Bearer ${t}` } });
      if (r.ok) {
        const d = await r.json();
        setData(d);
        setSelectedStaff(d.documentation_staff ? String(d.documentation_staff) : "");
        if (d.can_assign) {
          const sr = await fetch(`${getApiBase(domain)}/api/users/documentation-staff/`, { headers: { Authorization: `Bearer ${t}` } });
          if (sr.ok) setDocStaff(await sr.json());
        }
      } else if (r.status === 403 || r.status === 404) {
        setError("You don't have access to this customer, or it isn't in documentation.");
      } else setError("Failed to load.");
    } catch { setError("Network error."); }
    finally { setLoading(false); }
  }, [domain, id, router]);

  useEffect(() => { load(); }, [load]);

  const assign = async () => {
    setAssigning(true);
    try {
      const r = await fetch(`${getApiBase(domain)}/api/leads/${id}/assign-documentation/`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token()}` },
        body: JSON.stringify({ staff: selectedStaff || null }),
      });
      if (r.ok) { await load(); alert("Documentation staff updated."); }
      else { const d = await r.json().catch(() => ({})); alert(d.error || "Failed to assign."); }
    } catch { alert("Network error."); }
    finally { setAssigning(false); }
  };

  if (loading) return <DetailSkeleton />;
  if (error || !data) return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-[900px]">
      <Link href="/documentation" className="text-sm text-indigo-600 hover:underline">← Back to Documentation Stage 1</Link>
      <p className="mt-6 text-sm text-rose-600">{error || "Not found."}</p>
    </div>
  );

  const sv = data.site_visit;
  const svRows = sv ? SV_LABELS
    .map(f => ({ label: f.label, value: f.key === "rcc_roof_types" ? (Array.isArray(sv[f.key]) ? sv[f.key].join(", ") : "") : sv[f.key] }))
    .filter(r => r.value !== null && r.value !== undefined && r.value !== "") : [];

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-[1100px]">
      <div className="flex items-center justify-between gap-3">
        <Link href="/documentation" className="text-sm text-indigo-600 hover:underline">← Back to Documentation Stage 1</Link>
        <ActivityTimeline leadId={params.id} />
      </div>

      {/* Header */}
      <div className="mt-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">{data.first_name} {data.last_name}</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {data.phone || "—"}{data.email ? ` · ${data.email}` : ""}{data.location ? ` · ${data.location}` : ""}
          </p>
        </div>
        <div className="text-right">
          <p className="text-[10px] text-slate-400 uppercase tracking-wide">Documentation Staff</p>
          <p className="text-sm font-semibold text-amber-600">{data.documentation_staff_name || "Unassigned"}</p>
        </div>
      </div>

      {/* Assign (managers/admins) */}
      {data.can_assign && (
        <div className="mt-5 bg-white border border-slate-200 rounded-2xl shadow-sm p-5">
          <h2 className="text-sm font-bold text-slate-900 mb-3">Assign Documentation Staff</h2>
          <div className="flex flex-col sm:flex-row gap-3 sm:items-end">
            <div className="flex-1">
              <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wide mb-1.5">Staff</label>
              <select value={selectedStaff} onChange={e => setSelectedStaff(e.target.value)} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all">
                <option value="">— Unassigned —</option>
                {docStaff.map(s => <option key={s.id} value={s.id}>{s.name}{s.branch_name ? ` (${s.branch_name})` : ""}</option>)}
              </select>
              {docStaff.length === 0 && <p className="text-[11px] text-amber-600 mt-1.5">No documentation staff yet — set a user&apos;s role to &quot;Documentation Staff&quot; under Team.</p>}
            </div>
            <button onClick={assign} disabled={assigning} className="px-5 py-2.5 bg-amber-600 text-white rounded-xl text-sm font-semibold hover:bg-amber-700 disabled:opacity-50 transition-all">{assigning ? "Saving…" : "Save"}</button>
          </div>
        </div>
      )}

      {/* Customer details */}
      <div className="mt-5 bg-white border border-slate-200 rounded-2xl shadow-sm p-5">
        <h2 className="text-sm font-bold text-slate-900 mb-4">Customer</h2>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-3">
          <Detail label="Installation Location" value={data.installation_location} />
          <Detail label="Product" value={data.product_name} />
          <Detail label="Deal Value" value={data.value ? `₹${formatCurrency(data.value)}` : null} />
          <Detail label="BDE" value={data.bde_name} />
          <Detail label="Status" value={data.status} />
          <Detail label="Pushed On" value={data.pushed_at ? new Date(data.pushed_at).toLocaleString("en-IN") : null} />
        </div>
      </div>

      {/* Site visit details */}
      {svRows.length > 0 && (
        <div className="mt-5 bg-white border border-slate-200 rounded-2xl shadow-sm p-5">
          <h2 className="text-sm font-bold text-slate-900 mb-4">Site Visit Details</h2>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-3">
            {svRows.map(r => <Detail key={r.label} label={r.label} value={r.value} />)}
          </div>
        </div>
      )}

      {/* Attachments preview — managers/admins only. Documentation staff work with
          these files directly in the Stage 1 slots below, so it's hidden for them
          to keep their view focused on what they need to fill. */}
      {data.can_assign && (
      <div className="mt-5 bg-white border border-slate-200 rounded-2xl shadow-sm p-5">
        <h2 className="text-sm font-bold text-slate-900 mb-4">Attachments <span className="text-slate-400 font-medium">({data.attachments.length})</span></h2>
        {data.attachments.length === 0 ? (
          <p className="text-sm text-slate-400">No attachments uploaded.</p>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
            {data.attachments.map((a, i) => (
              <div key={i} className="border border-slate-200 rounded-xl overflow-hidden bg-slate-50">
                <a href={a.url} target="_blank" rel="noreferrer" className="block">
                  {a.is_image ? (
                    <img src={a.url} alt={a.label} className="w-full h-36 object-cover bg-slate-100" />
                  ) : (
                    <div className="w-full h-36 flex items-center justify-center bg-slate-100 text-slate-400">
                      <svg width="40" height="40" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" /><path d="M14 2v6h6" /></svg>
                    </div>
                  )}
                </a>
                <div className="px-3 py-2.5">
                  <p className="text-xs font-semibold text-slate-700 truncate" title={a.label}>{a.label}</p>
                  <div className="flex items-center gap-3 mt-1.5">
                    <a href={a.url} target="_blank" rel="noreferrer" className="text-[11px] font-semibold text-indigo-600 hover:text-indigo-800">Open</a>
                    <a href={a.url} download className="text-[11px] font-semibold text-slate-500 hover:text-slate-700">Download</a>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      )}

      {/* Documentation Stage 1 */}
      <DocumentationStage1Section
        leadId={data.id}
        canEdit={data.can_edit_stage1}
        canReopen={data.can_reopen_stage1}
        siteVisit={data.site_visit}
        customerEmail={data.email}
        onChanged={load}
      />
    </div>
  );
}

function Detail({ label, value }: { label: string; value: any }) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <div>
      <p className="text-[10px] text-slate-400 uppercase tracking-wide">{label}</p>
      <p className="text-sm font-medium text-slate-700 break-words">{String(value)}</p>
    </div>
  );
}

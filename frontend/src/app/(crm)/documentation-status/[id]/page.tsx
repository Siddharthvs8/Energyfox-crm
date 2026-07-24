"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase, formatCurrency } from "@/lib/mock-data";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

type HistoryItem = { id: number; type: string; description: string; actor: string | null; auto_generated?: boolean; timestamp: string };
type Detail = {
  id: number;
  name: string;
  phone: string | null; email: string | null;
  location: string | null; installation_location: string | null;
  product_name: string | null; value: number; status: string; source: string;
  created_at: string | null;
  tele_caller_name: string | null; bde_name: string | null; documentation_staff_name: string | null;
  pushed_at: string | null;
  stage1_status: "not_started" | "in_progress" | "completed";
  stage1_completed_at: string | null; stage1_completed_by: string | null;
  stage2_status: string;
  site_visit: Record<string, any> | null;
  stage1: Record<string, any> | null;
  attachments: { label: string; url: string; is_image: boolean }[];
  history: HistoryItem[];
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
const yesNo = (v: any) => (v === true ? "Yes" : v === false ? "No" : null);

const STAGE_STYLES: Record<string, { label: string; cls: string }> = {
  completed: { label: "Completed", cls: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  in_progress: { label: "In progress", cls: "bg-amber-50 text-amber-700 border-amber-200" },
  not_started: { label: "Not started", cls: "bg-slate-100 text-slate-500 border-slate-200" },
  pending: { label: "Pending", cls: "bg-slate-100 text-slate-500 border-slate-200" },
};
function StageBadge({ status }: { status: string }) {
  const s = STAGE_STYLES[status] || STAGE_STYLES.not_started;
  return <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-[11px] font-semibold border ${s.cls}`}>{s.label}</span>;
}

const TYPE_DOT: Record<string, string> = {
  lead_created: "bg-indigo-500",
  lead_status_change: "bg-amber-500",
  note_added: "bg-emerald-500",
  task_created: "bg-blue-500",
  task_completed: "bg-emerald-500",
  call_logged: "bg-violet-500",
};

function fmtTime(ts: string) {
  const d = new Date(ts.replace(" ", "T"));
  if (isNaN(d.getTime())) return ts;
  return d.toLocaleString("en-IN", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

export default function DocumentationStatusDetail({ params: paramsPromise }: { params: Promise<{ id: string }> }) {
  const params = React.use(paramsPromise);
  const id = params.id;
  const domain = APP_SLUG;
  const router = useRouter();

  const [data, setData] = useState<Detail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const t = localStorage.getItem(`${domain}_access`);
    if (!t) { router.push("/login"); return; }
    try {
      const r = await fetch(`${getApiBase(domain)}/api/leads/${id}/documentation-overview-detail/`, { headers: { Authorization: `Bearer ${t}` } });
      if (r.ok) setData(await r.json());
      else if (r.status === 403 || r.status === 404) setError("This customer isn't available to you, or isn't in documentation.");
      else setError("Failed to load.");
    } catch { setError("Network error."); }
    finally { setLoading(false); }
  }, [domain, id, router]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <div className="flex items-center justify-center min-h-[60vh]"><div className="w-8 h-8 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" /></div>;
  if (error || !data) return (
    <div className="p-6 lg:p-8 max-w-[1000px]">
      <Link href="/documentation-status" className="text-sm text-indigo-600 hover:underline">← Back to Documentation</Link>
      <p className="mt-6 text-sm text-rose-600">{error || "Not found."}</p>
    </div>
  );

  const sv = data.site_visit;
  // Show every site-visit field's heading; empty ones render as "—" (see Detail).
  const svRows = sv
    ? SV_LABELS.map(f => ({
        label: f.label,
        value: f.key === "rcc_roof_types" ? (Array.isArray(sv[f.key]) ? sv[f.key].join(", ") : "") : sv[f.key],
      }))
    : [];

  return (
    <div className="p-6 lg:p-8 max-w-[1000px]">
      <Link href="/documentation-status" className="text-sm text-indigo-600 hover:underline">← Back to Documentation</Link>

      {/* Header */}
      <div className="mt-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">{data.name || "—"}</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {data.phone || "—"}{data.email ? ` · ${data.email}` : ""}{data.location ? ` · ${data.location}` : ""}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="text-right">
            <p className="text-[10px] text-slate-400 uppercase tracking-wide">Stage 1</p>
            <StageBadge status={data.stage1_status} />
          </div>
          <div className="text-right">
            <p className="text-[10px] text-slate-400 uppercase tracking-wide">Stage 2</p>
            <StageBadge status={data.stage2_status} />
          </div>
        </div>
      </div>

      {/* Customer + documentation details */}
      <div className="mt-5 bg-white border border-slate-200 rounded-2xl shadow-sm p-5">
        <h2 className="text-sm font-bold text-slate-900 mb-4">Customer & Process</h2>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-3">
          <Detail label="Installation Location" value={data.installation_location} />
          <Detail label="Product" value={data.product_name} />
          <Detail label="Deal Value" value={data.value ? `₹${formatCurrency(data.value)}` : null} />
          <Detail label="Status" value={data.status} />
          <Detail label="Source" value={data.source} />
          <Detail label="Created" value={data.created_at ? new Date(data.created_at).toLocaleDateString("en-IN") : null} />
          <Detail label="Tele Caller" value={data.tele_caller_name} />
          <Detail label="BDE" value={data.bde_name} />
          <Detail label="Documentation Staff" value={data.documentation_staff_name} />
          <Detail label="Pushed to Documentation" value={data.pushed_at ? new Date(data.pushed_at).toLocaleString("en-IN") : null} />
          <Detail label="Stage 1 Completed" value={data.stage1_completed_at ? `${new Date(data.stage1_completed_at).toLocaleDateString("en-IN")}${data.stage1_completed_by ? ` · ${data.stage1_completed_by}` : ""}` : null} />
        </div>
      </div>

      {/* Site Visit details (BDE) */}
      {svRows.length > 0 && (
        <div className="mt-5 bg-white border border-slate-200 rounded-2xl shadow-sm p-5">
          <h2 className="text-sm font-bold text-slate-900 mb-4">Site Visit Details</h2>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-3">
            {svRows.map(r => <Detail key={r.label} label={r.label} value={r.value} />)}
          </div>
        </div>
      )}

      {/* Documentation Stage 1 data */}
      {data.stage1 && (
        <div className="mt-5 bg-white border border-slate-200 rounded-2xl shadow-sm p-5">
          <h2 className="text-sm font-bold text-slate-900 mb-4">Documentation Stage 1</h2>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-3">
            <Detail label="Plant Capacity" value={data.stage1.plant_capacity} />
            <Detail label="Test cum Completion Report" value={yesNo(data.stage1.test_cum_completion_report)} />
            <Detail label="Sketch" value={yesNo(data.stage1.sketch)} />
            <Detail label="Loan above ₹2 lakh" value={yesNo(data.stage1.loan_above_2_lakh)} />
            <Detail label="Stage 1 Complete" value={yesNo(data.stage1.is_complete)} />
          </div>
        </div>
      )}

      {/* Attachments preview (site visit + Stage 1 + invoice) */}
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

      {/* Complete history */}
      <div className="mt-5 bg-white border border-slate-200 rounded-2xl shadow-sm p-5">
        <h2 className="text-sm font-bold text-slate-900 mb-4">Complete History <span className="text-slate-400 font-medium">({data.history.length})</span></h2>
        {data.history.length === 0 ? (
          <p className="text-sm text-slate-400">No activity recorded yet.</p>
        ) : (
          <ol className="relative border-l border-slate-200 ml-1.5 space-y-5">
            {data.history.map(h => (
              <li key={h.id} className="ml-5">
                <span className={`absolute -left-[7px] w-3.5 h-3.5 rounded-full ring-4 ring-white ${TYPE_DOT[h.type] || "bg-slate-400"}`} />
                <p className="text-sm text-slate-800 leading-snug">{h.description}</p>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  {fmtTime(h.timestamp)}{h.auto_generated ? " · by Auto generated" : (h.actor ? ` · by ${h.actor}` : "")}
                </p>
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}

function Detail({ label, value }: { label: string; value: any }) {
  const empty = value === null || value === undefined || value === "";
  return (
    <div>
      <p className="text-[10px] text-slate-400 uppercase tracking-wide">{label}</p>
      <p className={`text-sm font-medium break-words ${empty ? "text-slate-300" : "text-slate-700 capitalize"}`}>
        {empty ? "—" : String(value)}
      </p>
    </div>
  );
}

"use client";
import { getApiBase, formatCurrency } from "@/lib/mock-data";
import { APP_SLUG } from "@/lib/config";

import React, { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import WarrantySection from "./WarrantySection";
import { DetailSkeleton } from "@/components/Skeleton";

type WarrantyDetail = {
  id: number;
  first_name: string; last_name: string | null;
  phone: string | null; email: string | null;
  location: string | null; installation_location: string | null;
  product_name: string | null; value: number; status: string;
  bde_name: string | null;
  documentation_staff_name: string | null;
  pushed_at: string | null;
  is_complete: boolean;
  can_edit: boolean;
  record: { completed_by_name: string | null } | null;
  /** The photos liasoning signed off on — read-only here. */
  liasoning_images?: { id: number; doc_type: string; label: string; file: string }[];
};

export default function WarrantyDetailPage({ params: paramsPromise }: { params: Promise<{ id: string }> }) {
  const params = React.use(paramsPromise);
  const id = params.id;
  const domain = APP_SLUG;
  const router = useRouter();

  const [data, setData] = useState<WarrantyDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const token = () => localStorage.getItem(`${domain}_access`);

  const load = useCallback(async () => {
    const t = token();
    if (!t) { router.push("/login"); return; }
    try {
      const r = await fetch(`${getApiBase(domain)}/api/leads/${id}/warranty-detail/`, { headers: { Authorization: `Bearer ${t}` } });
      if (r.ok) setData(await r.json());
      else if (r.status === 403 || r.status === 404) setError("You don't have access to this customer, or it isn't in the warranty stage.");
      else setError("Failed to load.");
    } catch { setError("Network error."); }
    finally { setLoading(false); }
  }, [domain, id, router]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <DetailSkeleton />;
  if (error || !data) return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-[900px]">
      <Link href="/warranty" className="text-sm text-indigo-600 hover:underline">← Back to Warranty</Link>
      <p className="mt-6 text-sm text-rose-600">{error || "Not found."}</p>
    </div>
  );

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-[1100px]">
      <Link href="/warranty" className="text-sm text-indigo-600 hover:underline">← Back to Warranty</Link>

      <div className="mt-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">{data.first_name} {data.last_name}</h1>
          <p className="text-sm text-slate-500 mt-0.5">{data.phone || "—"}{data.email ? ` · ${data.email}` : ""}{data.location ? ` · ${data.location}` : ""}</p>
        </div>
        {data.is_complete && (
          <span className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-emerald-50 border border-emerald-200 text-emerald-700 rounded-lg text-xs font-semibold">
            ✓ Completed{data.record?.completed_by_name ? ` by ${data.record.completed_by_name}` : ""}
          </span>
        )}
      </div>

      {/* Customer details */}
      <div className="mt-5 bg-white border border-slate-200 rounded-2xl shadow-sm p-5">
        <h2 className="text-sm font-bold text-slate-900 mb-4">Customer</h2>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-3">
          <Detail label="Installation Location" value={data.installation_location} />
          <Detail label="Product" value={data.product_name} />
          <Detail label="Deal Value" value={data.value ? `₹${formatCurrency(data.value)}` : null} />
          <Detail label="BDE" value={data.bde_name} />
          <Detail label="Documentation Staff" value={data.documentation_staff_name} />
          <Detail label="Reached Warranty" value={data.pushed_at ? new Date(data.pushed_at).toLocaleString("en-IN") : null} />
        </div>
      </div>

      {/* The evidence liasoning signed off on. The customer is only here
          because liasoning said the plant is live, and the certificate below
          describes that same plant — so the pictures of it belong on this page
          rather than one module away. */}
      <div className="mt-5 bg-white border border-slate-200 rounded-2xl shadow-sm p-5">
        <h2 className="text-sm font-bold text-slate-900">Liasoning Images</h2>
        <p className="text-[11px] text-slate-400 mt-0.5 mb-4">
          Uploaded at liasoning sign-off. Read-only.
        </p>
        {(data.liasoning_images || []).length === 0 ? (
          <p className="text-[11px] text-slate-400">No photos on the liasoning record.</p>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
            {(data.liasoning_images || []).map(img => (
              <a key={img.id} href={img.file} target="_blank" rel="noreferrer"
                title={`Open the ${img.label.toLowerCase()}`}
                className="group block border border-slate-200 rounded-xl overflow-hidden bg-white hover:border-indigo-300 hover:shadow-sm transition">
                <div className="aspect-[4/3] bg-slate-50 overflow-hidden">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={img.file} alt={img.label} loading="lazy"
                    className="w-full h-full object-cover group-hover:scale-[1.03] transition-transform" />
                </div>
                <p className="px-2.5 py-1.5 text-[10px] font-semibold text-slate-600 truncate">{img.label}</p>
              </a>
            ))}
          </div>
        )}
      </div>

      {/* Warranty form */}
      <WarrantySection
        leadId={data.id}
        canEdit={data.can_edit}
        phone={data.phone}
        email={data.email}
        customerName={`${data.first_name} ${data.last_name || ""}`.trim()}
        onChanged={load}
      />
    </div>
  );
}

function Detail({ label, value }: { label: string; value: any }) {
  return (
    <div>
      <p className="text-[10px] text-slate-400 uppercase tracking-wide">{label}</p>
      <p className="text-sm font-medium text-slate-700 break-words">{value === null || value === undefined || value === "" ? "—" : String(value)}</p>
    </div>
  );
}

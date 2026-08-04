"use client";
import { getApiBase, formatCurrency } from "@/lib/mock-data";
import { APP_SLUG } from "@/lib/config";

import React, { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import ActivityTimeline from "@/components/ActivityTimeline";
type LiasoningDetail = {
  id: number;
  first_name: string; last_name: string | null;
  phone: string | null; email: string | null;
  location: string | null; installation_location: string | null;
  product_name: string | null; value: number; status: string;
  bde_name: string | null;
  pushed_at: string | null;
  is_complete: boolean;
  can_edit: boolean;
  record: {
    completed_by_name: string | null; completed_at: string | null;
    // Liasoning waits on the commissioned plant photo — signing off says the
    // plant is live, so it needs the evidence.
    has_plant_photo?: boolean;
    documents?: { id: number; doc_type: string; file: string; uploaded_at: string }[];
  } | null;
};

const PLANT_PHOTO = "plant_commissioned";

export default function LiasoningDetailPage({ params: paramsPromise }: { params: Promise<{ id: string }> }) {
  const params = React.use(paramsPromise);
  const id = params.id;
  const domain = APP_SLUG;
  const router = useRouter();

  const [data, setData] = useState<LiasoningDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [completing, setCompleting] = useState(false);
  const [uploading, setUploading] = useState(false);

  const token = () => localStorage.getItem(`${domain}_access`);

  const load = useCallback(async () => {
    const t = token();
    if (!t) { router.push("/login"); return; }
    try {
      const r = await fetch(`${getApiBase(domain)}/api/leads/${id}/liasoning-detail/`, { headers: { Authorization: `Bearer ${t}` } });
      if (r.ok) setData(await r.json());
      else if (r.status === 403 || r.status === 404) setError("You don't have access to this customer, or it isn't in liasoning & service.");
      else setError("Failed to load.");
    } catch { setError("Network error."); }
    finally { setLoading(false); }
  }, [domain, id, router]);

  useEffect(() => { load(); }, [load]);

  /** The photo is the evidence behind the sign-off, so it is uploaded here. */
  const upload = async (files: FileList | null) => {
    if (!files?.length) return;
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        const body = new FormData();
        body.append("file", file);
        body.append("doc_type", PLANT_PHOTO);
        const r = await fetch(`${getApiBase(domain)}/api/leads/${id}/liasoning/documents/`, {
          method: "POST", headers: { Authorization: `Bearer ${token()}` }, body,
        });
        if (!r.ok) {
          const d = await r.json().catch(() => ({}));
          alert(d.error || "Could not upload the photo.");
          return;
        }
      }
      await load();
    } catch { alert("Network error while uploading."); }
    finally { setUploading(false); }
  };

  const removePhoto = async (docId: number) => {
    if (!window.confirm("Remove this photo?")) return;
    try {
      const r = await fetch(`${getApiBase(domain)}/api/leads/${id}/liasoning/documents/${docId}/`,
                            { method: "DELETE", headers: { Authorization: `Bearer ${token()}` } });
      if (r.ok || r.status === 204) await load();
      else alert("Could not remove the photo.");
    } catch { alert("Network error."); }
  };

  const complete = async () => {
    if (!window.confirm("Mark Liasoning & Service complete for this customer?")) return;
    setCompleting(true);
    try {
      const r = await fetch(`${getApiBase(domain)}/api/leads/${id}/complete-liasoning/`, { method: "POST", headers: { Authorization: `Bearer ${token()}` } });
      if (r.ok) { setData(await r.json()); }
      else { const d = await r.json().catch(() => ({})); alert(d.error || "Could not complete."); }
    } catch { alert("Network error."); }
    finally { setCompleting(false); }
  };

  if (loading) return <div className="flex items-center justify-center min-h-[60vh]"><div className="w-8 h-8 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" /></div>;
  if (error || !data) return (
    <div className="p-6 lg:p-8 max-w-[900px]">
      <Link href="/liasoning" className="text-sm text-indigo-600 hover:underline">← Back to Liasoning &amp; Service</Link>
      <p className="mt-6 text-sm text-rose-600">{error || "Not found."}</p>
    </div>
  );

  return (
    <div className="p-6 lg:p-8 max-w-[1100px]">
      <div className="flex items-center justify-between gap-3">
        <Link href="/liasoning" className="text-sm text-indigo-600 hover:underline">← Back to Liasoning &amp; Service</Link>
        <ActivityTimeline leadId={params.id} />
      </div>

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
          <Detail label="Status" value={data.status} />
          <Detail label="Reached Liasoning" value={data.pushed_at ? new Date(data.pushed_at).toLocaleString("en-IN") : null} />
        </div>
      </div>

      {/* Liasoning & Service work */}
      <div className="mt-5 bg-white border border-slate-200 rounded-2xl shadow-sm p-5">
        <h2 className="text-base font-bold text-slate-900">Liasoning &amp; Service</h2>
        <p className="text-xs text-slate-400 mt-0.5 mb-4">
          The commissioned plant photo is required before this customer can move on.
        </p>

        {(() => {
          const photos = (data.record?.documents || []).filter(d => d.doc_type === PLANT_PHOTO);
          const hasPhoto = !!data.record?.has_plant_photo || photos.length > 0;
          const editable = data.can_edit && !data.is_complete;
          return (
            <>
              <div className="mb-4">
                <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-2">
                  Plant Commissioned Photo <span className="text-rose-500 normal-case">(required)</span>
                </label>

                {photos.length > 0 ? (
                  <div className="flex flex-wrap gap-3 mb-2">
                    {photos.map(d => (
                      <div key={d.id} className="relative">
                        <a href={d.file} target="_blank" rel="noreferrer"
                          className="block w-28 h-28 rounded-xl border border-slate-200 overflow-hidden bg-slate-50">
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img src={d.file} alt="Commissioned plant" className="w-full h-full object-cover" />
                        </a>
                        {editable && (
                          <button onClick={() => removePhoto(d.id)} aria-label="Remove photo"
                            className="absolute -top-1.5 -right-1.5 w-6 h-6 rounded-full bg-white border border-slate-200 shadow-sm text-slate-400 hover:text-rose-600 text-xs font-bold">
                            ×
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-amber-600 mb-2">Not uploaded yet.</p>
                )}

                {editable && (
                  <input type="file" accept="image/*" multiple disabled={uploading}
                    onChange={e => upload(e.target.files)}
                    className="block w-full max-w-sm text-xs text-slate-500 file:mr-3 file:py-2 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100 transition cursor-pointer disabled:opacity-60" />
                )}
                {uploading && <p className="text-[11px] text-slate-400 mt-1">Uploading…</p>}
              </div>

              {editable && (
                <>
                  <button onClick={complete} disabled={completing || !hasPhoto}
                    title={hasPhoto ? "Completes liasoning for this customer"
                                    : "Upload the commissioned plant photo first"}
                    className="px-5 py-2.5 bg-emerald-600 text-white rounded-xl text-sm font-semibold hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed transition">
                    {completing ? "Completing…" : "Mark Complete"}
                  </button>
                  {!hasPhoto && (
                    <p className="text-[11px] text-amber-600 mt-2">
                      Upload the commissioned plant photo to enable this.
                    </p>
                  )}
                </>
              )}
            </>
          );
        })()}
        {!data.can_edit && <p className="text-xs text-slate-400">Read-only.</p>}
      </div>
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

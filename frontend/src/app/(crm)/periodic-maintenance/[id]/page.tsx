"use client";
import { getApiBase } from "@/lib/mock-data";
import { APP_SLUG } from "@/lib/config";

import React, { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

type Visit = {
  id: number; sequence: number; due_date: string;
  // Set once a visit has been moved, so the slip stays visible.
  original_due_date: string | null; reschedule_reason: string; is_rescheduled: boolean;
  dc_voltage: string; structure_damage: string; inverter_cleaned: boolean;
  ac_ne_voltage: string; ac_pn_voltage: string; ac_pe_voltage: string;
  monthly_production: string; error_codes: string;
  panel_before: string | null; panel_after: string | null;
  is_complete: boolean; completed_at: string | null; completed_by_name: string | null;
};
type Detail = {
  id: number;
  first_name: string; last_name: string | null;
  phone: string | null; email: string | null;
  location: string | null; installation_location: string | null;
  product_name: string | null; bde_name: string | null;
  plan: { start_date: string; visits: Visit[] } | null;
  can_edit: boolean;
};

const inputCls = "w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all disabled:opacity-70";
const labelCls = "block text-[10px] font-bold text-slate-400 uppercase tracking-wide mb-1.5";

export default function MaintenanceDetailPage({ params: paramsPromise }: { params: Promise<{ id: string }> }) {
  const params = React.use(paramsPromise);
  const id = params.id;
  const domain = APP_SLUG;
  const router = useRouter();
  const apiBase = getApiBase(domain);

  const [data, setData] = useState<Detail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [openVisit, setOpenVisit] = useState<Visit | null>(null);
  // Rescheduling gets a real dialog with a date picker — a text prompt made
  // the officer type the format by hand.
  const [moving, setMoving] = useState<Visit | null>(null);
  const [moveDate, setMoveDate] = useState("");
  const [moveReason, setMoveReason] = useState("");
  const [moveSaving, setMoveSaving] = useState(false);
  const [draft, setDraft] = useState<any>({});
  const [saving, setSaving] = useState(false);
  const [uploadingSlot, setUploadingSlot] = useState<string | null>(null);

  const token = () => localStorage.getItem(`${domain}_access`);
  const authHeader = () => ({ Authorization: `Bearer ${token()}` });

  const load = useCallback(async () => {
    const t = token();
    if (!t) { router.push("/login"); return; }
    try {
      const r = await fetch(`${apiBase}/api/leads/${id}/maintenance-detail/`, { headers: authHeader() });
      if (r.ok) setData(await r.json());
      else if (r.status === 403 || r.status === 404) setError("You don't have access, or this customer isn't scheduled for maintenance.");
      else setError("Failed to load.");
    } catch { setError("Network error."); }
    finally { setLoading(false); }
  }, [apiBase, id, router]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { load(); }, [load]);

  const openForm = (v: Visit) => {
    setDraft({
      dc_voltage: v.dc_voltage || "", structure_damage: v.structure_damage || "",
      inverter_cleaned: !!v.inverter_cleaned,
      ac_ne_voltage: v.ac_ne_voltage || "", ac_pn_voltage: v.ac_pn_voltage || "", ac_pe_voltage: v.ac_pe_voltage || "",
      monthly_production: v.monthly_production || "", error_codes: v.error_codes || "",
      is_complete: !!v.is_complete,
    });
    setOpenVisit(v);
  };

  /** Move a visit's due date. Its own endpoint, so the original date and the
   *  reason are recorded rather than the schedule quietly rewriting itself. */
  const submitReschedule = async () => {
    if (!moving) return;
    if (!moveDate || moveDate === moving.due_date) {
      alert("Pick a different date."); return;
    }
    setMoveSaving(true);
    try {
      const r = await fetch(
        `${getApiBase(domain)}/api/leads/${id}/maintenance-visits/${moving.id}/reschedule/`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${token()}` },
          body: JSON.stringify({ due_date: moveDate, reason: moveReason }),
        });
      if (!r.ok) { const d = await r.json().catch(() => ({})); alert(d.error || "Could not reschedule."); return; }
      setMoving(null);
      await load();
    } catch { alert("Network error while rescheduling."); }
    finally { setMoveSaving(false); }
  };

  const openReschedule = (v: Visit) => {
    setMoving(v);
    setMoveDate(v.due_date);                       // the picker opens on the current date
    setMoveReason(v.reschedule_reason || "");
  };

  const patchVisit = async (visitId: number, body: any) => {
    const r = await fetch(`${apiBase}/api/leads/${id}/maintenance-visits/${visitId}/`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...authHeader() },
      body: JSON.stringify(body),
    });
    if (!r.ok) { const e = await r.json().catch(() => ({})); alert(e.error || "Failed to save."); return null; }
    return r.json();
  };

  const saveVisit = async () => {
    if (!openVisit) return;
    setSaving(true);
    try {
      const updated = await patchVisit(openVisit.id, draft);
      if (updated) { await load(); setOpenVisit(null); }
    } catch { alert("Network error."); }
    finally { setSaving(false); }
  };

  const uploadPhoto = async (slot: "before" | "after", file: File) => {
    if (!openVisit) return;
    setUploadingSlot(slot);
    try {
      const fd = new FormData();
      fd.append("slot", slot);
      fd.append("file", file);
      const r = await fetch(`${apiBase}/api/leads/${id}/maintenance-visits/${openVisit.id}/photos/`, {
        method: "POST", headers: authHeader(), body: fd,
      });
      if (r.ok) {
        const v = await r.json();
        setOpenVisit(v);
        await load();
      } else { const e = await r.json().catch(() => ({})); alert(e.error || "Upload failed."); }
    } catch { alert("Network error while uploading."); }
    finally { setUploadingSlot(null); }
  };

  if (loading) return <div className="flex items-center justify-center min-h-[60vh]"><div className="w-8 h-8 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" /></div>;
  if (error || !data) return (
    <div className="p-6 lg:p-8 max-w-[900px]">
      <Link href="/periodic-maintenance" className="text-sm text-indigo-600 hover:underline">← Back to Periodic Maintenance</Link>
      <p className="mt-6 text-sm text-rose-600">{error || "Not found."}</p>
    </div>
  );

  const visits = data.plan?.visits || [];
  const done = visits.filter(v => v.is_complete).length;
  const todayStr = new Date().toISOString().slice(0, 10);
  const fileHref = (f: string | null) => (f ? (f.startsWith("http") ? f : `${apiBase}${f}`) : null);

  return (
    <div className="p-6 lg:p-8 max-w-[1100px]">
      <Link href="/periodic-maintenance" className="text-sm text-indigo-600 hover:underline">← Back to Periodic Maintenance</Link>

      <div className="mt-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">{data.first_name} {data.last_name}</h1>
          <p className="text-sm text-slate-500 mt-0.5">{data.phone || "—"}{data.email ? ` · ${data.email}` : ""}{data.location ? ` · ${data.location}` : ""}</p>
        </div>
        <div className="text-right">
          <p className="text-[10px] text-slate-400 uppercase tracking-wide">Progress</p>
          <p className={`text-sm font-bold ${done === visits.length ? "text-emerald-600" : "text-slate-700"}`}>{done}/{visits.length} visits done</p>
        </div>
      </div>

      {data.plan && (
        <p className="mt-2 text-xs text-slate-400">
          Schedule started {new Date(data.plan.start_date).toLocaleDateString("en-IN")} — one visit every 6 months for 5 years.
        </p>
      )}

      <div className="mt-5 bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[700px]">
            <thead>
              <tr className="text-left text-[10px] font-bold text-slate-400 uppercase tracking-wide border-b border-slate-100 bg-slate-50/60">
                <th className="px-5 py-3">#</th>
                <th className="px-5 py-3">Due Date</th>
                <th className="px-5 py-3">Status</th>
                <th className="px-5 py-3">Photos</th>
                <th className="px-5 py-3">Production</th>
                <th className="px-5 py-3 text-right"></th>
              </tr>
            </thead>
            <tbody>
              {visits.map(v => {
                const overdue = !v.is_complete && v.due_date < todayStr;
                return (
                  <tr key={v.id} className="border-b border-slate-50 hover:bg-slate-50/60">
                    <td className="px-5 py-3 font-bold text-slate-700">{v.sequence}</td>
                    <td className="px-5 py-3 text-slate-600 whitespace-nowrap">
                      {new Date(v.due_date).toLocaleDateString("en-IN")}
                      {v.is_rescheduled && v.original_due_date && (
                        <span className="block text-[10px] text-slate-400"
                          title={v.reschedule_reason || "Rescheduled"}>
                          moved from {new Date(v.original_due_date).toLocaleDateString("en-IN")}
                        </span>
                      )}
                    </td>
                    <td className="px-5 py-3">
                      <span className={`text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full ${v.is_complete ? "bg-emerald-50 text-emerald-700" : overdue ? "bg-rose-50 text-rose-700" : "bg-amber-50 text-amber-700"}`}>
                        {v.is_complete ? "Done" : overdue ? "Overdue" : "Scheduled"}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-[11px]">
                      {v.panel_before ? <a className="text-emerald-600 font-semibold hover:underline mr-2" href={fileHref(v.panel_before)!} target="_blank" rel="noreferrer">before</a> : <span className="text-slate-300 mr-2">before</span>}
                      {v.panel_after ? <a className="text-emerald-600 font-semibold hover:underline" href={fileHref(v.panel_after)!} target="_blank" rel="noreferrer">after</a> : <span className="text-slate-300">after</span>}
                    </td>
                    <td className="px-5 py-3 text-slate-600">{v.monthly_production || "—"}</td>
                    <td className="px-5 py-3 text-right whitespace-nowrap">
                      {data.can_edit && !v.is_complete && (
                        <button onClick={() => openReschedule(v)}
                          className="text-[12px] font-semibold text-slate-500 hover:text-slate-800 mr-3">
                          Reschedule
                        </button>
                      )}
                      <button onClick={() => openForm(v)} className="text-[12px] font-semibold text-indigo-600 hover:text-indigo-800">
                        {data.can_edit && !v.is_complete ? "Fill visit" : "View"}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Visit form modal */}
      {/* Reschedule — a date picker rather than a typed string. */}
      {moving && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
          onClick={() => setMoving(null)}>
          <div className="bg-white w-full max-w-md rounded-2xl shadow-2xl overflow-hidden"
            onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
              <div>
                <h2 className="text-base font-bold text-slate-900">Reschedule visit #{moving.sequence}</h2>
                <p className="text-xs text-slate-400">
                  Currently due {new Date(moving.due_date).toLocaleDateString("en-IN")}
                </p>
              </div>
              <button onClick={() => setMoving(null)}
                className="w-8 h-8 flex items-center justify-center rounded-xl bg-slate-100 text-slate-500 hover:bg-slate-200 transition text-sm">✕</button>
            </div>

            <div className="px-6 py-5 space-y-4">
              <div>
                <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">
                  New due date
                </label>
                <input type="date" value={moveDate} autoFocus
                  onChange={e => setMoveDate(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all" />
              </div>
              <div>
                <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">
                  Reason <span className="normal-case font-semibold text-slate-300">(optional)</span>
                </label>
                <input value={moveReason} placeholder="e.g. customer away, monsoon"
                  onChange={e => setMoveReason(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all" />
              </div>
              <p className="text-[11px] text-slate-400">
                The date it was originally due is kept, so the change stays visible.
              </p>
            </div>

            <div className="flex gap-3 px-6 pb-5">
              <button onClick={() => setMoving(null)}
                className="flex-1 px-4 py-2.5 text-slate-600 font-medium hover:bg-slate-50 rounded-xl transition-colors">
                Cancel
              </button>
              <button onClick={submitReschedule} disabled={moveSaving || !moveDate || moveDate === moving.due_date}
                className="flex-1 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-2.5 rounded-xl transition shadow-sm disabled:opacity-50 disabled:cursor-not-allowed">
                {moveSaving ? "Saving…" : "Reschedule"}
              </button>
            </div>
          </div>
        </div>
      )}

      {openVisit && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4" onClick={() => setOpenVisit(null)}>
          <div className="bg-white w-full max-w-2xl rounded-2xl shadow-2xl max-h-[90vh] overflow-hidden flex flex-col" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 flex-shrink-0">
              <div>
                <h2 className="text-base font-bold text-slate-900">Visit #{openVisit.sequence}</h2>
                <p className="text-xs text-slate-400">Due {new Date(openVisit.due_date).toLocaleDateString("en-IN")}{openVisit.completed_by_name ? ` · completed by ${openVisit.completed_by_name}` : ""}</p>
              </div>
              <button onClick={() => setOpenVisit(null)} className="w-8 h-8 flex items-center justify-center rounded-xl bg-slate-100 text-slate-500 hover:bg-slate-200 transition text-sm">✕</button>
            </div>
            <div className="overflow-y-auto flex-1 px-6 py-5 space-y-4">
              {/* Photos */}
              <div className="bg-slate-50/70 border border-slate-100 rounded-xl p-4">
                <p className="text-[10px] font-bold text-indigo-600 uppercase tracking-wide mb-3">Photos — panel washed before and after</p>
                <div className="grid sm:grid-cols-2 gap-3">
                  {(["before", "after"] as const).map(slot => {
                    const current = slot === "before" ? openVisit.panel_before : openVisit.panel_after;
                    const busy = uploadingSlot === slot;
                    return (
                      <div key={slot}>
                        <label className={labelCls}>Panel {slot}</label>
                        {current && <a href={fileHref(current)!} target="_blank" rel="noreferrer" className="block text-[11px] font-semibold text-emerald-600 hover:underline truncate mb-1.5">{decodeURIComponent(current.split("/").pop() || "photo")}</a>}
                        {data.can_edit && (
                          <label className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-semibold transition ${busy ? "bg-slate-100 text-slate-400 cursor-not-allowed" : "bg-slate-100 text-slate-700 hover:bg-slate-200 cursor-pointer"}`}>
                            {busy ? "Uploading…" : current ? "Replace photo" : "+ Add photo"}
                            <input type="file" accept="image/*" disabled={busy} className="hidden"
                              onChange={e => { const f = e.target.files?.[0]; e.currentTarget.value = ""; if (f) uploadPhoto(slot, f); }} />
                          </label>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>

              <div className="grid sm:grid-cols-2 gap-4">
                <div><label className={labelCls}>DC Voltage</label><input value={draft.dc_voltage} disabled={!data.can_edit} onChange={e => setDraft({ ...draft, dc_voltage: e.target.value })} className={inputCls} placeholder="e.g. 240 V" /></div>
                <div><label className={labelCls}>Error Codes (if any)</label><input value={draft.error_codes} disabled={!data.can_edit} onChange={e => setDraft({ ...draft, error_codes: e.target.value })} className={inputCls} placeholder="Error codes" /></div>
                <div className="sm:col-span-2"><label className={labelCls}>Structure Damage, Deformity or Rust</label><input value={draft.structure_damage} disabled={!data.can_edit} onChange={e => setDraft({ ...draft, structure_damage: e.target.value })} className={inputCls} placeholder="Observations" /></div>
                <div><label className={labelCls}>Monthly Production</label><input value={draft.monthly_production} disabled={!data.can_edit} onChange={e => setDraft({ ...draft, monthly_production: e.target.value })} className={inputCls} placeholder="e.g. 550 kWh" /></div>
                <div className="flex items-end pb-1">
                  <label className={`inline-flex items-center gap-2 text-sm font-medium ${!data.can_edit ? "text-slate-400" : "text-slate-700 cursor-pointer"}`}>
                    <input type="checkbox" checked={!!draft.inverter_cleaned} disabled={!data.can_edit}
                      onChange={e => setDraft({ ...draft, inverter_cleaned: e.target.checked })}
                      className="w-4 h-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500/30" />
                    Inverter cleaned
                  </label>
                </div>
              </div>

              <div className="bg-slate-50/70 border border-slate-100 rounded-xl p-4">
                <p className="text-[10px] font-bold text-indigo-600 uppercase tracking-wide mb-3">AC Voltage</p>
                <div className="grid sm:grid-cols-3 gap-3">
                  <div><label className={labelCls}>N-E Voltage</label><input value={draft.ac_ne_voltage} disabled={!data.can_edit} onChange={e => setDraft({ ...draft, ac_ne_voltage: e.target.value })} className={inputCls} placeholder="N-E" /></div>
                  <div><label className={labelCls}>P-N</label><input value={draft.ac_pn_voltage} disabled={!data.can_edit} onChange={e => setDraft({ ...draft, ac_pn_voltage: e.target.value })} className={inputCls} placeholder="P-N" /></div>
                  <div><label className={labelCls}>P-E</label><input value={draft.ac_pe_voltage} disabled={!data.can_edit} onChange={e => setDraft({ ...draft, ac_pe_voltage: e.target.value })} className={inputCls} placeholder="P-E" /></div>
                </div>
              </div>

              {data.can_edit && (
                <label className="inline-flex items-center gap-2 text-sm font-medium text-slate-700 cursor-pointer">
                  <input type="checkbox" checked={!!draft.is_complete}
                    onChange={e => setDraft({ ...draft, is_complete: e.target.checked })}
                    className="w-4 h-4 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500/30" />
                  Visit completed
                </label>
              )}
            </div>
            <div className="px-6 py-4 border-t border-slate-100 flex justify-end gap-3 flex-shrink-0">
              <button onClick={() => setOpenVisit(null)} className="px-4 py-2.5 border border-slate-200 rounded-xl text-sm font-semibold text-slate-600 hover:bg-slate-50 transition">Close</button>
              {data.can_edit && (
                <button onClick={saveVisit} disabled={saving || uploadingSlot !== null}
                  className="px-5 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 disabled:opacity-50 transition">
                  {saving ? "Saving…" : "Save Visit"}
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

"use client";
import { getApiBase } from "@/lib/mock-data";
import { APP_SLUG } from "@/lib/config";

import React, { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { DetailSkeleton } from "@/components/Skeleton";

type VisitDoc = { id: number; doc_type: string; file: string; uploaded_at: string };

/** Picture-only slots: the wash and what the plant made either side of it —
 *  there is no number to type for these, only the photograph. */
const PICTURE_SLOTS = [
  ["panel_before", "Panel Before"],
  ["panel_after", "Panel After"],
  ["production_before", "Production Before Service"],
  ["production_after", "Production After Service"],
] as const;

/** Readings: a typed value and its photos. Matches MaintenanceVisit.READING_SLOTS. */
const READING_SLOTS = [
  ["dc_voltage", "dc_voltage", "DC Voltage", "e.g. 240 V"],
  ["dc_floating_voltage", "dc_floating_voltage", "DC Floating Voltages", "e.g. 12 V"],
  ["error_codes", "error_codes", "Error Codes (if any)", "Error codes"],
  ["structure_damage", "structure_damage", "Structure Damage, Deformity or Rust", "Observations"],
  ["monthly_production", "monthly_production", "Monthly Production", "e.g. 550 kWh"],
  ["ac_ne_voltage", "ac_ne", "N-E Voltage", "N-E"],
  ["ac_pn_voltage", "ac_pn", "P-N", "P-N"],
  ["ac_pe_voltage", "ac_pe", "P-E", "P-E"],
] as const;

type Visit = {
  id: number; sequence: number; due_date: string;
  // Set once a visit has been moved, so the slip stays visible.
  original_due_date: string | null; reschedule_reason: string; is_rescheduled: boolean;
  dc_voltage: string; structure_damage: string; inverter_cleaned: boolean;
  ac_ne_voltage: string; ac_pn_voltage: string; ac_pe_voltage: string;
  monthly_production: string; error_codes: string;
  dc_floating_voltage: string;
  // Photos hang off the visit, several per slot.
  documents: VisitDoc[];
  is_complete: boolean; completed_at: string | null; completed_by_name: string | null;
};
type Detail = {
  id: number;
  first_name: string; last_name: string | null;
  phone: string | null; email: string | null;
  location: string | null; installation_location: string | null;
  product_name: string | null; bde_name: string | null;
  plan: { start_date: string; visits: Visit[] } | null;
  // The schedule runs from the warranty certificate for a customer the CRM
  // installed, from the project's completion for a past customer.
  starts_from: "warranty" | "completion";
  warranty_date: string | null;
  can_edit: boolean;
};

const inputCls = "w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all disabled:opacity-70";
const labelCls = "block text-[10px] font-bold text-slate-400 uppercase tracking-wide mb-1.5";

/**
 * A slot's files: green links with a ✕, then "+ Add file(s)".
 *
 * Module scope, not inside the page — a component declared during render is a
 * new type every time state changes, which tears the subtree down and rebuilds
 * it on each keystroke.
 */
function PhotoSlot({ slot, docs, canEdit, busy, fileHref, onAdd, onDelete }: {
  slot: string; docs: VisitDoc[]; canEdit: boolean; busy: boolean;
  fileHref: (u: string | null) => string | null;
  onAdd: (files: File[]) => void;
  onDelete: (doc: VisitDoc) => void;
}) {
  const mine = docs.filter(d => d.doc_type === slot);
  return (
    <>
      {mine.length > 0 && (
        <ul className="mb-1.5 space-y-1">
          {mine.map(d => {
            const name = decodeURIComponent(d.file.split("/").pop() || "photo");
            return (
              <li key={d.id} className="flex items-center gap-2 text-[11px]">
                <a href={fileHref(d.file)!} target="_blank" rel="noreferrer" title={name}
                  className="font-semibold text-emerald-600 hover:underline truncate max-w-[150px]">{name}</a>
                {canEdit && (
                  <button type="button" onClick={() => onDelete(d)} title="Delete file"
                    className="font-bold text-rose-500 hover:text-rose-700">✕</button>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {canEdit && (
        <label className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-semibold transition ${busy ? "bg-slate-100 text-slate-400 cursor-not-allowed" : "bg-slate-100 text-slate-700 hover:bg-slate-200 cursor-pointer"}`}>
          {busy ? "Uploading…" : "+ Add file(s)"}
          <input type="file" accept="image/*" multiple capture="environment" disabled={busy} className="hidden"
            onChange={e => { const fs = Array.from(e.target.files || []); e.currentTarget.value = ""; onAdd(fs); }} />
        </label>
      )}
    </>
  );
}

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
  // Correcting the customer, and taking them off the schedule. Both live here
  // because this is the only page that knows the schedule exists.
  const [editing, setEditing] = useState(false);
  const [editForm, setEditForm] = useState({ name: "", phone: "", location: "", completed_on: "" });
  const [editSaving, setEditSaving] = useState(false);
  const [removing, setRemoving] = useState(false);

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

  const customerUrl = `${apiBase}/api/leads/${id}/maintenance-customer/`;
  const authJson = () => ({ "Content-Type": "application/json", ...authHeader() });

  const openEdit = () => {
    if (!data) return;
    setEditForm({
      name: `${data.first_name} ${data.last_name || ""}`.trim(),
      phone: data.phone || "",
      location: data.location || "",
      completed_on: data.plan?.start_date || "",
    });
    setEditing(true);
  };

  /** Moving the completed date re-dates the visits still to come; the ones
   *  already done keep their dates, because they happened. */
  const saveCustomer = async () => {
    setEditSaving(true);
    try {
      const r = await fetch(customerUrl, {
        method: "PATCH", headers: authJson(), body: JSON.stringify(editForm),
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) { alert(d.error || "Could not save the customer."); return; }
      setEditing(false);
      setData(d);
      if (d.visits_moved) alert(`Saved — ${d.visits_moved} upcoming visit(s) re-dated.`);
    } catch { alert("Network error. Please try again."); }
    finally { setEditSaving(false); }
  };

  /** Removes the schedule, not the customer: they can be scheduled again. What
   *  goes is the visits, and any readings and photos recorded against them. */
  const removeSchedule = async () => {
    const visits = data?.plan?.visits || [];
    const done = visits.filter((v: Visit) => v.is_complete).length;
    const warn = done
      ? `

${done} of them are already filled in — those readings and photos go with them.`
      : "";
    if (!confirm(
      `Take ${data?.first_name || "this customer"} off the maintenance schedule?`
      + `

All ${visits.length} visits will be deleted.${warn}`
      + `

The customer stays on the books and can be scheduled again.`
    )) return;
    setRemoving(true);
    try {
      const r = await fetch(customerUrl, { method: "DELETE", headers: authHeader() });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        alert(d.error || "Could not remove the schedule.");
        return;
      }
      router.push("/periodic-maintenance");
    } catch { alert("Network error. Please try again."); }
    finally { setRemoving(false); }
  };

  const openForm = (v: Visit) => {
    setDraft({
      dc_voltage: v.dc_voltage || "", dc_floating_voltage: v.dc_floating_voltage || "",
      structure_damage: v.structure_damage || "",
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

  /** The visit already exists, so photos go up as they are picked. */
  const uploadPhotos = async (slot: string, files: File[]) => {
    if (!openVisit || !files.length) return;
    setUploadingSlot(slot);
    try {
      const added: VisitDoc[] = [];
      for (const file of files) {
        const fd = new FormData();
        fd.append("doc_type", slot);
        fd.append("file", file);
        const r = await fetch(
          `${apiBase}/api/leads/${id}/maintenance-visits/${openVisit.id}/documents/`,
          { method: "POST", headers: authHeader(), body: fd });
        if (!r.ok) {
          const e = await r.json().catch(() => ({}));
          alert(e.error || `Could not upload ${file.name}.`);
          break;
        }
        added.push(await r.json());
      }
      if (added.length) {
        setOpenVisit(v => (v ? { ...v, documents: [...(v.documents || []), ...added] } : v));
        await load();
      }
    } catch { alert("Network error while uploading."); }
    finally { setUploadingSlot(null); }
  };

  const deletePhoto = async (doc: VisitDoc) => {
    if (!openVisit || !window.confirm("Remove this photo?")) return;
    try {
      const r = await fetch(
        `${apiBase}/api/leads/${id}/maintenance-visits/${openVisit.id}/documents/${doc.id}/`,
        { method: "DELETE", headers: authHeader() });
      if (r.ok || r.status === 204) {
        setOpenVisit(v => (v ? { ...v, documents: (v.documents || []).filter(d => d.id !== doc.id) } : v));
        await load();
      } else alert("Could not remove the photo.");
    } catch { alert("Network error."); }
  };


  if (loading) return <DetailSkeleton />;
  if (error || !data) return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-[900px]">
      <Link href="/periodic-maintenance" className="text-sm text-indigo-600 hover:underline">← Back to Periodic Maintenance</Link>
      <p className="mt-6 text-sm text-rose-600">{error || "Not found."}</p>
    </div>
  );

  const visits = data.plan?.visits || [];
  const done = visits.filter(v => v.is_complete).length;
  const todayStr = new Date().toISOString().slice(0, 10);
  const fileHref = (f: string | null) => (f ? (f.startsWith("http") ? f : `${apiBase}${f}`) : null);

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-[1100px]">
      {editing && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm px-4">
          <div className="bg-white w-full max-w-md rounded-2xl shadow-2xl max-h-[calc(100dvh-2rem)] overflow-y-auto overscroll-contain">
            <div className="px-6 py-4 border-b border-slate-100">
              <h2 className="text-[15px] font-bold text-slate-900">Edit customer</h2>
              <p className="text-xs text-slate-400 mt-0.5">
                {data.starts_from === "warranty"
                  ? "Their details, and the date the schedule is counted from."
                  : "Their details, and the date the project completed — the schedule is counted from it."}
              </p>
            </div>
            <div className="p-6 space-y-4">
              <div>
                <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">Customer name *</label>
                <input value={editForm.name} autoFocus
                  onChange={e => setEditForm({ ...editForm, name: e.target.value })}
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all" />
              </div>
              <div>
                <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">Phone number *</label>
                <input value={editForm.phone}
                  onChange={e => setEditForm({ ...editForm, phone: e.target.value })}
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all" />
              </div>
              <div>
                <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">Location</label>
                <input value={editForm.location}
                  onChange={e => setEditForm({ ...editForm, location: e.target.value })}
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all" />
              </div>
              <div>
                <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">
                  {data.starts_from === "warranty" ? "Schedule start date" : "Project completed date"}
                </label>
                <input type="date" value={editForm.completed_on} max={todayStr}
                  onChange={e => setEditForm({ ...editForm, completed_on: e.target.value })}
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all" />
                <p className="mt-1 text-[11px] text-slate-400">
                  {data.starts_from === "warranty" && (data.warranty_date
                    ? `The warranty date is ${new Date(data.warranty_date).toLocaleDateString("en-IN")}; change this only to correct it. `
                    : "Normally the warranty date: the day the certificate was generated. ")}
                  Changing this re-dates the visits still to come. Visits already filled in keep
                  their dates and their readings.
                </p>
              </div>
            </div>
            <div className="px-6 py-4 border-t border-slate-100 flex gap-3">
              <button onClick={() => setEditing(false)}
                className="flex-1 py-2.5 border border-slate-200 rounded-xl text-sm font-semibold text-slate-600 hover:bg-slate-50 transition-all">Cancel</button>
              <button onClick={saveCustomer}
                disabled={editSaving || !editForm.name.trim() || !editForm.phone.trim()}
                className="flex-1 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 disabled:opacity-50 transition-all">
                {editSaving ? "Saving…" : "Save"}
              </button>
            </div>
          </div>
        </div>
      )}

      <Link href="/periodic-maintenance" className="text-sm text-indigo-600 hover:underline">← Back to Periodic Maintenance</Link>

      <div className="mt-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">{data.first_name} {data.last_name}</h1>
          <p className="text-sm text-slate-500 mt-0.5">{data.phone || "—"}{data.email ? ` · ${data.email}` : ""}{data.location ? ` · ${data.location}` : ""}</p>
        </div>
        <div className="flex items-center gap-4">
          <div className="text-right">
            <p className="text-[10px] text-slate-400 uppercase tracking-wide">Progress</p>
            <p className={`text-sm font-bold ${done === visits.length ? "text-emerald-600" : "text-slate-700"}`}>{done}/{visits.length} visits done</p>
          </div>
          <div className="flex items-center gap-2">
            <button type="button" onClick={openEdit}
              className="px-3.5 py-2 bg-white border border-slate-200 rounded-xl text-xs font-semibold text-slate-600 hover:bg-slate-50 transition-all">
              Edit customer
            </button>
            <button type="button" onClick={removeSchedule} disabled={removing}
              className="px-3.5 py-2 bg-white border border-rose-200 rounded-xl text-xs font-semibold text-rose-600 hover:bg-rose-50 transition-all disabled:opacity-50">
              {removing ? "Removing…" : "Delete service"}
            </button>
          </div>
        </div>
      </div>

      {data.plan && (
        <p className="mt-2 text-xs text-slate-400">
          Schedule started {new Date(data.plan.start_date).toLocaleDateString("en-IN")}
          {data.warranty_date === data.plan.start_date && ", the warranty date"}
          {" "}— one visit every 6 months for 5 years.
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
                    <td className="px-5 py-3 text-[11px] whitespace-nowrap">
                      {/* The wash and production pictures; a slot can hold several. */}
                      {PICTURE_SLOTS.map(([slot, label], n) => {
                        const shots = (v.documents || []).filter(d => d.doc_type === slot);
                        const short = label.replace("Panel ", "").replace(" Service", "").toLowerCase();
                        return (
                          <span key={slot} className={n > 0 ? "ml-2" : ""}>
                            {shots.length ? (
                              <a className="text-emerald-600 font-semibold hover:underline"
                                href={fileHref(shots[0].file)!} target="_blank" rel="noreferrer"
                                title={`${shots.length} photo(s)`}>
                                {short}{shots.length > 1 ? ` (${shots.length})` : ""}
                              </a>
                            ) : <span className="text-slate-300">{short}</span>}
                          </span>
                        );
                      })}
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
          <div className="bg-white w-full max-w-md rounded-2xl shadow-2xl max-h-[calc(100dvh-2rem)] overflow-y-auto overscroll-contain"
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
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
          <div className="bg-white w-full max-w-2xl rounded-2xl shadow-2xl max-h-[90vh] overflow-hidden flex flex-col" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 flex-shrink-0">
              <div>
                <h2 className="text-base font-bold text-slate-900">Visit #{openVisit.sequence}</h2>
                <p className="text-xs text-slate-400">Due {new Date(openVisit.due_date).toLocaleDateString("en-IN")}{openVisit.completed_by_name ? ` · completed by ${openVisit.completed_by_name}` : ""}</p>
              </div>
              <button onClick={() => setOpenVisit(null)} className="w-8 h-8 flex items-center justify-center rounded-xl bg-slate-100 text-slate-500 hover:bg-slate-200 transition text-sm">✕</button>
            </div>
            <div className="overflow-y-auto flex-1 px-6 py-5 space-y-4">
              {/* Pictures — the wash, and what the plant made either side of it.
                  Nothing to type for these, only the photograph. */}
              <div className="bg-slate-50/70 border border-slate-100 rounded-xl p-4">
                <p className="text-[10px] font-bold text-indigo-600 uppercase tracking-wide mb-3">Photos</p>
                <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
                  {PICTURE_SLOTS.map(([slot, label]) => (
                    <div key={slot}>
                      <label className={labelCls}>{label}</label>
                      <PhotoSlot slot={slot} docs={openVisit.documents || []} canEdit={!!data.can_edit}
                        busy={uploadingSlot === slot} fileHref={fileHref}
                        onAdd={(fs: File[]) => uploadPhotos(slot, fs)} onDelete={deletePhoto} />
                    </div>
                  ))}
                </div>
              </div>

              {/* Readings — a typed value and its photos. */}
              <div className="grid sm:grid-cols-2 gap-4">
                {READING_SLOTS.map(([field, slot, label, ph]) => (
                  <div key={slot} className={field === "structure_damage" ? "sm:col-span-2" : ""}>
                    <label className={labelCls}>{label}</label>
                    <input value={(draft as any)[field] || ""} disabled={!data.can_edit}
                      onChange={e => setDraft({ ...draft, [field]: e.target.value })}
                      className={inputCls} placeholder={ph} />
                    <div className="mt-1.5"><PhotoSlot slot={slot} docs={openVisit.documents || []} canEdit={!!data.can_edit}
                        busy={uploadingSlot === slot} fileHref={fileHref}
                        onAdd={(fs: File[]) => uploadPhotos(slot, fs)} onDelete={deletePhoto} /></div>
                  </div>
                ))}
                {/* Ticked and photographed — the box is the claim, the photo the evidence. */}
                <div>
                  <label className={`inline-flex items-center gap-2 text-sm font-medium ${!data.can_edit ? "text-slate-400" : "text-slate-700 cursor-pointer"}`}>
                    <input type="checkbox" checked={!!draft.inverter_cleaned} disabled={!data.can_edit}
                      onChange={e => setDraft({ ...draft, inverter_cleaned: e.target.checked })}
                      className="w-4 h-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500/30" />
                    Inverter cleaned
                  </label>
                  <div className="mt-1.5"><PhotoSlot slot="inverter_cleaned" docs={openVisit.documents || []} canEdit={!!data.can_edit}
                      busy={uploadingSlot === "inverter_cleaned"} fileHref={fileHref}
                      onAdd={(fs: File[]) => uploadPhotos("inverter_cleaned", fs)} onDelete={deletePhoto} /></div>
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

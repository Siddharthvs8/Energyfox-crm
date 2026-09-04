"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import DeletedLeadCleanup, { DeletedLeadBadge } from "@/components/DeletedLeadCleanup";
import { isSpectator } from "@/lib/spectator";
import BdeTag from "@/components/BdeTag";
const PLANT_PHOTO = "plant_commissioned";
const RF_IMAGE = "rf_image";
// Both are evidence the sign-off rests on, so both are required before it —
// mirrors LiasoningService.PHOTO_SLOTS on the server, which enforces it.
const PHOTO_SLOTS: [string, string][] = [
  [PLANT_PHOTO, "Plant Photo"],
  [RF_IMAGE, "RF Image"],
];

type LiasoningRecord = {
  // Liasoning waits on both photos before it can be signed off.
  has_plant_photo?: boolean;
  has_rf_image?: boolean;
  photos_complete?: boolean;
  documents?: { id: number; doc_type: string; file: string }[];
  annexure3_completed: boolean; annexure3_remark: string;
  discom_approval: string;
  is_complete: boolean;
};
type LiasoningLead = {
  /** Who did the site visit — shown as a tag on the row. */
  bde_name?: string | null;
  // Set when the lead behind this row has been deleted; the row is then
  // unopenable, and an admin gets a control to clear it out.
  lead_deleted?: boolean;
  can_cleanup?: boolean;
  id: number;
  first_name: string;
  last_name: string | null;
  phone: string | null;
  location: string | null;
  product_name: string | null;
  value: number;
  is_complete: boolean;
  can_edit: boolean;
  /** Super admin only — the server decides it and the row offers Unlock. */
  can_reopen?: boolean;
  pushed_at: string | null;
  record: LiasoningRecord | null;
};

const DISCOM_OPTIONS = [
  { value: "pending", label: "Pending" },
  { value: "yes", label: "Approved" },
  { value: "no", label: "Not Approved" },
];

type RowDraft = {
  annexure3_completed: boolean; annexure3_remark: string;
};

const inputCls = "w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all disabled:opacity-70";

export default function LiasoningPage() {
  const domain = APP_SLUG;
  const router = useRouter();
  const [authChecked, setAuthChecked] = useState(false);
  const [allowed, setAllowed] = useState(false);
  const [leads, setLeads] = useState<LiasoningLead[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [rows, setRows] = useState<Record<number, RowDraft>>({});
  const [savingId, setSavingId] = useState<number | null>(null);
  // "<leadId>:<slot>" while that one slot is uploading.
  const [photoId, setPhotoId] = useState<string | null>(null);

  const token = () => localStorage.getItem(`${domain}_access`);

  useEffect(() => {
    const t = token();
    if (!t) { router.push("/login"); return; }
    fetch(`${getApiBase(domain)}/api/users/me/`, { headers: { Authorization: `Bearer ${t}` } })
      .then(r => r.json())
      .then(d => {
        const ok = isSpectator(d) || d.role === "liasoning_officer" || d.is_staff || d.is_general_manager;
        setAllowed(ok);
        setAuthChecked(true);
        if (!ok) router.replace("/");
      })
      .catch(() => setAuthChecked(true));
  }, [domain, router]);

  const seed = (list: LiasoningLead[]) => {
    const drafts: Record<number, RowDraft> = {};
    for (const l of list) {
      drafts[l.id] = {
        annexure3_completed: !!l.record?.annexure3_completed,
        annexure3_remark: l.record?.annexure3_remark || "",
      };
    }
    setRows(drafts);
  };

  useEffect(() => {
    if (!allowed) return;
    fetch(`${getApiBase(domain)}/api/leads/liasoning/`, { headers: { Authorization: `Bearer ${token()}` } })
      .then(r => (r.ok ? r.json() : []))
      .then(d => { const list = Array.isArray(d) ? d : []; setLeads(list); seed(list); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [allowed, domain]); // eslint-disable-line react-hooks/exhaustive-deps

  const setRow = (id: number, patch: Partial<RowDraft>) =>
    setRows(p => ({ ...p, [id]: { ...p[id], ...patch } }));

  /** Upload one of the two photos from the row, so the officer does not have to
   *  open the customer to attach it.
   *
   *  The same call replaces: a slot holds one picture, and the server drops the
   *  slot's previous file when a new one arrives. So "Replace" is this with a
   *  slot that already has something in it, not a separate operation. */
  const uploadPhoto = async (lead: LiasoningLead, slot: string, file: File | null) => {
    if (!file) return;
    setPhotoId(`${lead.id}:${slot}`);
    try {
      const body = new FormData();
      body.append("file", file);
      body.append("doc_type", slot);
      const r = await fetch(`${getApiBase(domain)}/api/leads/${lead.id}/liasoning/documents/`, {
        method: "POST", headers: { Authorization: `Bearer ${token()}` }, body,
      });
      if (!r.ok) { const e = await r.json().catch(() => ({})); alert(e.error || "Could not upload the photo."); return; }
      const doc = await r.json();
      setLeads(prev => prev.map(x => {
        if (x.id !== lead.id) return x;
        // Mirror the server: this slot now holds exactly the new file.
        const kept = (x.record?.documents || []).filter(d => d.doc_type !== slot);
        const documents = [...kept, doc];
        const has = (t: string) => documents.some(d => d.doc_type === t);
        return {
          ...x,
          record: {
            ...(x.record || {} as LiasoningRecord),
            documents,
            has_plant_photo: has(PLANT_PHOTO),
            has_rf_image: has(RF_IMAGE),
            photos_complete: has(PLANT_PHOTO) && has(RF_IMAGE),
          },
        };
      }));
    } catch { alert("Network error while uploading."); }
    finally { setPhotoId(null); }
  };

  /** Super admin unlocks a signed-off row so it can be edited again. */
  const unlock = async (lead: LiasoningLead) => {
    if (!window.confirm(`Unlock ${lead.first_name} ${lead.last_name || ""} for editing?`)) return;
    setSavingId(lead.id);
    try {
      const r = await fetch(`${getApiBase(domain)}/api/leads/${lead.id}/reopen-liasoning/`, {
        method: "POST", headers: { Authorization: `Bearer ${token()}` },
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) { alert(d.error || "Could not unlock this record."); return; }
      setLeads(prev => prev.map(x => (x.id === lead.id ? d : x)));
    } catch { alert("Network error while unlocking."); }
    finally { setSavingId(null); }
  };

  const saveRow = async (lead: LiasoningLead) => {
    const draft = rows[lead.id];
    if (!draft) return;
    const body = {
      annexure3_completed: draft.annexure3_completed,
      annexure3_remark: draft.annexure3_remark,
    };
    setSavingId(lead.id);
    try {
      const r = await fetch(`${getApiBase(domain)}/api/leads/${lead.id}/liasoning-record/`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token()}` },
        body: JSON.stringify(body),
      });
      if (r.ok) {
        const d = await r.json();
        // Keep the saved record on the lead so the Annexure 3 gate reflects saved state.
        setLeads(prev => prev.map(x => (x.id === lead.id ? { ...x, record: { ...(x.record || {}), ...d } } : x)));
        // Ticking Completed is the sign-off, and the sign-off is what locks the
        // row. Done after the save so the remark is stored before the record
        // closes to editing. The server re-checks the photos.
        //
        // Guarded on the photos here as well, so that Save on a row ticked
        // before this rule existed still saves rather than failing on a
        // sign-off it was never going to be allowed.
        const docs = lead.record?.documents || [];
        const photosIn = lead.record?.photos_complete
          ?? (docs.some(x => x.doc_type === PLANT_PHOTO) && docs.some(x => x.doc_type === RF_IMAGE));
        if (draft.annexure3_completed && photosIn && !lead.record?.is_complete) {
          const c = await fetch(`${getApiBase(domain)}/api/leads/${lead.id}/complete-liasoning/`, {
            method: "POST", headers: { Authorization: `Bearer ${token()}` },
          });
          const cd = await c.json().catch(() => ({}));
          if (!c.ok) { alert(cd.error || "Saved, but could not complete this record."); return; }
          setLeads(prev => prev.map(x => (x.id === lead.id ? cd : x)));
        }
      } else { const e = await r.json().catch(() => ({})); alert(e.error || "Failed to save."); }
    } catch { alert("Network error while saving."); }
    finally { setSavingId(null); }
  };

  if (!authChecked) return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="w-8 h-8 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
    </div>
  );
  if (!allowed) return null;

  const stageLeads = leads.filter(l => {
    const q = search.trim().toLowerCase();
    if (!q) return true;
    return (`${l.first_name} ${l.last_name || ""}`.toLowerCase().includes(q)
      || (l.phone || "").toLowerCase().includes(q)
      || (l.location || "").toLowerCase().includes(q));
  });

  return (
    <div className="p-6 lg:p-8 max-w-[1200px]">
      <div className="mb-5">
        <h1 className="text-2xl font-bold text-slate-900">Liasoning</h1>
        <p className="text-sm text-slate-500 mt-1">Annexure 3 — completion doc submission for each customer in liasoning.</p>
      </div>

      <>
          <p className="mb-4 text-[11px] text-slate-400">Annexure 3 status syncs directly to the customer&apos;s MNRE Stage 2. Discom approval is recorded in Documentation Stage 2 and shown here.</p>

          <div className="mb-4 flex items-center gap-3">
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search by name, phone or location…"
              className="w-full max-w-md bg-white border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all"
            />
            <span className="text-xs font-semibold text-slate-400">{stageLeads.length} customer{stageLeads.length === 1 ? "" : "s"}</span>
          </div>

          {loading ? (
            <div className="py-16 text-center text-sm text-slate-400">Loading…</div>
          ) : stageLeads.length === 0 ? (
            <div className="bg-white border border-dashed border-slate-200 rounded-2xl p-12 text-center text-sm text-slate-400">
              No customers in liasoning yet.
            </div>
          ) : (
            <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm min-w-[1080px]">
                  <thead>
                    <tr className="text-left text-[10px] font-bold text-slate-400 uppercase tracking-wide border-b border-slate-100 bg-slate-50/60">
                      <th className="px-5 py-3">Customer</th>
                      <th className="px-5 py-3">Completed</th>
                      <th className="px-5 py-3">Remarks</th>
                      <th className="px-5 py-3">Discom Approval</th>
                      {PHOTO_SLOTS.map(([slot, label]) => (
                        <th key={slot} className="px-5 py-3">{label}</th>
                      ))}
                      <th className="px-5 py-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stageLeads.map(l => {
                      const d = rows[l.id];
                      if (!d) return null;
                      const locked = !l.can_edit || !!l.record?.is_complete;
                      const docs = l.record?.documents || [];
                      const hasSlot = (t: string) => docs.some(x => x.doc_type === t);
                      const photosIn = l.record?.photos_complete
                        ?? (hasSlot(PLANT_PHOTO) && hasSlot(RF_IMAGE));
                      const completed = d.annexure3_completed;
                      const remark = d.annexure3_remark;
                      return (
                        <tr key={l.id} className="border-b border-slate-50 hover:bg-slate-50/60 align-middle">
                          <td className="px-5 py-3">
                            <div className="flex items-center gap-2 flex-wrap">
                              <Link href={`/liasoning/${l.id}`} className="font-semibold text-slate-800 hover:text-indigo-600 transition">
                                {l.first_name} {l.last_name}
                              </Link>
                              <BdeTag name={l.bde_name} />
                              {l.lead_deleted && <DeletedLeadBadge />}
                              {l.can_cleanup && (
                                <DeletedLeadCleanup leadId={l.id} module="liasoning"
                                  name={`${l.first_name} ${l.last_name || ""}`.trim()}
                                  onRemoved={() => setLeads(prev => prev.filter(x => x.id !== l.id))} />
                              )}
                            </div>
                            <p className="text-[11px] text-slate-400">{l.phone || "—"}{l.location ? ` · ${l.location}` : ""}</p>
                          </td>
                          <td className="px-5 py-3">
                            {/* Ticking this signs the record off, and the sign-off
                                says the plant is live with the evidence on file —
                                so it stays out of reach until both photos are in. */}
                            <label className={`inline-flex items-center gap-2 ${
                              locked || photosIn || completed ? "cursor-pointer" : "cursor-not-allowed"}`}
                              title={!locked && !photosIn && !completed
                                ? "Upload the plant photo and the RF image first"
                                : undefined}>
                              <input type="checkbox" checked={completed}
                                disabled={locked || (!photosIn && !completed)}
                                onChange={e => setRow(l.id, { annexure3_completed: e.target.checked })}
                                className="w-4 h-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500/30 disabled:opacity-40" />
                              <span className={`text-xs font-semibold ${completed ? "text-emerald-600" : "text-slate-400"}`}>
                                {completed ? "Completed" : "Not completed"}
                              </span>
                            </label>
                            {/* Only where it is still the thing standing in the
                                way. A row ticked before this rule existed keeps
                                its tick and can still be unticked. */}
                            {!locked && !photosIn && !completed && (
                              <p className="text-[10px] text-amber-600 mt-1">Both photos required</p>
                            )}
                          </td>
                          <td className="px-5 py-3 min-w-[220px]">
                            <input value={remark} disabled={locked} placeholder="Remarks"
                              onChange={e => setRow(l.id, { annexure3_remark: e.target.value })}
                              className={inputCls} />
                          </td>
                          <td className="px-5 py-3 min-w-[150px]">
                            {/* Owned by Documentation Stage 2 — shown here so the
                                officer knows where each approval stands. */}
                            {(() => {
                              const v = l.record?.discom_approval || "pending";
                              const opt = DISCOM_OPTIONS.find(o => o.value === v) || DISCOM_OPTIONS[0];
                              const tone = v === "yes" ? "bg-emerald-50 border-emerald-200 text-emerald-700"
                                : v === "no" ? "bg-rose-50 border-rose-200 text-rose-600"
                                : "bg-amber-50 border-amber-200 text-amber-700";
                              return (
                                <span className={`inline-flex items-center gap-1.5 px-3 py-1.5 border rounded-lg text-xs font-semibold ${tone}`}>
                                  {v === "yes" ? "✓ " : ""}{opt.label}
                                </span>
                              );
                            })()}
                          </td>
                          {/* Both required before the record can be signed off.
                              Uploaded, each offers Open and Replace; the replace
                              is the same upload, which supersedes the slot. */}
                          {PHOTO_SLOTS.map(([slot, label]) => {
                            const busy = photoId === `${l.id}:${slot}`;
                            const doc = docs.find(x => x.doc_type === slot);
                            return (
                              <td key={slot} className="px-5 py-3 min-w-[150px]">
                                {doc ? (
                                  <div className="flex items-center gap-2">
                                    <a href={doc.file} target="_blank" rel="noreferrer"
                                      title={`Open the ${label.toLowerCase()}`}
                                      className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-600 hover:text-emerald-800">
                                      ✓ Open
                                    </a>
                                    {!locked && (
                                      <label className="text-xs font-semibold text-slate-400 hover:text-indigo-600 cursor-pointer transition"
                                        title={`Replace the ${label.toLowerCase()}`}>
                                        {busy ? "Replacing…" : "Replace"}
                                        <input type="file" accept="image/*" className="hidden" disabled={busy}
                                          onChange={e => { const f = e.target.files?.[0] ?? null; e.currentTarget.value = ""; uploadPhoto(l, slot, f); }} />
                                      </label>
                                    )}
                                  </div>
                                ) : locked ? (
                                  <span className="text-xs text-slate-400">—</span>
                                ) : (
                                  <label className="inline-flex items-center gap-2 cursor-pointer text-xs font-semibold text-amber-600 hover:text-amber-800">
                                    {busy ? "Uploading…" : "+ Upload"}
                                    <input type="file" accept="image/*" className="hidden" disabled={busy}
                                      onChange={e => { const f = e.target.files?.[0] ?? null; e.currentTarget.value = ""; uploadPhoto(l, slot, f); }} />
                                  </label>
                                )}
                              </td>
                            );
                          })}
                          <td className="px-5 py-3 text-right">
                            {locked ? (
                              <div className="inline-flex items-center gap-3">
                                <span className="text-[11px] text-slate-400">
                                  {l.record?.is_complete ? "Locked" : "Read-only"}
                                </span>
                                {l.record?.is_complete && l.can_reopen && (
                                  <button onClick={() => unlock(l)} disabled={savingId === l.id}
                                    title="Unlock this record so it can be edited again"
                                    className="px-3 py-1.5 bg-white border border-slate-200 text-slate-600 rounded-lg text-[11px] font-semibold hover:bg-slate-50 hover:text-indigo-600 disabled:opacity-50 transition">
                                    {savingId === l.id ? "Unlocking…" : "Unlock"}
                                  </button>
                                )}
                              </div>
                            ) : (
                              <button onClick={() => saveRow(l)} disabled={savingId === l.id}
                                className="px-4 py-2 bg-indigo-600 text-white rounded-xl text-xs font-semibold hover:bg-indigo-700 disabled:opacity-50 transition">
                                {savingId === l.id ? "Saving…" : "Save"}
                              </button>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
      </>
    </div>
  );
}

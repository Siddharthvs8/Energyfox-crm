"use client";
/**
 * Quotations — what the customer is offered, before any invoice is raised.
 *
 * Built from a project: the specification and the package price come across,
 * and from there it is negotiated. Items are edited, a discount is given, extra
 * costs are added — and every one of those adjustments carries a remark,
 * because "why is this ₹12,000 more than the list price" gets asked months
 * later by someone who was not in the room.
 *
 * Accepted, it converts to a proforma invoice for the figure that was agreed.
 */
import React, { useCallback, useEffect, useState } from "react";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";
import { fetchProposal, proposalFileName, saveBlob } from "@/lib/quotationProposal";
import QuotationFormModal, { VARIANTS, money, type Quotation }
  from "@/components/QuotationFormModal";
import QuotationPreviewModal from "@/components/QuotationPreviewModal";

const STATUS_STYLE: Record<string, string> = {
  draft: "bg-slate-100 text-slate-600",
  sent: "bg-blue-50 text-blue-700",
  accepted: "bg-emerald-50 text-emerald-700",
  declined: "bg-rose-50 text-rose-700",
  converted: "bg-indigo-50 text-indigo-700",
};

/* 'converted' on the offer side means a proforma invoice was raised from it —
   not that it became an order. Both used to print CONVERTED, which left a BDE
   unable to tell an invoiced offer from a paid order on the same list. */
const STATUS_LABEL: Record<string, string> = { converted: "Invoiced" };

/** "3 Sep 2026, 9:30 am" — the date carries the time because two quotations
 *  raised for the same customer on the same day are told apart by it. */
const when = (iso: string) => {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("en-IN", {
    day: "numeric", month: "short", year: "numeric",
    hour: "numeric", minute: "2-digit", hour12: true,
  });
};

const inputCls =
  "w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-800 " +
  "placeholder:text-slate-400 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition";

/** Quotation and Converted Orders are the same list either side of payment, so
 *  they are one page told which side it is showing. Two copies would drift the
 *  moment either grew a column. */
export default function QuotationsPage({ scope = "open" }: { scope?: "open" | "orders" }) {
  const isOrders = scope === "orders";
  const api = getApiBase(APP_SLUG);
  const headers = useCallback(() => ({
    "Content-Type": "application/json",
    Authorization: `Bearer ${localStorage.getItem(`${APP_SLUG}_access`)}`,
  }), []);

  const [rows, setRows] = useState<Quotation[]>([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Quotation | null>(null);
  const [preview, setPreview] = useState<Quotation | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  // Raised between these two dates. Either alone is a valid question.
  const [createdFrom, setCreatedFrom] = useState("");
  const [createdTo, setCreatedTo] = useState("");

  const load = useCallback(async () => {
    try {
      const query = new URLSearchParams({ scope });
      if (statusFilter !== "all") query.set("status", statusFilter);
      if (createdFrom) query.set("created_from", createdFrom);
      if (createdTo) query.set("created_to", createdTo);
      const r = await fetch(`${api}/api/quotations/?${query}`, { headers: headers() });
      if (r.ok) {
        const d = await r.json();
        setRows(Array.isArray(d) ? d : (d.results || []));
      }
    } catch { /* an empty board rather than a broken one */ }
    finally { setLoading(false); }
  }, [api, headers, scope, statusFilter, createdFrom, createdTo]);

  useEffect(() => { load(); }, [load]);

  const openNew = () => { setEditing(null); setOpen(true); };
  const openEdit = (q: Quotation) => { setEditing(q); setOpen(true); };

  const download = async (q: Quotation) => {
    setBusy(q.id);
    try {
      saveBlob(await fetchProposal(q.id), proposalFileName(q.number, q.lead_name));
    } catch (e: any) {
      alert(e?.message || "Could not build the document.");
    } finally { setBusy(null); }
  };

  const send = async (q: Quotation) => {
    setBusy(q.id);
    try {
      // The very file the customer would download — sent, not rebuilt.
      const pdf = await fetchProposal(q.id);
      const fd = new FormData();
      fd.append("pdf", pdf, proposalFileName(q.number, q.lead_name));
      fd.append("channels", "email");
      const r = await fetch(`${api}/api/quotations/${q.id}/send/`, {
        method: "POST",
        headers: { Authorization: `Bearer ${localStorage.getItem(`${APP_SLUG}_access`)}` },
        body: fd,
      });
      const d = await r.json().catch(() => ({}));
      alert(d.sent ? `Sent to ${d.sent_to || "the customer"}.`
                   : (d.error || (d.failures || []).join(" ") || "Could not send."));
      await load();
    } catch (e: any) {
      alert(e?.message || "Could not send this quotation.");
    } finally { setBusy(null); }
  };

  const remove = async (q: Quotation) => {
    if (!window.confirm(`Delete ${q.number}? This cannot be undone.`)) return;
    const r = await fetch(`${api}/api/quotations/${q.id}/`, { method: "DELETE", headers: headers() });
    if (r.ok || r.status === 204) await load();
  };

  const shown = rows.filter(q => {
    const t = search.trim().toLowerCase();
    if (!t) return true;
    return [q.number, q.lead_name, q.project_name].some(v => (v || "").toLowerCase().includes(t));
  });

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-[1500px] mx-auto">
      <div className="flex flex-wrap items-start justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-black text-slate-900">
            {isOrders ? "Converted Orders" : "Quotation"}
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            {isOrders
              ? "Accepted quotations the customer has paid against. Kept as the record of what was agreed, so they cannot be edited."
              : "What the customer is offered — built from a project, then negotiated."}
          </p>
        </div>
        {!isOrders && (
          <button onClick={openNew}
            className="px-5 py-3 rounded-xl bg-indigo-600 text-white text-sm font-bold hover:bg-indigo-700 transition shadow-sm">
            + New Quotation
          </button>
        )}
      </div>

      <div className="flex flex-wrap gap-3 mb-5">
        <input value={search} onChange={e => setSearch(e.target.value)}
          placeholder="Search by number, customer or project…"
          className={`${inputCls} flex-1 min-w-[240px] max-w-md`} />
        {/* Only offers have a status worth filtering: an order is by definition
            one that was accepted and paid. */}
        {!isOrders && (
          <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
            className={`${inputCls} w-[180px]`}>
            <option value="all">All statuses</option>
            <option value="draft">Draft</option>
            <option value="sent">Sent</option>
            <option value="accepted">Accepted</option>
            <option value="declined">Declined</option>
          </select>
        )}
        {/* Raised between. Labelled, because two bare date boxes side by side
            do not say which end is which. */}
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Raised</span>
          <input type="date" value={createdFrom} max={createdTo || undefined}
            onChange={e => setCreatedFrom(e.target.value)}
            title="From this date" className={`${inputCls} w-[150px] max-w-[45vw]`} />
          <span className="text-xs text-slate-400">to</span>
          <input type="date" value={createdTo} min={createdFrom || undefined}
            onChange={e => setCreatedTo(e.target.value)}
            title="Up to this date" className={`${inputCls} w-[150px] max-w-[45vw]`} />
          {(createdFrom || createdTo) && (
            <button onClick={() => { setCreatedFrom(""); setCreatedTo(""); }}
              className="text-xs font-bold text-slate-400 hover:text-slate-700 transition px-1"
              title="Clear the date range">Clear</button>
          )}
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden">
        <div className="overflow-x-auto">
          {/* A full grid: every cell boxed, so a row of six columns can be read
              across without losing the line. The vertical rules follow the
              horizontal ones — slate-200 through the header, slate-100 between
              the rows — and the last column drops its rule so the card's own
              rounded border closes the table. */}
          <table className="w-full text-sm
                            [&_th]:border-r [&_th]:border-slate-200
                            [&_td]:border-r [&_td]:border-slate-100
                            [&_th:last-child]:border-r-0 [&_td:last-child]:border-r-0">
            <thead className="bg-slate-50 border-b border-slate-200 text-left text-[11px] font-bold text-slate-500 uppercase tracking-wider">
              <tr>
                <th className="py-4 px-6">Number</th>
                <th className="py-4 px-6">Created</th>
                <th className="py-4 px-6">Customer</th>
                <th className="py-4 px-6">Project</th>
                <th className="py-4 px-6 text-right">Total</th>
                <th className="py-4 px-6 text-center">Status</th>
                <th className="py-4 px-6 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                <tr><td colSpan={7} className="py-12 text-center text-slate-400">Loading…</td></tr>
              ) : shown.length === 0 ? (
                <tr><td colSpan={7} className="py-12 text-center text-slate-500">
                  {isOrders
                    ? "No converted orders yet. An accepted quotation lands here once the customer pays."
                    : "No quotations yet. Build one from a project."}
                </td></tr>
              ) : shown.map(q => (
                <tr key={q.id} className="hover:bg-slate-50/70 transition">
                  <td className="py-4 px-6 whitespace-nowrap">
                    <button onClick={() => setPreview(q)}
                      className="font-semibold text-slate-900 hover:text-indigo-600 transition">
                      {q.number}
                    </button>
                  </td>
                  <td className="py-4 px-6 text-slate-500 whitespace-nowrap text-[12px]">
                    {when(q.created_at)}
                  </td>
                  <td className="py-4 px-6 text-slate-600">{q.lead_name || <span className="text-slate-400">—</span>}</td>
                  <td className="py-4 px-6 text-slate-600">
                    {q.project_name || <span className="text-slate-400">—</span>}
                    <span className="block text-[10px] text-slate-400">
                      {VARIANTS.find(([k]) => k === q.price_variant)?.[1]}
                    </span>
                  </td>
                  <td className="py-4 px-6 text-right whitespace-nowrap">
                    <span className="text-slate-900 font-medium">₹{money(q.grand_total)}</span>
                    {Number(q.discount_amount) > 0 && (
                      <span className="block text-[10px] text-emerald-600">
                        after ₹{money(q.discount_amount)} off
                      </span>
                    )}
                  </td>
                  <td className="py-4 px-6 text-center">
                    <span className={`inline-block px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wide ${
                      q.is_order ? "bg-indigo-50 text-indigo-700"
                                 : STATUS_STYLE[q.status] || "bg-slate-100 text-slate-600"}`}>
                      {q.is_order ? "Converted" : (STATUS_LABEL[q.status] || q.status)}
                    </span>
                  </td>
                  <td className="py-4 px-6 text-right whitespace-nowrap">
                    <div className="inline-flex items-center gap-3 text-xs font-bold">
                      <button onClick={() => setPreview(q)}
                        className="text-slate-500 hover:text-slate-800">Preview</button>
                      <button onClick={() => download(q)} disabled={busy === q.id}
                        className="text-slate-500 hover:text-slate-800 disabled:opacity-40">PDF</button>
                      <button onClick={() => send(q)} disabled={busy === q.id}
                        className="text-slate-500 hover:text-slate-800 disabled:opacity-40">Send</button>
                      {!q.is_order && (
                        <>
                          <button onClick={() => openEdit(q)}
                            className="text-indigo-600 hover:text-indigo-800">Edit</button>
                          <button onClick={() => remove(q)} className="text-rose-500 hover:text-rose-700">Delete</button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <QuotationPreviewModal quotation={preview}
        onClose={() => setPreview(null)} onSent={load} />

      <QuotationFormModal
        open={open} editing={editing}
        onClose={() => setOpen(false)}
        onSaved={load} />
    </div>
  );
}


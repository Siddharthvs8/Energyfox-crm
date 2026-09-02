"use client";
/**
 * The quotation form — one form, wherever a quotation is raised.
 *
 * The Quotation module opens it from its list; a lead's own page opens it with
 * that customer already fixed. Both get the same fields, because a quotation
 * raised from a lead is not a lesser document than one raised from the module —
 * it is the same document, and a BDE sitting with a customer needs the whole of
 * it, not a short form that has to be finished somewhere else later.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";

export type SpecLine = { item_name: string; brand: string; quantity: string; position: number };
export type Cost = { remark: string; amount: string; position: number };
export type Quotation = {
  id: number; number: string; status: string;
  lead: number | null; lead_name: string | null;
  project: number | null; project_name: string | null; price_variant: string;
  quotation_date: string | null; expiry_date: string | null; site: string;
  package_amount: string; tax_percent: string; price_includes_tax: boolean;
  discount_amount: string; discount_remark: string;
  spec_lines: SpecLine[]; costs: Cost[];
  extras_total: string; subtotal: string; net_amount: string;
  base_amount: string; tax_amount: string; total: string; grand_total: string; round_off: string;
  converted_quote: number | null; pdf: string | null; notes: string;
};

export const VARIANTS: [string, string][] = [["dcr", "DCR"], ["non_dcr", "Non-DCR"]];

export const money = (v: string | number) =>
  Number(v || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const inputCls =
  "w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-800 " +
  "placeholder:text-slate-400 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition";
const labelCls = "block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5";

/** What actually went wrong, in words.
 *
 * A rejection arrives in one of three shapes and only one of them was being
 * read: {"detail": "..."} for a permission problem, {"field": ["reason"]} for a
 * validation one, and HTML for a server error. Everything but the first used to
 * come out as "Could not save this quotation", which tells the person at the
 * screen nothing and sends them to ask someone with a server log.
 */
async function describeFailure(r: Response): Promise<string> {
  let body: any = null;
  try { body = await r.json(); } catch { /* not JSON — a server error page */ }

  if (!body) {
    return r.status >= 500
      ? `The server could not save this (error ${r.status}). Nothing was changed.`
      : `Could not save this quotation (error ${r.status}).`;
  }
  if (typeof body === "string") return body;
  if (body.detail || body.error) return body.detail || body.error;

  // Field errors: name the field, so the fix is obvious.
  const parts = Object.entries(body).map(([field, msgs]) => {
    const text = Array.isArray(msgs) ? msgs.join(" ") : String(msgs);
    return field === "non_field_errors" ? text
      : `${field.replace(/_/g, " ")}: ${text}`;
  });
  return parts.join("  ·  ") || "Could not save this quotation.";
}

const blankForm = () => ({
  lead: "", project: "", price_variant: "dcr", status: "draft",
  quotation_date: new Date().toISOString().slice(0, 10), expiry_date: "", site: "",
  package_amount: "", tax_percent: "", price_includes_tax: false,
  discount_amount: "", discount_remark: "", notes: "",
});

export default function QuotationFormModal({ open, editing, lockedLeadId, onClose, onSaved }: {
  open: boolean;
  editing: Quotation | null;
  /** Set when opened from a lead's page: that customer is the quotation's, and
   *  is not a choice to be made again here. */
  lockedLeadId?: number | string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const api = getApiBase(APP_SLUG);
  const headers = useCallback(() => ({
    "Content-Type": "application/json",
    Authorization: `Bearer ${localStorage.getItem(`${APP_SLUG}_access`)}`,
  }), []);

  const [leads, setLeads] = useState<any[]>([]);
  const [projects, setProjects] = useState<any[]>([]);
  const [form, setForm] = useState(blankForm());
  const [spec, setSpec] = useState<SpecLine[]>([]);
  const [costs, setCosts] = useState<Cost[]>([]);
  const [specOpen, setSpecOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Loaded once the form is opened rather than on mount: the lead page keeps
  // this mounted behind a button, and a page of leads is not free.
  useEffect(() => {
    if (!open) return;
    const unwrap = async (r: Response) => {
      if (!r.ok) return [];
      const d = await r.json();
      return Array.isArray(d) ? d : (d.results || []);
    };
    (async () => {
      try {
        const [p, l] = await Promise.all([
          fetch(`${api}/api/projects/`, { headers: headers() }),
          lockedLeadId ? Promise.resolve(null as any)
                       : fetch(`${api}/api/leads/?all=true`, { headers: headers() }),
        ]);
        setProjects(await unwrap(p));
        if (l) setLeads(await unwrap(l));
      } catch { /* the form still works; the pickers are just empty */ }
    })();
  }, [open, api, headers, lockedLeadId]);

  // Reset to whatever this opening is for — a fresh quotation or an existing one.
  useEffect(() => {
    if (!open) return;
    setError(null);
    setSpecOpen(false);
    if (editing) {
      setForm({
        lead: editing.lead ? String(editing.lead) : "",
        project: editing.project ? String(editing.project) : "",
        price_variant: editing.price_variant, status: editing.status,
        quotation_date: editing.quotation_date || "", expiry_date: editing.expiry_date || "",
        site: editing.site || "",
        package_amount: Number(editing.package_amount) ? String(Number(editing.package_amount)) : "",
        tax_percent: Number(editing.tax_percent) ? String(Number(editing.tax_percent)) : "",
        price_includes_tax: editing.price_includes_tax,
        discount_amount: Number(editing.discount_amount) ? String(Number(editing.discount_amount)) : "",
        discount_remark: editing.discount_remark || "", notes: editing.notes || "",
      });
      setSpec(editing.spec_lines.map(l => ({ ...l })));
      setCosts(editing.costs.map(c => ({ ...c })));
    } else {
      setForm({ ...blankForm(), lead: lockedLeadId ? String(lockedLeadId) : "" });
      setSpec([]); setCosts([]);
    }
  }, [open, editing, lockedLeadId]);

  const project = useMemo(
    () => projects.find(p => String(p.id) === form.project), [projects, form.project]);

  // The running statement, mirrored from the server's arithmetic so the figures
  // move as you type. The server stays the authority on save.
  const live = useMemo(() => {
    const pkg = Number(form.package_amount) || 0;
    const extras = costs.reduce((n, c) => n + (Number(c.amount) || 0), 0);
    const discount = Number(form.discount_amount) || 0;
    const net = pkg + extras - discount;
    const rate = Number(form.tax_percent) || 0;
    const base = form.price_includes_tax
      ? Math.round((net / (1 + rate / 100)) * 100) / 100
      : net;
    const total = form.price_includes_tax ? net : Math.round((net + net * rate / 100) * 100) / 100;
    return { pkg, extras, discount, net, base, tax: total - base, total };
  }, [form.package_amount, form.discount_amount, form.tax_percent, form.price_includes_tax, costs]);

  /** Picking a project pulls its sheet and price in, so the form shows what the
   *  server would fill without waiting for a save. */
  const chooseProject = (id: string, variant = form.price_variant) => {
    const p = projects.find(pr => String(pr.id) === id);
    if (!p) { setSpec([]); setForm(f => ({ ...f, project: id })); return; }
    setSpec((p.lines || []).map((l: SpecLine) => ({ ...l })));
    const price = p.pricing?.[variant]?.price;
    setForm(f => ({
      ...f, project: id, price_variant: variant,
      package_amount: Number(price) ? String(Number(price)) : "",
      tax_percent: Number(p.tax_percent) ? String(Number(p.tax_percent)) : "",
      price_includes_tax: !!p.price_includes_tax,
    }));
  };

  // Anything that moves the price has to say why — the same rule the server
  // enforces, checked here so it is caught beside the field rather than after a
  // round trip. Named once and read by both the inputs and the save.
  const discountNeedsReason =
    Number(form.discount_amount) > 0 && !form.discount_remark.trim();
  const costNeedsReason = (c: Cost) => Number(c.amount) > 0 && !c.remark.trim();
  const missingReason = discountNeedsReason || costs.some(costNeedsReason);

  const save = async () => {
    if (missingReason) {
      setError(discountNeedsReason
        ? "Say why the discount was given."
        : "Say what each additional cost is for.");
      return;
    }
    setSaving(true); setError(null);
    try {
      const body = {
        ...form,
        lead: lockedLeadId ? Number(lockedLeadId) : (form.lead ? Number(form.lead) : null),
        project: form.project ? Number(form.project) : null,
        package_amount: form.package_amount || 0,
        tax_percent: form.tax_percent || 0,
        discount_amount: form.discount_amount || 0,
        expiry_date: form.expiry_date || null,
        quotation_date: form.quotation_date || null,
        spec_lines: spec.map((l, i) => ({ ...l, position: i })),
        costs: costs.filter(c => c.remark.trim() || Number(c.amount))
                    .map((c, i) => ({ ...c, amount: c.amount || 0, position: i })),
      };
      const r = await fetch(
        editing ? `${api}/api/quotations/${editing.id}/` : `${api}/api/quotations/`,
        { method: editing ? "PATCH" : "POST", headers: headers(), body: JSON.stringify(body) });
      if (!r.ok) { setError(await describeFailure(r)); return; }
      onSaved();
      onClose();
    } catch { setError("Network error — nothing was saved."); }
    finally { setSaving(false); }
  };

  if (!open) return null;

  const setCost = (i: number, patch: Partial<Cost>) =>
    setCosts(costs.map((c, n) => (n === i ? { ...c, ...patch } : c)));

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-start justify-center p-4 overflow-y-auto">
      <div className="bg-white rounded-2xl w-full max-w-4xl my-8 shadow-xl">
        <div className="px-6 py-5 border-b border-slate-100">
          <h2 className="text-lg font-black text-slate-900">
            {editing ? `Edit ${editing.number}` : "New Quotation"}
          </h2>
          {lockedLeadId && !editing && (
            <p className="text-[11px] text-slate-400 mt-0.5">
              Filed on this customer, and listed in Inventory → Quotation.
            </p>
          )}
        </div>

        <div className="px-6 py-5 space-y-5">
          <div className="grid sm:grid-cols-2 gap-4">
            {!lockedLeadId && (
              <div>
                <label className={labelCls}>Customer (Lead)</label>
                <select value={form.lead} onChange={e => setForm({ ...form, lead: e.target.value })}
                  className={inputCls}>
                  <option value="">No lead</option>
                  {leads.map(l => (
                    <option key={l.id} value={l.id}>
                      {`${l.first_name || ""} ${l.last_name || ""}`.trim() || l.phone}
                    </option>
                  ))}
                </select>
                <p className="text-[10px] text-slate-400 mt-1">
                  Choosing a lead files this quotation on that customer&apos;s page.
                </p>
              </div>
            )}
            <div>
              <label className={labelCls}>Status</label>
              <select value={form.status} onChange={e => setForm({ ...form, status: e.target.value })}
                className={inputCls}>
                {["draft", "sent", "accepted", "declined"].map(s =>
                  <option key={s} value={s}>{s[0].toUpperCase() + s.slice(1)}</option>)}
              </select>
            </div>
            <div>
              <label className={labelCls}>Quotation date</label>
              <input type="date" value={form.quotation_date}
                onChange={e => setForm({ ...form, quotation_date: e.target.value })} className={inputCls} />
            </div>
            <div>
              <label className={labelCls}>Valid until</label>
              <input type="date" value={form.expiry_date}
                onChange={e => setForm({ ...form, expiry_date: e.target.value })} className={inputCls} />
            </div>
          </div>

          {/* ── The project it is built from ── */}
          <div className="border border-slate-200 rounded-xl p-4">
            <div className="grid sm:grid-cols-[1fr_auto_auto] gap-4 items-end">
              <div>
                <label className={labelCls}>Project</label>
                <select value={form.project} onChange={e => chooseProject(e.target.value)}
                  className={inputCls}>
                  <option value="">No project</option>
                  {projects.map(p => (
                    <option key={p.id} value={p.id}>
                      {[p.name, p.system_type_display, p.capacity].filter(Boolean).join(" · ")}
                    </option>
                  ))}
                </select>
              </div>
              {form.project && (
                <div>
                  <label className={labelCls}>Price</label>
                  <div className="flex rounded-xl border border-slate-200 overflow-hidden bg-white">
                    {VARIANTS.map(([key, label]) => {
                      const chosen = form.price_variant === key;
                      const amount = project?.pricing?.[key]?.total;
                      return (
                        <button key={key} type="button"
                          onClick={() => chooseProject(form.project, key)}
                          className={`px-4 py-2 text-xs font-bold transition ${
                            chosen ? "bg-indigo-600 text-white" : "text-slate-500 hover:bg-slate-50"}`}>
                          {label}
                          {Number(amount) > 0 && (
                            <span className={`block text-[10px] font-semibold ${
                              chosen ? "text-indigo-100" : "text-slate-400"}`}>
                              ₹{Number(amount).toLocaleString("en-IN")}
                            </span>
                          )}
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}
              {form.project && !specOpen && (
                <button type="button" onClick={() => setSpecOpen(true)}
                  className="px-4 py-2.5 rounded-xl border border-slate-200 text-xs font-bold text-slate-600 hover:bg-slate-50 transition">
                  Edit items
                </button>
              )}
            </div>

            {specOpen && (
              <div className="mt-4 space-y-3">
                <div className="border border-slate-100 rounded-lg p-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wide">
                      Specifications
                    </span>
                    <button type="button"
                      onClick={() => setSpec([...spec, { item_name: "", brand: "", quantity: "", position: spec.length }])}
                      className="text-[11px] font-bold text-indigo-600 hover:text-indigo-800">+ Add</button>
                  </div>
                  {spec.length === 0 ? (
                    <p className="text-[11px] text-slate-400">Nothing specified yet.</p>
                  ) : spec.map((r, i) => {
                    const set = (patch: Partial<SpecLine>) =>
                      setSpec(spec.map((x, n) => (n === i ? { ...x, ...patch } : x)));
                    return (
                      <div key={i} className="grid gap-2 mb-2 items-center sm:grid-cols-[1fr_1fr_130px_28px]">
                        <input value={r.item_name} onChange={e => set({ item_name: e.target.value })}
                          placeholder="Item" className={inputCls} />
                        <input value={r.brand} onChange={e => set({ brand: e.target.value })}
                          placeholder="Brand" className={inputCls} />
                        <input value={r.quantity} onChange={e => set({ quantity: e.target.value })}
                          placeholder="Qty" className={inputCls} />
                        <button type="button" onClick={() => setSpec(spec.filter((_, n) => n !== i))}
                          className="justify-self-center text-slate-300 hover:text-rose-500">
                          <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2"
                            strokeLinecap="round" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12" /></svg>
                        </button>
                      </div>
                    );
                  })}
                </div>

                <div className="flex justify-end pt-1">
                  <button type="button" onClick={() => setSpecOpen(false)}
                    className="px-5 py-2 rounded-xl bg-slate-800 text-white text-xs font-bold hover:bg-slate-900 transition">
                    Save
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* ── The money ── */}
          <div className="border border-slate-200 rounded-xl p-4 space-y-4">
            <div className="grid sm:grid-cols-[1fr_120px] gap-4">
              <div>
                <label className={labelCls}>Package price (₹)</label>
                <input type="number" min="0" step="0.01" value={form.package_amount}
                  onChange={e => setForm({ ...form, package_amount: e.target.value })}
                  placeholder="200000" className={inputCls} />
              </div>
              <div>
                <label className={labelCls}>Tax %</label>
                <input type="number" min="0" step="0.01" value={form.tax_percent}
                  onChange={e => setForm({ ...form, tax_percent: e.target.value })}
                  placeholder="18" className={inputCls} />
              </div>
            </div>
            <label className="flex items-center gap-2.5 cursor-pointer select-none">
              <input type="checkbox" checked={form.price_includes_tax}
                onChange={e => setForm({ ...form, price_includes_tax: e.target.checked })}
                className="w-4 h-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500/30" />
              <span className="text-sm text-slate-700">Price includes tax</span>
            </label>

            {/* Each extra carries its own reason. A crane, a longer cable run and
                a scaffold are three conversations; one lump labelled "extra
                charges" is the one a customer argues with. */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className={labelCls}>Additional costs</span>
                <button type="button"
                  onClick={() => setCosts([...costs, { remark: "", amount: "", position: costs.length }])}
                  className="text-[11px] font-bold text-indigo-600 hover:text-indigo-800">+ Add cost</button>
              </div>
              {costs.length === 0 ? (
                <p className="text-[11px] text-slate-400">None. Add one for anything beyond the package.</p>
              ) : costs.map((c, i) => (
                <div key={i} className="grid sm:grid-cols-[1fr_150px_28px] gap-2 mb-2 items-center">
                  <input value={c.remark} onChange={e => setCost(i, { remark: e.target.value })}
                    placeholder="Why — e.g. crane hire for 3rd floor"
                    className={`${inputCls} ${costNeedsReason(c)
                      ? "border-rose-300 bg-rose-50/40 focus:ring-rose-500/20 focus:border-rose-400" : ""}`} />
                  <input type="number" min="0" step="0.01" value={c.amount}
                    onChange={e => setCost(i, { amount: e.target.value })}
                    placeholder="12000" className={inputCls} />
                  <button type="button" onClick={() => setCosts(costs.filter((_, n) => n !== i))}
                    className="justify-self-center text-slate-300 hover:text-rose-500">
                    <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2"
                      strokeLinecap="round" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12" /></svg>
                  </button>
                </div>
              ))}
            </div>

            <div className="grid sm:grid-cols-[150px_1fr] gap-2">
              <div>
                <label className={labelCls}>Discount (₹)</label>
                <input type="number" min="0" step="0.01" value={form.discount_amount}
                  onChange={e => setForm({ ...form, discount_amount: e.target.value })}
                  placeholder="15000" className={inputCls} />
              </div>
              <div>
                <label className={labelCls}>
                  Why the discount
                  {Number(form.discount_amount) > 0 && <span className="text-rose-500 ml-1">*</span>}
                </label>
                <input value={form.discount_remark}
                  onChange={e => setForm({ ...form, discount_remark: e.target.value })}
                  placeholder="e.g. repeat customer"
                  className={`${inputCls} ${discountNeedsReason
                    ? "border-rose-300 bg-rose-50/40 focus:ring-rose-500/20 focus:border-rose-400" : ""}`} />
              </div>
            </div>

            {/* The statement, as the customer will read it. */}
            <div className="border-t border-slate-100 pt-3 text-[13px] space-y-1">
              <Row label="Package" value={live.pkg} />
              {costs.filter(c => Number(c.amount)).map((c, i) => (
                <Row key={i} label={c.remark || "Additional cost"} value={Number(c.amount)} plus />
              ))}
              {live.discount > 0 && (
                <Row label={`Discount${form.discount_remark ? ` — ${form.discount_remark}` : ""}`}
                  value={-live.discount} />
              )}
              {Number(form.tax_percent) > 0 && (
                <Row label={`${form.price_includes_tax ? "Includes" : "Plus"} tax @ ${Number(form.tax_percent)}%`}
                  value={live.tax} muted />
              )}
              <div className="flex justify-between pt-2 border-t border-slate-100 font-black text-slate-900">
                <span>Total</span><span>₹{money(live.total)}</span>
              </div>
            </div>
          </div>

          {error && <p className="text-[12px] font-medium text-rose-600">{error}</p>}
        </div>

        <div className="px-6 py-4 border-t border-slate-100 flex justify-end gap-3">
          <button onClick={onClose}
            className="px-5 py-2.5 rounded-xl border border-slate-200 text-sm font-bold text-slate-600 hover:bg-slate-50 transition">
            Cancel
          </button>
          <button onClick={save} disabled={saving || missingReason}
            title={missingReason ? "Every discount and extra cost needs a reason" : undefined}
            className="px-5 py-2.5 rounded-xl bg-indigo-600 text-white text-sm font-bold hover:bg-indigo-700 disabled:opacity-50 transition">
            {saving ? "Saving…" : editing ? "Save changes" : "Create quotation"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Row({ label, value, plus, muted }: {
  label: string; value: number; plus?: boolean; muted?: boolean;
}) {
  return (
    <div className={`flex justify-between gap-4 ${muted ? "text-slate-400" : "text-slate-600"}`}>
      <span className="truncate">{label}</span>
      <span className="whitespace-nowrap">
        {plus ? "+ " : value < 0 ? "− " : ""}₹{money(Math.abs(value))}
      </span>
    </div>
  );
}

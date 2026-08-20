"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { isSpectator } from "@/lib/spectator";

type Member = { id: number; name: string; role: string; role_label: string };
type Branch = {
  id: number;
  name: string;
  code: string;
  manager: number | null;
  manager_name: string | null;
  location: string;
  address: string;
  phone: string;
  email: string;
  is_active: boolean;
  member_count: number;
  lead_count: number;
  members: Member[];
  created_at: string;
};

type PerfRow = {
  id: number; name: string; code: string; manager_name: string | null; is_active: boolean;
  staff: number; leads: number; converted: number; conversion_rate: number;
  closed_deals: number; completed_projects: number; lost: number;
  deal_value: number; collected: number; balance_due: number;
};
type Perf = { period: string; period_label: string; branches: PerfRow[]; totals: any };

const PERIODS = [
  { value: "this_month", label: "This Month" },
  { value: "last_30", label: "Last 30 Days" },
  { value: "this_year", label: "This Year" },
  { value: "all", label: "All Time" },
];

const money = (n: number) =>
  "₹" + (n >= 10000000 ? `${(n / 10000000).toFixed(2)} Cr`
    : n >= 100000 ? `${(n / 100000).toFixed(2)} L`
    : n.toLocaleString("en-IN"));

const BLANK = {
  name: "", code: "", manager: "" as string | number, location: "",
  address: "", phone: "", email: "",
};

const inputCls = "w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all";
const labelCls = "block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5";

export default function BranchesPage() {
  const domain = APP_SLUG;
  const router = useRouter();
  const [authChecked, setAuthChecked] = useState(false);
  const [allowed, setAllowed] = useState(false);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [managers, setManagers] = useState<{ id: number; name: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState({ ...BLANK });
  const [saving, setSaving] = useState(false);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [tab, setTab] = useState<"manage" | "performance">("manage");
  const [period, setPeriod] = useState("this_month");
  const [perf, setPerf] = useState<Perf | null>(null);
  const [perfLoading, setPerfLoading] = useState(false);

  const token = () => localStorage.getItem(`${domain}_access`);
  const authHeader = () => ({ Authorization: `Bearer ${token()}` });

  useEffect(() => {
    const t = token();
    if (!t) { router.push("/login"); return; }
    fetch(`${getApiBase(domain)}/api/users/me/`, { headers: { Authorization: `Bearer ${t}` } })
      .then(r => r.json())
      .then(d => {
        const ok = isSpectator(d) || !!d.is_staff || !!d.is_superuser;
        setAllowed(ok); setAuthChecked(true);
        if (!ok) router.replace("/");
      })
      .catch(() => setAuthChecked(true));
  }, [domain, router]);

  const load = () => {
    fetch(`${getApiBase(domain)}/api/branches/`, { headers: authHeader() })
      .then(r => (r.ok ? r.json() : []))
      .then(d => setBranches(Array.isArray(d) ? d : d.results || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (!allowed) return;
    load();
    // Branch managers (and admins) are eligible to head a branch.
    fetch(`${getApiBase(domain)}/api/users/`, { headers: authHeader() })
      .then(r => (r.ok ? r.json() : []))
      .then(d => {
        const rows = Array.isArray(d) ? d : d.results || [];
        setManagers(rows
          .filter((u: any) => ["branch_manager", "manager", "general_manager", "admin", "super_admin"].includes(u.role))
          .map((u: any) => ({ id: u.id, name: `${u.first_name || ""} ${u.last_name || ""}`.trim() || u.username })));
      })
      .catch(() => {});
  }, [allowed]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!allowed || tab !== "performance") return;
    setPerfLoading(true);
    fetch(`${getApiBase(domain)}/api/branches/performance/?period=${period}`, { headers: authHeader() })
      .then(r => (r.ok ? r.json() : null))
      .then(d => { if (d) setPerf(d); })
      .catch(() => {})
      .finally(() => setPerfLoading(false));
  }, [allowed, tab, period]); // eslint-disable-line react-hooks/exhaustive-deps

  const openAdd = () => { setEditingId(null); setForm({ ...BLANK }); setShowForm(true); };
  const openEdit = (b: Branch) => {
    setEditingId(b.id);
    setForm({
      name: b.name || "", code: b.code || "", manager: b.manager ?? "",
      location: b.location || "", address: b.address || "", phone: b.phone || "", email: b.email || "",
    });
    setShowForm(true);
  };

  const save = async () => {
    if (!form.name.trim()) { alert("Enter a branch name."); return; }
    setSaving(true);
    try {
      const payload: any = { ...form, manager: form.manager || null };
      const r = await fetch(
        editingId ? `${getApiBase(domain)}/api/branches/${editingId}/` : `${getApiBase(domain)}/api/branches/`,
        {
          method: editingId ? "PATCH" : "POST",
          headers: { "Content-Type": "application/json", ...authHeader() },
          body: JSON.stringify(payload),
        });
      if (r.ok) { setShowForm(false); setEditingId(null); setForm({ ...BLANK }); load(); }
      else { const e = await r.json().catch(() => ({})); alert(e.error || e.detail || "Failed to save the branch."); }
    } catch { alert("Network error."); }
    finally { setSaving(false); }
  };

  const toggleActive = async (b: Branch) => {
    const r = await fetch(`${getApiBase(domain)}/api/branches/${b.id}/toggle-active/`, { method: "POST", headers: authHeader() });
    if (r.ok) load(); else alert("Could not update the branch.");
  };

  const remove = async (b: Branch) => {
    if (!window.confirm(`Delete the branch "${b.name}"? This cannot be undone.`)) return;
    const r = await fetch(`${getApiBase(domain)}/api/branches/${b.id}/`, { method: "DELETE", headers: authHeader() });
    if (r.ok || r.status === 204) load();
    else { const e = await r.json().catch(() => ({})); alert(e.error || "Could not delete the branch."); }
  };

  if (!authChecked) return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="w-8 h-8 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
    </div>
  );
  if (!allowed) return null;

  const q = search.trim().toLowerCase();
  const filtered = branches.filter(b => !q
    || b.name.toLowerCase().includes(q)
    || (b.code || "").toLowerCase().includes(q)
    || (b.location || "").toLowerCase().includes(q)
    || (b.manager_name || "").toLowerCase().includes(q));

  const totalStaff = branches.reduce((n, b) => n + (b.member_count || 0), 0);
  const activeCount = branches.filter(b => b.is_active).length;

  return (
    <div className="p-6 lg:p-8 max-w-[1200px]">
      <div className="mb-6 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Branches</h1>
          <p className="text-sm text-slate-500 mt-1">Create and manage all branch offices, their heads and their staff.</p>
        </div>
        {tab === "manage" && (
          <button onClick={openAdd}
            className="px-4 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 active:scale-[0.97] transition shadow-sm shadow-indigo-200">
            + New Branch
          </button>
        )}
      </div>

      {/* Manage | Performance */}
      <div className="mb-5 inline-flex bg-slate-100 rounded-xl p-1">
        {([["manage", "Manage"], ["performance", "Performance"]] as const).map(([k, lbl]) => (
          <button key={k} onClick={() => setTab(k)}
            className={`px-4 py-2 rounded-lg text-sm font-semibold transition ${tab === k ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}>
            {lbl}
          </button>
        ))}
      </div>

      {tab === "manage" && (<>
      {/* Summary */}
      <div className="grid grid-cols-3 gap-3 mb-5">
        {[
          { label: "Branches", value: branches.length },
          { label: "Active", value: activeCount },
          { label: "Staff Assigned", value: totalStaff },
        ].map(s => (
          <div key={s.label} className="bg-white border border-slate-200 rounded-2xl shadow-sm px-5 py-4">
            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wide">{s.label}</p>
            <p className="text-2xl font-bold text-slate-900 mt-1 tabular-nums">{s.value}</p>
          </div>
        ))}
      </div>

      <div className="mb-5">
        <input value={search} onChange={e => setSearch(e.target.value)}
          placeholder="Search by name, code, location or head…"
          className="w-full max-w-md bg-white border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all" />
      </div>

      {loading ? (
        <div className="py-16 text-center text-sm text-slate-400">Loading…</div>
      ) : filtered.length === 0 ? (
        <div className="bg-white border border-dashed border-slate-200 rounded-2xl p-12 text-center text-sm text-slate-400">
          {branches.length === 0 ? "No branches yet — create your first one." : "No branches match your search."}
        </div>
      ) : (
        <div className="space-y-4">
          {filtered.map(b => (
            <div key={b.id} className={`bg-white border rounded-2xl shadow-sm overflow-hidden ${b.is_active ? "border-slate-200" : "border-slate-200 opacity-70"}`}>
              <div className="px-5 py-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="text-sm font-bold text-slate-900">{b.name}</p>
                      {b.code && <span className="text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full bg-slate-100 text-slate-500">{b.code}</span>}
                      <span className={`text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full ${b.is_active ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>
                        {b.is_active ? "Active" : "Inactive"}
                      </span>
                    </div>
                    <p className="text-xs text-slate-500 mt-1">
                      {b.location || "No location"}
                      {b.phone ? ` · ${b.phone}` : ""}
                      {b.email ? ` · ${b.email}` : ""}
                    </p>
                    <p className="text-[11px] text-slate-400 mt-0.5">
                      Head: <span className="font-semibold text-slate-600">{b.manager_name || "Unassigned"}</span>
                      {" · "}{b.member_count} staff{" · "}{b.lead_count} leads
                    </p>
                  </div>
                  <div className="flex items-center gap-3 flex-shrink-0">
                    <button onClick={() => setExpanded(expanded === b.id ? null : b.id)}
                      className="text-[12px] font-semibold text-slate-500 hover:text-slate-700">
                      {expanded === b.id ? "Hide staff" : "View staff"}
                    </button>
                    <button onClick={() => openEdit(b)} className="text-[12px] font-semibold text-indigo-600 hover:text-indigo-800">Edit</button>
                    <button onClick={() => toggleActive(b)} className="text-[12px] font-semibold text-amber-600 hover:text-amber-700">
                      {b.is_active ? "Deactivate" : "Activate"}
                    </button>
                    <button onClick={() => remove(b)} className="text-[12px] font-semibold text-rose-500 hover:text-rose-700">Delete</button>
                  </div>
                </div>
                {b.address && <p className="text-[11px] text-slate-400 mt-2 whitespace-pre-line">{b.address}</p>}
              </div>

              {expanded === b.id && (
                <div className="border-t border-slate-100 bg-slate-50/60 px-5 py-4">
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wide mb-2">Staff in this branch</p>
                  {b.members.length === 0 ? (
                    <p className="text-xs text-slate-400">No one is assigned to this branch yet — set a member&apos;s branch from the Team module.</p>
                  ) : (
                    <div className="flex flex-wrap gap-2">
                      {b.members.map(m => (
                        <span key={m.id} className="inline-flex items-center gap-1.5 bg-white border border-slate-200 rounded-xl px-3 py-1.5 text-xs">
                          <span className="font-semibold text-slate-700">{m.name}</span>
                          <span className="text-[10px] text-slate-400">{m.role_label}</span>
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      </>)}

      {/* ── Performance ─────────────────────────────────────────────────────── */}
      {tab === "performance" && (
        <>
          <div className="mb-5 flex flex-wrap items-center gap-3">
            <div className="inline-flex bg-white border border-slate-200 rounded-xl p-1">
              {PERIODS.map(p => (
                <button key={p.value} onClick={() => setPeriod(p.value)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${period === p.value ? "bg-indigo-600 text-white" : "text-slate-500 hover:text-slate-700"}`}>
                  {p.label}
                </button>
              ))}
            </div>
            <span className="text-[11px] text-slate-400">
              Every figure covers the leads each branch received in {perf?.period_label?.toLowerCase() || "this period"}.
            </span>
          </div>

          {perfLoading ? (
            <div className="py-16 text-center text-sm text-slate-400">Loading…</div>
          ) : !perf || perf.branches.length === 0 ? (
            <div className="bg-white border border-dashed border-slate-200 rounded-2xl p-12 text-center text-sm text-slate-400">
              No branch activity to report yet.
            </div>
          ) : (
            <>
              {/* Company totals */}
              <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 mb-5">
                {[
                  { label: "Leads", value: perf.totals.leads },
                  { label: "Converted", value: perf.totals.converted },
                  { label: "Conversion", value: `${perf.totals.conversion_rate}%` },
                  { label: "Collected", value: money(perf.totals.collected) },
                  { label: "Balance Due", value: money(perf.totals.balance_due) },
                ].map(s => (
                  <div key={s.label} className="bg-white border border-slate-200 rounded-2xl shadow-sm px-5 py-4">
                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wide">{s.label}</p>
                    <p className="text-xl font-bold text-slate-900 mt-1 tabular-nums">{s.value}</p>
                  </div>
                ))}
              </div>

              <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm min-w-[980px]">
                    <thead>
                      <tr className="text-left text-[10px] font-bold text-slate-400 uppercase tracking-wide border-b border-slate-100 bg-slate-50/60">
                        <th className="px-5 py-3">#</th>
                        <th className="px-5 py-3">Branch</th>
                        <th className="px-4 py-3 text-right">Staff</th>
                        <th className="px-4 py-3 text-right">Leads</th>
                        <th className="px-4 py-3 text-right">Converted</th>
                        <th className="px-4 py-3 text-right">Conv. %</th>
                        <th className="px-4 py-3 text-right">Closed</th>
                        <th className="px-4 py-3 text-right">Done</th>
                        <th className="px-4 py-3 text-right">Lost</th>
                        <th className="px-4 py-3 text-right">Collected</th>
                        <th className="px-4 py-3 text-right">Balance</th>
                      </tr>
                    </thead>
                    <tbody>
                      {perf.branches.map((b, i) => (
                        <tr key={b.id} className="border-b border-slate-50 hover:bg-slate-50/60">
                          <td className="px-5 py-3">
                            <span className={`inline-flex items-center justify-center w-6 h-6 rounded-lg text-[11px] font-bold ${
                              i === 0 ? "bg-amber-100 text-amber-700" : i === 1 ? "bg-slate-200 text-slate-600" : i === 2 ? "bg-orange-100 text-orange-700" : "text-slate-400"}`}>
                              {i + 1}
                            </span>
                          </td>
                          <td className="px-5 py-3">
                            <div className="flex items-center gap-2">
                              <p className="font-semibold text-slate-800">{b.name}</p>
                              {b.code && <span className="text-[10px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded bg-slate-100 text-slate-500">{b.code}</span>}
                              {!b.is_active && <span className="text-[10px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded bg-slate-100 text-slate-400">Inactive</span>}
                            </div>
                            <p className="text-[11px] text-slate-400">{b.manager_name || "No head assigned"}</p>
                          </td>
                          <td className="px-4 py-3 text-right text-slate-600 tabular-nums">{b.staff}</td>
                          <td className="px-4 py-3 text-right text-slate-600 tabular-nums">{b.leads}</td>
                          <td className="px-4 py-3 text-right font-semibold text-emerald-600 tabular-nums">{b.converted}</td>
                          <td className="px-4 py-3 text-right tabular-nums">
                            <span className={`font-bold ${b.conversion_rate >= 25 ? "text-emerald-600" : b.conversion_rate >= 10 ? "text-amber-600" : "text-slate-500"}`}>
                              {b.conversion_rate}%
                            </span>
                          </td>
                          <td className="px-4 py-3 text-right text-slate-600 tabular-nums">{b.closed_deals}</td>
                          <td className="px-4 py-3 text-right text-slate-600 tabular-nums">{b.completed_projects}</td>
                          <td className="px-4 py-3 text-right tabular-nums">
                            <span className={b.lost ? "text-rose-500 font-semibold" : "text-slate-400"}>{b.lost}</span>
                          </td>
                          <td className="px-4 py-3 text-right font-bold text-slate-800 tabular-nums">{money(b.collected)}</td>
                          <td className="px-4 py-3 text-right text-amber-600 tabular-nums">{money(b.balance_due)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
              <p className="text-[11px] text-slate-400 mt-3">
                Ranked by amount collected. <b>Closed</b> = pushed to documentation, <b>Done</b> = installation completed,
                <b> Balance</b> = still due from verified payments. A lead counts towards a branch through the staff member it is assigned to.
              </p>
            </>
          )}
        </>
      )}

      {/* Create / edit modal */}
      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
          <div className="bg-white w-full max-w-xl rounded-2xl shadow-2xl max-h-[90vh] overflow-hidden flex flex-col" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 flex-shrink-0">
              <h2 className="text-base font-bold text-slate-900">{editingId ? "Edit Branch" : "New Branch"}</h2>
              <button onClick={() => setShowForm(false)} className="w-8 h-8 flex items-center justify-center rounded-xl bg-slate-100 text-slate-500 hover:bg-slate-200 transition text-sm">✕</button>
            </div>
            <div className="overflow-y-auto flex-1 px-6 py-5">
              <div className="grid sm:grid-cols-2 gap-4">
                <div>
                  <label className={labelCls}>Branch Name</label>
                  <input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="e.g. Thiruvananthapuram" className={inputCls} />
                </div>
                <div>
                  <label className={labelCls}>Branch Code</label>
                  <input value={form.code} onChange={e => setForm({ ...form, code: e.target.value })} placeholder="e.g. TVM" className={inputCls} />
                </div>
                <div>
                  <label className={labelCls}>Branch Head</label>
                  <select value={form.manager} onChange={e => setForm({ ...form, manager: e.target.value })} className={inputCls}>
                    <option value="">Unassigned</option>
                    {managers.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
                  </select>
                </div>
                <div>
                  <label className={labelCls}>Location / City</label>
                  <input value={form.location} onChange={e => setForm({ ...form, location: e.target.value })} placeholder="City or area" className={inputCls} />
                </div>
                <div>
                  <label className={labelCls}>Phone</label>
                  <input value={form.phone} onChange={e => setForm({ ...form, phone: e.target.value })} placeholder="Office phone" className={inputCls} />
                </div>
                <div>
                  <label className={labelCls}>Email</label>
                  <input value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} placeholder="branch@energyfox.in" className={inputCls} />
                </div>
                <div className="sm:col-span-2">
                  <label className={labelCls}>Address</label>
                  <textarea value={form.address} onChange={e => setForm({ ...form, address: e.target.value })} rows={3} placeholder="Full office address" className={inputCls} />
                </div>
              </div>
              <p className="text-[11px] text-slate-400 mt-4">
                Staff are put into a branch from the Team module — set a member&apos;s Branch there and they appear here.
              </p>
            </div>
            <div className="px-6 py-4 border-t border-slate-100 flex justify-end gap-3 flex-shrink-0">
              <button onClick={() => setShowForm(false)} className="px-4 py-2.5 border border-slate-200 rounded-xl text-sm font-semibold text-slate-600 hover:bg-slate-50 transition">Cancel</button>
              <button onClick={save} disabled={saving}
                className="px-5 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 disabled:opacity-50 transition">
                {saving ? "Saving…" : editingId ? "Update Branch" : "Create Branch"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

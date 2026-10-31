"use client";
/**
 * Settings → Roles & Permissions.
 *
 * Custom user types: a named set of permission keys from the backend catalogue
 * (users/permission_catalog.py). A user put on the "Custom Role" user type in
 * Team gets exactly the modules and capabilities ticked here — nothing is
 * implied, so an empty role is valid and powerless.
 */
import React, { useEffect, useState } from "react";
import { getApiBase } from "@/lib/mock-data";

type Perm = { key: string; label: string; group: string };
export type CustomRole = {
  id: number; name: string; description: string;
  permissions: string[]; is_active: boolean; member_count: number;
};

const blankRole = { name: "", description: "", permissions: [] as string[], is_active: true };

const FIELD = "w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition";

export default function RolesSection({ domain, isAdmin }: { domain: string; isAdmin: boolean }) {
  const api = getApiBase(domain);
  const token = () => localStorage.getItem(`${domain}_access`);
  const authJson = () => ({ "Content-Type": "application/json", Authorization: `Bearer ${token()}` });

  const [catalog, setCatalog] = useState<{ modules: Perm[]; capabilities: Perm[] } | null>(null);
  const [roles, setRoles] = useState<CustomRole[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<CustomRole | null>(null);
  const [form, setForm] = useState<typeof blankRole>(blankRole);
  const [saving, setSaving] = useState(false);
  const [note, setNote] = useState("");

  const load = async () => {
    try {
      const h = { Authorization: `Bearer ${token()}` };
      const [cRes, rRes] = await Promise.all([
        fetch(`${api}/api/users/permission-catalog/`, { headers: h }),
        fetch(`${api}/api/custom-roles/`, { headers: h }),
      ]);
      if (cRes.ok) setCatalog(await cRes.json());
      if (rRes.ok) { const d = await rRes.json(); setRoles(Array.isArray(d) ? d : d.results || []); }
    } catch { /* leave the section empty rather than breaking Settings */ }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [domain]); // eslint-disable-line react-hooks/exhaustive-deps

  const startNew = () => { setEditing(null); setForm(blankRole); setNote(""); };
  const startEdit = (r: CustomRole) => {
    setEditing(r);
    setForm({
      name: r.name, description: r.description || "",
      permissions: [...(r.permissions || [])], is_active: r.is_active,
    });
    setNote("");
  };

  const toggle = (key: string) => setForm(f => ({
    ...f,
    permissions: f.permissions.includes(key) ? f.permissions.filter(k => k !== key) : [...f.permissions, key],
  }));

  /** Whole-group toggle — a role usually wants a department, not single screens. */
  const toggleGroup = (perms: Perm[], on: boolean) => setForm(f => {
    const keys = perms.map(p => p.key);
    return {
      ...f,
      permissions: on
        ? Array.from(new Set([...f.permissions, ...keys]))
        : f.permissions.filter(k => !keys.includes(k)),
    };
  });

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim()) return;
    setSaving(true); setNote("");
    try {
      const r = await fetch(editing ? `${api}/api/custom-roles/${editing.id}/` : `${api}/api/custom-roles/`, {
        method: editing ? "PATCH" : "POST", headers: authJson(), body: JSON.stringify(form),
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) {
        setNote(d.name?.[0] || d.permissions?.[0] || d.detail || "Could not save the role.");
        return;
      }
      setNote(editing ? "Role updated." : "Role created.");
      setEditing(null); setForm(blankRole);
      load();
    } catch { setNote("Network error."); } finally { setSaving(false); }
  };

  const remove = async (r: CustomRole) => {
    if (!confirm(`Delete the "${r.name}" role?`)) return;
    const res = await fetch(`${api}/api/custom-roles/${r.id}/`, { method: "DELETE", headers: authJson() });
    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      setNote(d.error || "Could not delete the role.");
      return;
    }
    if (editing?.id === r.id) startNew();
    load();
  };

  if (loading) return (
    <div className="bg-white rounded-2xl border border-slate-100 p-12 flex justify-center">
      <div className="w-7 h-7 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
    </div>
  );

  const byGroup = (perms: Perm[]) => {
    const out: Record<string, Perm[]> = {};
    perms.forEach(p => { if (!out[p.group]) out[p.group] = []; out[p.group].push(p); });
    return out;
  };

  return (
    <div className="space-y-5">
      {note && <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl text-sm text-slate-600">{note}</div>}

      {/* Existing roles */}
      <div className="bg-white rounded-2xl border border-slate-100 overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between gap-3">
          <div className="min-w-0">
            <h3 className="text-base font-bold text-slate-900">Custom user types</h3>
            <p className="text-xs text-slate-400 mt-0.5">Assign one from Team by choosing the &ldquo;Custom Role&rdquo; user type.</p>
          </div>
          {isAdmin && (
            <button type="button" onClick={startNew}
              className="px-4 py-2 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 transition-colors flex-shrink-0">
              New role
            </button>
          )}
        </div>
        {roles.length === 0 ? (
          <p className="px-6 py-10 text-center text-sm text-slate-400">No custom roles yet.</p>
        ) : (
          <ul className="divide-y divide-slate-50">
            {roles.map(r => (
              <li key={r.id} className="px-6 py-4 flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-sm font-bold text-slate-900 truncate">{r.name}</p>
                    {!r.is_active && <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded-full bg-slate-100 text-slate-500">Inactive</span>}
                    <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700">
                      {r.permissions.length} permission{r.permissions.length === 1 ? "" : "s"}
                    </span>
                    <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded-full bg-slate-100 text-slate-500">
                      {r.member_count} user{r.member_count === 1 ? "" : "s"}
                    </span>
                  </div>
                  {r.description && <p className="text-xs text-slate-400 mt-0.5 truncate">{r.description}</p>}
                </div>
                {isAdmin && (
                  <div className="flex items-center gap-3 flex-shrink-0">
                    <button type="button" onClick={() => startEdit(r)} className="text-sm font-semibold text-indigo-600 hover:text-indigo-800">Edit</button>
                    <button type="button" onClick={() => remove(r)} className="text-sm font-semibold text-rose-600 hover:text-rose-800">Delete</button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Builder */}
      {isAdmin && (
        <form onSubmit={save} className="bg-white rounded-2xl border border-slate-100 p-6 space-y-5">
          <h3 className="text-base font-bold text-slate-900">
            {editing ? `Edit ${editing.name}` : "Create a user type"}
          </h3>

          <div className="grid sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-1.5">Role name *</label>
              <input required value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}
                placeholder="e.g. Site Supervisor" className={FIELD} />
            </div>
            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-1.5">Description</label>
              <input value={form.description} onChange={e => setForm({ ...form, description: e.target.value })}
                placeholder="What this user type is for" className={FIELD} />
            </div>
          </div>

          <label className="flex items-center gap-2 text-sm font-semibold text-slate-600">
            <input type="checkbox" checked={form.is_active} onChange={e => setForm({ ...form, is_active: e.target.checked })}
              className="w-4 h-4 rounded accent-indigo-600" />
            Active
            <span className="font-normal text-xs text-slate-400">— switching this off removes access for everyone on the role.</span>
          </label>

          {(["modules", "capabilities"] as const).map(kind => (
            <div key={kind}>
              <p className="text-sm font-bold text-slate-800 mb-2">
                {kind === "modules" ? "Modules they can open" : "What they can do"}
              </p>
              {kind === "modules" && (
                <p className="-mt-1 mb-2 text-xs text-slate-400">
                  Tasks and Referral Rewards are not listed: every user has them.
                </p>
              )}
              <div className="space-y-3">
                {Object.entries(byGroup(catalog?.[kind] || [])).map(([group, perms]) => {
                  const all = perms.every(p => form.permissions.includes(p.key));
                  return (
                    <div key={group} className="border border-slate-100 rounded-xl p-3">
                      <div className="flex items-center justify-between mb-2">
                        <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">{group}</p>
                        <button type="button" onClick={() => toggleGroup(perms, !all)}
                          className="text-[11px] font-semibold text-indigo-600 hover:text-indigo-800">
                          {all ? "Clear all" : "Select all"}
                        </button>
                      </div>
                      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2">
                        {perms.map(p => (
                          <label key={p.key} className="flex items-center gap-2 text-[13px] text-slate-600 cursor-pointer">
                            <input type="checkbox" checked={form.permissions.includes(p.key)} onChange={() => toggle(p.key)}
                              className="w-4 h-4 rounded accent-indigo-600 flex-shrink-0" />
                            <span className="truncate" title={p.key}>{p.label}</span>
                          </label>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}

          <div className="flex items-center justify-end gap-3 pt-2">
            <span className="text-xs text-slate-400 mr-auto">{form.permissions.length} selected</span>
            {editing && (
              <button type="button" onClick={startNew}
                className="px-4 py-2.5 text-sm font-semibold text-slate-600 hover:bg-slate-50 rounded-xl transition-colors">
                Cancel
              </button>
            )}
            <button type="submit" disabled={saving}
              className="px-6 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-bold hover:bg-indigo-700 disabled:opacity-50 transition-colors">
              {saving ? "Saving…" : editing ? "Save role" : "Create role"}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}

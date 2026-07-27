"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";
import Avatar from "@/components/Avatar";

import React, { useState, useEffect, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";

// ─── Icons ────────────────────────────────────────────────────────────────────
const I = {
  Plus:  () => <svg width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>,
  Edit:  () => <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>,
  Trash: () => <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4a1 1 0 011-1h4a1 1 0 011 1v2"/></svg>,
  X:     () => <svg width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg>,
  Users: () => <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87"/><path d="M16 3.13a4 4 0 010 7.75"/></svg>,
  Team:  () => <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" viewBox="0 0 24 24"><rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 21V5a2 2 0 00-2-2h-4a2 2 0 00-2 2v16"/></svg>,
  ChevronDown: () => <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><polyline points="6 9 12 15 18 9"/></svg>,
};

const gradients = [
  "from-indigo-500 to-violet-600",
  "from-cyan-500 to-blue-600",
  "from-emerald-500 to-teal-600",
  "from-amber-500 to-orange-600",
  "from-pink-500 to-rose-600",
];

const ROLES = [
  { value: "tele_caller", label: "Tele Caller" },
  { value: "bde", label: "BDE" },
  { value: "branch_manager", label: "Branch Manager" },
  { value: "sales_manager", label: "Sales Manager" },
  { value: "documentation_staff", label: "Documentation Staff" },
  { value: "documentation_manager", label: "Documentation Manager" },
  { value: "accounts_staff", label: "Accounts Staff" },
  { value: "purchase_staff", label: "Purchase Staff" },
  { value: "project_manager", label: "Project Manager" },
  { value: "liasoning_officer", label: "Liasoning Officer" },
  { value: "store_manager", label: "Store Manager" },
  { value: "store_keeper", label: "Store Keeper" },
  { value: "accounts_b2b", label: "Accounts B2B" },
  { value: "custom", label: "Custom Role" },
  { value: "coo", label: "COO" },
  { value: "admin", label: "Admin" },
  { value: "superadmin", label: "Super Admin" },
];
// Wholesale-side roles. They live in their own roster: the B2B Team module
// lists them, the CRM's Team module doesn't. Mirrors users.models.B2B_ONLY_ROLES.
const B2B_ONLY_ROLES = ["store_manager", "store_keeper", "accounts_b2b"];

const ROLE_COLORS: Record<string, { bg: string; text: string }> = {
  superadmin: { bg: "bg-violet-50", text: "text-violet-700" },
  admin: { bg: "bg-violet-50", text: "text-violet-700" },
  coo: { bg: "bg-purple-50", text: "text-purple-700" },
  sales_manager: { bg: "bg-blue-50", text: "text-blue-700" },
  documentation_manager: { bg: "bg-blue-50", text: "text-blue-700" },
  branch_manager: { bg: "bg-cyan-50", text: "text-cyan-700" },
  documentation_staff: { bg: "bg-emerald-50", text: "text-emerald-700" },
  accounts_staff: { bg: "bg-teal-50", text: "text-teal-700" },
  purchase_staff: { bg: "bg-orange-50", text: "text-orange-700" },
  project_manager: { bg: "bg-indigo-50", text: "text-indigo-700" },
  liasoning_officer: { bg: "bg-purple-50", text: "text-purple-700" },
  store_manager: { bg: "bg-amber-50", text: "text-amber-700" },
  store_keeper: { bg: "bg-amber-50", text: "text-amber-700" },
  accounts_b2b: { bg: "bg-amber-50", text: "text-amber-700" },
  custom: { bg: "bg-fuchsia-50", text: "text-fuchsia-700" },
  bde: { bg: "bg-slate-100", text: "text-slate-600" },
  tele_caller: { bg: "bg-slate-100", text: "text-slate-600" },
};
const roleBadge = (u: any) => {
  const label = u.role_label || ROLES.find(r => r.value === u.role)?.label || "—";
  const c = ROLE_COLORS[u.role] || { bg: "bg-slate-100", text: "text-slate-600" };
  return { label, bg: c.bg, text: c.text };
};

// ─── Modal wrapper ─────────────────────────────────────────────────────────
const Modal = ({ show, onClose, title, subtitle, children, footer }: any) => show ? (
  <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/40 backdrop-blur-sm" onClick={onClose}>
    <div className="bg-white w-full sm:max-w-lg sm:mx-4 rounded-t-2xl sm:rounded-2xl shadow-2xl max-h-[90vh] overflow-hidden flex flex-col" onClick={(e: any) => e.stopPropagation()}>
      <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 flex-shrink-0">
        <div><h2 className="text-base font-bold text-slate-900">{title}</h2><p className="text-xs text-slate-400 mt-0.5">{subtitle}</p></div>
        <button onClick={onClose} className="w-8 h-8 flex items-center justify-center rounded-xl bg-slate-100 text-slate-500 hover:bg-slate-200 transition-all"><I.X /></button>
      </div>
      <div className="overflow-y-auto flex-1 px-6 py-5">{children}</div>
      <div className="px-6 py-4 border-t border-slate-100 flex-shrink-0">{footer}</div>
    </div>
  </div>
) : null;

function TeamPageInner() {
  const domain = APP_SLUG as string;
  const router = useRouter();
  const searchParams = useSearchParams();

  const [team, setTeam] = useState<any[]>([]);
  const [workspaceTeams, setWorkspaceTeams] = useState<any[]>([]);
  const [branches, setBranches] = useState<any[]>([]);
  const [currentUser, setCurrentUser] = useState<any>(null);
  // Roles this user may grant (null until loaded = no filtering yet).
  const [assignableRoles, setAssignableRoles] = useState<string[] | null>(null);
  // Custom user types defined in Settings → Roles & Permissions.
  const [customRoles, setCustomRoles] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<"members" | "teams">("members");
  const [showModal, setShowModal] = useState(false);
  const [maxUsers, setMaxUsers] = useState(10);
  const [editingUser, setEditingUser] = useState<any>(null);
  const [showTeamModal, setShowTeamModal] = useState(false);
  const [editingTeam, setEditingTeam] = useState<any>(null);
  const [telephonyProvider, setTelephonyProvider] = useState("voxbay");
  // B2B staff always see the wholesale roster; an admin sees whichever side the
  // sidebar switch is on.
  const [segment, setSegment] = useState<"b2c" | "b2b">("b2c");
  const [avatarBusy, setAvatarBusy] = useState(false);
  const avatarInput = React.useRef<HTMLInputElement>(null);
  const isB2B = segment === "b2b";

  const blankForm = { username: "", first_name: "", last_name: "", email: "", password: "", role: "tele_caller", custom_role: "" as string | number, team: "" as string | number, branch: "" as string | number, phone: "", voxbay_extension: "" };
  const [form, setForm] = useState(blankForm);

  const blankTeamForm = { name: "", manager: "" as string | number, member_ids: [] as (string | number)[] };
  const [teamForm, setTeamForm] = useState(blankTeamForm);

  useEffect(() => { fetchTeam(); }, [domain]);

  useEffect(() => {
    if (searchParams.get("edit") === "me" && team.length > 0 && currentUser) {
      const me = team.find(u => u.id === currentUser.id);
      if (me) { openEditModal(me); router.replace(`/team`); }
    }
  }, [searchParams, team, currentUser]);

  const fetchTeam = async () => {
    const token = localStorage.getItem(`${domain}_access`);
    if (!token) return;
    // The backend pins B2B staff to their own roster whatever we ask for; this
    // only decides which side an admin is looking at.
    const seg = localStorage.getItem(`${domain}_biz_mode`) === "b2b" ? "b2b" : "b2c";
    const q = `?segment=${seg}`;
    try {
      const [tRes, wtRes, meRes, subRes, brRes, arRes, crRes] = await Promise.all([
        fetch(`${getApiBase(domain)}/api/users/${q}`, { headers: { Authorization: `Bearer ${token}` } }),
        fetch(`${getApiBase(domain)}/api/teams/`, { headers: { Authorization: `Bearer ${token}` } }),
        fetch(`${getApiBase(domain)}/api/users/me/`, { headers: { Authorization: `Bearer ${token}` } }),
        fetch(`${getApiBase(domain)}/api/subscription/`, { headers: { Authorization: `Bearer ${token}` } }),
        fetch(`${getApiBase(domain)}/api/branches/`, { headers: { Authorization: `Bearer ${token}` } }),
        fetch(`${getApiBase(domain)}/api/users/assignable-roles/${q}`, { headers: { Authorization: `Bearer ${token}` } }),
        fetch(`${getApiBase(domain)}/api/custom-roles/`, { headers: { Authorization: `Bearer ${token}` } }),
      ]);
      const tData = await tRes.json(); setTeam(Array.isArray(tData) ? tData : tData.results || []);
      const wtData = await wtRes.json(); setWorkspaceTeams(Array.isArray(wtData) ? wtData : wtData.results || []);
      if (brRes.ok) { const brData = await brRes.json(); setBranches(Array.isArray(brData) ? brData : brData.results || []); }
      if (meRes.ok) {
        const me = await meRes.json();
        setCurrentUser(me);
        setSegment(B2B_ONLY_ROLES.includes(me.role) ? "b2b" : (seg as "b2c" | "b2b"));
      }
      if (arRes.ok) { const ar = await arRes.json(); if (Array.isArray(ar)) setAssignableRoles(ar.map((r: any) => r.value)); }
      if (crRes.ok) { const cr = await crRes.json(); setCustomRoles((Array.isArray(cr) ? cr : cr.results || []).filter((r: any) => r.is_active)); }
      if (subRes.ok) {
        const subData = await subRes.json();
        setMaxUsers(subData.max_users || 10);
        setTelephonyProvider(subData.telephony_provider || "voxbay");
      }
    } catch {} finally { setLoading(false); }
  };

  // The picture is stored the moment it's chosen (its own multipart endpoint),
  // rather than waiting for Save Changes with the rest of the JSON form.
  const uploadAvatar = async (file: File) => {
    if (!editingUser) return;
    setAvatarBusy(true);
    const token = localStorage.getItem(`${domain}_access`);
    const body = new FormData();
    body.append("avatar", file);
    try {
      const r = await fetch(`${getApiBase(domain)}/api/users/${editingUser.id}/avatar/`, {
        method: "POST", headers: { Authorization: `Bearer ${token}` }, body,
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) { alert(d.avatar?.[0] || d.detail || d.error || "Could not upload the picture."); return; }
      setEditingUser(d);
      fetchTeam();
    } catch { alert("Network error while uploading the picture."); }
    finally { setAvatarBusy(false); if (avatarInput.current) avatarInput.current.value = ""; }
  };

  const removeAvatar = async () => {
    if (!editingUser?.avatar_url) return;
    setAvatarBusy(true);
    const token = localStorage.getItem(`${domain}_access`);
    try {
      const r = await fetch(`${getApiBase(domain)}/api/users/${editingUser.id}/avatar/`, {
        method: "DELETE", headers: { Authorization: `Bearer ${token}` },
      });
      if (r.ok) { setEditingUser(await r.json()); fetchTeam(); }
    } catch {} finally { setAvatarBusy(false); }
  };

  const openEditModal = (user: any) => {
    setEditingUser(user);
    setForm({ username: user.username, first_name: user.first_name || "", last_name: user.last_name || "", email: user.email || "", password: "", role: user.role || "tele_caller", custom_role: user.custom_role || "", team: user.team || "", branch: user.branch || "", phone: user.phone || "", voxbay_extension: user.voxbay_extension || "" });
    setShowModal(true);
  };

  const addBranch = async () => {
    const name = window.prompt("New branch name:");
    if (!name || !name.trim()) return;
    const token = localStorage.getItem(`${domain}_access`);
    try {
      const r = await fetch(`${getApiBase(domain)}/api/branches/`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ name: name.trim() }),
      });
      if (r.ok) {
        const b = await r.json();
        setBranches(prev => [...prev, b]);
        setForm(f => ({ ...f, branch: b.id }));
      } else { alert("Failed to create branch."); }
    } catch { alert("Network error creating branch."); }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const token = localStorage.getItem(`${domain}_access`);
    const payload: any = { ...form };
    if (!form.password) delete payload.password;
    payload.team = form.team || null;       // "" -> null for the FK
    payload.branch = form.branch || null;
    // Only meaningful on the custom user type; clear it otherwise so a role
    // change doesn't leave a stale permission set attached.
    payload.custom_role = form.role === "custom" ? (form.custom_role || null) : null;
    const method = editingUser ? "PATCH" : "POST";
    const url = editingUser ? `${getApiBase(domain)}/api/users/${editingUser.id}/` : `${getApiBase(domain)}/api/users/`;
    try {
      const r = await fetch(url, { method, headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify(payload) });
      if (r.ok) { setShowModal(false); setEditingUser(null); setForm(blankForm); fetchTeam(); }
      else { const err = await r.json(); alert(err.detail || JSON.stringify(err)); }
    } catch {}
  };

  const deleteUser = async (id: number) => {
    if (!confirm("Remove this team member?")) return;
    const token = localStorage.getItem(`${domain}_access`);
    const r = await fetch(`${getApiBase(domain)}/api/users/${id}/`, { method: "DELETE", headers: { Authorization: `Bearer ${token}` } });
    // Surface refusals (e.g. removing a peer admin) instead of failing silently.
    if (!r.ok) { try { const e = await r.json(); alert(e.detail || "Could not remove this member."); } catch { alert("Could not remove this member."); } }
    fetchTeam();
  };

  const handleTeamSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const token = localStorage.getItem(`${domain}_access`);
    const method = editingTeam ? "PATCH" : "POST";
    const url = editingTeam ? `${getApiBase(domain)}/api/teams/${editingTeam.id}/` : `${getApiBase(domain)}/api/teams/`;
    const r = await fetch(url, { method, headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify({ name: teamForm.name, manager: teamForm.manager || null, member_ids: teamForm.member_ids }) });
    if (r.ok) { setShowTeamModal(false); setEditingTeam(null); setTeamForm(blankTeamForm); fetchTeam(); }
  };

  const openEditTeamModal = (t: any) => {
    setEditingTeam(t);
    setTeamForm({ name: t.name, manager: t.manager || "", member_ids: t.members_detail?.map((m: any) => m.id) || [] });
    setShowTeamModal(true);
  };

  const deleteTeam = async (id: number) => {
    if (!confirm("Delete team?")) return;
    const token = localStorage.getItem(`${domain}_access`);
    await fetch(`${getApiBase(domain)}/api/teams/${id}/`, { method: "DELETE", headers: { Authorization: `Bearer ${token}` } });
    fetchTeam();
  };

  if (loading) return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="text-center"><div className="w-8 h-8 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin mx-auto mb-3" /><p className="text-sm text-slate-400">Loading team...</p></div>
    </div>
  );

  const isAdminOrGM = currentUser?.is_staff || currentUser?.is_general_manager;

  // Agent / manager view: surface the current user's team manager.
  const myTeam = workspaceTeams.find((t) => t.id === currentUser?.team);
  const myManager = myTeam?.manager_detail;
  const showManagerCard = !isAdminOrGM && myManager && myManager.id !== currentUser?.id;

  return (
    <div className="min-h-screen bg-[#f5f7fb]">
      {/* ── Header ── */}
      <div className="bg-white border-b border-slate-200/60 sticky top-0 z-20">
        <div className="max-w-[1200px] mx-auto px-4 sm:px-6 xl:px-8 py-3 sm:py-0 min-h-[4rem] flex justify-center flex-col">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
            <div className="flex items-center gap-6">
              <div>
                <h1 className="text-lg font-bold text-slate-900">{isB2B ? "B2B Team" : isAdminOrGM ? "Team" : "My Team"}</h1>
                <p className="text-[11px] text-slate-400 mt-0.5">{team.length} members</p>
              </div>
              {/* Tabs - only show for admin/GM. Workspace teams are a sales-side
                  concept, so the wholesale roster is a flat member list. */}
              {isAdminOrGM && !isB2B && (
              <div className="flex items-center gap-1 bg-slate-100 rounded-xl p-1 w-full sm:w-auto overflow-x-auto no-scrollbar">
                {([["members", "Members", <I.Users key="u" />], ["teams", "Teams", <I.Team key="t" />]] as [string, string, React.ReactNode][]).map(([id, label, icon]) => (
                  <button key={id} onClick={() => setActiveTab(id as any)} className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${activeTab === id ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}>
                    {icon}<span className="hidden sm:inline">{label}</span>
                  </button>
                ))}
              </div>
              )}
            </div>
            {(currentUser?.is_staff || currentUser?.is_general_manager) && (
              <button
                onClick={() => activeTab === "members"
                  ? (currentUser?.is_staff
                    ? (setEditingUser(null), setForm({ ...blankForm, role: isB2B ? "store_keeper" : blankForm.role }), setShowModal(true))
                    : alert("Only admins can create new users."))
                  : (setEditingTeam(null), setTeamForm(blankTeamForm), setShowTeamModal(true))}
                className="flex items-center justify-center gap-1.5 px-4 py-2 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 transition-all shadow-sm shadow-indigo-200 w-full sm:w-auto"
              >
                <I.Plus /> <span className="hidden sm:inline">{activeTab === "members" ? "Add Member" : "Create Team"}</span>
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="max-w-[1200px] mx-auto px-4 sm:px-6 xl:px-8 py-6">
        {/* ── Your Manager (agent / non-admin view) ── */}
        {showManagerCard && (
          <div className="bg-white border border-slate-100 rounded-2xl p-5 mb-6 shadow-sm relative overflow-hidden">
            <div className="absolute left-0 top-0 bottom-0 w-1 bg-gradient-to-b from-indigo-500 to-violet-600" />
            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-3">Your Manager</p>
            <div className="flex items-center gap-4">
              <Avatar name={myManager.first_name || myManager.username} url={myManager.avatar_url}
                size={48} className="shadow-sm" textClass="text-base" />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <h3 className="text-sm font-bold text-slate-900 truncate">{myManager.first_name} {myManager.last_name || myManager.username}</h3>
                  <span className={`inline-flex text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ${roleBadge(myManager).bg} ${roleBadge(myManager).text}`}>{roleBadge(myManager).label}</span>
                </div>
                <p className="text-xs text-slate-400 truncate">{myManager.email || `@${myManager.username}`}</p>
                {(myManager.phone || (telephonyProvider === "voxbay" && myManager.voxbay_extension)) && (
                  <p className="text-[10px] text-indigo-500 mt-1 font-mono">
                    {myManager.phone && `📞 ${myManager.phone}`}
                    {myManager.phone && telephonyProvider === "voxbay" && myManager.voxbay_extension && " | "}
                    {telephonyProvider === "voxbay" && myManager.voxbay_extension && `Ext: ${myManager.voxbay_extension}`}
                  </p>
                )}
              </div>
              {myManager.email && (
                <a href={`mailto:${myManager.email}`} className="hidden sm:inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-indigo-50 text-indigo-600 text-xs font-semibold hover:bg-indigo-100 transition-all flex-shrink-0">
                  Contact
                </a>
              )}
            </div>
          </div>
        )}

        {/* ── Members Grid ── */}
        {activeTab === "members" && (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {team.map((member, i) => {
              const role = roleBadge(member);
              const teamName = workspaceTeams.find(t => t.id === member.team)?.name;
              return (
                <div key={member.id} className="bg-white border border-slate-100 rounded-2xl p-5 shadow-sm hover:shadow-md transition-all group">
                  <div className="flex items-start justify-between mb-4">
                    <div className="flex items-center gap-3">
                      <Avatar name={member.first_name || member.username} url={member.avatar_url}
                        size={44} className="shadow-sm" textClass="text-sm" />
                      <div className="min-w-0">
                        <h3 className="text-sm font-bold text-slate-900 truncate">{member.first_name} {member.last_name || member.username}</h3>
                        <p className="text-xs text-slate-400 truncate">{member.email || `@${member.username}`}</p>
                        {(member.phone || (telephonyProvider === "voxbay" && member.voxbay_extension)) && (
                          <p className="text-[10px] text-indigo-500 mt-1 font-mono">
                            {member.phone && `📞 ${member.phone}`}
                            {member.phone && telephonyProvider === "voxbay" && member.voxbay_extension && " | "}
                            {telephonyProvider === "voxbay" && member.voxbay_extension && `Ext: ${member.voxbay_extension}`}
                          </p>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      {/* can_manage comes from the API: your own profile, or an
                          account below you in the hierarchy. */}
                      {member.can_manage && (
                        <button onClick={() => openEditModal(member)} className="w-7 h-7 flex items-center justify-center rounded-lg text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 transition-all"><I.Edit /></button>
                      )}
                      {currentUser?.is_staff && member.can_manage && member.id !== currentUser?.id && (
                        <button onClick={() => deleteUser(member.id)} className="w-7 h-7 flex items-center justify-center rounded-lg text-slate-400 hover:text-red-500 hover:bg-red-50 transition-all"><I.Trash /></button>
                      )}
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2 pt-4 border-t border-slate-50">
                    <span className={`inline-flex text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full ${role.bg} ${role.text}`}>{role.label}</span>
                    {member.branch_name && <span className="inline-flex text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full bg-amber-50 text-amber-700">{member.branch_name}</span>}
                    {teamName && <span className="inline-flex text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full bg-indigo-50 text-indigo-600">{teamName}</span>}
                    <span className="ml-auto text-[10px] text-slate-400 font-mono">@{member.username}</span>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* ── Teams Grid ── */}
        {activeTab === "teams" && (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {workspaceTeams.length === 0 && (
              <div className="col-span-full py-20 flex flex-col items-center text-center text-slate-400">
                <div className="w-14 h-14 bg-slate-100 rounded-2xl flex items-center justify-center mb-4"><I.Team /></div>
                <p className="text-base font-semibold text-slate-700 mb-1">No teams yet</p>
                <p className="text-sm">Create a team to organize your members</p>
              </div>
            )}
            {workspaceTeams.map(wt => {
              const mgr = team.find(u => u.id === wt.manager);
              const members = wt.members_detail || [];
              return (
                <div key={wt.id} onClick={() => openEditTeamModal(wt)} className="bg-white border border-slate-100 rounded-2xl p-5 shadow-sm hover:shadow-md hover:border-indigo-200 transition-all cursor-pointer group">
                  <div className="flex items-start justify-between mb-4">
                    <div>
                      <h3 className="text-sm font-bold text-slate-900 group-hover:text-indigo-600 transition-colors">{wt.name}</h3>
                      <p className="text-[10px] text-slate-400 mt-0.5">{members.length} members</p>
                    </div>
                    {(currentUser?.is_staff || currentUser?.is_general_manager) && (
                      <button onClick={e => { e.stopPropagation(); deleteTeam(wt.id); }} className="w-7 h-7 flex items-center justify-center rounded-lg text-slate-300 hover:text-red-500 hover:bg-red-50 transition-all opacity-0 group-hover:opacity-100">
                        <I.Trash />
                      </button>
                    )}
                  </div>

                  {/* Manager */}
                  <div className="bg-slate-50 rounded-xl p-3 mb-3">
                    <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-widest mb-2">Manager</p>
                    <div className="flex items-center gap-2">
                      <div className="w-6 h-6 rounded-full bg-indigo-600 text-white flex items-center justify-center text-[10px] font-bold flex-shrink-0">
                        {mgr?.first_name?.charAt(0)?.toUpperCase() || "?"}
                      </div>
                      <span className="text-xs font-medium text-slate-700">{mgr ? `${mgr.first_name} ${mgr.last_name}` : "None assigned"}</span>
                    </div>
                  </div>

                  {/* Members avatars */}
                  <div>
                    <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-widest mb-2">Members</p>
                    <div className="flex flex-wrap gap-1.5">
                      {members.slice(0, 6).map((m: any, i: number) => (
                        <Avatar key={m.id} name={m.first_name || m.username} url={m.avatar_url} size={28}
                          ring="ring-2 ring-white" textClass="text-[10px]" />
                      ))}
                      {members.length > 6 && <div className="w-7 h-7 rounded-full bg-slate-100 flex items-center justify-center text-[10px] font-bold text-slate-400 ring-2 ring-white">+{members.length - 6}</div>}
                      {members.length === 0 && <span className="text-xs text-slate-400">No members assigned</span>}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* ── Member Modal ─────────────────────────────────────────────────────── */}
      <Modal show={showModal} onClose={() => setShowModal(false)} title={editingUser ? "Edit Member" : "Add Member"} subtitle={editingUser ? "Update profile details" : "Invite a new team member"}
        footer={
          <div className="flex gap-3">
            <button onClick={() => setShowModal(false)} className="flex-1 py-2.5 border border-slate-200 rounded-xl text-sm font-semibold text-slate-600 hover:bg-slate-50 transition-all">Cancel</button>
            <button onClick={(e: any) => handleSubmit(e)} className="flex-1 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 transition-all shadow-sm shadow-indigo-200">{editingUser ? "Save Changes" : "Add Member"}</button>
          </div>
        }
      >
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Profile picture. Only offered on an existing account — a new one has
              no id yet to attach the upload to. */}
          {editingUser && (
            <div className="flex items-center gap-4 pb-4 border-b border-slate-100">
              <Avatar name={form.first_name || form.username} url={editingUser.avatar_url}
                size={64} textClass="text-xl" />
              <div className="min-w-0">
                <p className="text-xs font-semibold text-slate-600 mb-1.5">Profile Picture</p>
                <div className="flex items-center gap-2">
                  <button type="button" disabled={avatarBusy} onClick={() => avatarInput.current?.click()}
                    className="px-3 py-1.5 rounded-xl bg-indigo-50 text-indigo-700 text-xs font-semibold hover:bg-indigo-100 disabled:opacity-50 transition-all">
                    {avatarBusy ? "Uploading…" : editingUser.avatar_url ? "Change" : "Upload"}
                  </button>
                  {editingUser.avatar_url && (
                    <button type="button" disabled={avatarBusy} onClick={removeAvatar}
                      className="px-3 py-1.5 rounded-xl text-slate-500 text-xs font-semibold hover:bg-rose-50 hover:text-rose-600 disabled:opacity-50 transition-all">
                      Remove
                    </button>
                  )}
                </div>
                <p className="text-[10px] text-slate-400 mt-1.5">JPEG, PNG, WebP or GIF · up to 5 MB</p>
                <input ref={avatarInput} type="file" accept="image/jpeg,image/png,image/webp,image/gif"
                  className="hidden"
                  onChange={e => { const f = e.target.files?.[0]; if (f) uploadAvatar(f); }} />
              </div>
            </div>
          )}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div><label className="block text-xs font-semibold text-slate-600 mb-1.5">First Name</label><input required value={form.first_name} onChange={e => setForm({...form, first_name: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all" /></div>
            <div><label className="block text-xs font-semibold text-slate-600 mb-1.5">Last Name</label><input required value={form.last_name} onChange={e => setForm({...form, last_name: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all" /></div>
          </div>
          {/* The login name is issued by the company: only an Admin or Super Admin
              can change it, so everyone else sees it read-only. */}
          <div><label className="block text-xs font-semibold text-slate-600 mb-1.5">Username *</label><input required readOnly={!!editingUser && !currentUser?.is_staff} title={!!editingUser && !currentUser?.is_staff ? "Only an Admin or Super Admin can change a username." : undefined} value={form.username} onChange={e => setForm({...form, username: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all read-only:opacity-60 read-only:cursor-not-allowed" /></div>
          <div><label className="block text-xs font-semibold text-slate-600 mb-1.5">Email Address</label><input type="email" required value={form.email} onChange={e => setForm({...form, email: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all" /></div>
          <div><label className="block text-xs font-semibold text-slate-600 mb-1.5">{editingUser ? "New Password (leave blank to keep)" : "Password *"}</label><input required={!editingUser} type="password" value={form.password} onChange={e => setForm({...form, password: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all" /></div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className={telephonyProvider === "voxbay" ? "" : "col-span-2"}>
              <label className="block text-xs font-semibold text-slate-600 mb-1.5">Phone Number</label>
              <input value={form.phone} onChange={e => setForm({...form, phone: e.target.value})} placeholder="e.g. +919876543210" className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all" />
            </div>
            {telephonyProvider === "voxbay" && (
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1.5">Voxbay Extension</label>
                <input value={form.voxbay_extension} onChange={e => setForm({...form, voxbay_extension: e.target.value})} placeholder="e.g. 101" className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all" />
              </div>
            )}
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1.5">Role</label>
              <div className="relative">
                <select disabled={!currentUser?.is_staff && !currentUser?.is_general_manager} value={form.role} onChange={e => setForm({...form, role: e.target.value})} className="w-full appearance-none bg-slate-50 border border-slate-200 rounded-xl pl-4 pr-8 py-2.5 text-sm font-medium outline-none focus:ring-2 focus:ring-indigo-500/20 cursor-pointer disabled:opacity-60 transition-all">
                  {/* Only roles below the current user's own — appointing an
                      admin is a Super Admin's job. */}
                  {ROLES.filter(r => assignableRoles === null || assignableRoles.includes(r.value) || r.value === form.role)
                        .map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
                </select>
                <div className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none"><I.ChevronDown /></div>
              </div>
            </div>
            {/* Which custom user type — its permission list is what this account
                can actually reach. Built in Settings → Roles & Permissions. */}
            {form.role === "custom" && (
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1.5">Custom User Type *</label>
                <div className="relative">
                  <select required disabled={!currentUser?.is_staff} value={form.custom_role}
                    onChange={e => setForm({ ...form, custom_role: e.target.value })}
                    className="w-full appearance-none bg-slate-50 border border-slate-200 rounded-xl pl-4 pr-8 py-2.5 text-sm font-medium outline-none focus:ring-2 focus:ring-indigo-500/20 cursor-pointer disabled:opacity-60 transition-all">
                    <option value="">Select a role…</option>
                    {customRoles.map(r => <option key={r.id} value={r.id}>{r.name} ({r.permissions.length} permissions)</option>)}
                  </select>
                  <div className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none"><I.ChevronDown /></div>
                </div>
                {customRoles.length === 0 && (
                  <p className="text-[10px] text-amber-600 mt-1">No custom roles yet — create one in Settings → Roles &amp; Permissions.</p>
                )}
              </div>
            )}
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1.5">Assign Team</label>
              <div className="relative">
                <select disabled={!currentUser?.is_staff && !currentUser?.is_general_manager} value={form.team} onChange={e => setForm({...form, team: e.target.value})} className="w-full appearance-none bg-slate-50 border border-slate-200 rounded-xl pl-4 pr-8 py-2.5 text-sm font-medium outline-none focus:ring-2 focus:ring-indigo-500/20 cursor-pointer disabled:opacity-60 transition-all">
                  <option value="">No Team</option>{workspaceTeams.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>
                <div className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none"><I.ChevronDown /></div>
              </div>
            </div>
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="block text-xs font-semibold text-slate-600">Branch</label>
                {currentUser?.is_staff && (
                  <button type="button" onClick={addBranch} className="text-[11px] font-semibold text-indigo-600 hover:text-indigo-800">+ New branch</button>
                )}
              </div>
              <div className="relative">
                <select disabled={!currentUser?.is_staff && !currentUser?.is_general_manager} value={form.branch} onChange={e => setForm({...form, branch: e.target.value})} className="w-full appearance-none bg-slate-50 border border-slate-200 rounded-xl pl-4 pr-8 py-2.5 text-sm font-medium outline-none focus:ring-2 focus:ring-indigo-500/20 cursor-pointer disabled:opacity-60 transition-all">
                  <option value="">No Branch</option>{branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
                </select>
                <div className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none"><I.ChevronDown /></div>
              </div>
            </div>
          </div>
        </form>
      </Modal>

      {/* ── Team Modal ───────────────────────────────────────────────────────── */}
      <Modal show={showTeamModal} onClose={() => setShowTeamModal(false)} title={editingTeam ? "Edit Team" : "Create Team"} subtitle="Manage team composition and leadership"
        footer={
          <div className="flex gap-3">
            <button onClick={() => setShowTeamModal(false)} className="flex-1 py-2.5 border border-slate-200 rounded-xl text-sm font-semibold text-slate-600 hover:bg-slate-50 transition-all">Cancel</button>
            <button onClick={(e: any) => handleTeamSubmit(e)} className="flex-1 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 transition-all shadow-sm shadow-indigo-200">{editingTeam ? "Save Changes" : "Create Team"}</button>
          </div>
        }
      >
        <form onSubmit={handleTeamSubmit} className="space-y-5">
          <div><label className="block text-xs font-semibold text-slate-600 mb-1.5">Team Name *</label><input required value={teamForm.name} onChange={e => setTeamForm({...teamForm, name: e.target.value})} placeholder="e.g. Sales East" className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all" /></div>
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1.5">Manager</label>
            <div className="relative">
              <select required value={teamForm.manager} onChange={e => setTeamForm({...teamForm, manager: e.target.value})} className="w-full appearance-none bg-slate-50 border border-slate-200 rounded-xl pl-4 pr-8 py-2.5 text-sm font-medium outline-none focus:ring-2 focus:ring-indigo-500/20 cursor-pointer transition-all">
                <option value="">Select manager...</option>{team.filter(u => u.is_manager || u.is_staff || u.is_general_manager).map(u => <option key={u.id} value={u.id}>{u.first_name} {u.last_name} (@{u.username})</option>)}
              </select>
              <div className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none"><I.ChevronDown /></div>
            </div>
            <p className="text-[10px] text-slate-400 mt-1">Only Managers and Admins can lead teams.</p>
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1.5">Members</label>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 max-h-[200px] overflow-y-auto bg-slate-50 border border-slate-200 rounded-xl p-2">
              {team.map(u => {
                const checked = teamForm.member_ids.includes(u.id);
                return (
                  <label key={u.id} className={`flex items-center gap-2 p-2.5 rounded-lg cursor-pointer transition-all ${checked ? "bg-indigo-50 border border-indigo-100" : "bg-white border border-slate-100 hover:border-slate-200"}`}>
                    <div className={`w-4 h-4 rounded border-2 flex items-center justify-center flex-shrink-0 ${checked ? "bg-indigo-600 border-indigo-600" : "border-slate-300"}`}>
                      {checked && <svg width="9" height="9" fill="none" stroke="white" strokeWidth="3" strokeLinecap="round" viewBox="0 0 12 12"><polyline points="2 6 5 9 10 3"/></svg>}
                    </div>
                    <input type="checkbox" className="sr-only" checked={checked} onChange={e => { const ids = e.target.checked ? [...teamForm.member_ids, u.id] : teamForm.member_ids.filter(id => id !== u.id); setTeamForm({...teamForm, member_ids: ids}); }} disabled={!currentUser?.is_staff && !currentUser?.is_general_manager} />
                    <div className="min-w-0">
                      <p className="text-xs font-semibold text-slate-700 truncate">{u.first_name} {u.last_name}</p>
                      <p className="text-[10px] text-slate-400">@{u.username}</p>
                    </div>
                  </label>
                );
              })}
            </div>
          </div>
        </form>
      </Modal>
    </div>
  );
}

export default function TeamPage() {
  return (
    <Suspense fallback={null}>
      <TeamPageInner />
    </Suspense>
  );
}

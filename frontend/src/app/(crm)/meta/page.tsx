"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";

import React, { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { isSpectator } from "@/lib/spectator";
import { PageSkeleton } from "@/components/Skeleton";

// ─── Icons ────────────────────────────────────────────────────────────────────
const I = {
  Check: () => <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg>,
  Copy:  () => <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>,
  Link:  () => <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" viewBox="0 0 24 24"><path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71"/></svg>,
  Sync:  () => <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M1 4v6h6"/><path d="M3.51 15a9 9 0 102.13-9.36L1 10"/></svg>,
  Zap:   () => <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>,
  Eye:   () => <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>,
  EyeOff:() => <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>,
  AlertCircle: () => <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>,
  Plus:  () => <svg width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>,
  Trash: () => <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/><path d="M10 11v6M14 11v6"/></svg>,
  Save:  () => <svg width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>,
};

const MetaLogo = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="#1877F2">
    <path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/>
  </svg>
);

type Integration = {
  id: number;
  name: string;
  meta_verify_token: string;
  meta_access_token: string;
  meta_page_id: string;
  meta_form_id: string;
  lead_count: number;
  connected: boolean;
  // Sync state, written by the sync itself — the twelve-hourly job and the
  // Sync Now button share one clock.
  last_synced_at: string | null;
  last_sync_ok: boolean | null;
  last_sync_note: string;
  next_sync_due_at: string | null;
};

/** "3h ago" / "in 9h" — close enough for a sync clock, and short enough for a row. */
function whenRelative(iso: string | null): string {
  if (!iso) return '';
  const ms = new Date(iso).getTime() - Date.now();
  if (Number.isNaN(ms)) return '';
  const future = ms > 0;
  const mins = Math.round(Math.abs(ms) / 60000);
  if (mins < 1) return future ? 'any moment' : 'just now';
  if (mins < 60) return future ? `in ${mins}m` : `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return future ? `in ${hrs}h` : `${hrs}h ago`;
  const days = Math.round(hrs / 24);
  return future ? `in ${days}d` : `${days}d ago`;
}

type CurrentUser = { is_staff?: boolean; is_general_manager?: boolean; role?: string;
                     read_only?: boolean };

/** When the automatic sync runs. One schedule, governing every integration. */
type Schedule = {
  enabled: boolean;
  times: string[];          // "HH:MM", read in `timezone`
  timezone: string;         // IANA name
  next_due_at: string | null;
  /** Stamped every time the app looks at the clock — proof it is watching. */
  last_checked_at: string | null;
};

/* A short list rather than the full IANA set: these are the zones EnergyFox
   actually operates in or reports against, and a 400-entry dropdown on a phone
   is worse than no dropdown. */
const TIMEZONES = [
  { value: "Asia/Kolkata", label: "IST — India (Asia/Kolkata)" },
  { value: "Asia/Dubai", label: "GST — Gulf (Asia/Dubai)" },
  { value: "Asia/Singapore", label: "SGT — Singapore" },
  { value: "Europe/London", label: "UK (Europe/London)" },
  { value: "America/New_York", label: "US Eastern (America/New_York)" },
  { value: "UTC", label: "UTC" },
];

/** A scheduled instant, written in the zone it was scheduled in. */
function formatInZone(iso: string, timeZone: string): string {
  try {
    return new Date(iso).toLocaleString("en-IN", {
      timeZone, day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: true,
    });
  } catch {
    // An unknown zone must not take the page down with it.
    return new Date(iso).toLocaleString("en-IN");
  }
}

/** Mirrors MetaIntegrationAccess on the API: admins, plus the leads manager
 *  who owns where leads come from — and the spectator, who reads everything.
 *  The API already admits all three (`watches_everything` covers the last). */
const canOpenMeta = (u?: CurrentUser | null) =>
  !!(u?.is_staff || u?.role === "leads_manager" || isSpectator(u));

const inputCls =
  "w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all font-mono";

export default function MetaPage() {
  const domain = APP_SLUG;
  const router = useRouter();
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [authChecked, setAuthChecked] = useState(false);

  const [webhookUrl, setWebhookUrl] = useState("");
  const [copied, setCopied] = useState(false);
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [showTokenFor, setShowTokenFor] = useState<number | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);

  const [schedule, setSchedule] = useState<Schedule>({
    enabled: true, times: [], timezone: "Asia/Kolkata", next_due_at: null, last_checked_at: null,
  });
  const [newTime, setNewTime] = useState("");
  const [savingSchedule, setSavingSchedule] = useState(false);

  const [summary, setSummary] = useState<{
    connected: boolean;
    total_meta_leads: number;
    campaigns: Array<{ id: number | null; name: string; meta_campaign_id: string | null; status: string; leads_count: number; last_import: string | null }>;
  }>({ connected: false, total_meta_leads: 0, campaigns: [] });

  const authHeader = () => ({ Authorization: `Bearer ${localStorage.getItem(`${domain}_access`)}` });

  const fetchIntegrations = useCallback(async () => {
    try {
      const res = await fetch(`${getApiBase(domain)}/api/integration-settings/`, { headers: authHeader() });
      if (res.ok) {
        const data = await res.json();
        setIntegrations((Array.isArray(data) ? data : data.results || []).map((d: Integration) => ({
          ...d,
          meta_verify_token: d.meta_verify_token || "",
          meta_access_token: d.meta_access_token || "",
          meta_page_id: d.meta_page_id || "",
          meta_form_id: d.meta_form_id || "",
        })));
      }
    } catch { /* keep page usable */ }
  }, [domain]);

  const fetchSummary = useCallback(async () => {
    try {
      const res = await fetch(`${getApiBase(domain)}/api/integration-settings/meta_summary/`, { headers: authHeader() });
      if (res.ok) setSummary(await res.json());
    } catch { /* ignore */ }
  }, [domain]);

  const fetchSchedule = useCallback(async () => {
    try {
      const res = await fetch(`${getApiBase(domain)}/api/integration-settings/sync-schedule/`, { headers: authHeader() });
      if (res.ok) setSchedule(await res.json());
    } catch { /* keep page usable */ }
  }, [domain]);

  // Auth guard: admins and the leads manager.
  useEffect(() => {
    const token = localStorage.getItem(`${domain}_access`);
    if (!token) return;
    fetch(`${getApiBase(domain)}/api/users/me/`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.json())
      .then(d => {
        setCurrentUser(d);
        setAuthChecked(true);
        if (!canOpenMeta(d)) router.replace(`/`);
      })
      .catch(() => setAuthChecked(true));
  }, [domain, router]);

  useEffect(() => {
    if (!authChecked || !canOpenMeta(currentUser)) return;
    setWebhookUrl(`${getApiBase(domain)}/api/webhooks/meta-leads/`);
    fetchIntegrations();
    fetchSummary();
    fetchSchedule();
  }, [domain, authChecked, currentUser, fetchIntegrations, fetchSummary, fetchSchedule]);

  const flash = (kind: "ok" | "err", text: string) => {
    setMsg({ kind, text });
    setTimeout(() => setMsg(null), 4000);
  };

  const saveSchedule = async () => {
    setSavingSchedule(true);
    try {
      const res = await fetch(`${getApiBase(domain)}/api/integration-settings/sync-schedule/`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...authHeader() },
        body: JSON.stringify({ enabled: schedule.enabled, times: schedule.times, timezone: schedule.timezone }),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        setSchedule(data);
        // The rows show "next sync", which the schedule has just moved.
        await fetchIntegrations();
        flash("ok", schedule.enabled && schedule.times.length
          ? `Saved. Syncing at ${schedule.times.join(", ")} ${schedule.timezone}.`
          : "Saved.");
      } else {
        // The server is the authority on a bad time or zone; show what it said.
        const detail = data?.times?.[0] || data?.timezone?.[0] || "Could not save the schedule.";
        flash("err", String(detail));
      }
    } catch { flash("err", "Network error."); }
    finally { setSavingSchedule(false); }
  };

  const updateField = (id: number, key: keyof Integration, value: string) => {
    setIntegrations(prev => prev.map(it => (it.id === id ? { ...it, [key]: value } : it)));
  };

  const createIntegration = async () => {
    if (!newName.trim()) return;
    setCreating(true);
    try {
      const res = await fetch(`${getApiBase(domain)}/api/integration-settings/`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeader() },
        body: JSON.stringify({ name: newName.trim() }),
      });
      if (res.ok) { setNewName(""); await fetchIntegrations(); flash("ok", "Integration created. Add its credentials and Page ID."); }
      else flash("err", "Failed to create integration.");
    } catch { flash("err", "Network error."); }
    finally { setCreating(false); }
  };

  const saveIntegration = async (it: Integration) => {
    setBusyId(it.id);
    try {
      const res = await fetch(`${getApiBase(domain)}/api/integration-settings/${it.id}/`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...authHeader() },
        body: JSON.stringify({
          name: it.name,
          meta_verify_token: it.meta_verify_token,
          meta_access_token: it.meta_access_token,
          meta_page_id: it.meta_page_id,
          meta_form_id: it.meta_form_id,
        }),
      });
      if (res.ok) { await fetchIntegrations(); flash("ok", `Saved "${it.name || "integration"}".`); }
      else flash("err", "Failed to save.");
    } catch { flash("err", "Network error."); }
    finally { setBusyId(null); }
  };

  const deleteIntegration = async (it: Integration) => {
    if (!confirm(`Delete integration "${it.name || it.id}"? Leads already imported stay, but lose their integration label.`)) return;
    setBusyId(it.id);
    try {
      const res = await fetch(`${getApiBase(domain)}/api/integration-settings/${it.id}/`, { method: "DELETE", headers: authHeader() });
      if (res.ok || res.status === 204) { await fetchIntegrations(); flash("ok", "Integration deleted."); }
      else flash("err", "Failed to delete.");
    } catch { flash("err", "Network error."); }
    finally { setBusyId(null); }
  };

  const syncIntegration = async (it: Integration) => {
    setBusyId(it.id);
    try {
      const res = await fetch(`${getApiBase(domain)}/api/integration-settings/${it.id}/sync/`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeader() },
        body: JSON.stringify({ limit: 100, page_id: it.meta_page_id, form_id: it.meta_form_id }),
      });
      const data = await res.json();
      if (res.ok) { flash("ok", `${it.name || "Integration"}: imported ${data.imported || 0}, skipped ${data.skipped || 0}.`); fetchIntegrations(); fetchSummary(); }
      else flash("err", data?.errors?.[0] || "Sync failed. Check token and Page ID.");
    } catch { flash("err", "Sync failed. Please try again."); }
    finally { setBusyId(null); }
  };

  const copyWebhook = () => {
    navigator.clipboard.writeText(webhookUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (!authChecked) return <PageSkeleton />;
  if (!canOpenMeta(currentUser)) return null;

  const connectedCount = integrations.filter(i => i.connected).length;

  return (
    <div className="min-h-screen bg-[#f5f7fb]">
      {/* ── Header ── */}
      <div className="bg-white border-b border-slate-200/60 sticky-under-topbar z-20">
        <div className="max-w-[1400px] mx-auto px-4 sm:px-6 xl:px-8">
          <div className="flex items-center justify-between h-16">
            <div>
              <h1 className="text-lg font-bold text-slate-900">Meta Integrations</h1>
              <p className="text-[11px] text-slate-400 mt-0.5">One Meta Lead Ads account per branch</p>
            </div>
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-full border bg-slate-50 border-slate-100">
              <span className={`w-2 h-2 rounded-full ${connectedCount ? "bg-emerald-500 animate-pulse" : "bg-amber-500"}`} />
              <span className="text-xs font-semibold text-slate-600">{connectedCount} of {integrations.length} connected</span>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-[1400px] mx-auto px-4 sm:px-6 xl:px-8 py-6 space-y-6">

        {/* ── Flash message ── */}
        {msg && (
          <div className={`flex items-center gap-2 px-4 py-3 rounded-xl text-sm font-medium ${msg.kind === "ok" ? "bg-emerald-50 text-emerald-700 border border-emerald-100" : "bg-red-50 text-red-600 border border-red-100"}`}>
            {msg.kind === "ok" ? <I.Check /> : <I.AlertCircle />}{msg.text}
          </div>
        )}

        {/* ── Stat cards ── */}
        <div className="grid sm:grid-cols-3 gap-4">
          <div className="bg-white border border-slate-100 rounded-2xl p-5 shadow-sm flex items-center gap-3">
            <div className="w-11 h-11 bg-blue-50 rounded-xl flex items-center justify-center flex-shrink-0"><MetaLogo /></div>
            <div>
              <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-widest mb-0.5">Integrations</p>
              <p className="text-2xl font-bold text-slate-900">{integrations.length}</p>
            </div>
          </div>
          <div className="bg-white border border-slate-100 rounded-2xl p-5 shadow-sm">
            <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-widest mb-2">Imported Leads</p>
            <p className="text-3xl font-bold text-slate-900 mb-1">{summary.total_meta_leads.toLocaleString("en-IN")}</p>
            <p className="text-xs font-semibold text-emerald-600">Across all Meta accounts</p>
          </div>
          <div className="bg-white border border-slate-100 rounded-2xl p-5 shadow-sm">
            <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-widest mb-2">Campaign Groups</p>
            <p className="text-3xl font-bold text-slate-900 mb-1">{summary.campaigns.length.toLocaleString("en-IN")}</p>
            <p className="text-xs font-semibold text-emerald-600">Auto-created CRM campaigns</p>
          </div>
        </div>

        {/* ── Shared Webhook ── */}
        <div className="bg-white border border-slate-100 rounded-2xl p-5 shadow-sm">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-8 h-8 bg-indigo-50 rounded-xl flex items-center justify-center text-indigo-600"><I.Link /></div>
            <div>
              <h2 className="text-base font-bold text-slate-900">Webhook URL (shared)</h2>
              <p className="text-xs text-slate-400">Use this same URL for every Meta account — leads route by Page ID.</p>
            </div>
          </div>
          <div className="flex gap-3">
            <div className="flex-1 bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 font-mono text-xs text-slate-600 overflow-x-auto whitespace-nowrap flex items-center">{webhookUrl}</div>
            <button onClick={copyWebhook} className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold transition-all flex-shrink-0 ${copied ? "bg-emerald-600 text-white" : "bg-indigo-600 text-white hover:bg-indigo-700"}`}>
              {copied ? <I.Check /> : <I.Copy />}{copied ? "Copied!" : "Copy"}
            </button>
          </div>
        </div>

        {/* ── Automatic sync ── */}
        {/* One schedule for every integration: the times belong to the company,
            not to a particular Facebook page. */}
        <div className="bg-white border border-slate-100 rounded-2xl p-5 shadow-sm">
          <div className="flex items-start gap-3 mb-4">
            <div className="w-8 h-8 bg-indigo-50 rounded-xl flex items-center justify-center text-indigo-600"><I.Sync /></div>
            <div className="flex-1 min-w-0">
              <h2 className="text-base font-bold text-slate-900">Automatic sync</h2>
              <p className="text-xs text-slate-400">
                Leads are pulled at these times, on top of the webhook. Applies to every integration.
              </p>
            </div>
            <label className="flex items-center gap-2 text-xs font-semibold text-slate-600 cursor-pointer flex-shrink-0">
              <input
                type="checkbox"
                checked={schedule.enabled}
                onChange={e => setSchedule({ ...schedule, enabled: e.target.checked })}
                className="w-4 h-4 rounded accent-indigo-600"
              />
              {schedule.enabled ? "On" : "Off"}
            </label>
          </div>

          <div className={schedule.enabled ? "" : "opacity-50 pointer-events-none"}>
            <label className="block text-xs font-semibold text-slate-600 mb-1.5">Sync at</label>
            <div className="flex flex-wrap items-center gap-2 mb-4">
              {schedule.times.map(t => (
                <span key={t} className="inline-flex items-center gap-2 bg-indigo-50 text-indigo-700 rounded-xl pl-3 pr-2 py-1.5 text-sm font-semibold">
                  {t}
                  <button
                    onClick={() => setSchedule({ ...schedule, times: schedule.times.filter(x => x !== t) })}
                    title={`Remove ${t}`}
                    className="text-indigo-400 hover:text-red-500 font-bold leading-none"
                  >
                    ✕
                  </button>
                </span>
              ))}
              <input
                type="time"
                value={newTime}
                onChange={e => setNewTime(e.target.value)}
                className="border border-slate-200 rounded-xl px-3 py-1.5 text-sm outline-none focus:border-indigo-400"
              />
              <button
                onClick={() => {
                  if (!newTime || schedule.times.includes(newTime)) return;
                  setSchedule({ ...schedule, times: [...schedule.times, newTime].sort() });
                  setNewTime("");
                }}
                disabled={!newTime || schedule.times.includes(newTime)}
                className="px-3 py-1.5 rounded-xl text-sm font-semibold bg-slate-100 text-slate-700 hover:bg-slate-200 disabled:opacity-40"
              >
                Add time
              </button>
            </div>

            <div className="flex flex-col sm:flex-row sm:items-end gap-3">
              <div className="flex-1">
                <label className="block text-xs font-semibold text-slate-600 mb-1.5">Time zone</label>
                <select
                  value={schedule.timezone}
                  onChange={e => setSchedule({ ...schedule, timezone: e.target.value })}
                  className={inputCls}
                >
                  {TIMEZONES.map(tz => (
                    <option key={tz.value} value={tz.value}>{tz.label}</option>
                  ))}
                </select>
                <p className="text-[10px] text-slate-400 mt-1.5">
                  The times above are read in this zone, whatever the server's own clock says.
                </p>
              </div>
              <button
                onClick={saveSchedule}
                disabled={savingSchedule}
                className="flex items-center gap-1.5 px-4 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 disabled:opacity-50 transition-all flex-shrink-0"
              >
                <I.Save /> {savingSchedule ? "Saving…" : "Save schedule"}
              </button>
            </div>

            {schedule.times.length === 0 && (
              <p className="text-xs font-semibold text-amber-600 mt-3">
                No times set — nothing will sync automatically. Sync Now still works.
              </p>
            )}
            {schedule.enabled && schedule.next_due_at && (
              <p className="text-xs text-slate-500 mt-3">
                Next automatic sync <b>{formatInZone(schedule.next_due_at, schedule.timezone)}</b>.
              </p>
            )}

            {/* Whether anything is actually watching the clock. Without this,
                a schedule that never fires looks exactly like one with nothing
                due yet, and the difference is the whole problem. */}
            {schedule.enabled && (
              schedule.last_checked_at && Date.now() - new Date(schedule.last_checked_at).getTime() < 5 * 60 * 1000 ? (
                <p className="text-xs text-emerald-600 font-semibold mt-1">
                  ● Running — last checked {whenRelative(schedule.last_checked_at)}.
                </p>
              ) : (
                <p className="text-xs text-amber-600 font-semibold mt-1">
                  ● Not running — the app has {schedule.last_checked_at
                    ? `not checked since ${whenRelative(schedule.last_checked_at)}`
                    : "never checked"}. Restart the backend, or check that META_SYNC_SCHEDULER is not set to 0.
                </p>
              )
            )}
          </div>
        </div>

        {/* ── Create new integration ── */}
        <div className="bg-white border border-slate-100 rounded-2xl p-5 shadow-sm">
          <div className="flex flex-col sm:flex-row sm:items-end gap-3">
            <div className="flex-1">
              <label className="block text-xs font-semibold text-slate-600 mb-1.5">New Integration Name</label>
              <input
                value={newName}
                onChange={e => setNewName(e.target.value)}
                onKeyDown={e => { if (e.key === "Enter") createIntegration(); }}
                placeholder="e.g. Kochi Branch"
                className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all"
              />
            </div>
            <button onClick={createIntegration} disabled={creating || !newName.trim()} className="flex items-center justify-center gap-2 px-5 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 disabled:opacity-50 transition-all">
              <I.Plus /> Create Integration
            </button>
          </div>
        </div>

        {/* ── Integration cards ── */}
        {integrations.length === 0 ? (
          <div className="bg-white border border-dashed border-slate-200 rounded-2xl p-10 text-center text-sm text-slate-400">
            No integrations yet. Create one above for each branch&apos;s Meta account.
          </div>
        ) : integrations.map(it => (
          <div key={it.id} className="bg-white border border-slate-100 rounded-2xl shadow-sm overflow-hidden">
            <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
              <div className="flex items-center gap-3 min-w-0">
                <div className="w-9 h-9 bg-blue-50 rounded-xl flex items-center justify-center flex-shrink-0"><MetaLogo /></div>
                <div className="min-w-0">
                  <input
                    value={it.name}
                    onChange={e => updateField(it.id, "name", e.target.value)}
                    placeholder="Integration name"
                    className="font-bold text-slate-900 bg-transparent outline-none border-b border-transparent focus:border-indigo-300 transition-colors w-full"
                  />
                  <p className="text-[11px] text-slate-400">{it.lead_count} lead{it.lead_count === 1 ? "" : "s"} imported</p>
                </div>
              </div>
              <span className={`flex-shrink-0 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wide ${it.connected ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>
                <span className={`w-1.5 h-1.5 rounded-full ${it.connected ? "bg-emerald-500" : "bg-amber-500"}`} />
                {it.connected ? "Connected" : "Token needed"}
              </span>
            </div>

            <div className="p-5 grid md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1.5">Facebook Page ID <span className="text-red-400">*</span></label>
                <input value={it.meta_page_id} onChange={e => updateField(it.id, "meta_page_id", e.target.value)} placeholder="e.g. 123456789012345" className={inputCls} />
                <p className="text-[10px] text-slate-400 mt-1.5">Required — incoming webhook leads route to this integration by Page ID.</p>
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1.5">Verify Token</label>
                <input value={it.meta_verify_token} onChange={e => updateField(it.id, "meta_verify_token", e.target.value)} placeholder="my_webhook_secret" className={inputCls} />
                <p className="text-[10px] text-slate-400 mt-1.5">Used when Meta verifies the shared webhook URL.</p>
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1.5">Page Access Token</label>
                <div className="relative">
                  <input type={showTokenFor === it.id ? "text" : "password"} value={it.meta_access_token} onChange={e => updateField(it.id, "meta_access_token", e.target.value)} placeholder="EAAB..." className={inputCls.replace("px-4", "pl-4 pr-10")} />
                  <button onClick={() => setShowTokenFor(showTokenFor === it.id ? null : it.id)} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600">
                    {showTokenFor === it.id ? <I.EyeOff /> : <I.Eye />}
                  </button>
                </div>
                <p className="text-[10px] text-slate-400 mt-1.5">Required to fetch lead details and to Sync.</p>
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1.5">Lead Form ID</label>
                <input value={it.meta_form_id} onChange={e => updateField(it.id, "meta_form_id", e.target.value)} placeholder="Optional" className={inputCls} />
                <p className="text-[10px] text-slate-400 mt-1.5">Optional — sync one form directly.</p>
              </div>
            </div>

            <div className="flex items-center justify-between gap-3 px-5 py-4 border-t border-slate-100 bg-slate-50/40">
              <button onClick={() => deleteIntegration(it)} disabled={busyId === it.id} className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold text-red-500 hover:bg-red-50 disabled:opacity-50 transition-all">
                <I.Trash /> Delete
              </button>
              <div className="flex items-center gap-3">
                {/* What the schedule has actually been doing. Without this the
                    only way to know the twelve-hourly job is alive is to read
                    the server log. */}
                {it.connected && (
                  <p className="hidden sm:block text-[11px] text-right leading-tight">
                    {it.last_synced_at ? (
                      <>
                        <span className={it.last_sync_ok === false ? 'font-semibold text-red-600' : 'text-slate-500'}>
                          {it.last_sync_ok === false ? 'Sync failed' : 'Synced'} {whenRelative(it.last_synced_at)}
                        </span>
                        <br />
                        <span className="text-slate-400">
                          {it.last_sync_ok === false
                            ? it.last_sync_note
                            : schedule.enabled && it.next_sync_due_at
                              ? `next ${whenRelative(it.next_sync_due_at)}`
                              : "automatic sync off"}
                        </span>
                      </>
                    ) : (
                      <span className="text-slate-400">
                        {schedule.enabled && schedule.times.length
                          ? `Syncs at ${schedule.times.join(", ")} · not run yet`
                          : "Automatic sync off · not run yet"}
                      </span>
                    )}
                  </p>
                )}
                <button onClick={() => syncIntegration(it)} disabled={busyId === it.id || !it.connected} className="flex items-center gap-1.5 px-3.5 py-2 border border-slate-200 rounded-xl text-xs font-semibold text-slate-600 hover:bg-white disabled:opacity-50 disabled:cursor-not-allowed transition-all">
                  <I.Sync /> Sync Now
                </button>
                <button onClick={() => saveIntegration(it)} disabled={busyId === it.id} className="flex items-center gap-1.5 px-4 py-2 bg-indigo-600 text-white rounded-xl text-xs font-semibold hover:bg-indigo-700 disabled:opacity-50 transition-all">
                  <I.Save /> Save
                </button>
              </div>
            </div>
          </div>
        ))}

        {/* ── Campaigns Table ── */}
        <div className="bg-white border border-slate-100 rounded-2xl shadow-sm overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-100"><h2 className="text-base font-bold text-slate-900">Connected Campaigns</h2></div>
          <div className="overflow-x-auto">
            <table className="w-full text-left min-w-[700px]">
              <thead>
                <tr className="bg-slate-50/60 border-b border-slate-100">
                  {["Campaign", "Meta ID", "Leads", "Last Import"].map(h => (
                    <th key={h} className="px-5 py-3.5 text-[10px] font-bold text-slate-400 uppercase tracking-widest">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {summary.campaigns.length === 0 && (
                  <tr><td colSpan={4} className="px-5 py-10 text-center text-sm text-slate-400">No Meta campaigns imported yet.</td></tr>
                )}
                {summary.campaigns.map((c, index) => (
                  <tr key={c.id || `${c.name}-${index}`} className="hover:bg-slate-50/60 transition-colors">
                    <td className="px-5 py-4"><p className="text-sm font-semibold text-slate-800">{c.name}</p></td>
                    <td className="px-5 py-4"><span className="font-mono text-xs text-slate-500">{c.meta_campaign_id || "Uncategorized"}</span></td>
                    <td className="px-5 py-4 text-sm font-bold text-slate-700">{c.leads_count}</td>
                    <td className="px-5 py-4 text-xs text-slate-400">{c.last_import ? new Date(c.last_import).toLocaleString("en-IN") : "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* ── Setup Guide ── */}
        <div className="bg-[#0f1629] border border-white/5 rounded-2xl p-6 text-white shadow-xl relative overflow-hidden">
          <div className="absolute top-0 right-0 w-64 h-64 bg-indigo-600/10 rounded-full -mr-16 -mt-16 blur-3xl pointer-events-none" />
          <div className="relative z-10">
            <div className="flex items-center gap-2 mb-4"><I.Zap /><h2 className="text-base font-bold">Quick Setup Guide</h2></div>
            <div className="grid sm:grid-cols-3 gap-4">
              {[
                { step: "01", title: "Create an Integration", desc: "Add one integration per branch and give it a clear name (e.g. the branch)." },
                { step: "02", title: "Set Page ID + Tokens", desc: "Enter the Facebook Page ID, verify token, and Page Access Token for that account." },
                { step: "03", title: "Point Meta to the Webhook", desc: "Use the shared Webhook URL above in Meta → Webhooks → Lead Ads. Leads route to the right branch by Page ID." },
              ].map(s => (
                <div key={s.step} className="bg-white/5 border border-white/10 rounded-xl p-4">
                  <span className="text-[10px] font-black text-indigo-400 tracking-widest">STEP {s.step}</span>
                  <h3 className="text-sm font-bold text-white mt-1 mb-2">{s.title}</h3>
                  <p className="text-xs text-slate-400 leading-relaxed">{s.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

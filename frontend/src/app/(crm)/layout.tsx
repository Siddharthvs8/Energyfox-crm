"use client";
import { APP_SLUG } from "@/lib/config";
import { applyTheme } from "@/lib/themes";

import React, { useState, useEffect, useCallback, useRef } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { getApiBase } from "@/lib/mock-data";

// ── Premium SVG Icons ──────────────────────────────────────────────────────────
const Nav = {
  Dashboard: () => (
    <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" viewBox="0 0 24 24">
      <rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" />
    </svg>
  ),
  Leads: () => (
    <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" viewBox="0 0 24 24">
      <path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" /><circle cx="9" cy="7" r="4" />
      <path d="M23 21v-2a4 4 0 00-3-3.87" /><path d="M16 3.13a4 4 0 010 7.75" />
    </svg>
  ),
  Campaigns: () => (
    <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
      <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
      <path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"></path>
    </svg>
  ),
  Tasks: () => (
    <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" viewBox="0 0 24 24">
      <path d="M9 11l3 3 8-8" /><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" />
    </svg>
  ),
  Meta: () => (
    <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" viewBox="0 0 24 24">
      <path d="M21 2H3v16h5l3 3 3-3h7V2z" /><path d="M12 8.5v5M8.5 11h7" />
    </svg>
  ),
  Team: () => (
    <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" viewBox="0 0 24 24">
      <path d="M13 16h-2a4 4 0 00-4 4H3" /><circle cx="9" cy="9" r="4" />
      <path d="M21 20a4 4 0 00-4-4h-1" /><circle cx="17" cy="9" r="3" />
    </svg>
  ),
  Billing: () => (
    <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" viewBox="0 0 24 24">
      <rect x="2" y="5" width="20" height="14" rx="2" /><line x1="2" y1="10" x2="22" y2="10" />
      <line x1="6" y1="15" x2="10" y2="15" />
    </svg>
  ),
  Admin: () => (
    <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" viewBox="0 0 24 24">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  ),
  Settings: () => (
    <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" viewBox="0 0 24 24">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06a1.65 1.65 0 00.33-1.82 1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06a1.65 1.65 0 001.82.33H9a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z" />
    </svg>
  ),
  Products: () => (
    <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
      <path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"></path>
      <line x1="7" y1="7" x2="7.01" y2="7"></line>
    </svg>
  ),
  Menu: () => (
    <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24">
      <line x1="3" y1="6" x2="21" y2="6" /><line x1="3" y1="12" x2="21" y2="12" /><line x1="3" y1="18" x2="21" y2="18" />
    </svg>
  ),
  Close: () => (
    <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24">
      <path d="M18 6L6 18M6 6l12 12" />
    </svg>
  ),
  Logout: () => (
    <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24">
      <path d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
    </svg>
  ),
  Alert: () => (
    <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24">
      <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
      <line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  ),
  AIManager: () => (
    <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" viewBox="0 0 24 24">
      <path d="M12 2a7 7 0 017 7c0 2.38-1.19 4.47-3 5.74V17a3 3 0 01-3 3h-2a3 3 0 01-3-3v-2.26C6.19 13.47 5 11.38 5 9a7 7 0 017-7z" />
      <path d="M9 21v1M15 21v1M12 2v3" />
    </svg>
  ),
  Bell: () => (
    <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" viewBox="0 0 24 24">
      <path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.73 21a2 2 0 01-3.46 0" />
    </svg>
  ),
  MyPerformance: () => (
    <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" viewBox="0 0 24 24">
      <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
    </svg>
  ),
  Meeting: () => (
    <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" viewBox="0 0 24 24">
      <path d="M12 2a7 7 0 017 7c0 2.38-1.19 4.47-3 5.74V17a3 3 0 01-3 3h-2a3 3 0 01-3-3v-2.26C6.19 13.47 5 11.38 5 9a7 7 0 017-7z"/>
      <circle cx="12" cy="9" r="2" />
    </svg>
  ),
  Leaderboard: () => (
    <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" viewBox="0 0 24 24">
      <path d="M6 9H4.5a1.5 1.5 0 010-3H6m0 3V4a1 1 0 011-1h10a1 1 0 011 1v16a1 1 0 01-1 1H7a1 1 0 01-1-1v-5m0-6V9m12-3v12M14 6v12" />
      <path d="M18 9h1.5a1.5 1.5 0 000-3H18" />
    </svg>
  ),
  Phone: () => (
    <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" viewBox="0 0 24 24">
      <path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6 19.79 19.79 0 01-3.07-8.67A2 2 0 014.11 2h3a2 2 0 012 1.72 12.84 12.84 0 00.7 2.81 2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l2.27-2.27a2 2 0 012.11-.45 12.84 12.84 0 002.81.7A2 2 0 0122 16.92z" />
    </svg>
  ),
  Automation: () => (
    <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
      <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
    </svg>
  ),
  Trophy: () => (
    <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
      <path d="M6 9H4.5a2.5 2.5 0 010-5H6"></path>
      <path d="M18 9h1.5a2.5 2.5 0 000-5H18"></path>
      <path d="M4 22h16"></path>
      <path d="M10 14.66V17c0 1.1-.9 2-2 2H6"></path>
      <path d="M14 14.66V17c0 1.1.9 2 2 2h2"></path>
      <path d="M18 4H6v5c0 3.31 2.69 6 6 6s6-2.69 6-6V4z"></path>
    </svg>
  ),
  Inventory: () => (
    <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
      <path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z" />
      <path d="M3.27 6.96L12 12.01l8.73-5.05M12 22.08V12" />
    </svg>
  ),
  Vendor: () => (
    <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
      <rect x="1" y="3" width="15" height="13" rx="1" /><path d="M16 8h4l3 3v5h-7V8z" />
      <circle cx="5.5" cy="18.5" r="2.5" /><circle cx="18.5" cy="18.5" r="2.5" />
    </svg>
  ),
  Quote: () => (
    <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" /><path d="M14 2v6h6" />
      <path d="M9 13h6M9 17h4" />
    </svg>
  ),
  SalesOrder: () => (
    <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
      <circle cx="9" cy="21" r="1" /><circle cx="20" cy="21" r="1" />
      <path d="M1 1h4l2.68 13.39a2 2 0 002 1.61h9.72a2 2 0 002-1.61L23 6H6" />
    </svg>
  ),
  PurchaseOrder: () => (
    <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
      <path d="M16 4h2a2 2 0 012 2v14a2 2 0 01-2 2H6a2 2 0 01-2-2V6a2 2 0 012-2h2" />
      <rect x="8" y="2" width="8" height="4" rx="1" /><path d="M9 14l2 2 4-4" />
    </svg>
  ),
  Caret: () => (
    <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
      <polyline points="6 9 12 15 18 9" />
    </svg>
  ),
};

// Module key (from /api/leads/module-counts/) -> the name used in the "new work"
// popup. The keys match each module's route, so the badge maps by href.
const MODULE_LABELS: Record<string, string> = {
  "leads": "Leads",
  "documentation": "Documentation Stage 1",
  "documentation-stage2": "Documentation Stage 2",
  "discom-followup": "Discom Follow-up",
  "warranty": "Warranty",
  "accounts": "Accounts",
  "accounts/partially-paid": "Partially Paid",
  "accounts/fully-paid": "Fully Paid",
  "accounts/completed": "Completed Projects",
  "purchase": "Purchase & Logistics",
  "project": "Project",
  "liasoning": "Liasoning",
  "periodic-maintenance": "Periodic Maintenance",
};

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const domain = APP_SLUG;
  const pathname = usePathname();
  const router = useRouter();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [userName, setUserName] = useState("User");
  const [subscription, setSubscription] = useState<any>(null);
  const [currentUser, setCurrentUser] = useState<any>(null);
  const [unreadCount, setUnreadCount] = useState(0);
  const [notifications, setNotifications] = useState<any[]>([]);
  const [popups, setPopups] = useState<any[]>([]);
  const [activePopup, setActivePopup] = useState<any>(null);
  const [showNotifDropdown, setShowNotifDropdown] = useState(false);
  const [toasts, setToasts] = useState<any[]>([]);
  const [inventoryOpen, setInventoryOpen] = useState(false);

  // Apply the cached accent theme immediately on mount (avoids a flash before
  // the subscription fetch resolves and re-applies the authoritative value).
  useEffect(() => {
    applyTheme(localStorage.getItem(`${domain}_theme`));
  }, [domain]);

  // When popups change, ensure an active popup is set
  useEffect(() => {
    if (popups.length > 0 && !activePopup) {
      setActivePopup(popups[0]);
    }
  }, [popups, activePopup]);

  const dismissPopup = () => {
    setPopups(prev => prev.slice(1));
    setActivePopup(null);
  };

  React.useEffect(() => {
    const token = localStorage.getItem(`${domain}_access`);
    if (!token && !pathname.endsWith("/login")) {
      router.push(`/login`);
      return;
    }
    const savedName = localStorage.getItem(`${domain}_username`);
    if (savedName) setUserName(savedName);
    if (token) {
      fetch(`${getApiBase(domain)}/api/subscription/`, {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then(r => r.json())
        .then(d => {
          setSubscription(d);
          applyTheme(d.theme);
          if (d.theme) localStorage.setItem(`${domain}_theme`, d.theme);
        })
        .catch(() => {});
      // Fetch current user role
      fetch(`${getApiBase(domain)}/api/users/me/`, {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then(r => r.json())
        .then(d => {
          setCurrentUser(d);
          if (d.first_name) setUserName(d.first_name);
          // Documentation team lands on their own view, not the sales dashboard.
          if (["documentation_staff", "documentation_manager"].includes(d.role) && window.location.pathname === "/") {
            router.replace("/documentation");
          }
          // Accounts staff land on the accounts queue.
          if (d.role === "accounts_staff" && window.location.pathname === "/") {
            router.replace("/accounts");
          }
          // Purchase staff land on the purchase & logistics queue.
          if (d.role === "purchase_staff" && window.location.pathname === "/") {
            router.replace("/purchase");
          }
          // Project manager lands on the project queue.
          if (d.role === "project_manager" && window.location.pathname === "/") {
            router.replace("/project");
          }
          // Liasoning officer lands on the Liasoning & Service queue.
          if (d.role === "liasoning_officer" && window.location.pathname === "/") {
            router.replace("/liasoning");
          }
        })
        .catch(() => {});
    }

    // Global interceptor for 401 Unauthorized errors
    const originalFetch = window.fetch;
    window.fetch = async function (...args) {
      const response = await originalFetch.apply(this, args);
      if (response.status === 401 && !window.location.pathname.endsWith("/login")) {
        localStorage.removeItem(`${domain}_access`);
        localStorage.removeItem(`${domain}_refresh`);
        window.location.href = `/login`;
        return Promise.reject(new Error("Unauthorized API Error"));
      }
      return response;
    };
    return () => {
      window.fetch = originalFetch;
    };
  }, [domain, pathname, router]);

  // ── Notification Polling ──
  const fetchNotifications = useCallback(async () => {
    const tk = localStorage.getItem(`${domain}_access`);
    if (!tk) return;
    try {
      const [countR, listR, popupsR] = await Promise.all([
        fetch(`${getApiBase(domain)}/api/ai-manager/notifications/unread_count/`, { headers: { Authorization: `Bearer ${tk}` } }),
        fetch(`${getApiBase(domain)}/api/ai-manager/notifications/?limit=10`, { headers: { Authorization: `Bearer ${tk}` } }),
        fetch(`${getApiBase(domain)}/api/ai-manager/popups/`, { headers: { Authorization: `Bearer ${tk}` } })
      ]);
      if (countR.ok) {
        const d = await countR.json();
        const newCount = d.count || 0;
        // Show toast for newly arrived notifications
        if (newCount > unreadCount && unreadCount > 0) {
          setToasts(prev => [...prev, { id: Date.now(), message: `${newCount - unreadCount} new notification(s)` }]);
        }
        setUnreadCount(newCount);
      }
      if (listR.ok) {
        const data = await listR.json();
        setNotifications(Array.isArray(data) ? data.slice(0, 10) : (data.results || []).slice(0, 10));
      }
      if (popupsR.ok) {
        const newPopups = await popupsR.json();
        if (Array.isArray(newPopups) && newPopups.length > 0) {
          setPopups(prev => [...prev, ...newPopups]);
        }
      }
    } catch {}
  }, [domain, unreadCount]);

  useEffect(() => {
    fetchNotifications();
    const interval = setInterval(fetchNotifications, 60000);
    return () => clearInterval(interval);
  }, [fetchNotifications]);

  // ── Per-module work counts (sidebar badges + "new work" popup) ──
  // The badge shows how many items in that module are still waiting on this
  // user; when a count grows between polls, that's new work arriving for them.
  const [moduleCounts, setModuleCounts] = useState<Record<string, number>>({});
  const prevCountsRef = useRef<Record<string, number> | null>(null);
  const prevAssignedRef = useRef<Record<string, number> | null>(null);
  // Work newly assigned to this user by name — shown as a centre-screen modal.
  const [assignAlert, setAssignAlert] = useState<{ key: string; added: number } | null>(null);

  const fetchModuleCounts = useCallback(async () => {
    const tk = localStorage.getItem(`${domain}_access`);
    if (!tk) return;
    try {
      const r = await fetch(`${getApiBase(domain)}/api/leads/module-counts/`, {
        headers: { Authorization: `Bearer ${tk}` },
      });
      if (!r.ok) return;
      const data = await r.json();
      const next: Record<string, number> = data.counts || {};
      const nextAssigned: Record<string, number> = data.assigned || {};
      const prev = prevCountsRef.current;
      const prevAssigned = prevAssignedRef.current;

      if (prev) {
        // Anything newly assigned to this user personally gets the modal…
        const newlyAssigned = prevAssigned
          ? Object.entries(nextAssigned)
              .filter(([k, v]) => v > (prevAssigned[k] ?? 0))
              .map(([k, v]) => ({ key: k, added: v - (prevAssigned[k] ?? 0) }))
          : [];
        // One modal at a time, however many customers it covers — a bulk
        // assignment of 50 leads is a single "50 new customers" popup, not 50.
        if (newlyAssigned.length) setAssignAlert(newlyAssigned[0]);

        // …everything else that grew is a quieter corner toast (including any
        // further assigned modules beyond the one in the modal).
        const modalKeys = new Set(newlyAssigned.slice(0, 1).map(g => g.key));
        const grown = Object.entries(next)
          .filter(([k, v]) => v > (prev[k] ?? 0) && !modalKeys.has(k))
          .map(([k, v]) => ({ key: k, added: v - (prev[k] ?? 0) }));
        if (grown.length) {
          setToasts(t => [...t, ...grown.map(g => ({
            id: `${Date.now()}-${g.key}`,
            message: `${g.added} new ${g.added === 1 ? "item" : "items"} in ${MODULE_LABELS[g.key] || g.key}`,
            href: `/${g.key}`,
          }))]);
        }
      }
      prevCountsRef.current = next;
      prevAssignedRef.current = nextAssigned;
      setModuleCounts(next);
    } catch { /* keep the previous badges */ }
  }, [domain]);

  useEffect(() => {
    fetchModuleCounts();
    const interval = setInterval(fetchModuleCounts, 60000);
    return () => clearInterval(interval);
  }, [fetchModuleCounts]);

  // Opening a customer inside a module marks it seen, so it stops counting
  // towards that module's badge; then refresh the badges.
  useEffect(() => {
    const tk = localStorage.getItem(`${domain}_access`);
    if (!tk) return;
    // Detail routes look like /module/<id> or /accounts/partially-paid/<id>.
    const m = pathname.match(/^\/(.+)\/(\d+)$/);
    const moduleKey = m?.[1];
    const leadId = m?.[2];
    const markSeen = async () => {
      if (moduleKey && leadId && MODULE_LABELS[moduleKey]) {
        // The accounts detail page is shared by its three queues.
        const modules = moduleKey === "accounts"
          ? ["accounts", "accounts/partially-paid", "accounts/fully-paid", "accounts/completed"]
          : [moduleKey];
        try {
          await fetch(`${getApiBase(domain)}/api/leads/${leadId}/seen/`, {
            method: "POST",
            headers: { "Content-Type": "application/json", Authorization: `Bearer ${tk}` },
            body: JSON.stringify({ modules }),
          });
        } catch { /* the badge just stays until the next visit */ }
      }
      fetchModuleCounts();
    };
    markSeen();
  }, [pathname]); // eslint-disable-line react-hooks/exhaustive-deps



  // Auto-dismiss toasts
  useEffect(() => {
    if (toasts.length === 0) return;
    const timer = setTimeout(() => setToasts(prev => prev.slice(1)), 4000);
    return () => clearTimeout(timer);
  }, [toasts]);

  const markAllRead = async () => {
    const tk = localStorage.getItem(`${domain}_access`);
    if (!tk) return;
    await fetch(`${getApiBase(domain)}/api/ai-manager/notifications/mark_read/`, {
      method: 'POST', headers: { Authorization: `Bearer ${tk}`, 'Content-Type': 'application/json' }, body: '{}',
    });
    setUnreadCount(0);
    setNotifications(prev => prev.map(n => ({ ...n, is_read: true })));
  };


  const allNavItems: any[] = [
    { href: `/`,               label: "Dashboard",       Icon: Nav.Dashboard, exact: true },
    { href: `/leads`,         label: "Leads",           Icon: Nav.Leads },
    { href: `/converted`,     label: "Converted Leads", Icon: Nav.Trophy },
    { href: `/campaigns`,     label: "Campaigns",       Icon: Nav.Campaigns, managerFeature: true },
    { href: `/calls`,         label: "Calls",           Icon: Nav.Phone },
    { href: `/tasks`,         label: "Tasks",           Icon: Nav.Tasks },
    { inventoryGroup: true },
    { href: `/leaderboard`,    label: "Leaderboard",     Icon: Nav.Leaderboard },
    { href: `/my-performance`,label: "My Performance",  Icon: Nav.MyPerformance, hideForManager: true },
    { href: `/team-performance`,label: "Team Performance",Icon: Nav.Team, managerOnly: true },
    { href: `/manager`,       label: "Manager",         Icon: Nav.Admin, managerFeature: true },
    { href: `/automations`,   label: "Automations",    Icon: Nav.Automation, adminOnly: true },
    { href: `/meta`,          label: "Meta Integration",Icon: Nav.Meta, strictAdminOnly: true },
    { href: `/team`,          label: "Team",            Icon: Nav.Team },
    { href: `/branches`,      label: "Branches",        Icon: Nav.Admin, adminOnly: true },
    { href: `/documentation`, label: "Documentation Stage 1", Icon: Nav.Quote, docFeature: true },
    { href: `/documentation-stage2`, label: "Documentation Stage 2", Icon: Nav.Quote, docStage2Feature: true },
    { href: `/warranty`,      label: "Warranty",         Icon: Nav.Quote, warrantyFeature: true },
    { href: `/discom-followup`, label: "Discom Follow-up", Icon: Nav.Alert, docStage2Feature: true },
    { href: `/documentation-status`, label: "Documentation", Icon: Nav.Quote, docTracker: true },
    { href: `/feasibility`,   label: "KSEB Feasibility", Icon: Nav.Tasks, feasibilityFeature: true },
    { href: `/accounts`,      label: "Accounts",        Icon: Nav.Billing, accountsFeature: true },
    { href: `/accounts/partially-paid`, label: "Partially Paid", Icon: Nav.MyPerformance, paymentBucketFeature: true },
    { href: `/accounts/fully-paid`, label: "Fully Paid",   Icon: Nav.Trophy, paymentBucketFeature: true },
    { href: `/accounts/completed`, label: "Completed Projects", Icon: Nav.Tasks, completedProjectsFeature: true },
    { href: `/purchase`,      label: "Purchase & Logistics", Icon: Nav.Inventory, purchaseFeature: true },
    { href: `/accounts`,      label: "Accounts",        Icon: Nav.Billing, purchaseAccountsView: true },
    { href: `/project`,       label: "Project",         Icon: Nav.PurchaseOrder, pmFeature: true },
    { href: `/service`,       label: "Service",         Icon: Nav.Tasks, pmFeature: true },
    { href: `/team-stats`,    label: "Team Stats",      Icon: Nav.Leaderboard, pmFeature: true },
    { href: `/liasoning`,     label: "Liasoning",        Icon: Nav.Tasks, liasoningFeature: true },
    { href: `/periodic-maintenance`, label: "Periodic Maintenance", Icon: Nav.Settings, liasoningFeature: true },
    { href: `/emergency-service`, label: "Emergency Service", Icon: Nav.Alert, liasoningFeature: true },
    { href: `/settings`,      label: "Settings",        Icon: Nav.Settings, adminOnly: true },
  ];

  // Documentation team (staff/manager) get a focused view — only the Documentation page.
  const isDocOnly = ["documentation_staff", "documentation_manager"].includes(currentUser?.role);
  // Accounts staff get a focused view — only the Accounts page.
  const isAccountsOnly = currentUser?.role === "accounts_staff";
  // Purchase staff get a focused view — only the Purchase & Logistics page.
  const isPurchaseOnly = currentUser?.role === "purchase_staff";
  // Project manager gets a focused view — Project, Service and Team Stats.
  const isPmOnly = currentUser?.role === "project_manager";
  // Liasoning officer gets a focused view — only the Liasoning & Service module.
  const isLiasoningOnly = currentUser?.role === "liasoning_officer";

  // Manager features visible to manager, general manager, and admin
  const navItems = allNavItems.filter(item => {
    if (isDocOnly) {
      return !!item.docFeature || !!item.docStage2Feature || !!item.warrantyFeature;
    }
    if (isLiasoningOnly) {
      return !!item.liasoningFeature;
    }
    if (isAccountsOnly) {
      return !!item.accountsFeature || !!item.completedProjectsFeature || !!item.paymentBucketFeature;
    }
    if (isPurchaseOnly) {
      // Purchase staff see their own module plus a read-only Accounts view under it.
      return !!item.purchaseFeature || !!item.purchaseAccountsView;
    }
    if (isPmOnly) {
      return !!item.pmFeature;
    }
    if (item.purchaseAccountsView) {
      return false;  // purchase-staff-only duplicate; everyone else uses the real Accounts item
    }
    if (item.docFeature) {
      return false;  // the work queue is for the documentation team only
    }
    if (item.docStage2Feature) {
      // Documentation Stage 2 — the documentation team (above) plus admins / general managers.
      return currentUser?.is_staff || currentUser?.is_general_manager;
    }
    if (item.warrantyFeature) {
      // Warranty — the documentation team (above) plus admins / general managers.
      return currentUser?.is_staff || currentUser?.is_general_manager;
    }
    if (item.liasoningFeature) {
      // Liasoning & Service — the liasoning officer (above) plus admins / general managers.
      return currentUser?.is_staff || currentUser?.is_general_manager;
    }
    if (item.accountsFeature) {
      // Accounts queue — accounts staff (above) plus admins / general managers who oversee them.
      return currentUser?.is_staff || currentUser?.is_general_manager;
    }
    if (item.completedProjectsFeature) {
      // Completed-projects (RF) queue — accounts staff (above) plus admins / general managers.
      return currentUser?.is_staff || currentUser?.is_general_manager;
    }
    if (item.paymentBucketFeature) {
      // Partially / Fully paid buckets — accounts staff (above) plus admins / general managers.
      return currentUser?.is_staff || currentUser?.is_general_manager;
    }
    if (item.purchaseFeature) {
      // Purchase & logistics queue — purchase staff (above) plus admins / general managers.
      return currentUser?.is_staff || currentUser?.is_general_manager;
    }
    if (item.pmFeature) {
      // Project / Service / Team Stats — project manager (above) plus admins / general managers.
      return currentUser?.is_staff || currentUser?.is_general_manager;
    }
    if (item.docTracker) {
      return true;   // read-only documentation tracker — everyone except the doc team
    }
    if (item.feasibilityFeature) {
      // BDE's KSEB feasibility task list — BDEs plus their managers / admins.
      return currentUser?.role === "bde" || currentUser?.is_staff
        || currentUser?.is_general_manager || currentUser?.is_manager;
    }
    if (item.strictAdminOnly) {
      return currentUser?.is_staff;
    }
    if (item.adminOnly) {
      return currentUser?.is_staff || currentUser?.is_general_manager;
    }
    if (item.managerFeature) {
      return currentUser?.is_staff || currentUser?.is_general_manager || currentUser?.is_manager;
    }
    if (item.managerOnly) {
      return currentUser?.is_manager && !currentUser?.is_staff && !currentUser?.is_general_manager;
    }
    if (item.hideForManager) {
      // Hidden for branch managers and admins (they use Team/Manager views instead).
      return !((currentUser?.is_manager && !currentUser?.is_general_manager) || currentUser?.is_staff);
    }
    if (item.agentOnly) {
      // Show AI Meeting only for non-staff, non-manager, non-GM agents
      return !currentUser?.is_staff && !currentUser?.is_general_manager && !currentUser?.is_manager;
    }
    return true;
  });

  // Match on whole path segments so a sibling route like /documentation-stage2
  // doesn't also light up /documentation (which is only a string prefix).
  const isActive = (href: string, exact?: boolean) =>
    exact ? pathname === href || pathname === `/` : (pathname === href || pathname.startsWith(href + "/"));

  // ── Inventory module (grouped, collapsible) ──
  const inventoryItems = [
    { href: `/products`,        label: "Products",        Icon: Nav.Products },
    { href: `/vendors`,         label: "Vendors",         Icon: Nav.Vendor },
    { href: `/quotes`,          label: "Quotes",          Icon: Nav.Quote },
    { href: `/sales-orders`,    label: "Sales Orders",    Icon: Nav.SalesOrder },
    { href: `/purchase-orders`, label: "Purchase Orders", Icon: Nav.PurchaseOrder },
  ];
  const canSeeInventory = currentUser?.is_staff || currentUser?.is_general_manager;
  const inventoryActive = inventoryItems.some(i => pathname.startsWith(i.href));
  const inventoryExpanded = inventoryOpen || inventoryActive;

  const avatarColors = ["from-indigo-500 to-violet-600", "from-cyan-500 to-blue-600", "from-pink-500 to-rose-500"];
  const color = avatarColors[domain.charCodeAt(0) % avatarColors.length];

  const isLoginPage = pathname.endsWith("/login");
  if (isLoginPage) {
    return (
      <div className="min-h-screen bg-[#f5f7fb]" style={{ fontFamily: "'Inter', sans-serif" }}>
        {children}
      </div>
    );
  }

  return (
    <div className="min-h-screen flex bg-[#f5f7fb]" style={{ fontFamily: "'Inter', sans-serif" }}>
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-40 lg:hidden" onClick={() => setSidebarOpen(false)} />
      )}

      {/* ── Sidebar ── */}
      <aside className={`accent-transition w-60 bg-[#0f1629] flex flex-col fixed inset-y-0 left-0 z-50 transition-transform duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] ${sidebarOpen ? "translate-x-0" : "-translate-x-full"} lg:translate-x-0`}>
        {/* Logo */}
        <div className="h-16 flex items-center justify-between px-5 border-b border-white/5 flex-shrink-0">
          <div className="flex items-center gap-3 min-w-0">
            {/* The square Energyfox mark reads cleanly on the dark sidebar; a wide
                lockup would either crop or shrink to a sliver here, so the mark is
                always used and the workspace name sits beside it as text. */}
            <img src="/energyfox-mark.png" alt="Energyfox" className="w-9 h-9 object-contain flex-shrink-0" />
            <div className="overflow-hidden">
              <div className="text-white font-semibold text-sm capitalize truncate leading-tight">{subscription?.name || domain}</div>
              <div className="text-[10px] text-slate-500 leading-tight">Workspace</div>
            </div>
          </div>
          <button onClick={() => setSidebarOpen(false)} className="lg:hidden text-slate-500 hover:text-white p-1 transition-colors">
            <Nav.Close />
          </button>
        </div>

        {/* Nav items */}
        <nav className="flex-1 py-3 px-2.5 space-y-0.5 overflow-y-auto">
          {navItems.map(item => {
            if (item.inventoryGroup) {
              if (!canSeeInventory) return null;
              return (
                <div key="inventory-group" className="pt-1">
                  <button
                    onClick={() => setInventoryOpen(o => !o)}
                    className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-[13px] font-medium transition-all duration-200 group ${
                      inventoryActive && !inventoryExpanded
                        ? "bg-accent-soft text-white"
                        : "text-slate-400 hover:bg-white/[0.06] hover:text-slate-200"
                    }`}
                  >
                    <span className={`flex-shrink-0 transition-colors ${inventoryActive ? "text-indigo-300" : "text-slate-500 group-hover:text-slate-300"}`}>
                      <Nav.Inventory />
                    </span>
                    <span className="truncate">Inventory</span>
                    <span className={`ml-auto flex-shrink-0 text-slate-500 transition-transform duration-200 ${inventoryExpanded ? "rotate-180" : ""}`}>
                      <Nav.Caret />
                    </span>
                  </button>
                  {inventoryExpanded && (
                    <div className="mt-0.5 ml-3 pl-3 border-l border-white/10 space-y-0.5">
                      {inventoryItems.map(sub => {
                        const subActive = pathname.startsWith(sub.href);
                        return (
                          <Link
                            key={sub.href}
                            href={sub.href}
                            onClick={() => setSidebarOpen(false)}
                            className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-[12.5px] font-medium transition-all duration-200 group ${
                              subActive
                                ? "bg-accent text-white shadow-lg shadow-accent"
                                : "text-slate-400 hover:bg-white/[0.06] hover:text-slate-200 hover:translate-x-0.5"
                            }`}
                          >
                            <span className={`flex-shrink-0 transition-colors ${subActive ? "text-white" : "text-slate-500 group-hover:text-slate-300"}`}>
                              <sub.Icon />
                            </span>
                            <span className="truncate">{sub.label}</span>
                            {subActive && <span className="ml-auto w-1.5 h-1.5 bg-white/60 rounded-full flex-shrink-0 animate-pulse" />}
                          </Link>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            }
            // The Accounts item must not light up on its nested sub-module routes
            // (Completed Projects / Partially Paid / Fully Paid have their own items).
            const isAccountsSubRoute = pathname.startsWith("/accounts/completed")
              || pathname.startsWith("/accounts/partially-paid")
              || pathname.startsWith("/accounts/fully-paid");
            const active = item.href === "/accounts" && isAccountsSubRoute
              ? false
              : isActive(item.href, item.exact);
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setSidebarOpen(false)}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-[13px] font-medium transition-all duration-200 group ${
                  active
                    ? "bg-accent text-white shadow-lg shadow-accent"
                    : "text-slate-400 hover:bg-white/[0.06] hover:text-slate-200 hover:translate-x-0.5"
                }`}
                style={{ transitionTimingFunction: 'cubic-bezier(0.4, 0, 0.2, 1)' }}
              >
                <span className={`flex-shrink-0 transition-colors duration-200 ${active ? "text-white" : "text-slate-500 group-hover:text-slate-300"}`}>
                  <item.Icon />
                </span>
                <span className="truncate">{item.label}</span>
                {/* Items in this module still waiting on the user. */}
                {(() => {
                  const n = moduleCounts[item.href.replace(/^\//, "")] || 0;
                  if (!n) return active ? <span className="ml-auto w-1.5 h-1.5 bg-white/60 rounded-full flex-shrink-0 animate-pulse" /> : null;
                  return (
                    <span title={`${n} waiting`}
                      className={`ml-auto min-w-[20px] h-5 px-1.5 rounded-full text-[10px] font-bold flex items-center justify-center flex-shrink-0 ${active ? "bg-white/25 text-white" : "bg-rose-500 text-white"}`}>
                      {n > 99 ? "99+" : n}
                    </span>
                  );
                })()}
              </Link>
            );
          })}
        </nav>

        {/* Notification Bell */}
        <div className="px-3 py-2 border-t border-white/5 flex-shrink-0">
          <button
            onClick={() => setShowNotifDropdown(v => !v)}
            className="w-full flex items-center justify-between px-3 py-2.5 rounded-xl text-slate-400 hover:bg-white/5 hover:text-white transition-colors text-sm font-medium"
          >
            <span className="flex items-center gap-3">
              <Nav.Bell />
              <span>Notifications</span>
            </span>
            {unreadCount > 0 && (
              <span className="w-5 h-5 bg-rose-500 text-white text-[10px] font-bold rounded-full flex items-center justify-center animate-pulse">
                {unreadCount > 9 ? '9+' : unreadCount}
              </span>
            )}
          </button>
        </div>

        {/* User section */}
        <div className="p-3 border-t border-white/5 flex-shrink-0">
          <div className="flex items-center gap-3 p-2 rounded-xl hover:bg-white/5 transition-colors group">
            <Link href={`/team?edit=me`} className="flex items-center gap-3 flex-1 min-w-0">
              <div className={`w-8 h-8 rounded-full bg-gradient-to-br ${color} flex items-center justify-center text-xs font-bold text-white flex-shrink-0 ring-2 ring-white/10`}>
                {userName.charAt(0).toUpperCase()}
              </div>
              <div className="min-w-0">
                <div className="text-sm font-medium text-slate-200 truncate capitalize leading-tight">{userName}</div>
                <div className="text-[10px] text-slate-500 leading-tight">Edit Profile</div>
              </div>
            </Link>
            <button
              onClick={() => {
                localStorage.removeItem(`${domain}_access`);
                localStorage.removeItem(`${domain}_refresh`);
                router.push(`/login`);
              }}
              className="text-slate-600 hover:text-red-400 p-1 transition-colors flex-shrink-0"
              title="Sign out"
            >
              <Nav.Logout />
            </button>
          </div>
        </div>
      </aside>

      {/* ── Main content ── */}
      <main className="flex-1 lg:ml-60 flex flex-col min-h-screen">
        {/* Mobile topbar */}
        <header className="lg:hidden h-14 bg-white border-b border-slate-200/60 px-4 flex items-center justify-between sticky top-0 z-30 flex-shrink-0">
          <button onClick={() => setSidebarOpen(true)} className="p-2 rounded-xl hover:bg-slate-100 text-slate-600 transition-colors">
            <Nav.Menu />
          </button>
          <div className="flex items-center gap-2">
            <img src="/energyfox-mark.png" alt="Energyfox" className="w-7 h-7 object-contain" />
            <span className="text-sm font-bold text-slate-900 capitalize">{subscription?.name || domain}</span>
          </div>
          <Link href={`/team?edit=me`}>
            <div className={`w-8 h-8 rounded-full bg-gradient-to-br ${color} flex items-center justify-center text-xs font-bold text-white`}>
              {userName.charAt(0).toUpperCase()}
            </div>
          </Link>
        </header>

        <div key={pathname} className="flex-1 page-enter">{children}</div>

        {/* ── Notification Toasts ── */}
        <div className="toast-container">
          {toasts.map(t => (
            <div key={t.id} className="toast toast-dark">
              <div className="toast-icon bg-violet-500/20">
                <span className="text-violet-400"><Nav.Bell /></span>
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-[13px] font-bold leading-tight">{t.message}</p>
                {t.href ? (
                  <Link href={t.href} onClick={() => setToasts(prev => prev.filter(x => x.id !== t.id))}
                    className="text-[11px] text-indigo-300 hover:text-indigo-200 mt-0.5 inline-block">
                    Open module →
                  </Link>
                ) : (
                  <p className="text-[11px] text-slate-400 mt-0.5">Just now</p>
                )}
              </div>
              <button onClick={() => setToasts(prev => prev.filter(x => x.id !== t.id))} className="text-slate-500 hover:text-white transition-colors flex-shrink-0 p-1">
                <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12" /></svg>
              </button>
            </div>
          ))}
        </div>


      </main>

      {/* ── Notification Dropdown ── */}
      {showNotifDropdown && (
        <div className="fixed inset-0 z-[60]" onClick={() => setShowNotifDropdown(false)}>
          <div
            className="notif-dropdown absolute left-60 bottom-20 w-[340px] max-h-[440px] flex flex-col"
            onClick={e => e.stopPropagation()}
          >
            <div className="notif-dropdown-header">
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-slate-900">Notifications</h3>
                {unreadCount > 0 && (
                  <span className="w-5 h-5 bg-indigo-600 text-white text-[10px] font-bold rounded-full flex items-center justify-center">
                    {unreadCount > 9 ? '9+' : unreadCount}
                  </span>
                )}
              </div>
              {unreadCount > 0 && (
                <button onClick={markAllRead} className="text-[11px] font-bold text-indigo-600 hover:text-indigo-700 px-2.5 py-1 rounded-lg hover:bg-indigo-50 transition-all">
                  Mark all read
                </button>
              )}
            </div>
            <div className="flex-1 overflow-y-auto custom-scrollbar">
              {notifications.length === 0 ? (
                <div className="py-14 text-center">
                  <div className="w-12 h-12 mx-auto rounded-2xl bg-slate-50 flex items-center justify-center text-slate-300 mb-3 border border-slate-100">
                    <Nav.Bell />
                  </div>
                  <p className="text-xs font-semibold text-slate-400">No notifications yet</p>
                  <p className="text-[10px] text-slate-300 mt-0.5">You&apos;re all caught up!</p>
                </div>
              ) : (
                <div>
                  {notifications.map((n: any) => {
                    const typeColors: Record<string, string> = {
                      daily_target: 'bg-indigo-50 text-indigo-600',
                      monthly_target: 'bg-emerald-50 text-emerald-600',
                      meeting: 'bg-blue-50 text-blue-600',
                      achievement: 'bg-amber-50 text-amber-600',
                      general: 'bg-slate-50 text-slate-600',
                    };
                    const typeIcons: Record<string, string> = {
                      daily_target: '📋', monthly_target: '📊',
                      meeting: '📅', achievement: '🏆', general: '💬',
                    };
                    return (
                      <div key={n.id} className={`notif-item ${!n.is_read ? 'unread' : ''}`}>
                        <span className={`mt-0.5 w-8 h-8 rounded-xl flex items-center justify-center text-sm flex-shrink-0 ${typeColors[n.notification_type] || typeColors.general}`}>
                          {typeIcons[n.notification_type] || '💬'}
                        </span>
                        <div className="flex-1 min-w-0">
                          <p className="text-[12px] font-semibold text-slate-800 leading-snug">{n.title}</p>
                          <p className="text-[11px] text-slate-500 mt-0.5 leading-relaxed line-clamp-2">{n.message}</p>
                          <p className="text-[10px] text-slate-400 mt-1.5 font-medium">
                            {new Date(n.created_at).toLocaleString('en-IN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                          </p>
                        </div>
                        {!n.is_read && <span className="w-2.5 h-2.5 bg-indigo-500 rounded-full mt-1.5 flex-shrink-0 ring-2 ring-indigo-100" />}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Global Popup Alert Modal */}
      {/* New work assigned to this user by name — same treatment as the AI
          Manager popups so it can't be missed. */}
      {assignAlert && (
        <div className="popup-overlay">
          <div className="popup-backdrop" onClick={() => setAssignAlert(null)} />
          <div className="popup-card max-w-lg">
            <div className="h-40 bg-gradient-to-br from-amber-400 via-orange-500 to-rose-500 w-full flex items-center justify-center text-white relative overflow-hidden">
              <div className="absolute top-0 right-0 w-32 h-32 bg-white/10 rounded-bl-full" />
              <div className="absolute bottom-0 left-0 w-24 h-24 bg-black/10 rounded-tr-full" />
              <div className="relative scale-[2.2]"><Nav.Quote /></div>
            </div>
            <div className="px-10 pb-10 pt-8 text-center flex flex-col items-center">
              <h2 className="text-2xl font-black text-slate-800 mb-3 tracking-tight">New work assigned to you</h2>
              <p className="text-slate-500 text-base mb-8 leading-relaxed">
                <b className="text-slate-700">{assignAlert.added}</b> new {assignAlert.added === 1 ? "customer has" : "customers have"} been
                assigned to you in <b className="text-slate-700">{MODULE_LABELS[assignAlert.key] || assignAlert.key}</b>.
              </p>
              <div className="flex gap-3 w-full max-w-sm">
                <button onClick={() => setAssignAlert(null)}
                  className="flex-1 py-3.5 bg-slate-100 text-slate-600 text-base font-bold rounded-2xl hover:bg-slate-200 transition-all active:scale-[0.98]">
                  Later
                </button>
                <button onClick={() => { const k = assignAlert.key; setAssignAlert(null); router.push(`/${k}`); }}
                  className="flex-1 py-3.5 bg-gradient-to-br from-amber-500 to-orange-600 text-white text-base font-black rounded-2xl hover:from-amber-600 hover:to-orange-700 transition-all shadow-lg shadow-amber-200 hover:-translate-y-0.5 active:translate-y-0">
                  Open
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {activePopup && (
        <div className="popup-overlay">
          {/* Backdrop with animation */}
          <div className="popup-backdrop" onClick={dismissPopup} />
          
          {/* Modal Box */}
          <div className="popup-card max-w-2xl">
            {/* Header Gradient Container */}
            <div className={`h-44 ${activePopup.notification_type === 'monthly_target' ? 'bg-gradient-to-br from-indigo-500 via-purple-500 to-fuchsia-600' : (activePopup.notification_type === 'daily_target' ? 'bg-gradient-to-br from-cyan-400 via-blue-500 to-indigo-600' : 'bg-gradient-to-br from-rose-500 via-red-500 to-orange-500')} w-full flex items-center justify-center text-white relative overflow-hidden`}>
              {/* Decorative shapes */}
               <div className="absolute top-0 right-0 w-36 h-36 bg-white/10 rounded-bl-full" />
               <div className="absolute bottom-0 left-0 w-28 h-28 bg-black/10 rounded-tr-full" />
               <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-64 h-64 bg-white/5 rounded-full blur-3xl" />
               
               <div className="transform scale-[2.5] drop-shadow-xl z-10">
                 {activePopup.notification_type === 'monthly_target' ? (
                    <Nav.MyPerformance />
                 ) : activePopup.notification_type === 'daily_target' ? (
                    <Nav.Leads />
                 ) : (
                    <Nav.Alert />
                 )}
               </div>
            </div>
            
            <div className="px-10 pb-10 pt-8 text-center flex flex-col items-center">
              <h2 className="text-3xl font-black text-slate-800 mb-4 tracking-tight leading-tight">{activePopup.title}</h2>
              <p className="text-slate-500 text-base mb-8 max-w-lg leading-relaxed">{activePopup.message}</p>
              
              {/* Optional Progress Graphics */}
              {activePopup.extra_data && activePopup.extra_data.leads_pct !== undefined && (
                 <div className="flex justify-center mb-10 mt-2">
                   <div className="relative flex items-center justify-center w-40 h-40 rounded-full bg-slate-50 shadow-inner [box-shadow:inset_0px_0px_20px_rgba(0,0,0,0.05)]">
                      <svg className="w-full h-full transform -rotate-90">
                         <circle cx="50%" cy="50%" r="42%" className="stroke-slate-200 fill-none" strokeWidth="10"/>
                         <circle cx="50%" cy="50%" r="42%" className={`fill-none transition-all duration-1000 ease-out ${activePopup.extra_data.leads_pct >= 100 ? 'stroke-emerald-500' : 'stroke-violet-500'}`} strokeWidth="12" strokeDasharray="264" strokeDashoffset={264 - (264 * Math.min(activePopup.extra_data.leads_pct, 100)) / 100} strokeLinecap="round" style={{ filter: 'drop-shadow(0px 4px 6px rgba(139, 92, 246, 0.3))' }}/>
                      </svg>
                      <span className={`absolute text-4xl font-black ${activePopup.extra_data.leads_pct >= 100 ? 'text-emerald-500' : 'text-slate-800'}`}>
                        {activePopup.extra_data.leads_pct}%
                      </span>
                   </div>
                 </div>
              )}

              {/* Meeting type: show Join + Dismiss buttons */}
              {activePopup.notification_type === 'meeting' ? (
                <div className="flex gap-3 w-full max-w-sm">
                  <button
                    onClick={dismissPopup}
                    className="flex-1 py-4 bg-slate-100 text-slate-600 text-base font-bold rounded-2xl hover:bg-slate-200 transition-all active:scale-[0.98]"
                  >
                    Later
                  </button>
                  <button
                    onClick={() => { dismissPopup(); router.push(`/ai-meeting`); }}
                    className="flex-1 py-4 bg-gradient-to-br from-violet-600 to-indigo-600 text-white text-base font-black rounded-2xl hover:from-violet-700 hover:to-indigo-700 transition-all shadow-lg shadow-violet-200 flex items-center justify-center gap-2 hover:-translate-y-0.5 active:translate-y-0"
                  >
                    🎙️ Join Meeting
                  </button>
                </div>
              ) : (
                <button onClick={dismissPopup} className="w-full max-w-sm py-4 bg-slate-900 text-white text-lg font-black rounded-2xl hover:bg-slate-800 hover:-translate-y-1 hover:shadow-2xl hover:shadow-slate-900/20 active:translate-y-0 active:scale-[0.98] transition-all duration-200">
                  Got it, Let&apos;s Go!
                </button>
              )}
            </div>
          </div>
        </div>
      )}


    </div>
  );
}

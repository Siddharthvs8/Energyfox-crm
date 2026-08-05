"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";
import { THEMES, applyTheme } from "@/lib/themes";
import RolesSection from "./RolesSection";
import InventoryDocumentsSection from "./InventoryDocumentsSection";
import EmailSignatureEditor from "./EmailSignatureEditor";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";

type SettingsTab = "general" | "integrations" | "automation" | "documents" | "roles";

const TABS: { key: SettingsTab; label: string; blurb: string }[] = [
  { key: "general", label: "General", blurb: "Company profile, branding and plan." },
  { key: "integrations", label: "Integrations", blurb: "Payments, telephony, WhatsApp and email." },
  { key: "automation", label: "Automation", blurb: "Target reminders and your own lead statuses." },
  { key: "documents", label: "Documents", blurb: "Inventory document letterheads, invoices and the warranty certificate." },
  { key: "roles", label: "Roles & Permissions", blurb: "Build your own user types and choose what each one can reach." },
];

export default function TenantSettingsPage({ params: paramsPromise }: { params: Promise<{ domain: string }> }) {
  const params = React.use(paramsPromise);
  const domain = APP_SLUG;
  const router = useRouter();

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  
  const [tenantData, setTenantData] = useState({
    name: "",
    logo: "",
    subscription_plan: "",
    max_users: 0,
    razorpay_key_id: "",
    razorpay_key_secret: "",
    invoice_template: "",
    voxbay_uid: "",
    voxbay_upin: "",
    voxbay_callerid: "",
    voxbay_api_url: "",
    voxbay_access_token: "",
    telephony_provider: "voxbay",
    exotel_sid: "",
    exotel_api_key: "",
    exotel_api_token: "",
    exotel_callerid: "",
    exotel_subdomain: "api.exotel.com",
    whatsapp_phone_number_id: "",
    whatsapp_access_token: "",
    whatsapp_business_account_id: "",
    whatsapp_verify_token: "",
    email_host: "",
    b2b_email_host: "", b2b_email_port: 587, b2b_email_use_tls: true, b2b_email_use_ssl: false,
    b2b_email_host_user: "", b2b_email_host_password: "", b2b_email_from_name: "",
    b2b_email_from_address: "", b2b_email_signature: "", b2b_email_signature_html: "",
    b2b_whatsapp_phone_number_id: "", b2b_whatsapp_business_account_id: "",
    b2b_whatsapp_access_token: "",
    email_port: 587,
    email_use_tls: true,
    email_use_ssl: false,
    email_host_user: "",
    email_host_password: "",
    email_from_name: "",
    email_from_address: "",
    email_signature: "",
    email_signature_html: "",
    theme: "indigo",
    warranty_company_name: "",
    warranty_cin: "",
    warranty_gst: "",
    warranty_director_name: "",
    warranty_director_designation: "",
    warranty_panel_years: "",
    warranty_inverter_years: "",
    warranty_service_years: "",
    warranty_signature: "",
    warranty_seal: "",
  });

  const [isSuperAdmin, setIsSuperAdmin] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);
  // Whether outgoing email is actually working, and a way to prove it.
  const [emailStatus, setEmailStatus] = useState<any>(null);

  // Which sending account the WhatsApp + Email blocks are editing. The wholesale
  // side may trade under its own identity; a blank B2B field falls back to B2C,
  // so switching it on is opt-in per credential.
  const [intSide, setIntSide] = useState<"b2c" | "b2b">("b2c");
  const sidePrefix = intSide === "b2b" ? "b2b_" : "";
  const fld = (name: string) => (tenantData as any)[sidePrefix + name] ?? "";
  const setFld = (name: string, value: any) =>
    setTenantData({ ...tenantData, [sidePrefix + name]: value });
  // For fields that move together, like the mutually exclusive TLS/SSL pair.
  const setFlds = (patch: Record<string, any>) =>
    setTenantData({
      ...tenantData,
      ...Object.fromEntries(Object.entries(patch).map(([k, v]) => [sidePrefix + k, v])),
    });
  const [testingEmail, setTestingEmail] = useState(false);
  const [themeSaving, setThemeSaving] = useState("");
  // Settings is long, so it's split into sections rather than one endless scroll.
  const [tab, setTab] = useState<SettingsTab>("general");

  const [logoFile, setLogoFile] = useState<File | null>(null);
  const [previewLogo, setPreviewLogo] = useState("");
  const [invoiceFile, setInvoiceFile] = useState<File | null>(null);
  const [invoiceFileName, setInvoiceFileName] = useState("");

  const [sigFile, setSigFile] = useState<File | null>(null);
  const [previewSig, setPreviewSig] = useState("");
  const [sealFile, setSealFile] = useState<File | null>(null);
  const [previewSeal, setPreviewSeal] = useState("");

  const [customStatuses, setCustomStatuses] = useState<{ value: string; label: string; bg?: string; text?: string; dot?: string; color?: string }[]>([]);
  const [newStatusLabel, setNewStatusLabel] = useState("");
  const [popupConfig, setPopupConfig] = useState({
    monthly_popup_interval_hours: 24,
    daily_popup_interval_hours: 3,
  });

  const COLOR_PALETTES = [
    { bg: "bg-purple-50", text: "text-purple-700", dot: "bg-purple-500", color: "#a855f7" },
    { bg: "bg-rose-50", text: "text-rose-700", dot: "bg-rose-500", color: "#f43f5e" },
    { bg: "bg-cyan-50", text: "text-cyan-700", dot: "bg-cyan-500", color: "#06b6d4" },
    { bg: "bg-lime-50", text: "text-lime-700", dot: "bg-lime-500", color: "#84cc16" },
    { bg: "bg-orange-50", text: "text-orange-700", dot: "bg-orange-400", color: "#f97316" },
    { bg: "bg-fuchsia-50", text: "text-fuchsia-700", dot: "bg-fuchsia-500", color: "#d946ef" },
    { bg: "bg-sky-50", text: "text-sky-700", dot: "bg-sky-500", color: "#0ea5e9" },
    { bg: "bg-teal-50", text: "text-teal-700", dot: "bg-teal-500", color: "#14b8a6" },
  ];

  const handleAddCustomStatus = () => {
    if (!newStatusLabel.trim()) return;
    
    const val = newStatusLabel.trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/(^_|_$)/g, '');
    if (!val) return;
    
    const standardValues = [
      "new","follow_up","positive","interested","not_interested","converted"
    ];
    if (standardValues.includes(val) || customStatuses.some(s => s.value === val)) {
      alert("This status already exists (either as a default or custom status).");
      return;
    }
    
    const palette = COLOR_PALETTES[customStatuses.length % COLOR_PALETTES.length];
    
    setCustomStatuses([...customStatuses, {
      value: val,
      label: newStatusLabel.trim(),
      ...palette
    }]);
    setNewStatusLabel("");
  };

  const handleRemoveCustomStatus = (idx: number) => {
    setCustomStatuses(customStatuses.filter((_, i) => i !== idx));
  };

  useEffect(() => {
    fetchTenantSettings();
  }, [domain]);

  const fetchTenantSettings = async () => {
    const token = localStorage.getItem(`${domain}_access`);
    if (!token) {
      router.push(`/login`);
      return;
    }

    try {
      const res = await fetch(`${getApiBase(domain)}/api/org-settings/`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setTenantData(data);
        if (data.logo) {
          setPreviewLogo(`${getApiBase(domain)}${data.logo}`);
        }
        if (data.invoice_template) {
          setInvoiceFileName(data.invoice_template.split('/').pop() || "Current Template");
        }
        if (data.custom_lead_statuses) {
          setCustomStatuses(data.custom_lead_statuses);
        }
        if (data.warranty_signature) setPreviewSig(`${getApiBase(domain)}${data.warranty_signature}`);
        if (data.warranty_seal) setPreviewSeal(`${getApiBase(domain)}${data.warranty_seal}`);
      } else if (res.status === 403) {
        setError("You do not have permission to access tenant settings.");
      }

      // Fetch popup config from AI manager settings
      try {
        const popupRes = await fetch(`${getApiBase(domain)}/api/ai-manager/meeting-config/`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        if (popupRes.ok) {
          const popupData = await popupRes.json();
          setPopupConfig({
            monthly_popup_interval_hours: popupData.monthly_popup_interval_hours || 24,
            daily_popup_interval_hours: popupData.daily_popup_interval_hours || 3,
          });
        }
      } catch (popupErr) {
        console.error("Failed to load popup configuration:", popupErr);
      }

      // Who am I? The theme picker is super-admin only.
      try {
        const meRes = await fetch(`${getApiBase(domain)}/api/users/me/`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        if (meRes.ok) {
          const me = await meRes.json();
          setIsSuperAdmin(!!me.is_superuser);
          setIsAdmin(!!me.is_staff);
        }
      } catch { /* non-fatal */ }
    } catch (err) {
      setError("Failed to load settings.");
    } finally {
      setLoading(false);
    }
  };

  // The banner describes whichever account is on screen, so it re-reads on switch.
  const loadEmailStatus = async (side = intSide) => {
    const token = localStorage.getItem(`${domain}_access`);
    if (!token) return;
    try {
      const r = await fetch(`${getApiBase(domain)}/api/email/status/?channel=${side}`, { headers: { Authorization: `Bearer ${token}` } });
      if (r.ok) setEmailStatus(await r.json());
    } catch { /* banner just stays hidden */ }
  };
  useEffect(() => { loadEmailStatus(); }, [domain, intSide]); // eslint-disable-line react-hooks/exhaustive-deps

  const sendTestEmail = async () => {
    const to = window.prompt("Send the test email to:", fld("email_from_address") || fld("email_host_user") || "");
    if (!to) return;
    setTestingEmail(true); setError(""); setSuccess("");
    try {
      const token = localStorage.getItem(`${domain}_access`);
      const r = await fetch(`${getApiBase(domain)}/api/email/test/`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ to, channel: intSide }),
      });
      const d = await r.json().catch(() => ({}));
      if (r.ok) setSuccess(`Test email sent to ${d.to} from ${d.from}.`);
      else setError(d.error || d.detail || "Test email failed.");
      loadEmailStatus();
    } catch { setError("Network error sending the test email."); }
    finally { setTestingEmail(false); }
  };

  // Instant-apply + persist the accent theme (super admin only).
  const selectTheme = async (key: string) => {
    setTenantData(p => ({ ...p, theme: key }));
    applyTheme(key);
    localStorage.setItem(`${domain}_theme`, key);
    setThemeSaving(key);
    setError(""); setSuccess("");
    try {
      const token = localStorage.getItem(`${domain}_access`);
      const res = await fetch(`${getApiBase(domain)}/api/org-settings/`, {
        method: "PATCH",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ theme: key }),
      });
      if (res.ok) setSuccess("Theme updated for everyone.");
      else setError("Could not update theme.");
    } catch { setError("Network error updating theme."); }
    finally { setThemeSaving(""); }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    setSuccess("");

    const token = localStorage.getItem(`${domain}_access`);
    const formData = new FormData();
    formData.append("name", tenantData.name);
    if (logoFile) {
      formData.append("logo", logoFile);
    }
    formData.append("razorpay_key_id", tenantData.razorpay_key_id);
    formData.append("razorpay_key_secret", tenantData.razorpay_key_secret);
    formData.append("voxbay_uid", tenantData.voxbay_uid || "");
    formData.append("voxbay_upin", tenantData.voxbay_upin || "");
    formData.append("voxbay_callerid", tenantData.voxbay_callerid || "");
    formData.append("voxbay_api_url", tenantData.voxbay_api_url || "");
    formData.append("voxbay_access_token", tenantData.voxbay_access_token || "");
    formData.append("telephony_provider", tenantData.telephony_provider || "voxbay");
    formData.append("exotel_sid", tenantData.exotel_sid || "");
    formData.append("exotel_api_key", tenantData.exotel_api_key || "");
    formData.append("exotel_api_token", tenantData.exotel_api_token || "");
    formData.append("exotel_callerid", tenantData.exotel_callerid || "");
    formData.append("exotel_subdomain", tenantData.exotel_subdomain || "api.exotel.com");
    formData.append("whatsapp_phone_number_id", tenantData.whatsapp_phone_number_id || "");
    formData.append("whatsapp_access_token", tenantData.whatsapp_access_token || "");
    formData.append("whatsapp_business_account_id", tenantData.whatsapp_business_account_id || "");
    formData.append("whatsapp_verify_token", tenantData.whatsapp_verify_token || "");
    formData.append("email_host", tenantData.email_host || "");
    // The wholesale account travels with the same PATCH.
    ["b2b_email_host", "b2b_email_port", "b2b_email_host_user", "b2b_email_host_password",
     "b2b_email_from_name", "b2b_email_from_address", "b2b_email_signature", "b2b_email_signature_html",
     "b2b_whatsapp_phone_number_id", "b2b_whatsapp_business_account_id",
     "b2b_whatsapp_access_token"].forEach(k =>
      formData.append(k, String((tenantData as any)[k] ?? "")));
    formData.append("b2b_email_use_tls", String(!!(tenantData as any).b2b_email_use_tls));
    formData.append("b2b_email_use_ssl", String(!!(tenantData as any).b2b_email_use_ssl));
    formData.append("email_port", String(tenantData.email_port || 587));
    formData.append("email_use_tls", String(!!tenantData.email_use_tls));
    formData.append("email_use_ssl", String(!!tenantData.email_use_ssl));
    formData.append("email_host_user", tenantData.email_host_user || "");
    formData.append("email_host_password", tenantData.email_host_password || "");
    formData.append("email_from_name", tenantData.email_from_name || "");
    formData.append("email_from_address", tenantData.email_from_address || "");
    formData.append("email_signature", tenantData.email_signature || "");
    formData.append("email_signature_html", tenantData.email_signature_html || "");
    if (invoiceFile) {
      formData.append("invoice_template", invoiceFile);
    }
    formData.append("custom_lead_statuses", JSON.stringify(customStatuses));
    formData.append("theme", tenantData.theme || "indigo");
    formData.append("warranty_company_name", tenantData.warranty_company_name || "");
    formData.append("warranty_cin", tenantData.warranty_cin || "");
    formData.append("warranty_gst", tenantData.warranty_gst || "");
    formData.append("warranty_director_name", tenantData.warranty_director_name || "");
    formData.append("warranty_director_designation", tenantData.warranty_director_designation || "");
    formData.append("warranty_panel_years", tenantData.warranty_panel_years || "");
    formData.append("warranty_inverter_years", tenantData.warranty_inverter_years || "");
    formData.append("warranty_service_years", tenantData.warranty_service_years || "");
    if (sigFile) formData.append("warranty_signature", sigFile);
    if (sealFile) formData.append("warranty_seal", sealFile);

    try {
      const res = await fetch(`${getApiBase(domain)}/api/org-settings/`, {
        method: "PATCH",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });

      if (res.ok) {
        const data = await res.json();
        setSuccess("Settings updated successfully!");
        setTenantData((prev) => ({
          ...prev,
          name: data.name,
          logo: data.logo,
          razorpay_key_id: data.razorpay_key_id,
          razorpay_key_secret: data.razorpay_key_secret,
          invoice_template: data.invoice_template,
          voxbay_uid: data.voxbay_uid,
          voxbay_upin: data.voxbay_upin,
          voxbay_callerid: data.voxbay_callerid,
          voxbay_api_url: data.voxbay_api_url,
          voxbay_access_token: data.voxbay_access_token,
          telephony_provider: data.telephony_provider || "voxbay",
          exotel_sid: data.exotel_sid,
          exotel_api_key: data.exotel_api_key,
          exotel_api_token: data.exotel_api_token,
          exotel_callerid: data.exotel_callerid,
          exotel_subdomain: data.exotel_subdomain || "api.exotel.com",
        }));
        if (data.logo) {
          setPreviewLogo(`${getApiBase(domain)}${data.logo}`);
        }
        if (data.invoice_template) {
          setInvoiceFileName(data.invoice_template.split('/').pop() || "Current Template");
        }
        if (data.custom_lead_statuses) {
          setCustomStatuses(data.custom_lead_statuses);
        }
        setLogoFile(null);
        setInvoiceFile(null);
        // A just-saved SMTP host changes what the banner should say.
        loadEmailStatus();
        if (data.warranty_signature) setPreviewSig(`${getApiBase(domain)}${data.warranty_signature}`);
        if (data.warranty_seal) setPreviewSeal(`${getApiBase(domain)}${data.warranty_seal}`);
        setSigFile(null);
        setSealFile(null);

        // Save target popup config
        try {
          await fetch(`${getApiBase(domain)}/api/ai-manager/meeting-config/`, {
            method: "PATCH",
            headers: {
              Authorization: `Bearer ${token}`,
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              monthly_popup_interval_hours: popupConfig.monthly_popup_interval_hours,
              daily_popup_interval_hours: popupConfig.daily_popup_interval_hours,
            }),
          });
        } catch (popupErr) {
          console.error("Failed to save target popup config:", popupErr);
        }
      } else {
        const data = await res.json();
        setError(data.error || "Failed to update settings.");
      }
    } catch (err) {
      setError("Network error. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  if (loading) return (
    <div className="p-8 flex items-center justify-center">
      <div className="w-8 h-8 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
    </div>
  );

  return (
    <div className="max-w-3xl mx-auto p-4 sm:p-6 lg:p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Workspace Settings</h1>
        <p className="text-sm text-slate-500 mt-1">{TABS.find(t => t.key === tab)?.blurb}</p>
      </div>

      <div className="flex gap-1 mb-6 border-b border-slate-200 overflow-x-auto no-scrollbar">
        {TABS.map(t => (
          <button key={t.key} type="button" onClick={() => setTab(t.key)}
            className={`px-4 py-2.5 text-sm font-semibold whitespace-nowrap border-b-2 -mb-px transition-colors ${
              tab === t.key ? "border-indigo-600 text-indigo-600" : "border-transparent text-slate-500 hover:text-slate-800"}`}>
            {t.label}
          </button>
        ))}
      </div>

      {error && <div className="mb-6 p-4 bg-red-50 text-red-600 rounded-xl text-sm border border-red-100">{error}</div>}
      {success && <div className="mb-6 p-4 bg-emerald-50 text-emerald-600 rounded-xl text-sm border border-emerald-100">{success}</div>}

      {/* Roles is its own module with its own saves, so it sits outside the
          workspace-settings form. */}
      {tab === "roles" ? <RolesSection domain={domain} isAdmin={isAdmin} /> : (
      <div className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden">
        <form onSubmit={handleSave} className="p-6 sm:p-8">
          <div className="space-y-6">
            {tab === "general" && (<>
            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-2">Company Name</label>
              <input 
                type="text" 
                required
                value={tenantData.name} 
                onChange={(e) => setTenantData({...tenantData, name: e.target.value})}
                className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition" 
              />
            </div>

            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-2">Company Logo</label>
              <div className="flex items-center gap-6">
                <div className="w-20 h-20 rounded-2xl bg-slate-100 border-2 border-dashed border-slate-300 flex items-center justify-center overflow-hidden flex-shrink-0">
                  {previewLogo ? (
                    <img src={previewLogo} alt="Logo" className="w-full h-full object-contain" />
                  ) : (
                    <svg width="24" height="24" fill="none" stroke="#94a3b8" strokeWidth="2" viewBox="0 0 24 24"><path d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>
                  )}
                </div>
                <div className="flex-1">
                  <input 
                    type="file" 
                    accept="image/*"
                    onChange={(e) => {
                      if (e.target.files && e.target.files.length > 0) {
                        const file = e.target.files[0];
                        setLogoFile(file);
                        setPreviewLogo(URL.createObjectURL(file));
                      }
                    }}
                    className="block w-full text-sm text-slate-500 file:mr-4 file:py-2.5 file:px-4 file:rounded-xl file:border-0 file:text-sm file:font-semibold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100 transition cursor-pointer"
                  />
                  <p className="text-xs text-slate-400 mt-2">Recommended: Square image, PNG or JPG, max 2MB.</p>
                </div>
              </div>
            </div>

            {isSuperAdmin && (
              <div className="pt-6 border-t border-slate-100">
                <label className="block text-sm font-semibold text-slate-700 mb-1">Appearance — Accent Theme</label>
                <p className="text-xs text-slate-400 mb-3">Sets the app accent colour (sidebar, buttons, highlights) for everyone. Super admin only.</p>
                <div className="flex flex-wrap gap-3">
                  {THEMES.map(t => {
                    const selected = tenantData.theme === t.key;
                    return (
                      <button key={t.key} type="button" onClick={() => selectTheme(t.key)} disabled={!!themeSaving}
                        className={`group relative flex flex-col items-center gap-1.5 rounded-2xl border-2 px-3.5 py-3 transition-all ${selected ? "border-slate-800 bg-slate-50" : "border-slate-200 hover:border-slate-300 hover:-translate-y-0.5"}`}>
                        <span className="w-11 h-11 rounded-xl shadow-sm ring-1 ring-black/5" style={{ background: t.gradient }} />
                        <span className="text-[11px] font-semibold text-slate-600">{t.label}</span>
                        {selected && <span className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-slate-900 text-white text-[11px] flex items-center justify-center shadow">✓</span>}
                        {themeSaving === t.key && <span className="absolute inset-0 rounded-2xl bg-white/60 flex items-center justify-center"><span className="w-4 h-4 border-2 border-slate-400 border-t-transparent rounded-full animate-spin" /></span>}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            <div className="grid sm:grid-cols-2 gap-6 pt-6 border-t border-slate-100">
              <div>
                <label className="block text-sm font-semibold text-slate-700 mb-2">Subscription Plan</label>
                <input 
                  type="text" 
                  disabled
                  value={tenantData.subscription_plan} 
                  className="w-full bg-slate-100 border border-slate-200 rounded-xl px-4 py-3 text-slate-500 cursor-not-allowed" 
                />
              </div>
              <div>
                <label className="block text-sm font-semibold text-slate-700 mb-2">User Limit</label>
                <input 
                  type="text" 
                  disabled
                  value={tenantData.max_users} 
                  className="w-full bg-slate-100 border border-slate-200 rounded-xl px-4 py-3 text-slate-500 cursor-not-allowed" 
                />
              </div>
            </div>

            </>)}

            {tab === "integrations" && (<>
            <div className="pt-6 border-t border-slate-100">
              <h3 className="text-lg font-bold text-slate-900 mb-4">Razorpay Integration</h3>
              <p className="text-sm text-slate-500 mb-6">Connect your Razorpay account to generate payment links for leads.</p>
              
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-semibold text-slate-700 mb-2">Key ID</label>
                  <input 
                    type="text" 
                    value={tenantData.razorpay_key_id} 
                    onChange={(e) => setTenantData({...tenantData, razorpay_key_id: e.target.value})}
                    placeholder="rzp_test_..."
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition" 
                  />
                </div>
                <div>
                  <label className="block text-sm font-semibold text-slate-700 mb-2">Key Secret</label>
                  <input 
                    type="password" 
                    value={tenantData.razorpay_key_secret} 
                    onChange={(e) => setTenantData({...tenantData, razorpay_key_secret: e.target.value})}
                    placeholder="••••••••••••••••••••••••"
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition" 
                  />
                </div>
              </div>
            </div>

            <div className="pt-6 border-t border-slate-100">
              <h3 className="text-lg font-bold text-slate-900 mb-2">Telephony Integration</h3>
              <p className="text-sm text-slate-500 mb-6">Choose your calling integration provider and configure credentials to enable agent dialer and automated call tracking.</p>
              
              <div className="mb-6">
                <label className="block text-sm font-semibold text-slate-700 mb-2">Select Call Integration Provider</label>
                <div className="relative">
                  <select
                    value={tenantData.telephony_provider}
                    onChange={(e) => setTenantData({...tenantData, telephony_provider: e.target.value})}
                    className="w-full appearance-none bg-slate-50 border border-slate-200 rounded-xl pl-4 pr-10 py-3 text-sm font-medium outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition cursor-pointer"
                  >
                    <option value="voxbay">Voxbay (API / Dialer redirection)</option>
                    <option value="exotel">Exotel (Cloud telephony click-to-call / webhook)</option>
                  </select>
                  <div className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none">
                    <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" viewBox="0 0 24 24"><polyline points="6 9 12 15 18 9"/></svg>
                  </div>
                </div>
              </div>

              {tenantData.telephony_provider === "voxbay" ? (
                <div className="grid sm:grid-cols-2 gap-4 animate-fade-in-up">
                  <div className="sm:col-span-2">
                    <label className="block text-sm font-semibold text-slate-700 mb-2">Voxbay API Base URL</label>
                    <input 
                      type="text" 
                      value={tenantData.voxbay_api_url} 
                      onChange={(e) => setTenantData({...tenantData, voxbay_api_url: e.target.value})}
                      placeholder="https://x.voxbay.com"
                      className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition" 
                    />
                  </div>
                  <div className="sm:col-span-2">
                    <label className="block text-sm font-semibold text-slate-700 mb-2">Voxbay Access Token</label>
                    <input 
                      type="password" 
                      value={tenantData.voxbay_access_token} 
                      onChange={(e) => setTenantData({...tenantData, voxbay_access_token: e.target.value})}
                      placeholder="••••••••••••••••••••••••"
                      className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition" 
                    />
                    <p className="text-xs text-slate-400 mt-2">Required for newer token-based Voxbay integrations. If set, UID and UPIN fields can be left blank.</p>
                  </div>
                  <div>
                    <label className="block text-sm font-semibold text-slate-700 mb-2">Voxbay UID</label>
                    <input 
                      type="text" 
                      value={tenantData.voxbay_uid} 
                      onChange={(e) => setTenantData({...tenantData, voxbay_uid: e.target.value})}
                      placeholder="Enter Voxbay Account UID"
                      className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition" 
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-semibold text-slate-700 mb-2">Voxbay UPIN (Password)</label>
                    <input 
                      type="password" 
                      value={tenantData.voxbay_upin} 
                      onChange={(e) => setTenantData({...tenantData, voxbay_upin: e.target.value})}
                      placeholder="••••••••••••••••••••••••"
                      className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition" 
                    />
                  </div>
                  <div className="sm:col-span-2">
                    <label className="block text-sm font-semibold text-slate-700 mb-2">Caller ID / DID Number</label>
                    <input 
                      type="text" 
                      value={tenantData.voxbay_callerid} 
                      onChange={(e) => setTenantData({...tenantData, voxbay_callerid: e.target.value})}
                      placeholder="919876543210"
                      className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition" 
                    />
                  </div>
                </div>
              ) : (
                <div className="grid sm:grid-cols-2 gap-4 animate-fade-in-up">
                  <div>
                    <label className="block text-sm font-semibold text-slate-700 mb-2">Exotel Account SID</label>
                    <input 
                      type="text" 
                      value={tenantData.exotel_sid} 
                      onChange={(e) => setTenantData({...tenantData, exotel_sid: e.target.value})}
                      placeholder="e.g. beehub1"
                      className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition" 
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-semibold text-slate-700 mb-2">Exotel Subdomain / Cluster</label>
                    <div className="relative">
                      <select
                        value={tenantData.exotel_subdomain}
                        onChange={(e) => setTenantData({...tenantData, exotel_subdomain: e.target.value})}
                        className="w-full appearance-none bg-slate-50 border border-slate-200 rounded-xl pl-4 pr-10 py-3 text-sm font-medium outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition cursor-pointer"
                      >
                        <option value="api.exotel.com">Singapore / Global (api.exotel.com)</option>
                        <option value="api.in.exotel.com">Mumbai / India (api.in.exotel.com)</option>
                      </select>
                      <div className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none">
                        <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" viewBox="0 0 24 24"><polyline points="6 9 12 15 18 9"/></svg>
                      </div>
                    </div>
                  </div>
                  <div className="sm:col-span-2">
                    <label className="block text-sm font-semibold text-slate-700 mb-2">Exotel API Key (Username)</label>
                    <input 
                      type="text" 
                      value={tenantData.exotel_api_key} 
                      onChange={(e) => setTenantData({...tenantData, exotel_api_key: e.target.value})}
                      placeholder="Enter Exotel API Key"
                      className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition" 
                    />
                  </div>
                  <div className="sm:col-span-2">
                    <label className="block text-sm font-semibold text-slate-700 mb-2">Exotel API Token (Password)</label>
                    <input 
                      type="password" 
                      value={tenantData.exotel_api_token} 
                      onChange={(e) => setTenantData({...tenantData, exotel_api_token: e.target.value})}
                      placeholder="••••••••••••••••••••••••"
                      className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition" 
                    />
                  </div>
                  <div className="sm:col-span-2">
                    <label className="block text-sm font-semibold text-slate-700 mb-2">Virtual Number (ExoPhone / Caller ID)</label>
                    <input 
                      type="text" 
                      value={tenantData.exotel_callerid} 
                      onChange={(e) => setTenantData({...tenantData, exotel_callerid: e.target.value})}
                      placeholder="e.g. +91XXXXXXXXXX"
                      className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition" 
                    />
                  </div>
                </div>
              )}
            </div>

            {/* Retail and wholesale can send from different accounts. Anything left
                blank on the B2B side falls back to the B2C one. */}
            <div className="pt-6 border-t border-slate-100">
              <div className="flex flex-wrap items-center gap-3">
                <span className="text-sm font-semibold text-slate-700">Sending account</span>
                <div className="inline-flex rounded-xl bg-slate-100 p-1">
                  {(["b2c", "b2b"] as const).map(side => (
                    <button key={side} type="button" onClick={() => setIntSide(side)}
                      className={`px-4 py-1.5 rounded-lg text-xs font-bold uppercase tracking-wide transition ${
                        intSide === side ? "bg-white text-indigo-600 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}>
                      {side}
                    </button>
                  ))}
                </div>
                <span className="text-xs text-slate-400">
                  {intSide === "b2b"
                    ? "Used by wholesale proforma invoices and dispatch invoices. Blank fields fall back to B2C."
                    : "Used by everything except the wholesale documents."}
                </span>
              </div>
            </div>

            <div className="pt-6 border-t border-slate-100">
              <h3 className="text-lg font-bold text-slate-900 mb-1">WhatsApp Automation <span className="text-xs font-semibold text-emerald-600 align-middle">Cloud API</span></h3>
              <p className="text-sm text-slate-500 mb-6">Connect Meta WhatsApp Cloud API to send messages from automations and bulk campaigns.</p>
              <div className="grid sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-semibold text-slate-700 mb-2">Phone Number ID</label>
                  <input type="text" value={fld("whatsapp_phone_number_id")}
                    onChange={(e) => setFld("whatsapp_phone_number_id", e.target.value)}
                    placeholder="e.g. 1234567890" className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition" />
                </div>
                <div>
                  <label className="block text-sm font-semibold text-slate-700 mb-2">WhatsApp Business Account ID</label>
                  <input type="text" value={fld("whatsapp_business_account_id")}
                    onChange={(e) => setFld("whatsapp_business_account_id", e.target.value)}
                    placeholder="Optional" className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition" />
                </div>
                <div className="sm:col-span-2">
                  <label className="block text-sm font-semibold text-slate-700 mb-2">Permanent Access Token</label>
                  <input type="password" value={fld("whatsapp_access_token")}
                    onChange={(e) => setFld("whatsapp_access_token", e.target.value)}
                    placeholder="•••• (leave masked to keep current)" className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition" />
                </div>
                <div className="sm:col-span-2">
                  <label className="block text-sm font-semibold text-slate-700 mb-2">Webhook Verify Token</label>
                  <input type="text" value={fld("whatsapp_verify_token")}
                    onChange={(e) => setFld("whatsapp_verify_token", e.target.value)}
                    placeholder="Any secret string you choose (used to verify the webhook)" className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition" />
                </div>
                <div className="sm:col-span-2">
                  <label className="block text-sm font-semibold text-slate-700 mb-2">Inbound Webhook URL <span className="text-slate-400 font-normal">(paste into Meta → Configuration)</span></label>
                  <input readOnly onFocus={(e) => e.target.select()} value={`${getApiBase(domain)}/api/whatsapp/webhook`}
                    className="w-full bg-slate-100 border border-slate-200 rounded-xl px-4 py-3 text-xs font-mono text-slate-600" />
                </div>
              </div>
            </div>

            <div className="pt-6 border-t border-slate-100">
              <h3 className="text-lg font-bold text-slate-900 mb-1">Email Integration <span className="text-xs font-semibold text-indigo-600 align-middle">SMTP</span></h3>
              <p className="text-sm text-slate-500 mb-4">
                Outgoing email for the CRM — customer emails, automation &quot;Send Email&quot; actions and
                purchase orders to vendors. Gmail / Google Workspace needs an <b>App Password</b>, not your login password.
              </p>

              {emailStatus && (
                <div className={`mb-4 flex flex-wrap items-center gap-3 px-4 py-3 rounded-xl border text-sm ${emailStatus.configured ? "bg-emerald-50 border-emerald-100 text-emerald-700" : "bg-amber-50 border-amber-100 text-amber-700"}`}>
                  <span className="font-semibold">
                    {emailStatus.configured
                      ? `✓ Connected — sending as ${emailStatus.from_address}`
                      : "Not configured — emails are written to the server log instead of being sent."}
                  </span>
                  {emailStatus.configured && emailStatus.source === "env" && (
                    <span className="text-[11px] text-emerald-600">(from server environment; fill in below to manage it here)</span>
                  )}
                </div>
              )}

              <div className="grid sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-semibold text-slate-700 mb-2">SMTP Host</label>
                  <input type="text" value={fld("email_host") || ""}
                    onChange={(e) => setFld("email_host", e.target.value)}
                    placeholder="smtp.gmail.com"
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition" />
                </div>
                <div>
                  <label className="block text-sm font-semibold text-slate-700 mb-2">Port</label>
                  <input type="number" value={fld("email_port") ?? 587}
                    onChange={(e) => setFld("email_port", parseInt(e.target.value) || 587)}
                    placeholder="587"
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition" />
                  <p className="text-xs text-slate-400 mt-2">587 with TLS, or 465 with SSL.</p>
                </div>
                <div>
                  <label className="block text-sm font-semibold text-slate-700 mb-2">Username</label>
                  <input type="text" value={fld("email_host_user") || ""}
                    onChange={(e) => setFld("email_host_user", e.target.value)}
                    placeholder="you@energyfox.in"
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition" />
                </div>
                <div>
                  <label className="block text-sm font-semibold text-slate-700 mb-2">Password / App Password</label>
                  <input type="password" value={fld("email_host_password") || ""}
                    onChange={(e) => setFld("email_host_password", e.target.value)}
                    placeholder="•••• (leave masked to keep current)"
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition" />
                </div>
                <div className="sm:col-span-2 flex flex-wrap items-center gap-6">
                  <label className="flex items-center gap-2 text-sm font-medium text-slate-700 cursor-pointer">
                    <input type="checkbox" checked={!!fld("email_use_tls")}
                      onChange={(e) => setFlds({ email_use_tls: e.target.checked, email_use_ssl: e.target.checked ? false : fld("email_use_ssl") })}
                      className="w-4 h-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500/30" />
                    Use TLS (port 587)
                  </label>
                  <label className="flex items-center gap-2 text-sm font-medium text-slate-700 cursor-pointer">
                    <input type="checkbox" checked={!!fld("email_use_ssl")}
                      onChange={(e) => setFlds({ email_use_ssl: e.target.checked, email_use_tls: e.target.checked ? false : fld("email_use_tls") })}
                      className="w-4 h-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500/30" />
                    Use SSL (port 465)
                  </label>
                </div>
                <div>
                  <label className="block text-sm font-semibold text-slate-700 mb-2">From Name</label>
                  <input type="text" value={fld("email_from_name") || ""}
                    onChange={(e) => setFld("email_from_name", e.target.value)}
                    placeholder="EnergyFox"
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition" />
                </div>
                <div>
                  <label className="block text-sm font-semibold text-slate-700 mb-2">From Address</label>
                  <input type="email" value={fld("email_from_address") || ""}
                    onChange={(e) => setFld("email_from_address", e.target.value)}
                    placeholder="info@energyfox.in"
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition" />
                  <p className="text-xs text-slate-400 mt-2">Defaults to the username if left blank.</p>
                </div>
                <div className="sm:col-span-2">
                  <EmailSignatureEditor
                    plain={fld("email_signature") || ""}
                    html={fld("email_signature_html") || ""}
                    onPlain={(v) => setFld("email_signature", v)}
                    onHtml={(v) => setFld("email_signature_html", v)}
                  />
                </div>
                <div className="sm:col-span-2 flex flex-wrap items-center gap-3">
                  <button type="button" onClick={sendTestEmail} disabled={testingEmail}
                    className="px-5 py-2.5 bg-slate-800 text-white rounded-xl text-sm font-semibold hover:bg-slate-900 disabled:opacity-50 transition">
                    {testingEmail ? "Sending…" : "Send Test Email"}
                  </button>
                  <span className="text-xs text-slate-400">Save first, then send a test to yourself to confirm it works.</span>
                </div>
              </div>
            </div>

            </>)}

            {tab === "documents" && (<>
            <div className="pt-6 border-t border-slate-100">
              <InventoryDocumentsSection domain={domain} isAdmin={isAdmin} />
            </div>

            <div className="pt-6 border-t border-slate-100">
              <h3 className="text-lg font-bold text-slate-900 mb-4">Invoice Generation</h3>
              <p className="text-sm text-slate-500 mb-6">Upload a DOCX invoice template. The system will use this template to automatically generate PDF invoices when a lead completes payment.</p>
              
              <div>
                <label className="block text-sm font-semibold text-slate-700 mb-2">Invoice Template (.docx)</label>
                <div className="flex items-center gap-4">
                  <div className="flex-1">
                    <input 
                      type="file" 
                      accept=".docx"
                      onChange={(e) => {
                        if (e.target.files && e.target.files.length > 0) {
                          setInvoiceFile(e.target.files[0]);
                        }
                      }}
                      className="block w-full text-sm text-slate-500 file:mr-4 file:py-2.5 file:px-4 file:rounded-xl file:border-0 file:text-sm file:font-semibold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100 transition cursor-pointer"
                    />
                    {(invoiceFile || invoiceFileName) && (
                      <p className="text-xs text-emerald-600 mt-2 font-semibold flex items-center gap-1">
                        <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path d="M5 13l4 4L19 7"/></svg>
                        {invoiceFile ? invoiceFile.name : invoiceFileName}
                      </p>
                    )}
                  </div>
                </div>
                <div className="mt-4 bg-slate-50 rounded-xl p-4 border border-slate-100">
                  <p className="text-xs font-semibold text-slate-700 mb-2">Supported Template Variables:</p>
                  <div className="flex flex-wrap gap-2">
                    {["{{lead_name}}", "{{lead_email}}", "{{lead_phone}}", "{{amount}}", "{{date}}", "{{invoice_number}}", "{{product_name}}"].map(v => (
                      <span key={v} className="bg-white border border-slate-200 text-slate-500 px-2 py-1 rounded text-[11px] font-mono">{v}</span>
                    ))}
                  </div>
                </div>
              </div>
            </div>
 
            </>)}

            {tab === "automation" && (<>
            <div className="pt-6 border-t border-slate-100">
              <h3 className="text-lg font-bold text-slate-900 mb-2">⏰ Target Popup Intervals</h3>
              <p className="text-sm text-slate-500 mb-6">Configure how frequently popup alerts appear to agents who are below their daily or monthly performance targets.</p>
              
              <div className="grid sm:grid-cols-2 gap-6">
                <div>
                  <label className="block text-sm font-semibold text-slate-700 mb-2">Monthly Target Popup (hours)</label>
                  <input 
                    type="number" 
                    min="1"
                    required
                    value={popupConfig.monthly_popup_interval_hours} 
                    onChange={(e) => setPopupConfig({...popupConfig, monthly_popup_interval_hours: parseInt(e.target.value) || 1})}
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition" 
                  />
                  <p className="text-xs text-slate-400 mt-2">Interval in hours between popup warnings for monthly targets.</p>
                </div>
                <div>
                  <label className="block text-sm font-semibold text-slate-700 mb-2">Daily Target Popup (hours)</label>
                  <input 
                    type="number" 
                    min="1"
                    required
                    value={popupConfig.daily_popup_interval_hours} 
                    onChange={(e) => setPopupConfig({...popupConfig, daily_popup_interval_hours: parseInt(e.target.value) || 1})}
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition" 
                  />
                  <p className="text-xs text-slate-400 mt-2">Interval in hours between popup warnings for daily targets.</p>
                </div>
              </div>
            </div>

            <div className="pt-6 border-t border-slate-100">
              <h3 className="text-lg font-bold text-slate-900 mb-2">Custom Lead Statuses</h3>
              <p className="text-sm text-slate-500 mb-6">Create additional stages for your lead pipeline. Default statuses cannot be modified.</p>
              
              <div className="space-y-4">
                {/* Add new status form */}
                <div className="flex gap-4">
                  <div className="flex-1">
                    <input 
                      type="text" 
                      value={newStatusLabel} 
                      onChange={(e) => setNewStatusLabel(e.target.value)}
                      placeholder="e.g. On Hold, Cold Lead"
                      className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition" 
                    />
                  </div>
                  <button 
                    type="button"
                    onClick={handleAddCustomStatus}
                    className="bg-indigo-50 hover:bg-indigo-100 text-indigo-700 font-bold px-6 py-3 rounded-xl transition"
                  >
                    Add Status
                  </button>
                </div>

                {/* List of custom statuses */}
                {customStatuses.length > 0 ? (
                  <div className="grid sm:grid-cols-2 gap-3 mt-4">
                    {customStatuses.map((s, idx) => (
                      <div key={idx} className="bg-slate-50 border border-slate-200 rounded-xl p-4 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className={`w-2.5 h-2.5 rounded-full`} style={{ backgroundColor: s.color || '#a855f7' }} />
                          <span className="font-bold text-sm text-slate-800">{s.label}</span>
                          <span className="text-xs text-slate-400 font-mono">({s.value})</span>
                        </div>
                        <button
                          type="button"
                          onClick={() => handleRemoveCustomStatus(idx)}
                          className="text-red-500 hover:text-red-700 text-sm font-semibold transition"
                        >
                          Remove
                        </button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-slate-400 italic mt-2">No custom lead statuses added yet.</p>
                )}
              </div>
            </div>

            </>)}

            {tab === "documents" && (<>
            <div className="pt-6 border-t border-slate-100">
              <h3 className="text-lg font-bold text-slate-900 mb-2">Warranty Document</h3>
              <p className="text-sm text-slate-500 mb-6">Fixed details printed on the generated warranty certificate — company identity, director sign-off, default warranty years, signature &amp; seal. These are not entered per customer.</p>

              <div className="grid sm:grid-cols-2 gap-4">
                <div className="sm:col-span-2">
                  <label className="block text-sm font-semibold text-slate-700 mb-2">Company Name (on certificate)</label>
                  <input type="text" value={tenantData.warranty_company_name}
                    onChange={(e) => setTenantData({ ...tenantData, warranty_company_name: e.target.value })}
                    placeholder="Energyfox Consultants Pvt. Ltd."
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition" />
                </div>
                <div>
                  <label className="block text-sm font-semibold text-slate-700 mb-2">CIN</label>
                  <input type="text" value={tenantData.warranty_cin}
                    onChange={(e) => setTenantData({ ...tenantData, warranty_cin: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition" />
                </div>
                <div>
                  <label className="block text-sm font-semibold text-slate-700 mb-2">GST</label>
                  <input type="text" value={tenantData.warranty_gst}
                    onChange={(e) => setTenantData({ ...tenantData, warranty_gst: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition" />
                </div>
                <div>
                  <label className="block text-sm font-semibold text-slate-700 mb-2">Director Name</label>
                  <input type="text" value={tenantData.warranty_director_name}
                    onChange={(e) => setTenantData({ ...tenantData, warranty_director_name: e.target.value })}
                    placeholder="AKASH AG"
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition" />
                </div>
                <div>
                  <label className="block text-sm font-semibold text-slate-700 mb-2">Designation</label>
                  <input type="text" value={tenantData.warranty_director_designation}
                    onChange={(e) => setTenantData({ ...tenantData, warranty_director_designation: e.target.value })}
                    placeholder="Director"
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition" />
                </div>
                <div>
                  <label className="block text-sm font-semibold text-slate-700 mb-2">Solar Panels Warranty (Years)</label>
                  <input type="text" value={tenantData.warranty_panel_years}
                    onChange={(e) => setTenantData({ ...tenantData, warranty_panel_years: e.target.value })}
                    placeholder="30"
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition" />
                </div>
                <div>
                  <label className="block text-sm font-semibold text-slate-700 mb-2">Inverter Warranty (Years)</label>
                  <input type="text" value={tenantData.warranty_inverter_years}
                    onChange={(e) => setTenantData({ ...tenantData, warranty_inverter_years: e.target.value })}
                    placeholder="12"
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition" />
                </div>
                <div>
                  <label className="block text-sm font-semibold text-slate-700 mb-2">Service Warranty (Years)</label>
                  <input type="text" value={tenantData.warranty_service_years}
                    onChange={(e) => setTenantData({ ...tenantData, warranty_service_years: e.target.value })}
                    placeholder="5"
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition" />
                </div>
                <div>
                  <label className="block text-sm font-semibold text-slate-700 mb-2">Signature</label>
                  <div className="flex items-center gap-4">
                    <div className="w-24 h-16 rounded-xl bg-slate-100 border-2 border-dashed border-slate-300 flex items-center justify-center overflow-hidden flex-shrink-0">
                      {previewSig ? <img src={previewSig} alt="Signature" className="w-full h-full object-contain" />
                        : <span className="text-[10px] text-slate-400">No signature</span>}
                    </div>
                    <input type="file" accept="image/*"
                      onChange={(e) => {
                        if (e.target.files && e.target.files.length > 0) {
                          const file = e.target.files[0];
                          setSigFile(file);
                          setPreviewSig(URL.createObjectURL(file));
                        }
                      }}
                      className="block w-full text-sm text-slate-500 file:mr-4 file:py-2 file:px-3 file:rounded-xl file:border-0 file:text-xs file:font-semibold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100 transition cursor-pointer" />
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-semibold text-slate-700 mb-2">Company Seal</label>
                  <div className="flex items-center gap-4">
                    <div className="w-16 h-16 rounded-xl bg-slate-100 border-2 border-dashed border-slate-300 flex items-center justify-center overflow-hidden flex-shrink-0">
                      {previewSeal ? <img src={previewSeal} alt="Seal" className="w-full h-full object-contain" />
                        : <span className="text-[10px] text-slate-400">No seal</span>}
                    </div>
                    <input type="file" accept="image/*"
                      onChange={(e) => {
                        if (e.target.files && e.target.files.length > 0) {
                          const file = e.target.files[0];
                          setSealFile(file);
                          setPreviewSeal(URL.createObjectURL(file));
                        }
                      }}
                      className="block w-full text-sm text-slate-500 file:mr-4 file:py-2 file:px-3 file:rounded-xl file:border-0 file:text-xs file:font-semibold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100 transition cursor-pointer" />
                  </div>
                </div>
                <p className="sm:col-span-2 text-xs text-slate-400">Transparent PNG works best for the signature and seal. They are embedded in every generated warranty certificate.</p>
              </div>
            </div>
            </>)}
          </div>

          <div className="mt-8 flex justify-end">
            <button 
              type="submit" 
              disabled={saving}
              className="bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-3 px-8 rounded-xl transition shadow-lg shadow-indigo-600/20 disabled:opacity-50"
            >
              {saving ? "Saving..." : "Save Changes"}
            </button>
          </div>
        </form>
      </div>
      )}
    </div>
  );
}

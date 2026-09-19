"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";
import { useLeadStatuses } from "@/hooks/useLeadStatuses";
import { useDistricts, districtOptions } from "@/hooks/useDistricts";
import { FALLBACK_STATUS_META, getLatestNote } from "@/lib/lead-statuses";

import React, { useState, useEffect, useRef, useCallback } from "react";
import Link from "next/link";
import { DetailSkeleton } from "@/components/Skeleton";
import { getSourceLabel, formatCurrency } from "@/lib/mock-data";
import SiteVisitSection from "./SiteVisitSection";
import LeadQuotationsPanel from "@/components/LeadQuotationsPanel";

export default function LeadDetailPage({
  params: paramsPromise,
}: {
  params: Promise<{ domain: string; id: string }>;
}) {
  const params = React.use(paramsPromise);
  // ─── Dynamic lead statuses ────────────────────────────────────────
  const { statusMeta } = useLeadStatuses(APP_SLUG);
  
  const getRecordingUrl = (url: string, id: number) => {
    if (!url) return "";
    if (url.includes("exotel") || url.includes("recordings.exotel")) {
      const token = localStorage.getItem(`${APP_SLUG}_access`);
      return `${getApiBase(APP_SLUG)}/api/calls/${id}/recording_proxy/${token ? `?token=${token}` : ''}`;
    }
    return url;
  };

  const [lead, setLead] = useState<any>(null);
  const [tasks, setTasks] = useState<any[]>([]);
  const [attachments, setAttachments] = useState<any[]>([]);
  const [calls, setCalls] = useState<any[]>([]);
  const [loadingCalls, setLoadingCalls] = useState(false);
  const [leadHistory, setLeadHistory] = useState<any[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [waMessages, setWaMessages] = useState<any[]>([]);
  const [waInput, setWaInput] = useState("");
  const [waSending, setWaSending] = useState(false);
  const [loading, setLoading] = useState(true);
  const pollingRef = useRef<NodeJS.Timeout | null>(null);
  
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [showEditModal, setShowEditModal] = useState(false);
  const [showManualCallModal, setShowManualCallModal] = useState(false);
  const [manualCallForm, setManualCallForm] = useState({ outcome: "connected", duration_seconds: "0", notes: "", recording_url: "" });
  const [editingCall, setEditingCall] = useState<any | null>(null);
  const [teamMembers, setTeamMembers] = useState<{ id: number; name: string }[]>([]);
  const [productsList, setProductsList] = useState<{ id: number; name: string; default_price: number }[]>([]);
  const [currentUser, setCurrentUser] = useState<any>(null);
  const [newNote, setNewNote] = useState("");
  const [addingNote, setAddingNote] = useState(false);
  // Notes are their own records now, each carrying who wrote it — that is what
  // lets someone tidy their own words without touching a colleague's.
  const [noteList, setNoteList] = useState<any[]>([]);
  const [editingNote, setEditingNote] = useState<number | null>(null);
  const [notesDraft, setNotesDraft] = useState("");
  const [savingNotes, setSavingNotes] = useState(false);
  const [newEditNote, setNewEditNote] = useState("");
  const [bdeList, setBdeList] = useState<{ id: number; name: string; branch_name: string | null }[]>([]);
  const [showBdeModal, setShowBdeModal] = useState(false);
  const [selectedBde, setSelectedBde] = useState("");
  const [assigningBde, setAssigningBde] = useState(false);
  // The product on the deal, set from the header by whoever works the site visit.
  const [productList, setProductList] = useState<{ id: number; name: string; default_price: string }[]>([]);
  const [showProductModal, setShowProductModal] = useState(false);
  const [productChoice, setProductChoice] = useState("");
  const [seedPrice, setSeedPrice] = useState(true);
  const [savingProduct, setSavingProduct] = useState(false);
  // Bumped when the product changes, to make the site visit re-read its deal —
  // the price is seeded from the product, and it should not wait for a refresh.
  const [dealVersion, setDealVersion] = useState(0);
  const [pushingDoc, setPushingDoc] = useState(false);
  const [docList, setDocList] = useState<{ id: number; name: string; branch_name: string | null }[]>([]);
  const [showDocModal, setShowDocModal] = useState(false);
  const [selectedDoc, setSelectedDoc] = useState("");
  const [assigningDoc, setAssigningDoc] = useState(false);

  const [form, setForm] = useState({
    first_name: "",
    last_name: "",
    email: "",
    phone: "",
    company: "",
    district: "",
    installation_location: "",
    source: "manual",
    status: "new",
    value: "0",
    notes: "",
    assigned_to: "",
    product: "",
  });

  const fetchCalls = useCallback(async () => {
    const token = localStorage.getItem(`${APP_SLUG}_access`);
    if (!token) return;
    setLoadingCalls(true);
    try {
      const res = await fetch(`${getApiBase(APP_SLUG)}/api/calls/?lead=${params.id}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setCalls(Array.isArray(data) ? data : data.results || []);
      }
    } catch (err) {
      console.error("Error fetching calls:", err);
    } finally {
      setLoadingCalls(false);
    }
  }, [APP_SLUG, params.id]);

  const fetchHistory = useCallback(async () => {
    const token = localStorage.getItem(`${APP_SLUG}_access`);
    if (!token) return;
    setHistoryLoading(true);
    try {
      const res = await fetch(`${getApiBase(APP_SLUG)}/api/leads/${params.id}/history/`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        setLeadHistory(await res.json());
      }
    } catch (err) {
      console.error("Error fetching history:", err);
    } finally {
      setHistoryLoading(false);
    }
  }, [APP_SLUG, params.id]);

  const fetchWa = useCallback(async () => {
    const token = localStorage.getItem(`${APP_SLUG}_access`);
    if (!token) return;
    try {
      const res = await fetch(`${getApiBase(APP_SLUG)}/api/whatsapp/messages/?lead=${params.id}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setWaMessages(await res.json());
    } catch { /* ignore */ }
  }, [APP_SLUG, params.id]);

  const sendWa = async () => {
    if (!waInput.trim()) return;
    setWaSending(true);
    const token = localStorage.getItem(`${APP_SLUG}_access`);
    try {
      const res = await fetch(`${getApiBase(APP_SLUG)}/api/whatsapp/send/`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ lead_id: params.id, kind: "text", text: waInput }),
      });
      const d = await res.json().catch(() => ({}));
      if (res.ok) { setWaInput(""); fetchWa(); }
      else alert(d.detail || d.error || "Failed to send WhatsApp message.");
    } catch { alert("Network error."); } finally { setWaSending(false); }
  };

  const fetchData = async () => {
    try {
      const token = localStorage.getItem(`${APP_SLUG}_access`);
      if (!token) return;

      const headers = { Authorization: `Bearer ${token}` };
      const apiBase = getApiBase(APP_SLUG);

      const [leadRes, tasksRes, attachmentsRes] = await Promise.all([
        fetch(`${apiBase}/api/leads/${params.id}/`, { headers }),
        fetch(`${apiBase}/api/tasks/?lead=${params.id}`, { headers }),
        fetch(`${apiBase}/api/leads/${params.id}/attachments/`, { headers }),
      ]);

      if (leadRes.ok) {
        setLead(await leadRes.json());
      }
      
      if (tasksRes.ok) {
        const tasksData = await tasksRes.json();
        setTasks(Array.isArray(tasksData) ? tasksData : tasksData.results || []);
      }

      if (attachmentsRes.ok) {
        setAttachments(await attachmentsRes.json());
      }

    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
    // Also fetch calls, history & WhatsApp thread
    fetchCalls();
    fetchHistory();
    fetchWa();
    fetchNotes();
  };

  useEffect(() => {
    fetchData();

    const token = localStorage.getItem(`${APP_SLUG}_access`);
    if (!token) return;

    // Fetch team members
    fetch(`${getApiBase(APP_SLUG)}/api/users/`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.json())
      .then(d => {
        const arr = Array.isArray(d) ? d : (d.results || []);
        setTeamMembers(arr.map((u: any) => ({ id: u.id, name: `${u.first_name} ${u.last_name}`.trim() || u.username })));
      }).catch(console.error);

    // Fetch products
    fetch(`${getApiBase(APP_SLUG)}/api/products/`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.json())
      .then(d => {
        const arr = Array.isArray(d) ? d : (d.results || []);
        setProductsList(arr.map((p: any) => ({ id: p.id, name: p.name, default_price: parseFloat(p.default_price) || 0 })));
      }).catch(console.error);

    // Fetch current user
    fetch(`${getApiBase(APP_SLUG)}/api/users/me/`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.json())
      .then(d => setCurrentUser(d))
      .catch(console.error);
  }, [APP_SLUG, params.id]);

  const openEdit = () => {
    if (!lead) return;
    setForm({
      first_name: lead.first_name || "",
      last_name: lead.last_name || "",
      email: lead.email || "",
      phone: lead.phone || "",
      company: lead.company || "",
      district: lead.district || "",
      installation_location: lead.installation_location || "",
      source: lead.source || "manual",
      status: lead.status || "new",
      value: (lead.value || 0).toString(),
      notes: lead.notes || "",
      assigned_to: lead.assigned_to?.toString() || "",
      product: lead.product?.toString() || "",
    });
    setNewEditNote("");
    setShowEditModal(true);
  };

  /** The product picker.
   *
   *  Writes through the site-visit endpoint rather than the lead, because a BDE
   *  is refused on the lead record itself — the site visit is the screen they
   *  own, and the product and its price belong to the deal they settle there.
   */
  const openProductModal = async () => {
    setProductChoice(lead?.product ? String(lead.product) : "");
    setShowProductModal(true);
    const token = localStorage.getItem(`${APP_SLUG}_access`);
    try {
      const r = await fetch(`${getApiBase(APP_SLUG)}/api/products/`, { headers: { Authorization: `Bearer ${token}` } });
      if (r.ok) {
        const d = await r.json();
        setProductList(Array.isArray(d) ? d : d.results || []);
      }
    } catch {}
  };

  const saveProduct = async () => {
    setSavingProduct(true);
    const token = localStorage.getItem(`${APP_SLUG}_access`);
    const chosen = productList.find(p => String(p.id) === productChoice);
    // Picking a product seeds the price from its catalogue figure; the BDE can
    // still change it in the Deal section, where the discount lives.
    const body: Record<string, unknown> = { product: productChoice || null };
    if (chosen && seedPrice) body.product_price = String(chosen.default_price ?? 0);
    try {
      const r = await fetch(`${getApiBase(APP_SLUG)}/api/leads/${params.id}/site-visit/`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify(body),
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        alert(err.error || err.detail || "Could not save the product.");
        return;
      }
      setShowProductModal(false);
      fetchData();                       // the header label follows
      setDealVersion(v => v + 1);        // and so does the site visit's deal
    } catch {
      alert("Network error. Please try again.");
    } finally {
      setSavingProduct(false);
    }
  };

  const openBdeModal = async () => {
    setSelectedBde(lead?.bde?.toString() || "");
    setShowBdeModal(true);
    const token = localStorage.getItem(`${APP_SLUG}_access`);
    try {
      const r = await fetch(`${getApiBase(APP_SLUG)}/api/users/bdes/`, { headers: { Authorization: `Bearer ${token}` } });
      if (r.ok) setBdeList(await r.json());
    } catch {}
  };

  const assignBde = async () => {
    const token = localStorage.getItem(`${APP_SLUG}_access`);
    setAssigningBde(true);
    try {
      const r = await fetch(`${getApiBase(APP_SLUG)}/api/leads/${params.id}/assign-bde/`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ bde: selectedBde || null }),
      });
      if (r.ok) { setLead(await r.json()); setShowBdeModal(false); }
      else alert("Failed to assign BDE.");
    } catch { alert("Network error."); }
    finally { setAssigningBde(false); }
  };

  const pushToDocumentation = async () => {
    if (!confirm("Push this lead to the documentation team?")) return;
    const token = localStorage.getItem(`${APP_SLUG}_access`);
    setPushingDoc(true);
    try {
      const r = await fetch(`${getApiBase(APP_SLUG)}/api/leads/${params.id}/push-to-documentation/`, {
        method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      });
      if (r.ok) setLead(await r.json());
      else { const d = await r.json().catch(() => ({})); alert(d.error || "Failed to push to documentation."); }
    } catch { alert("Network error."); }
    finally { setPushingDoc(false); }
  };

  const openDocModal = async () => {
    setSelectedDoc(lead?.documentation_staff?.toString() || "");
    setShowDocModal(true);
    const token = localStorage.getItem(`${APP_SLUG}_access`);
    try {
      const r = await fetch(`${getApiBase(APP_SLUG)}/api/users/documentation-staff/`, { headers: { Authorization: `Bearer ${token}` } });
      if (r.ok) setDocList(await r.json());
    } catch {}
  };

  const assignDoc = async () => {
    const token = localStorage.getItem(`${APP_SLUG}_access`);
    setAssigningDoc(true);
    try {
      const r = await fetch(`${getApiBase(APP_SLUG)}/api/leads/${params.id}/assign-documentation/`, {
        method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ staff: selectedDoc || null }),
      });
      if (r.ok) { setLead(await r.json()); setShowDocModal(false); }
      else { const d = await r.json().catch(() => ({})); alert(d.error || "Failed to assign documentation staff."); }
    } catch { alert("Network error."); }
    finally { setAssigningDoc(false); }
  };

  const handleEditSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const token = localStorage.getItem(`${APP_SLUG}_access`);
    if (!token) return;

    const finalNotes = newEditNote.trim()
      ? (form.notes ? `${form.notes}\n\n${newEditNote.trim()}` : newEditNote.trim())
      : form.notes;

    const payload = {
      first_name: form.first_name,
      last_name: form.last_name,
      email: form.email,
      phone: form.phone,
      company: form.company,
      district: form.district,
      installation_location: form.installation_location,
      source: form.source,
      status: form.status,
      notes: finalNotes,
      assigned_to: form.assigned_to ? parseInt(form.assigned_to) : null,
      product: form.product ? parseInt(form.product) : null,
    };

    try {
      // A lead can only be marked Converted after a BDE has been assigned.
      if (payload.status === 'converted' && lead.status !== 'converted' && !lead.bde) {
        alert("Assign a BDE to this lead before marking it Converted.");
        return;
      }

      const url = `${getApiBase(APP_SLUG)}/api/leads/${params.id}/`;
      const res = await fetch(url, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(payload),
      });

      if (res.ok) {
        const updatedLead = await res.json();
        setLead(updatedLead);
        setShowEditModal(false);
        fetchData();
      } else {
        const err = await res.json();
        const errMsgs = typeof err === 'object' ? Object.entries(err).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`).join(' | ') : null;
        alert(err.invoice?.[0] || err.error || errMsgs || "Failed to save lead");
      }
    } catch (err) {
      console.error(err);
      alert("An error occurred while saving the lead.");
    }
  };

  const notesUrl = `${getApiBase(APP_SLUG)}/api/leads/${params.id}/notes/`;
  const authJson = () => ({
    "Content-Type": "application/json",
    Authorization: `Bearer ${localStorage.getItem(`${APP_SLUG}_access`)}`,
  });

  const fetchNotes = async () => {
    try {
      const r = await fetch(notesUrl, { headers: authJson() });
      if (r.ok) setNoteList(await r.json());
    } catch { /* the panel keeps what it had */ }
  };

  const handleAddNote = async () => {
    if (!newNote.trim()) return;
    setAddingNote(true);
    try {
      const r = await fetch(notesUrl, {
        method: "POST", headers: authJson(),
        body: JSON.stringify({ body: newNote.trim() }),
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        alert(err.error || err.detail || "Could not add the note.");
        return;
      }
      setNewNote("");
      await Promise.all([fetchNotes(), fetchHistory()]);
    } catch {
      alert("Network error. Please try again.");
    } finally {
      setAddingNote(false);
    }
  };

  /** Correct one note. Only its author — or an admin — gets here; the server
   *  checks again, and the pencil is only drawn when it says `can_edit`. */
  const saveNote = async (id: number) => {
    if (!notesDraft.trim()) return;
    setSavingNotes(true);
    try {
      const r = await fetch(`${notesUrl}${id}/`, {
        method: "PATCH", headers: authJson(),
        body: JSON.stringify({ body: notesDraft.trim() }),
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        alert(err.error || err.detail || "Could not save the note.");
        return;
      }
      setEditingNote(null);
      await Promise.all([fetchNotes(), fetchHistory()]);
    } catch {
      alert("Network error. Please try again.");
    } finally {
      setSavingNotes(false);
    }
  };

  const deleteNote = async (id: number) => {
    if (!confirm("Delete this note?")) return;
    try {
      const r = await fetch(`${notesUrl}${id}/`, { method: "DELETE", headers: authJson() });
      if (!r.ok && r.status !== 204) {
        const err = await r.json().catch(() => ({}));
        alert(err.error || err.detail || "Could not delete the note.");
        return;
      }
      await Promise.all([fetchNotes(), fetchHistory()]);
    } catch { alert("Network error. Please try again."); }
  };


  // A view-only (spectator) account reads this page and touches nothing on it.
  // The per-lead can_* flags already arrive false from the server; these are the
  // controls decided client-side, which have to agree.
  const isSpectator = !!currentUser?.read_only;
  // Picked from Settings → Districts, the same list an import is matched
  // against, so a hand-typed district cannot differ from an imported one.
  const { districts: configuredDistricts } = useDistricts();
  const canAssign = !isSpectator && (currentUser?.is_staff || currentUser?.is_general_manager || currentUser?.is_manager);
  // A BDE reports through the site visit; the lead status belongs to the tele
  // caller / managers. Mirrors can_edit_lead_status() on the backend.
  const canEditStatus = !isSpectator && (!currentUser || currentUser.role !== "bde");
  // The lead record belongs to the tele-calling side; a BDE reports through the
  // site visit. Mirrors can_edit_leads() on the backend.
  const canEditLead = !isSpectator && (!currentUser || currentUser.role !== "bde");

  const initiateCall = async () => {
    if (!lead?.phone) return alert("Lead does not have a phone number.");
    if (!confirm(`Initiate automated call to ${lead.first_name}?`)) return;
    const token = localStorage.getItem(`${APP_SLUG}_access`);
    try {
      const r = await fetch(`${getApiBase(APP_SLUG)}/api/calls/initiate/`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ lead_id: lead.id })
      });
      const d = await r.json();
      if (r.ok) {
        if (d.voxbay_click_to_call_url) {
          window.open(d.voxbay_click_to_call_url, "_blank");
          alert("Redirecting to Voxbay mobile calling app...");
        } else {
          alert(d.status || "Call initiated!");
        }
        // Small delay then fetch calls to pick up the new record and trigger polling
        setTimeout(() => fetchCalls(), 500);
      } else {
        const errMsg = d.error || "Failed to initiate call";
        if (errMsg.includes("Telephony is not configured") || errMsg.includes("telephony")) {
          if (confirm(`${errMsg}\n\nWould you like to log this call manually instead?`)) {
            setManualCallForm({ outcome: "connected", duration_seconds: "0", notes: "", recording_url: "" });
            setShowManualCallModal(true);
          }
        } else {
          alert(errMsg);
        }
      }
    } catch { 
      if (confirm("Error connecting to dialer. Would you like to log this call manually?")) {
        setManualCallForm({ outcome: "connected", duration_seconds: "0", notes: "", recording_url: "" });
        setShowManualCallModal(true);
      }
    }
  };

  // Stable polling: only runs when there's an initiated call, uses ref to avoid dependency issues
  const syncCycleRef = useRef(0);
  useEffect(() => {
    const hasInitiated = calls.some((c: any) => c.outcome === 'initiated');

    // Clear any existing poll
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }

    if (!hasInitiated) {
      syncCycleRef.current = 0;
      return;
    }

    pollingRef.current = setInterval(async () => {
      syncCycleRef.current += 1;
      // Every 3rd poll cycle (~15s), trigger sync_exotel to poll Exotel API as fallback
      if (syncCycleRef.current % 3 === 0) {
        try {
          const token = localStorage.getItem(`${APP_SLUG}_access`);
          if (token) {
            await fetch(`${getApiBase(APP_SLUG)}/api/calls/sync_exotel/`, {
              method: "POST",
              headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
            });
          }
        } catch (e) {
          console.error("Exotel sync error:", e);
        }
      }
      fetchCalls();
    }, 5000);

    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [calls.length, calls.map(c => c.outcome).join(','), fetchCalls]);

  const handleManualCallSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const token = localStorage.getItem(`${APP_SLUG}_access`);
    if (!token) return;

    const payload = {
      lead: lead.id,
      outcome: manualCallForm.outcome,
      notes: manualCallForm.notes,
      duration_seconds: manualCallForm.outcome === 'connected' ? (parseInt(manualCallForm.duration_seconds) || 0) : 0,
      recording_url: manualCallForm.outcome === 'connected' ? (manualCallForm.recording_url || null) : null,
    };

    try {
      const res = await fetch(`${getApiBase(APP_SLUG)}/api/calls/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify(payload)
      });
      if (res.ok) {
        setShowManualCallModal(false);
        fetchCalls();
      } else {
        const err = await res.json();
        alert(err.error || "Failed to log call manually");
      }
    } catch {
      alert("Network error. Please try again.");
    }
  };

  const handleEditCallSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingCall) return;
    const token = localStorage.getItem(`${APP_SLUG}_access`);
    if (!token) return;

    const payload = {
      outcome: editingCall.outcome,
      notes: editingCall.notes,
      duration_seconds: editingCall.outcome === 'connected' ? (parseInt(editingCall.duration_seconds) || 0) : 0,
      recording_url: editingCall.outcome === 'connected' ? (editingCall.recording_url || null) : null,
    };

    try {
      const res = await fetch(`${getApiBase(APP_SLUG)}/api/calls/${editingCall.id}/`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify(payload)
      });
      if (res.ok) {
        setEditingCall(null);
        fetchCalls();
      } else {
        const err = await res.json();
        alert(err.error || "Failed to update call log");
      }
    } catch {
      alert("Network error. Please try again.");
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Optional client side validation
    if (file.size > 50 * 1024 * 1024) {
      alert("File size exceeds 50MB limit");
      return;
    }

    setUploading(true);
    try {
      const token = localStorage.getItem(`${APP_SLUG}_access`);
      if (!token) return;

      const formData = new FormData();
      formData.append("file", file);

      const res = await fetch(`${getApiBase(APP_SLUG)}/api/leads/${params.id}/attachments/`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`
        },
        body: formData
      });

      if (res.ok) {
        const newAttachment = await res.json();
        setAttachments([newAttachment, ...attachments]);
      } else {
        const errorData = await res.json();
        alert(errorData.error || "Failed to upload file");
      }
    } catch(err) {
      console.error(err);
      alert("Error uploading file");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  if (loading) {
    return <DetailSkeleton />;
  }

  if (!lead) {
    return (
      <div className="p-8 text-center">
        <h2 className="text-xl font-semibold text-slate-700">Lead not found</h2>
        <Link href={`/leads`} className="text-indigo-600 text-sm mt-2 inline-block">
          ← Back to Leads
        </Link>
      </div>
    );
  }

  // Format creation date
  const createdAt = new Date(lead.created_at);
  const dateStr = isNaN(createdAt.getTime()) ? "" : createdAt.toISOString().split("T")[0];

  const smColors = statusMeta[lead.status] || FALLBACK_STATUS_META;
  
  const sourceColors: Record<string, string> = {
    meta_ads: "bg-blue-50 text-blue-700",
    manual: "bg-slate-50 text-slate-700",
    website: "bg-emerald-50 text-emerald-700",
    referral: "bg-purple-50 text-purple-700",
    linkedin: "bg-sky-50 text-sky-700",
  };

  const typeConfig: Record<string, { label: string; icon: string; bg: string; text: string }> = {
    lead_created:       { label: "Lead Created",       icon: "➕", bg: "bg-indigo-50",  text: "text-indigo-600" },
    lead_status_change: { label: "Status Changed",     icon: "🔄", bg: "bg-amber-50",   text: "text-amber-600"  },
    note_added:         { label: "Note Added",         icon: "📝", bg: "bg-teal-50",    text: "text-teal-600"   },
    task_created:       { label: "Task Created",       icon: "📅", bg: "bg-violet-50",  text: "text-violet-600" },
    task_stage_change:  { label: "Task Stage Changed", icon: "⏳", bg: "bg-sky-50",     text: "text-sky-600"    },
    task_completed:     { label: "Task Completed",     icon: "✅", bg: "bg-emerald-50", text: "text-emerald-600"},
    meta_import:        { label: "Meta Import",        icon: "📥", bg: "bg-violet-50",  text: "text-violet-600" },
    call_logged:        { label: "Call",               icon: "📞", bg: "bg-emerald-50", text: "text-emerald-600"},
  };

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-[1200px]">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm text-slate-400 mb-6">
        <Link href={`/leads`} className="hover:text-indigo-600 transition-colors">Leads</Link>
        <span>/</span>
        <span className="text-slate-700">{lead.first_name} {lead.last_name}</span>
      </div>

      {/* Header */}
      <div className="bg-white rounded-2xl border border-slate-100 p-4 sm:p-6 mb-5 sm:mb-6 animate-fade-in-up">
        <div className="flex flex-col md:flex-row justify-between gap-4">
          <div className="flex items-center gap-3 sm:gap-4 min-w-0">
            <div className="w-14 h-14 sm:w-16 sm:h-16 rounded-2xl bg-gradient-to-br from-indigo-500 to-cyan-400 flex items-center justify-center text-xl sm:text-2xl font-bold text-white shadow-lg shadow-indigo-500/20 flex-shrink-0">
              {lead.first_name?.[0] || ""}{lead.last_name?.[0] || ""}
            </div>
            <div className="min-w-0">
              <h1 className="text-xl sm:text-2xl font-bold text-slate-900 break-words">{lead.first_name} {lead.last_name}</h1>
              <p className="text-sm text-slate-500 truncate">{lead.company}</p>
              <div className="flex flex-wrap items-center gap-2 mt-2">
                <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-semibold ${smColors.bg} ${smColors.text}`}>
                  <span className={`w-1.5 h-1.5 rounded-full ${smColors.dot}`} />
                  {smColors.label}
                </span>
                <span className={`badge ${sourceColors[lead.source] || "bg-slate-100 text-slate-700"}`}>
                  {getSourceLabel(lead.source)}
                </span>
                {lead.meta_integration_name && (
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-semibold bg-blue-50 text-blue-700">
                    {lead.meta_integration_name}
                  </span>
                )}
              </div>
            </div>
          </div>
          <div className="flex flex-wrap gap-2 sm:gap-3 items-start [&>*]:flex-shrink-0">
            <Link href={`/leads`} className="btn btn-secondary btn-sm">
              ← Back
            </Link>
            {/* The BDE's way in to the product: they cannot edit the lead record
                (leads.access.can_edit_leads), so it is set through the site
                visit, which is theirs. Anyone who can edit the site visit gets
                it — the assigned BDE, their manager, and the admin tier. */}
            {lead.can_edit_site_visit && (
              <button onClick={openProductModal}
                className={`btn btn-sm ${lead.product ? "btn-secondary" : "bg-violet-600 hover:bg-violet-700 text-white font-semibold border border-violet-600"}`}>
                {lead.product ? "Edit Product" : "Add Product"}
              </button>
            )}
            {lead.invoice && (
              <a 
                href={lead.invoice} 
                target="_blank" 
                rel="noreferrer" 
                className="btn btn-sm bg-fuchsia-100 text-fuchsia-700 hover:bg-fuchsia-200 border border-fuchsia-200 font-semibold flex items-center gap-1.5"
              >
                💰 View Invoice
              </a>
            )}
            {!isSpectator && (
            <button
              onClick={initiateCall}
              className="btn btn-sm bg-emerald-600 hover:bg-emerald-700 text-white font-semibold flex items-center gap-1.5 border border-emerald-600 shadow-sm shadow-emerald-100"
            >
              📞 Call Lead
            </button>
            )}
            {lead.can_assign_bde && (
              <button onClick={openBdeModal} className="btn btn-sm bg-blue-600 hover:bg-blue-700 text-white font-semibold border border-blue-600">{lead.bde ? "Reassign BDE" : "Assign to BDE"}</button>
            )}
            {lead.can_assign_documentation && lead.pushed_to_documentation && (
              <button onClick={openDocModal} className="btn btn-sm bg-amber-600 hover:bg-amber-700 text-white font-semibold border border-amber-600">{lead.documentation_staff ? "Reassign Documentation" : "Assign Documentation"}</button>
            )}
            {canEditLead && (
              <button onClick={openEdit} className="btn btn-primary btn-sm">Edit Lead</button>
            )}
          </div>
        </div>
      </div>

      <div className="grid lg:grid-cols-3 gap-4 sm:gap-6">
        {/* Left Column: Details.
            `min-w-0` on both columns: a grid track is `auto`, which means at
            least as wide as the widest thing in it, and a grid item is then
            stretched to its track. One intrinsically wide child — the call
            recording's audio player, which a browser gives a ~300px minimum —
            was enough to push both columns, and so every card in them, past the
            right edge of a phone. */}
        <div className="lg:col-span-2 space-y-6 min-w-0">
          {/* Contact Info */}
          <div className="bg-white rounded-2xl border border-slate-100 p-4 sm:p-6 animate-fade-in-up delay-100">
            <h2 className="font-semibold text-slate-900 mb-4">Contact Information</h2>
            <div className="grid sm:grid-cols-2 gap-4">
              <div>
                <p className="text-xs text-slate-400 mb-1">Email</p>
                <a href={`mailto:${lead.email}`} className="text-sm text-indigo-600 hover:text-indigo-700">{lead.email || "N/A"}</a>
              </div>
              <div>
                <p className="text-xs text-slate-400 mb-1">Phone</p>
                <p className="text-sm text-slate-700">{lead.phone || "N/A"}</p>
              </div>
              <div>
                <p className="text-xs text-slate-400 mb-1">Place</p>
                <p className="text-sm text-slate-700">{lead.company || "N/A"}</p>
              </div>
              <div>
                <p className="text-xs text-slate-400 mb-1">District</p>
                <p className="text-sm text-slate-700">{lead.district || "N/A"}</p>
              </div>
              <div>
                <p className="text-xs text-slate-400 mb-1">Deal Value</p>
                <p className="text-sm font-semibold text-slate-900">{formatCurrency(parseFloat(lead.value || "0"))}</p>
              </div>
            </div>
          </div>

          {/* Notes */}
          <div className="bg-white rounded-2xl border border-slate-100 p-4 sm:p-6 animate-fade-in-up delay-200">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-semibold text-slate-900">Notes</h2>
              {noteList.length > 0 && (
                <span className="text-[11px] text-slate-400">{noteList.length} note{noteList.length === 1 ? "" : "s"}</span>
              )}
            </div>

            {/* One entry per note, each carrying who wrote it. The pencil shows
                only on `can_edit`, which the server works out — your own words,
                or an admin's override. */}
            {noteList.length === 0 ? (
              <p className="text-sm text-slate-400">No notes added yet.</p>
            ) : (
              <div className="space-y-3">
                {noteList.map(n => (
                  <div key={n.id} className="rounded-xl border border-slate-100 bg-slate-50/60 px-3.5 py-2.5">
                    {editingNote === n.id ? (
                      <>
                        <textarea className="form-input" rows={3} value={notesDraft} autoFocus
                          onChange={e => setNotesDraft(e.target.value)} />
                        <div className="mt-2 flex items-center gap-2">
                          <button className="btn btn-primary btn-sm" onClick={() => saveNote(n.id)}
                            disabled={savingNotes || !notesDraft.trim() || notesDraft.trim() === n.body}>
                            {savingNotes ? "Saving..." : "Save"}
                          </button>
                          <button className="btn btn-secondary btn-sm" onClick={() => setEditingNote(null)}
                            disabled={savingNotes}>Cancel</button>
                        </div>
                      </>
                    ) : (
                      <>
                        <p className="text-sm text-slate-700 leading-relaxed whitespace-pre-wrap">{n.body}</p>
                        <div className="mt-1.5 flex items-center gap-2 text-[10px] text-slate-400">
                          <span>{n.author_name || "Unknown"}</span>
                          <span>·</span>
                          <span>{new Date(n.created_at).toLocaleString("en-IN",
                            { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })}</span>
                          {n.edited_at && <span className="italic">· edited</span>}
                          {n.can_edit && (
                            <span className="ml-auto flex items-center gap-2">
                              <button onClick={() => { setNotesDraft(n.body); setEditingNote(n.id); }}
                                className="font-semibold text-indigo-600 hover:text-indigo-800">Edit</button>
                              <button onClick={() => deleteNote(n.id)}
                                className="font-semibold text-rose-500 hover:text-rose-700">Delete</button>
                            </span>
                          )}
                        </div>
                      </>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Adding is open to anyone working the lead — the BDE included.
                Writing a note is not editing the lead record. */}
            {!isSpectator && (
            <div className="mt-4">
              <textarea
                className="form-input"
                rows={3}
                placeholder="Add a note..."
                value={newNote}
                onChange={(e) => setNewNote(e.target.value)}
              />
              <button
                className="btn btn-secondary btn-sm mt-2"
                onClick={handleAddNote}
                disabled={addingNote || !newNote.trim()}
              >
                {addingNote ? "Adding..." : "Add Note"}
              </button>
            </div>
            )}
          </div>

          {/* WhatsApp Conversation */}
          <div className="bg-white rounded-2xl border border-slate-100 p-4 sm:p-6 animate-fade-in-up delay-300">
            <div className="flex justify-between items-center mb-4">
              <h2 className="font-semibold text-slate-900 flex items-center gap-2"><span>💬</span> WhatsApp</h2>
              {waMessages.length > 0 && <span className="text-xs text-slate-400">{waMessages.length} message{waMessages.length !== 1 ? "s" : ""}</span>}
            </div>
            <div className="space-y-2 max-h-80 overflow-y-auto mb-4 pr-1">
              {waMessages.length === 0 ? (
                <p className="text-sm text-slate-400 text-center py-6">No WhatsApp messages yet.</p>
              ) : (
                [...waMessages].reverse().map((m: any) => (
                  <div key={m.id} className={`flex ${m.direction === "out" ? "justify-end" : "justify-start"}`}>
                    <div className={`max-w-[75%] rounded-2xl px-3.5 py-2 text-sm ${m.direction === "out" ? "bg-emerald-500 text-white rounded-br-sm" : "bg-slate-100 text-slate-800 rounded-bl-sm"}`}>
                      <p className="whitespace-pre-wrap break-words">{m.kind === "template" ? `[template: ${m.template_name}]${m.text ? ` ${m.text}` : ""}` : m.text}</p>
                      <div className={`text-[10px] mt-1 ${m.direction === "out" ? "text-emerald-50/80" : "text-slate-400"}`}>
                        {new Date(m.created_at).toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}
                        {m.direction === "out" && ` · ${m.status}`}
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
            <div className="flex gap-2">
              <input value={waInput} onChange={e => setWaInput(e.target.value)} onKeyDown={e => { if (e.key === "Enter") sendWa(); }} disabled={isSpectator} placeholder={isSpectator ? "View only" : "Type a WhatsApp message…"} className="flex-1 bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-400 transition disabled:opacity-60 disabled:cursor-not-allowed" />
              <button onClick={sendWa} disabled={isSpectator || waSending || !waInput.trim()} className="bg-emerald-500 hover:bg-emerald-600 text-white font-semibold px-5 rounded-xl text-sm transition disabled:opacity-50">{waSending ? "…" : "Send"}</button>
            </div>
            <p className="text-[11px] text-slate-400 mt-2">Free text reaches contacts who messaged in the last 24h. For first contact, use a template (Automations / Bulk).</p>
          </div>

          {/* Related Tasks */}
          <div className="bg-white rounded-2xl border border-slate-100 p-4 sm:p-6 animate-fade-in-up delay-300">
            <div className="flex justify-between items-center mb-4">
              <h2 className="font-semibold text-slate-900">Related Tasks</h2>
              <Link href={`/tasks`} className="text-sm text-indigo-600 font-medium">View All</Link>
            </div>
            {tasks.length > 0 ? (
              <div className="space-y-3">
                {tasks.map((task: any) => {
                  const statusConfig: Record<string, { label: string; bg: string; text: string; dot: string }> = {
                    todo:        { label: 'To Do',       bg: 'bg-slate-100',   text: 'text-slate-600',   dot: 'bg-slate-400'    },
                    in_progress: { label: 'In Progress', bg: 'bg-blue-50',     text: 'text-blue-600',    dot: 'bg-blue-500'     },
                    review:      { label: 'In Review',   bg: 'bg-violet-50',   text: 'text-violet-600',  dot: 'bg-violet-500'   },
                    done:        { label: 'Done',        bg: 'bg-emerald-50',  text: 'text-emerald-600', dot: 'bg-emerald-500'  },
                  };
                  const sc = statusConfig[task.status] || statusConfig['todo'];
                  const isDone = task.status === 'done';
                  return (
                    <Link
                      key={task.id}
                      href={`/tasks?task=${task.id}`}
                      title="Open task"
                      className={`flex items-center justify-between p-3 rounded-xl border transition-colors cursor-pointer ${
                        isDone
                          ? 'bg-slate-50/60 border-slate-100 opacity-70 hover:opacity-100 hover:border-slate-200'
                          : 'bg-white border-slate-100 hover:bg-indigo-50/40 hover:border-indigo-200'
                      }`}
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <div className={`w-2 h-2 rounded-full flex-shrink-0 ${
                          task.priority === 'high' ? 'bg-red-500' :
                          task.priority === 'medium' ? 'bg-amber-500' : 'bg-emerald-500'
                        }`} />
                        <span className={`text-sm truncate ${isDone ? 'line-through text-slate-400' : 'text-slate-700 font-medium'}`}>
                          {task.title}
                        </span>
                      </div>
                      <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-semibold uppercase tracking-wide flex-shrink-0 ml-3 ${sc.bg} ${sc.text}`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${sc.dot}`} />
                        {sc.label}
                      </span>
                    </Link>
                  );
                })}
              </div>
            ) : (
              <p className="text-sm text-slate-400">No tasks linked to this lead yet.</p>
            )}
          </div>

          {/* Call History & Recording Details */}
          <div className="bg-white rounded-2xl border border-slate-100 p-4 sm:p-6 animate-fade-in-up delay-[350ms]">
            <div className="flex justify-between items-center mb-4">
              <div>
                <h2 className="font-semibold text-slate-900">Call History & Recordings</h2>
                <p className="text-xs text-slate-400 mt-0.5">Logs and recordings of all calls with this client</p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={fetchCalls}
                  disabled={loadingCalls}
                  className="text-xs font-semibold text-slate-400 hover:text-slate-700 transition-colors disabled:opacity-50 flex items-center gap-1"
                  title="Refresh call logs"
                >
                  <svg width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24" className={loadingCalls ? 'animate-spin' : ''}><path d="M23 4v6h-6"/><path d="M1 20v-6h6"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/></svg>
                  {loadingCalls ? '' : 'Refresh'}
                </button>
                <button 
                  onClick={() => {
                    setManualCallForm({ outcome: "connected", duration_seconds: "0", notes: "", recording_url: "" });
                    setShowManualCallModal(true);
                  }}
                  className="text-xs font-semibold text-indigo-600 hover:text-indigo-800 transition-colors whitespace-nowrap flex-shrink-0"
                >
                  + Log Call
                </button>
              </div>
            </div>
            {calls.length > 0 ? (
              <div className="space-y-4">
                {calls.map((call: any) => {
                  const getStatusColor = (outcome: string) => {
                    switch ((outcome || '').toLowerCase()) {
                      case 'connected': return 'bg-emerald-50 text-emerald-700 border-emerald-100';
                      case 'rnr':       return 'bg-orange-50 text-orange-700 border-orange-100';
                      case 'busy':      return 'bg-blue-50 text-blue-700 border-blue-100';
                      case 'cancelled':
                      case 'canceled':  return 'bg-rose-50 text-rose-700 border-rose-100';
                      case 'initiated': return 'bg-violet-50 text-violet-700 border-violet-100';
                      default:          return 'bg-slate-50 text-slate-700 border-slate-100';
                    }
                  };
                  const getOutcomeLabel = (outcome: string) => {
                    switch ((outcome || '').toLowerCase()) {
                      case 'connected': return 'Connected';
                      case 'rnr':       return 'RNR';
                      case 'busy':      return 'Busy';
                      case 'cancelled':
                      case 'canceled':  return 'Cancelled';
                      case 'initiated': return 'Initiated';
                      case 'completed': return 'Connected';
                      case 'no-answer': return 'RNR';
                      case 'failed':    return 'Busy';
                      case 'rejected':  return 'Busy';
                      default:          return outcome;
                    }
                  };
                  const formatDuration = (sec: number) => {
                    const m = Math.floor(sec / 60);
                    const s = sec % 60;
                    return `${m}:${s < 10 ? '0' : ''}${s}`;
                  };

                  return (
                    <div key={call.id} className="p-4 rounded-xl border border-slate-100 bg-slate-50/30 hover:bg-slate-50 hover:border-slate-200 transition-colors space-y-3 relative group animate-fade-in-up">
                      <div className="absolute right-4 top-4 flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button 
                          onClick={() => setEditingCall({
                            id: call.id,
                            outcome: call.outcome,
                            duration_seconds: call.duration_seconds.toString(),
                            notes: call.notes || "",
                            recording_url: call.recording_url || "",
                          })}
                          className="text-[11px] font-bold text-indigo-600 hover:text-indigo-800 transition-colors"
                        >
                          Edit
                        </button>
                      </div>

                      <div className="flex flex-wrap items-center gap-2 pr-12">
                        <span className={`px-2.5 py-0.5 rounded-full text-[9px] font-black uppercase border tracking-wider ${getStatusColor(call.outcome)}`}>
                          {getOutcomeLabel(call.outcome)}
                        </span>
                        <span className="text-xs text-slate-500 font-medium">
                          by {call.user_name}
                        </span>
                        <span className="text-[11px] text-slate-400 font-mono ml-auto">
                          {new Date(call.created_at).toLocaleString("en-IN", { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}
                        </span>
                      </div>

                      <div className="flex items-center justify-between gap-4 text-xs">
                        <div className="flex items-center gap-1.5 text-slate-600 font-mono">
                          <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" /><path d="M12 6v6l4 2" /></svg>
                          Duration: {formatDuration(call.duration_seconds)}
                        </div>
                        
                        {call.notes && (
                          <div className="text-slate-500 italic max-w-[60%] truncate" title={call.notes}>
                            Notes: {call.notes}
                          </div>
                        )}
                      </div>

                      {call.recording_url ? (
                        <div className="pt-2 border-t border-slate-100/60">
                          <p className="text-[10px] text-slate-400 font-bold uppercase tracking-wider mb-1">
                            ⏺️ Call Recording
                          </p>
                          <audio src={getRecordingUrl(call.recording_url, call.id)} controls className="w-full max-w-full min-w-0 h-8 scale-95 origin-left" />
                        </div>
                      ) : (
                        <div className="pt-1 text-[10px] text-slate-400 italic">No recording available</div>
                      )}
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="text-sm text-slate-400 py-2">No calls tracked for this lead yet.</p>
            )}
          </div>

        </div>

        {/* Right Column: Sidebar */}
        <div className="space-y-6 min-w-0">
          {/* Quick Stats */}
          <div className="bg-white rounded-2xl border border-slate-100 p-4 sm:p-6 animate-fade-in-up delay-100">
            <h2 className="font-semibold text-slate-900 mb-4">Quick Stats</h2>
            <div className="space-y-4">
              <div>
                <p className="text-xs text-slate-400 mb-1">Lead Score</p>
                <div className="flex items-center gap-3">
                  <div className="progress-bar flex-1">
                    <div className="progress-bar-fill bg-gradient-to-r from-indigo-500 to-cyan-400" style={{ width: lead.status === "converted" ? "100%" : lead.status === "positive" ? "75%" : lead.status === "follow_up" ? "50%" : lead.status === "new" ? "25%" : "10%" }} />
                  </div>
                  <span className="text-sm font-semibold text-slate-700">
                    {lead.status === "converted" ? "100" : lead.status === "positive" ? "75" : lead.status === "follow_up" ? "50" : lead.status === "new" ? "25" : "10"}
                  </span>
                </div>
              </div>
              <div>
                <p className="text-xs text-slate-400 mb-1">Days in Pipeline</p>
                <p className="text-lg font-bold text-slate-900">
                  {Math.max(0, Math.floor((Date.now() - new Date(lead.created_at).getTime()) / (1000 * 60 * 60 * 24)))}
                </p>
              </div>
              <div>
                <p className="text-xs text-slate-400 mb-1">Tele Caller</p>
                <p className="text-sm font-semibold text-indigo-600">{lead.tele_caller_name || lead.assigned_to_name || "Unassigned"}</p>
              </div>
              <div>
                <p className="text-xs text-slate-400 mb-1">BDE</p>
                <p className="text-sm font-semibold text-blue-600">{lead.bde_name || "Not assigned"}</p>
              </div>
              {lead.installation_location && (
                <div>
                  <p className="text-xs text-slate-400 mb-1">Installation Location</p>
                  <p className="text-sm font-semibold text-slate-700">{lead.installation_location}</p>
                </div>
              )}
              <div>
                <p className="text-xs text-slate-400 mb-1">Documentation</p>
                {lead.pushed_to_documentation ? (
                  <p className="text-sm font-semibold text-amber-600">{lead.documentation_staff_name ? `Staff: ${lead.documentation_staff_name}` : "Pushed — unassigned"}</p>
                ) : (
                  <p className="text-sm font-semibold text-slate-400">Not pushed</p>
                )}
              </div>
            </div>
          </div>

          {/* Quotations — raised here, listed in the Quotation module too. */}
          <LeadQuotationsPanel leadId={params.id} customerEmail={lead?.email} />

          {/* Attachments UI Card */}
          <div className="bg-white rounded-2xl border border-slate-100 p-4 sm:p-6 animate-fade-in-up delay-[150ms]">
            <div className="flex justify-between items-center mb-4">
              <h2 className="font-semibold text-slate-900">Attachments</h2>
              <button 
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading}
                className="text-xs font-semibold text-indigo-600 hover:text-indigo-800 disabled:opacity-50 transition-colors"
                title="Max length 50MB"
              >
                {uploading ? "Uploading..." : "+ Add"}
              </button>
              <input 
                type="file" 
                ref={fileInputRef} 
                onChange={handleFileUpload} 
                className="hidden" 
              />
            </div>
            
            {attachments.length > 0 || lead.invoice ? (
              <div className="space-y-3 max-h-[300px] overflow-y-auto pr-1">
                {lead.invoice && (
                  <a 
                    href={lead.invoice} 
                    target="_blank" 
                    rel="noreferrer"
                    className="flex items-center gap-3 p-3 rounded-xl bg-fuchsia-50 border border-fuchsia-100 hover:bg-fuchsia-100 transition-all cursor-pointer group"
                  >
                    <div className="w-8 h-8 rounded-lg bg-fuchsia-200 text-fuchsia-700 flex items-center justify-center flex-shrink-0 group-hover:scale-105 transition-transform text-lg">
                      💰
                    </div>
                    <div className="flex-1 min-w-0 pr-2">
                      <p className="text-xs font-bold text-fuchsia-900 truncate">Official Invoice</p>
                      <p className="text-[10px] text-fuchsia-600 flex items-center gap-1">
                        <span>Invoice on file</span>
                      </p>
                    </div>
                  </a>
                )}
                {attachments.map(att => (
                  <a 
                    key={att.id} 
                    href={att.file_url} 
                    target="_blank" 
                    rel="noreferrer"
                    className="flex items-center gap-3 p-3 rounded-xl bg-slate-50 border border-slate-100 hover:bg-indigo-50 hover:border-indigo-100 transition-all cursor-pointer group"
                  >
                    <div className="w-8 h-8 rounded-lg bg-indigo-100 text-indigo-600 flex items-center justify-center flex-shrink-0 group-hover:scale-105 transition-transform">
                      📄
                    </div>
                    <div className="flex-1 min-w-0 pr-2">
                      <p className="text-xs font-semibold text-slate-700 truncate">{att.file_name}</p>
                      <p className="text-[10px] text-slate-400 flex items-center gap-1">
                        <span>{att.file_size_kb} KB</span>
                        <span>•</span>
                        <span>{new Date(att.uploaded_at).toLocaleDateString()}</span>
                      </p>
                    </div>
                  </a>
                ))}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-6 px-4 bg-slate-50 border border-dashed border-slate-200 rounded-xl">
                <span className="text-2xl mb-2 opacity-50">📂</span>
                <p className="text-xs text-slate-500 text-center font-medium">No attachments yet</p>
                <p className="text-[10px] text-slate-400 text-center mt-1">Upload files (max 50MB)</p>
              </div>
            )}
          </div>

          {/* Activity Timeline */}
          <div className="bg-white rounded-2xl border border-slate-100 p-4 sm:p-6 animate-fade-in-up delay-200">
            <h2 className="font-semibold text-slate-900 mb-4">Activity Timeline</h2>
            {historyLoading ? (
              <div className="flex justify-center py-8">
                <div className="w-6 h-6 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
              </div>
            ) : leadHistory.length === 0 ? (
              <p className="text-xs text-slate-400 text-center py-8">No activities recorded yet.</p>
            ) : (
              <div className="space-y-4">
                {leadHistory.map((log: any, i) => {
                  const cfg = typeConfig[log.type] || { label: log.type, icon: "📋", bg: "bg-slate-50", text: "text-slate-600" };
                  const oldStatus = log.extra?.old_status;
                  const newStatus = log.extra?.new_status;
                  const ts = new Date(log.timestamp);
                  const dateStr = isNaN(ts.getTime()) ? "" : ts.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
                  const timeStr = isNaN(ts.getTime()) ? "" : ts.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" });

                  return (
                    <div key={log.id || i} className="flex gap-3 relative">
                      {i < leadHistory.length - 1 && (
                        <div className="absolute left-4 top-8 w-px h-[calc(100%+4px)] bg-slate-100" />
                      )}
                      <div className={`w-8 h-8 rounded-lg ${cfg.bg} ${cfg.text} flex items-center justify-center text-sm flex-shrink-0 relative z-10`}>
                        {cfg.icon}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-start justify-between gap-2">
                          <p className="text-sm font-medium text-slate-700 leading-snug">{log.description}</p>
                          <span className="text-[10px] text-slate-400 whitespace-nowrap flex-shrink-0">{dateStr} {timeStr}</span>
                        </div>
                        
                        {log.extra?.note && (
                          <div className="mt-1.5 bg-teal-50/50 border border-teal-100/50 rounded-lg px-3 py-2">
                            <p className="text-xs text-slate-600 leading-relaxed whitespace-pre-wrap">{log.extra.note}</p>
                          </div>
                        )}

                        {oldStatus && newStatus && (
                          <div className="flex items-center gap-1.5 mt-1.5 text-xs text-slate-500">
                            <span className="font-semibold text-slate-600">{statusMeta[oldStatus]?.label || oldStatus}</span>
                            <span>→</span>
                            <span className="font-semibold text-slate-600">{statusMeta[newStatus]?.label || newStatus}</span>
                          </div>
                        )}
                        
                        {log.actor && (
                          <p className="text-[10px] text-slate-400 mt-1">by {log.actor}</p>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>

      <SiteVisitSection leadId={String(params.id)} canEdit={!!lead.can_edit_site_visit}
        onSaved={fetchData} reloadKey={dealVersion}
        canReopen={!!lead.can_reopen_site_visit}
        reopened={!!lead.site_visit_reopened}
        locked={!!lead.site_visit_complete || !!lead.pushed_to_documentation} />

      {/* Push to documentation — the hand-off that follows the site visit above. */}
      {lead.can_edit_site_visit && !lead.pushed_to_documentation && (
        <div className="mt-5 bg-white rounded-2xl border border-slate-100 p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <p className="text-sm font-bold text-slate-900">Push to Documentation</p>
            <p className="text-xs text-slate-400 mt-0.5">
              {lead.site_visit_complete
                ? "Site visit is complete — hand this lead over to the documentation team."
                : "Mark the site visit complete above before pushing this lead to documentation."}
            </p>
          </div>
          <button onClick={pushToDocumentation} disabled={pushingDoc || !lead.site_visit_complete}
            title={!lead.site_visit_complete ? "Mark the site visit complete first" : ""}
            className="px-5 py-2.5 bg-violet-600 hover:bg-violet-700 text-white rounded-xl text-sm font-semibold border border-violet-600 disabled:opacity-50 disabled:cursor-not-allowed transition flex-shrink-0">
            {pushingDoc ? "Pushing…" : "Push to Documentation"}
          </button>
        </div>
      )}

      {/* Product Modal */}
      {showProductModal && (() => {
        const chosen = productList.find(p => String(p.id) === productChoice);
        return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm px-4">
          <div className="bg-white w-full max-w-md rounded-2xl shadow-2xl max-h-[calc(100dvh-2rem)] overflow-y-auto overscroll-contain" onClick={e => e.stopPropagation()}>
            <div className="px-6 py-4 border-b border-slate-100">
              <h2 className="text-[15px] font-bold text-slate-900">{lead.product ? "Edit Product" : "Add Product"}</h2>
              <p className="text-xs text-slate-400 mt-0.5">What this customer is buying. The price and any discount are set in the Deal section of the site visit.</p>
            </div>
            <div className="p-6 space-y-4">
              <div>
                <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">Product</label>
                <select value={productChoice} onChange={e => setProductChoice(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm text-slate-800 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all">
                  <option value="">— None —</option>
                  {productList.map(p => (
                    <option key={p.id} value={p.id}>{p.name}{Number(p.default_price) > 0 ? ` — ₹${Number(p.default_price).toLocaleString("en-IN")}` : ""}</option>
                  ))}
                </select>
                {productList.length === 0 && (
                  <p className="text-[11px] text-amber-600 mt-2">No products yet. Add one under Inventory → Item Master first.</p>
                )}
              </div>
              {chosen && (
                <label className="flex items-start gap-2.5 cursor-pointer">
                  <input type="checkbox" checked={seedPrice} onChange={e => setSeedPrice(e.target.checked)}
                    className="mt-0.5 w-4 h-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500/30" />
                  <span className="text-xs text-slate-600 leading-snug">
                    Set the product price to <strong className="font-mono">₹{Number(chosen.default_price || 0).toLocaleString("en-IN")}</strong>,
                    this product&apos;s catalogue price. Untick to leave the price on the deal as it is.
                  </span>
                </label>
              )}
            </div>
            <div className="px-6 py-4 border-t border-slate-100 flex gap-3">
              <button onClick={() => setShowProductModal(false)} className="flex-1 py-2.5 border border-slate-200 rounded-xl text-sm font-semibold text-slate-600 hover:bg-slate-50 transition-all">Cancel</button>
              <button onClick={saveProduct} disabled={savingProduct} className="flex-1 py-2.5 bg-violet-600 text-white rounded-xl text-sm font-semibold hover:bg-violet-700 disabled:opacity-50 transition-all">{savingProduct ? "Saving…" : "Save Product"}</button>
            </div>
          </div>
        </div>
        );
      })()}

      {/* Assign to BDE Modal */}
      {showBdeModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm px-4">
          <div className="bg-white w-full max-w-md rounded-2xl shadow-2xl max-h-[calc(100dvh-2rem)] overflow-y-auto overscroll-contain" onClick={e => e.stopPropagation()}>
            <div className="px-6 py-4 border-b border-slate-100">
              <h2 className="text-[15px] font-bold text-slate-900">Assign to BDE</h2>
              <p className="text-xs text-slate-400 mt-0.5">Hand this lead off to a BDE for the site visit.</p>
            </div>
            <div className="p-6">
              <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">BDE</label>
              <select value={selectedBde} onChange={e => setSelectedBde(e.target.value)} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm text-slate-800 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all">
                <option value="">— Unassigned —</option>
                {bdeList.map(b => <option key={b.id} value={b.id}>{b.name}{b.branch_name ? ` (${b.branch_name})` : ""}</option>)}
              </select>
              {bdeList.length === 0 && <p className="text-[11px] text-amber-600 mt-2">No BDEs found. Set a user&apos;s role to &quot;BDE&quot; under Team first.</p>}
            </div>
            <div className="px-6 py-4 border-t border-slate-100 flex gap-3">
              <button onClick={() => setShowBdeModal(false)} className="flex-1 py-2.5 border border-slate-200 rounded-xl text-sm font-semibold text-slate-600 hover:bg-slate-50 transition-all">Cancel</button>
              <button onClick={assignBde} disabled={assigningBde} className="flex-1 py-2.5 bg-blue-600 text-white rounded-xl text-sm font-semibold hover:bg-blue-700 disabled:opacity-50 transition-all">{assigningBde ? "Assigning…" : "Assign"}</button>
            </div>
          </div>
        </div>
      )}

      {/* Assign Documentation Staff Modal */}
      {showDocModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm px-4">
          <div className="bg-white w-full max-w-md rounded-2xl shadow-2xl max-h-[calc(100dvh-2rem)] overflow-y-auto overscroll-contain" onClick={e => e.stopPropagation()}>
            <div className="px-6 py-4 border-b border-slate-100">
              <h2 className="text-[15px] font-bold text-slate-900">Assign Documentation Staff</h2>
              <p className="text-xs text-slate-400 mt-0.5">Hand this lead&apos;s paperwork to a documentation staff member.</p>
            </div>
            <div className="p-6">
              <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">Documentation Staff</label>
              <select value={selectedDoc} onChange={e => setSelectedDoc(e.target.value)} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm text-slate-800 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all">
                <option value="">— Unassigned —</option>
                {docList.map(d => <option key={d.id} value={d.id}>{d.name}{d.branch_name ? ` (${d.branch_name})` : ""}</option>)}
              </select>
              {docList.length === 0 && <p className="text-[11px] text-amber-600 mt-2">No documentation staff found. Set a user&apos;s role to &quot;Documentation Staff&quot; under Team first.</p>}
            </div>
            <div className="px-6 py-4 border-t border-slate-100 flex gap-3">
              <button onClick={() => setShowDocModal(false)} className="flex-1 py-2.5 border border-slate-200 rounded-xl text-sm font-semibold text-slate-600 hover:bg-slate-50 transition-all">Cancel</button>
              <button onClick={assignDoc} disabled={assigningDoc} className="flex-1 py-2.5 bg-amber-600 text-white rounded-xl text-sm font-semibold hover:bg-amber-700 disabled:opacity-50 transition-all">{assigningDoc ? "Assigning…" : "Assign"}</button>
            </div>
          </div>
        </div>
      )}

      {/* Edit Modal */}
      {showEditModal && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/40 backdrop-blur-sm"
          onClick={() => setShowEditModal(false)}>
          <div className="bg-white w-full sm:max-w-2xl sm:mx-4 rounded-t-2xl sm:rounded-2xl shadow-2xl max-h-[92vh] overflow-hidden flex flex-col"
            onClick={e => e.stopPropagation()}>

            {/* Modal header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 flex-shrink-0">
              <div>
                <h2 className="text-[15px] font-bold text-slate-900">Edit Lead</h2>
                <p className="text-xs text-slate-400 mt-0.5">Update lead details</p>
              </div>
              <button onClick={() => setShowEditModal(false)}
                className="w-8 h-8 flex items-center justify-center rounded-xl bg-slate-100 text-slate-500 hover:bg-slate-200 transition-all">
                <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg>
              </button>
            </div>

            {/* Form */}
            <form onSubmit={handleEditSubmit} className="overflow-y-auto flex-1 px-6 py-5 space-y-4">

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">First Name <span className="text-red-400 normal-case">*</span></label>
                  <input required value={form.first_name} onChange={e => setForm({ ...form, first_name: e.target.value })} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all" placeholder="Aarav" />
                </div>
                <div>
                  <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">Last Name</label>
                  <input value={form.last_name} onChange={e => setForm({ ...form, last_name: e.target.value })} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all" placeholder="Sharma" />
                </div>
                <div>
                  <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">Email</label>
                  <input type="email" value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all" placeholder="email@example.com" />
                </div>
                <div>
                  <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">Phone</label>
                  <input type="tel" value={form.phone} onChange={e => setForm({ ...form, phone: e.target.value })} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all" placeholder="+91 98765 43210" />
                </div>
                <div>
                  <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">Location</label>
                  <input value={form.company} onChange={e => setForm({ ...form, company: e.target.value })} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all" placeholder="e.g. Kochi" />
                </div>
                <div>
                  <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">District</label>
                  <div className="relative">
                    <select value={form.district} onChange={e => setForm({ ...form, district: e.target.value })} className="w-full appearance-none bg-slate-50 border border-slate-200 rounded-xl pl-4 pr-8 py-2.5 text-sm font-medium text-slate-700 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all cursor-pointer">
                      <option value="">— No district —</option>
                      {districtOptions(configuredDistricts, form.district).map(d => (
                        <option key={d} value={d}>{d}</option>
                      ))}
                    </select>
                    <div className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none">
                      <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><polyline points="6 9 12 15 18 9"/></svg>
                    </div>
                  </div>
                </div>
                <div>
                  <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">Installation Location</label>
                  <input value={form.installation_location} onChange={e => setForm({ ...form, installation_location: e.target.value })} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all" placeholder="Where the system is installed" />
                </div>
                <div>
                  <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">Source</label>
                  <div className="relative">
                    <select value={form.source} onChange={e => setForm({ ...form, source: e.target.value })} className="w-full appearance-none bg-slate-50 border border-slate-200 rounded-xl pl-4 pr-8 py-2.5 text-sm font-medium text-slate-700 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all cursor-pointer">
                      <option value="manual">Manual</option>
                      <option value="website">Website</option>
                      <option value="meta_ads">Meta Ads</option>
                      <option value="linkedin">LinkedIn</option>
                      <option value="referral">Referral</option>
                    </select>
                    <div className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none">
                      <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><polyline points="6 9 12 15 18 9"/></svg>
                    </div>
                  </div>
                </div>
                <div>
                  <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">Status</label>
                  <div className="relative">
                    <select value={form.status} disabled={!canEditStatus} title={canEditStatus ? undefined : "Only the tele caller or a manager can change the lead status."} onChange={e => setForm({ ...form, status: e.target.value })} className="w-full appearance-none bg-slate-50 border border-slate-200 rounded-xl pl-4 pr-8 py-2.5 text-sm font-medium text-slate-700 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all cursor-pointer disabled:opacity-60 disabled:cursor-not-allowed">
                      {Object.entries(statusMeta).map(([key, o]: [string, any]) => <option key={key} value={key}>{o.label}</option>)}
                    </select>
                    <div className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none">
                      <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><polyline points="6 9 12 15 18 9"/></svg>
                    </div>
                  </div>
                </div>
                <div>
                  <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">Product</label>
                  <div className="relative">
                    <select value={form.product} onChange={e => setForm({ ...form, product: e.target.value })} className="w-full appearance-none bg-slate-50 border border-slate-200 rounded-xl pl-4 pr-8 py-2.5 text-sm font-medium text-slate-700 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all cursor-pointer">
                      <option value="">None</option>
                      {productsList.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                    </select>
                    <div className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none">
                      <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><polyline points="6 9 12 15 18 9"/></svg>
                    </div>
                  </div>
                </div>
              </div>

              {canAssign && (
                <div>
                  <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">Assigned To</label>
                  <div className="relative">
                    <select value={form.assigned_to} onChange={e => setForm({ ...form, assigned_to: e.target.value })} className="w-full appearance-none bg-slate-50 border border-slate-200 rounded-xl pl-4 pr-8 py-2.5 text-sm font-medium text-slate-700 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all cursor-pointer">
                      <option value="">Unassigned</option>
                      {teamMembers.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
                    </select>
                    <div className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none">
                      <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><polyline points="6 9 12 15 18 9"/></svg>
                    </div>
                  </div>
                </div>
              )}

              <div>
                <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">Latest Note</label>
                <textarea rows={3} value={getLatestNote(form.notes)} readOnly
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm text-slate-500 outline-none cursor-not-allowed resize-none" />
              </div>

              <div>
                <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">Add New Note</label>
                <textarea rows={2} value={newEditNote} onChange={e => setNewEditNote(e.target.value)}
                  placeholder="Add a new comment/follow-up note..."
                  className="w-full bg-slate-50 border border-indigo-100 focus:border-indigo-400 rounded-xl px-4 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 outline-none focus:ring-2 focus:ring-indigo-500/20 transition-all resize-none" />
              </div>

              <div className="flex justify-end gap-3 pt-4 border-t border-slate-100">
                <button type="button" onClick={() => setShowEditModal(false)}
                  className="px-5 py-2.5 text-sm font-bold text-slate-500 hover:text-slate-800 border border-slate-200 rounded-xl transition-all">
                  Cancel
                </button>
                <button type="submit"
                  className="px-5 py-2.5 text-sm font-bold text-white bg-indigo-600 hover:bg-indigo-700 rounded-xl transition-all">
                  Save Changes
                </button>
              </div>

            </form>
          </div>
        </div>
      )}

      {/* Log Call Manually Modal */}
      {showManualCallModal && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/40 backdrop-blur-sm shadow-2xl"
          onClick={() => setShowManualCallModal(false)}>
          <div className="bg-white w-full sm:max-w-md sm:mx-4 rounded-t-2xl sm:rounded-2xl shadow-2xl overflow-hidden max-h-[90dvh] flex flex-col"
            onClick={e => e.stopPropagation()}>
            
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 flex-shrink-0">
              <div>
                <h2 className="text-[15px] font-bold text-slate-900">Log Call Manually</h2>
                <p className="text-xs text-slate-400 mt-0.5">Record a custom call interaction</p>
              </div>
              <button onClick={() => setShowManualCallModal(false)}
                className="w-8 h-8 flex items-center justify-center rounded-xl bg-slate-100 text-slate-500 hover:bg-slate-200 transition-all">
                <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg>
              </button>
            </div>

            <form onSubmit={handleManualCallSubmit} className="p-6 space-y-4 overflow-y-auto flex-1 overscroll-contain">
              <div>
                <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">Outcome</label>
                <div className="relative">
                  <select 
                    value={manualCallForm.outcome} 
                    onChange={e => setManualCallForm({ ...manualCallForm, outcome: e.target.value })} 
                    className="w-full appearance-none bg-slate-50 border border-slate-200 rounded-xl pl-4 pr-8 py-2.5 text-sm font-medium text-slate-700 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all cursor-pointer"
                  >
                    <option value="connected">Connected</option>
                    <option value="rnr">RNR</option>
                    <option value="busy">Busy</option>
                    <option value="cancelled">Cancelled</option>
                  </select>
                  <div className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none">
                    <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><polyline points="6 9 12 15 18 9"/></svg>
                  </div>
                </div>
              </div>

              {manualCallForm.outcome === 'connected' && (
                <>
                  <div>
                    <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">Duration (seconds)</label>
                    <input 
                      type="number" 
                      min="0"
                      value={manualCallForm.duration_seconds} 
                      onChange={e => setManualCallForm({ ...manualCallForm, duration_seconds: e.target.value })} 
                      className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all font-mono" 
                      placeholder="e.g. 45" 
                    />
                  </div>

                  <div>
                    <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">Recording URL (optional)</label>
                    <input 
                      type="url" 
                      value={manualCallForm.recording_url} 
                      onChange={e => setManualCallForm({ ...manualCallForm, recording_url: e.target.value })} 
                      className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all" 
                      placeholder="https://example.com/recording.mp3" 
                    />
                  </div>
                </>
              )}

              <div>
                <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">Notes</label>
                <textarea 
                  rows={3} 
                  value={manualCallForm.notes} 
                  onChange={e => setManualCallForm({ ...manualCallForm, notes: e.target.value })}
                  placeholder="Summarize the discussion, next steps..."
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all resize-none" 
                />
              </div>

              <div className="flex justify-end gap-3 pt-4 border-t border-slate-100">
                <button type="button" onClick={() => setShowManualCallModal(false)}
                  className="px-5 py-2.5 text-sm font-bold text-slate-500 hover:text-slate-800 border border-slate-200 rounded-xl transition-all">
                  Cancel
                </button>
                <button type="submit"
                  className="px-5 py-2.5 text-sm font-bold text-white bg-indigo-600 hover:bg-indigo-700 rounded-xl transition-all font-bold">
                  Save Call Log
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit Call Log Modal */}
      {editingCall && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/40 backdrop-blur-sm"
          onClick={() => setEditingCall(null)}>
          <div className="bg-white w-full sm:max-w-md sm:mx-4 rounded-t-2xl sm:rounded-2xl shadow-2xl overflow-hidden max-h-[90dvh] flex flex-col"
            onClick={e => e.stopPropagation()}>
            
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 flex-shrink-0">
              <div>
                <h2 className="text-[15px] font-bold text-slate-900">Edit Call Log</h2>
                <p className="text-xs text-slate-400 mt-0.5">Modify call details</p>
              </div>
              <button onClick={() => setEditingCall(null)}
                className="w-8 h-8 flex items-center justify-center rounded-xl bg-slate-100 text-slate-500 hover:bg-slate-200 transition-all">
                <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg>
              </button>
            </div>

            <form onSubmit={handleEditCallSubmit} className="p-6 space-y-4 overflow-y-auto flex-1 overscroll-contain">
              <div>
                <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">Outcome</label>
                <div className="relative">
                  <select 
                    value={editingCall.outcome} 
                    onChange={e => setEditingCall({ ...editingCall, outcome: e.target.value })} 
                    className="w-full appearance-none bg-slate-50 border border-slate-200 rounded-xl pl-4 pr-8 py-2.5 text-sm font-medium text-slate-700 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all cursor-pointer"
                  >
                    <option value="connected">Connected</option>
                    <option value="rnr">RNR</option>
                    <option value="busy">Busy</option>
                    <option value="cancelled">Cancelled</option>
                  </select>
                  <div className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none">
                    <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><polyline points="6 9 12 15 18 9"/></svg>
                  </div>
                </div>
              </div>

              {editingCall.outcome === 'connected' && (
                <>
                  <div>
                    <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">Duration (seconds)</label>
                    <input 
                      type="number" 
                      min="0"
                      value={editingCall.duration_seconds} 
                      onChange={e => setEditingCall({ ...editingCall, duration_seconds: e.target.value })} 
                      className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all font-mono" 
                    />
                  </div>

                  <div>
                    <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">Recording URL (optional)</label>
                    <input 
                      type="url" 
                      value={editingCall.recording_url} 
                      onChange={e => setEditingCall({ ...editingCall, recording_url: e.target.value })} 
                      className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all" 
                    />
                  </div>
                </>
              )}

              <div>
                <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">Notes</label>
                <textarea 
                  rows={3} 
                  value={editingCall.notes} 
                  onChange={e => setEditingCall({ ...editingCall, notes: e.target.value })}
                  placeholder="Summarize the discussion, next steps..."
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all resize-none" 
                />
              </div>

              <div className="flex justify-end gap-3 pt-4 border-t border-slate-100">
                <button type="button" onClick={() => setEditingCall(null)}
                  className="px-5 py-2.5 text-sm font-bold text-slate-500 hover:text-slate-800 border border-slate-200 rounded-xl transition-all">
                  Cancel
                </button>
                <button type="submit"
                  className="px-5 py-2.5 text-sm font-bold text-white bg-indigo-600 hover:bg-indigo-700 rounded-xl transition-all font-bold">
                  Save Changes
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

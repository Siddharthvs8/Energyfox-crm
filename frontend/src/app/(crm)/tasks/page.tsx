"use client";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";

import React, { useState, useEffect, useRef } from "react";
import { DragDropContext, Droppable, Draggable } from "@hello-pangea/dnd";
import { Skeleton, SkeletonRegion, Spinner } from "@/components/Skeleton";

// ─── Types ────────────────────────────────────────────────────────────────────
interface Task {
  id: number;
  title: string;
  description: string;
  status: "todo" | "in_progress" | "review" | "done";
  priority: "high" | "medium" | "low";
  assignee: string;
  assigneeId?: number;
  assigneeAvatar?: string;
  dueDate: string;
  dueTime: string;
  leadName?: string;
  leadId?: number;
  tags: string[];
}

// ─── SSR safety for DnD ──────────────────────────────────────────────────────
function useHasMounted() {
  const [m, setM] = useState(false);
  useEffect(() => setM(true), []);
  return m;
}

// ─── SVG Icon Library (Stroke-based, no emojis) ──────────────────────────────
const Icon = {
  Plus: () => (
    <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" viewBox="0 0 24 24">
      <path d="M12 5v14M5 12h14" />
    </svg>
  ),
  Search: () => (
    <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24">
      <circle cx="11" cy="11" r="8" /><path d="M21 21l-4.35-4.35" />
    </svg>
  ),
  ChevronLeft: () => (
    <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" viewBox="0 0 24 24">
      <path d="M15 18l-6-6 6-6" />
    </svg>
  ),
  ChevronRight: () => (
    <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" viewBox="0 0 24 24">
      <path d="M9 18l6-6-6-6" />
    </svg>
  ),
  X: () => (
    <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" viewBox="0 0 24 24">
      <path d="M18 6L6 18M6 6l12 12" />
    </svg>
  ),
  Trash: () => (
    <svg width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24">
      <polyline points="3 6 5 6 21 6" /><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6" /><path d="M10 11v6M14 11v6" /><path d="M9 6V4a1 1 0 011-1h4a1 1 0 011 1v2" />
    </svg>
  ),
  Board: () => (
    <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" viewBox="0 0 24 24">
      <rect x="3" y="3" width="7" height="18" rx="1.5" /><rect x="14" y="3" width="7" height="10" rx="1.5" /><rect x="14" y="17" width="7" height="4" rx="1.5" />
    </svg>
  ),
  List: () => (
    <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24">
      <line x1="8" y1="6" x2="21" y2="6" /><line x1="8" y1="12" x2="21" y2="12" /><line x1="8" y1="18" x2="21" y2="18" />
      <circle cx="3.5" cy="6" r="1.5" fill="currentColor" stroke="none" /><circle cx="3.5" cy="12" r="1.5" fill="currentColor" stroke="none" /><circle cx="3.5" cy="18" r="1.5" fill="currentColor" stroke="none" />
    </svg>
  ),
  Table: () => (
    <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" viewBox="0 0 24 24">
      <rect x="3" y="3" width="18" height="18" rx="2" /><line x1="3" y1="9" x2="21" y2="9" /><line x1="3" y1="15" x2="21" y2="15" /><line x1="9" y1="9" x2="9" y2="21" />
    </svg>
  ),
  Calendar: () => (
    <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" viewBox="0 0 24 24">
      <rect x="3" y="4" width="18" height="18" rx="2" /><line x1="16" y1="2" x2="16" y2="6" /><line x1="8" y1="2" x2="8" y2="6" /><line x1="3" y1="10" x2="21" y2="10" />
    </svg>
  ),
  Flag: ({ level }: { level: "high" | "medium" | "low" }) => {
    const color = level === "high" ? "#ef4444" : level === "medium" ? "#f59e0b" : "#10b981";
    return (
      <svg width="12" height="12" fill={color} stroke={color} strokeWidth="1.5" strokeLinecap="round" viewBox="0 0 24 24">
        <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z" /><line x1="4" y1="22" x2="4" y2="15" />
      </svg>
    );
  },
  Clock: () => (
    <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24">
      <circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" />
    </svg>
  ),
  User: () => (
    <svg width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24">
      <path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2" /><circle cx="12" cy="7" r="4" />
    </svg>
  ),
  Link2: () => (
    <svg width="11" height="11" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24">
      <path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71" /><path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71" />
    </svg>
  ),
  Tag: () => (
    <svg width="11" height="11" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24">
      <path d="M20.59 13.41l-7.17 7.17a2 2 0 01-2.83 0L2 12V2h10l8.59 8.59a2 2 0 010 2.82z" /><line x1="7" y1="7" x2="7.01" y2="7" />
    </svg>
  ),
  ChevronDown: () => (
    <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24">
      <polyline points="6 9 12 15 18 9" />
    </svg>
  ),
};

// ─── Config Maps ─────────────────────────────────────────────────────────────
const priorityMap = {
  high:   { label: "High",   bg: "bg-red-50",    text: "text-red-600",    dot: "bg-red-500",      border: "border-red-100"    },
  medium: { label: "Medium", bg: "bg-amber-50",  text: "text-amber-600",  dot: "bg-amber-500",    border: "border-amber-100"  },
  low:    { label: "Low",    bg: "bg-emerald-50", text: "text-emerald-600", dot: "bg-emerald-500", border: "border-emerald-100" },
};

const statusMap = {
  todo:        { label: "To Do",       bg: "bg-slate-100",   text: "text-slate-600",   dot: "bg-slate-400",    accent: "#94a3b8" },
  in_progress: { label: "In Progress", bg: "bg-blue-50",     text: "text-blue-600",    dot: "bg-blue-500",     accent: "#3b82f6" },
  review:      { label: "In Review",   bg: "bg-violet-50",   text: "text-violet-600",  dot: "bg-violet-500",   accent: "#8b5cf6" },
  done:        { label: "Done",        bg: "bg-emerald-50",  text: "text-emerald-600", dot: "bg-emerald-500",  accent: "#10b981" },
};

// ─── Helpers ─────────────────────────────────────────────────────────────────
function initials(name: string) {
  return name.split(" ").filter(Boolean).slice(0, 2).map(w => w[0]).join("").toUpperCase() || "?";
}

function formatDate(iso: string) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short" });
}

function isOverdue(dueDate: string, dueTime?: string) {
  if (!dueDate) return false;
  if (dueTime) return new Date(`${dueDate}T${dueTime}`) < new Date();
  const d = new Date(dueDate);
  d.setHours(23, 59, 59, 999);
  return d < new Date();
}

// ─── Tiny Avatar ─────────────────────────────────────────────────────────────
function Avatar({ name, size = 8, className = "" }: { name: string; size?: number; className?: string }) {
  const colors = ["from-indigo-500 to-violet-500", "from-cyan-500 to-blue-500", "from-pink-500 to-rose-500", "from-amber-500 to-orange-500", "from-emerald-500 to-teal-500"];
  const colorIdx = name.charCodeAt(0) % colors.length;
  return (
    <div className={`w-${size} h-${size} rounded-full bg-gradient-to-br ${colors[colorIdx]} flex items-center justify-center text-white text-[10px] font-bold flex-shrink-0 ring-2 ring-white ${className}`}>
      {initials(name)}
    </div>
  );
}

// ─── Label chip ──────────────────────────────────────────────────────────────
function StatusBadge({ status }: { status: Task["status"] }) {
  const c = statusMap[status];
  return <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-semibold uppercase tracking-wider ${c.bg} ${c.text}`}><span className={`w-1.5 h-1.5 rounded-full ${c.dot}`} />{c.label}</span>;
}

function PriorityBadge({ priority }: { priority: Task["priority"] }) {
  const c = priorityMap[priority];
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-semibold border ${c.bg} ${c.text} ${c.border}`}>
      <Icon.Flag level={priority} />
      {c.label}
    </span>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────
export default function TasksPage({ params: paramsPromise }: { params: Promise<{ domain: string }> }) {
  const params = React.use(paramsPromise);
  const domain = APP_SLUG;
  const hasMounted = useHasMounted();

  const [tasks, setTasks] = useState<Task[]>([]);
  const [view, setView] = useState<"kanban" | "list" | "table" | "calendar">("kanban");
  // A four-column drag-and-drop board is not what a phone is for: the list is
  // the same tasks, readable and tappable. Only the initial view is chosen —
  // switching to the board afterwards still works if that is what is wanted.
  // Read after hydration, not in the initial state: the server has no viewport
  // and a different first render on the client is a hydration mismatch.
  const viewPicked = useRef(false);
  useEffect(() => {
    if (viewPicked.current) return;
    viewPicked.current = true;
    if (window.innerWidth < 1024) setView("list");
  }, []);
  const [showModal, setShowModal] = useState(false);
  const [editingTask, setEditingTask] = useState<Task | null>(null);
  const [filterPriority, setFilterPriority] = useState("all");
  const [filterAssignee, setFilterAssignee] = useState("all");
  const [filterTimeline, setFilterTimeline] = useState<string[]>([]);
  const [filterDateFrom, setFilterDateFrom] = useState("");
  const [filterDateTo, setFilterDateTo] = useState("");
  const [search, setSearch] = useState("");
  const [teamMembers, setTeamMembers] = useState<{ id: number; name: string }[]>([]);
  const [leadsList, setLeadsList] = useState<{ id: number; name: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [currentDate, setCurrentDate] = useState(new Date());
  const searchRef = useRef<HTMLInputElement>(null);

  const blankForm = { title: "", description: "", status: "todo" as Task["status"], priority: "medium" as Task["priority"], assignee: "", dueDate: "", dueTime: "", leadName: "", tags: "" };
  const [form, setForm] = useState(blankForm);

  const columns = [
    { key: "todo" as Task["status"],        label: "To Do",       color: "bg-slate-400",   headerBg: "#f8fafc" },
    { key: "in_progress" as Task["status"], label: "In Progress", color: "bg-blue-500",    headerBg: "#eff6ff" },
    { key: "review" as Task["status"],      label: "In Review",   color: "bg-violet-500",  headerBg: "#f5f3ff" },
    { key: "done" as Task["status"],        label: "Done",        color: "bg-emerald-500", headerBg: "#ecfdf5" },
  ];

  // ── Data Fetching ──────────────────────────────────────────────────────────
  useEffect(() => {
    const token = localStorage.getItem(`${domain}_access`);
    if (!token) return;
    fetch(`${getApiBase(domain)}/api/users/`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.json()).then(d => {
        const arr = Array.isArray(d) ? d : (d.results || []);
        setTeamMembers(arr.map((u: any) => ({ id: u.id, name: `${u.first_name} ${u.last_name}`.trim() || u.username })));
      }).catch(() => {});
    fetch(`${getApiBase(domain)}/api/leads/?all=true`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.json()).then(d => {
        const arr = Array.isArray(d) ? d : (d.results || []);
        setLeadsList(arr.map((l: any) => ({ id: l.id, name: `${l.first_name || ""} ${l.last_name || ""}`.trim() || l.email })));
      }).catch(() => {});
  }, [domain]);

  useEffect(() => { fetchTasks(); }, [domain, filterPriority, filterAssignee]);

  // Deep-link: open a specific task when arriving via ?task=<id> (e.g. from a lead).
  const autoOpenedRef = useRef(false);
  useEffect(() => {
    if (autoOpenedRef.current || loading || tasks.length === 0) return;
    const targetId = new URLSearchParams(window.location.search).get("task");
    if (!targetId) return;
    const target = tasks.find((t) => String(t.id) === targetId);
    if (target) {
      autoOpenedRef.current = true;
      openEdit(target);
      // strip the param so a refresh doesn't reopen the modal
      const url = new URL(window.location.href);
      url.searchParams.delete("task");
      window.history.replaceState({}, "", url.toString());
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tasks, loading]);

  const fetchTasks = async () => {
    const token = localStorage.getItem(`${domain}_access`);
    if (!token) return;
    let url = `${getApiBase(domain)}/api/tasks/`;
    const q = new URLSearchParams();
    q.append("all", "true"); // load every task (board/list are not paginated)
    if (filterPriority !== "all") q.append("priority", filterPriority);
    if (filterAssignee === "me") q.append("assigned_to_me", "true");
    else if (filterAssignee !== "all") q.append("assignee_id", filterAssignee);
    if (q.toString()) url += `?${q}`;
    try {
      const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
      const data = await res.json();
      const list = Array.isArray(data) ? data : (data.results || []);
      setTasks(list.map((t: any) => ({
        ...t,
        assigneeAvatar: t.assignee_details?.first_name?.charAt(0)?.toUpperCase() || "?",
        assignee: t.assignee_details ? `${t.assignee_details.first_name} ${t.assignee_details.last_name}`.trim() : "Unassigned",
        assigneeId: t.assignee_details?.id,
        leadName: t.lead_details ? `${t.lead_details.first_name || ""} ${t.lead_details.last_name || ""}`.trim() : "",
        leadId: t.lead_details?.id || null,
        dueDate: t.due_date || "",
        dueTime: t.due_time || "",
        tags: t.tags || [],
      })));
    } catch (e) { console.error(e); } finally { setLoading(false); }
  };

  // ── Modal Helpers ──────────────────────────────────────────────────────────
  const openAdd = (status?: Task["status"], date?: string) => {
    setEditingTask(null);
    setForm({ ...blankForm, status: status || "todo", dueDate: date || "" });
    setShowModal(true);
  };
  const openEdit = (task: Task) => {
    setEditingTask(task);
    setForm({ title: task.title, description: task.description, status: task.status, priority: task.priority, assignee: task.assignee, dueDate: task.dueDate, dueTime: task.dueTime || "", leadName: task.leadName || "", tags: task.tags.join(", ") });
    setShowModal(true);
  };
  const deleteTask = async (id: number) => {
    if (!confirm("Delete this task?")) return;
    const token = localStorage.getItem(`${domain}_access`);
    await fetch(`${getApiBase(domain)}/api/tasks/${id}/`, { method: "DELETE", headers: { Authorization: `Bearer ${token}` } }).catch(console.error);
    setShowModal(false);
    fetchTasks();
  };
  const moveTask = async (id: number, newStatus: Task["status"]) => {
    setTasks(prev => prev.map(t => t.id === id ? { ...t, status: newStatus } : t));
    const token = localStorage.getItem(`${domain}_access`);
    await fetch(`${getApiBase(domain)}/api/tasks/${id}/`, { method: "PATCH", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify({ status: newStatus }) }).catch(() => fetchTasks());
  };
  const onDragEnd = (result: any) => {
    if (!result.destination) return;
    moveTask(parseInt(result.draggableId), result.destination.droppableId as Task["status"]);
  };
  // Saving is a network round trip; the button says so, and a second tap while
  // it is in flight would create the task twice.
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (saving) return;
    const token = localStorage.getItem(`${domain}_access`);
    if (!token) return;
    setSaving(true);
    const member = teamMembers.find(m => m.name === form.assignee);
    const lead = leadsList.find(l => l.name === form.leadName);
    const payload = { title: form.title, description: form.description, status: form.status, priority: form.priority, assignee: member?.id || null, lead: lead?.id || null, due_date: form.dueDate || null, due_time: form.dueTime || null, tags: form.tags.split(",").map(t => t.trim()).filter(Boolean) };
    const method = editingTask ? "PATCH" : "POST";
    const url = editingTask ? `${getApiBase(domain)}/api/tasks/${editingTask.id}/` : `${getApiBase(domain)}/api/tasks/`;
    try {
      const res = await fetch(url, { method, headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify(payload) });
      if (res.ok) { setShowModal(false); fetchTasks(); }
    } catch (e) { console.error(e); }
    finally { setSaving(false); }
  };

  const filtered = tasks.filter(t => {
    const matchesSearch = `${t.title} ${t.description} ${t.leadName || ""}`.toLowerCase().includes(search.toLowerCase());
    let matchesTimeline = true;
    if (filterTimeline.length > 0) {
      const isPending = t.status !== "done" && !isOverdue(t.dueDate, t.dueTime);
      const isOverdueTask = t.status !== "done" && isOverdue(t.dueDate, t.dueTime);
      const isCompleted = t.status === "done";
      
      matchesTimeline = 
        (filterTimeline.includes("pending") && isPending) ||
        (filterTimeline.includes("overdue") && isOverdueTask) ||
        (filterTimeline.includes("completed") && isCompleted);
    }

    let matchesDate = true;
    if (filterDateFrom && t.dueDate) {
      matchesDate = matchesDate && t.dueDate >= filterDateFrom;
    }
    if (filterDateTo && t.dueDate) {
      matchesDate = matchesDate && t.dueDate <= filterDateTo;
    }
    if ((filterDateFrom || filterDateTo) && !t.dueDate) {
      matchesDate = false;
    }

    return matchesSearch && matchesTimeline && matchesDate;
  });

  // ─────────────────────────── KANBAN ────────────────────────────────────────
  const KanbanView = () => {
    if (!hasMounted) return (
      <SkeletonRegion label="Preparing board">
        <div className="flex gap-4 overflow-hidden sm:grid sm:grid-cols-2 xl:grid-cols-4">
          {columns.map(col => (
            <div key={col.key} className="flex flex-col w-[78vw] max-w-[300px] sm:w-auto sm:max-w-none flex-shrink-0">
              <Skeleton className="h-9 w-full rounded-xl mb-2" />
              <div className="space-y-2.5">
                {Array.from({ length: 2 }).map((_, i) => (
                  <div key={i} className="bg-white border border-slate-100 rounded-xl p-4 space-y-2.5">
                    <Skeleton className="h-5 w-16 rounded-full" />
                    <Skeleton className="h-3.5 w-3/4 rounded-md" />
                    <Skeleton className="h-2.5 w-1/2 rounded-full" />
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </SkeletonRegion>
    );
    return (
      <DragDropContext onDragEnd={onDragEnd}>
        <div className="overflow-x-auto -mx-4 sm:mx-0 px-4 sm:px-0 pb-4">
          <div className="flex gap-4 min-w-max sm:min-w-0 sm:grid sm:grid-cols-2 xl:grid-cols-4">
            {columns.map(col => {
              const colTasks = filtered.filter(t => t.status === col.key);
              const sm = statusMap[col.key];
              return (
                <div key={col.key} className="flex flex-col w-[78vw] max-w-[300px] sm:w-auto sm:max-w-none sm:min-w-[220px]">
                  {/* Column header */}
                  <div className="flex items-center justify-between px-3 py-2 mb-2 rounded-xl" style={{ backgroundColor: col.headerBg }}>
                    <div className="flex items-center gap-2">
                      <span className={`w-2 h-2 rounded-full ${col.color}`} />
                      <span className="text-xs font-semibold text-slate-700">{col.label}</span>
                      <span className="text-[10px] font-bold text-slate-400 bg-white/80 px-1.5 py-0.5 rounded-full border border-slate-100">{colTasks.length}</span>
                    </div>
                    <button onClick={() => openAdd(col.key)} className="w-6 h-6 flex items-center justify-center rounded-lg text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 transition-all">
                      <Icon.Plus />
                    </button>
                  </div>

                  <Droppable droppableId={col.key}>
                    {(provided, snapshot) => (
                      <div
                        {...provided.droppableProps}
                        ref={provided.innerRef}
                        className={`flex-1 min-h-[300px] space-y-2.5 rounded-xl p-1.5 transition-all duration-200 ${snapshot.isDraggingOver ? "bg-indigo-50 ring-1 ring-indigo-200 ring-inset" : ""}`}
                      >
                        {colTasks.map((task, i) => {
                          const pc = priorityMap[task.priority];
                          const overdue = isOverdue(task.dueDate, task.dueTime);
                          return (
                            <Draggable key={task.id.toString()} draggableId={task.id.toString()} index={i}>
                              {(provided, snap) => (
                                <div
                                  ref={provided.innerRef}
                                  {...provided.draggableProps}
                                  {...provided.dragHandleProps}
                                  onClick={() => openEdit(task)}
                                  className={`group bg-white rounded-xl border border-slate-100 p-3.5 cursor-pointer select-none transition-all duration-150 ${snap.isDragging ? "shadow-2xl border-indigo-200 rotate-[1.5deg] opacity-90" : "shadow-sm hover:shadow-md hover:-translate-y-0.5"}`}
                                >
                                  {/* Priority line */}
                                  <div className="flex items-center justify-between mb-2.5">
                                    <PriorityBadge priority={task.priority} />
                                    {task.dueDate && (
                                      <span className={`flex items-center gap-1 text-[10px] font-medium ${overdue && task.status !== "done" ? "text-red-500" : "text-slate-400"}`}>
                                        <Icon.Clock />
                                        {formatDate(task.dueDate)}{task.dueTime ? ` · ${task.dueTime.slice(0, 5)}` : ""}
                                      </span>
                                    )}
                                  </div>

                                  {/* Title */}
                                  <h4 className={`text-sm font-semibold text-slate-800 leading-snug mb-1 line-clamp-2 ${task.status === "done" ? "line-through text-slate-400" : ""}`}>{task.title}</h4>
                                  {task.description && <p className="text-xs text-slate-400 line-clamp-2 mb-3 leading-relaxed">{task.description}</p>}

                                  {/* Footer: tags + avatar */}
                                  <div className="flex items-center justify-between pt-2.5 border-t border-slate-50">
                                    <div className="flex items-center gap-1 min-w-0">
                                      {task.tags.slice(0, 1).map(tag => (
                                        <span key={tag} className="text-[9px] font-medium text-slate-500 bg-slate-50 border border-slate-100 px-2 py-0.5 rounded truncate max-w-[80px]">{tag}</span>
                                      ))}
                                      {task.leadName && (
                                        <span className="text-[9px] font-medium text-indigo-500 bg-indigo-50 border border-indigo-100 px-2 py-0.5 rounded truncate max-w-[80px]">{task.leadName}</span>
                                      )}
                                    </div>
                                    <Avatar name={task.assignee} size={7} />
                                  </div>
                                </div>
                              )}
                            </Draggable>
                          );
                        })}
                        {provided.placeholder}
                        {colTasks.length === 0 && !snapshot.isDraggingOver && (
                          <div className="flex flex-col items-center py-8 text-slate-300">
                            <svg width="24" height="24" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24" className="mb-2"><rect x="3" y="3" width="18" height="18" rx="3" /><path d="M8 12h8M12 8v8" /></svg>
                            <span className="text-xs">No tasks</span>
                          </div>
                        )}
                      </div>
                    )}
                  </Droppable>
                </div>
              );
            })}
          </div>
        </div>
      </DragDropContext>
    );
  };

  // ─────────────────────────── LIST ──────────────────────────────────────────
  const ListView = () => (
    <div className="space-y-2">
      {filtered.length === 0 && <EmptyState />}
      {filtered.map(task => {
        const overdue = isOverdue(task.dueDate, task.dueTime);
        return (
          <div key={task.id} onClick={() => openEdit(task)} className="group bg-white border border-slate-100 rounded-xl px-4 py-3.5 flex flex-col sm:flex-row sm:items-center gap-3 cursor-pointer hover:shadow-md hover:border-slate-200 transition-all duration-150">
            {/* Left */}
            <div className="flex items-center gap-3 flex-1 min-w-0">
              <div className={`w-1 h-10 rounded-full flex-shrink-0 ${priorityMap[task.priority].dot}`} />
              <div className="min-w-0">
                <h4 className={`text-sm font-semibold text-slate-800 truncate ${task.status === "done" ? "line-through text-slate-400" : ""}`}>{task.title}</h4>
                <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 mt-0.5">
                  {task.leadName && (
                    <span className="flex items-center gap-1 text-[10px] text-indigo-500 font-medium"><Icon.Link2 />{task.leadName}</span>
                  )}
                  {task.dueDate && (
                    <span className={`flex items-center gap-1 text-[10px] font-medium ${overdue && task.status !== "done" ? "text-red-500" : "text-slate-400"}`}><Icon.Clock />{formatDate(task.dueDate)}{task.dueTime ? ` · ${task.dueTime.slice(0, 5)}` : ""}</span>
                  )}
                  <span className="flex items-center gap-1 text-[10px] text-slate-400"><Icon.User />{task.assignee}</span>
                </div>
              </div>
            </div>
            {/* Right */}
            <div className="flex items-center gap-2.5 sm:ml-4 flex-shrink-0 flex-wrap">
              <PriorityBadge priority={task.priority} />
              <StatusBadge status={task.status} />
              <Avatar name={task.assignee} size={7} className="hidden md:flex" />
              <button onClick={e => { e.stopPropagation(); deleteTask(task.id); }} className="w-7 h-7 flex items-center justify-center rounded-lg text-slate-300 hover:text-red-500 hover:bg-red-50 transition-all opacity-0 group-hover:opacity-100">
                <Icon.Trash />
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );

  // ─────────────────────────── TABLE ─────────────────────────────────────────
  const TableView = () => (
    <div className="bg-white border border-slate-100 rounded-2xl overflow-hidden shadow-sm">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[700px] text-left border-collapse">
          <thead>
            <tr className="border-b border-slate-100 bg-slate-50/70">
              <th className="px-5 py-3.5 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Task</th>
              <th className="px-5 py-3.5 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Status</th>
              <th className="px-5 py-3.5 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Priority</th>
              <th className="px-5 py-3.5 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Due Date</th>
              <th className="px-5 py-3.5 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Assignee</th>
              <th className="w-12"></th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 && (
              <tr><td colSpan={6}><div className="py-16 flex flex-col items-center text-slate-300"><svg width="32" height="32" fill="none" stroke="currentColor" strokeWidth="1.2" viewBox="0 0 24 24" className="mb-2"><path d="M9 11l3 3 8-8" /><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" /></svg><span className="text-sm">No tasks found</span></div></td></tr>
            )}
            {filtered.map((task, i) => {
              const overdue = isOverdue(task.dueDate, task.dueTime);
              return (
                <tr key={task.id} onClick={() => openEdit(task)} className={`group cursor-pointer hover:bg-blue-50/40 transition-colors ${i !== filtered.length - 1 ? "border-b border-slate-50" : ""}`}>
                  <td className="px-5 py-4">
                    <div>
                      <p className={`text-sm font-semibold text-slate-800 ${task.status === "done" ? "line-through text-slate-400" : ""}`}>{task.title}</p>
                      {task.leadName && <p className="flex items-center gap-1 text-[10px] text-indigo-500 font-medium mt-0.5"><Icon.Link2 />{task.leadName}</p>}
                    </div>
                  </td>
                  <td className="px-5 py-4"><StatusBadge status={task.status} /></td>
                  <td className="px-5 py-4"><PriorityBadge priority={task.priority} /></td>
                  <td className="px-5 py-4">
                    <span className={`flex items-center gap-1.5 text-xs font-medium ${overdue && task.status !== "done" ? "text-red-500" : "text-slate-500"}`}>
                      <Icon.Clock />
                      {task.dueDate ? `${formatDate(task.dueDate)}${task.dueTime ? ` · ${task.dueTime.slice(0, 5)}` : ""}` : "—"}
                    </span>
                  </td>
                  <td className="px-5 py-4">
                    <div className="flex items-center gap-2">
                      <Avatar name={task.assignee} size={7} />
                      <span className="text-xs font-medium text-slate-600 hidden lg:block">{task.assignee}</span>
                    </div>
                  </td>
                  <td className="pr-4">
                    <button onClick={e => { e.stopPropagation(); deleteTask(task.id); }} className="w-8 h-8 flex items-center justify-center rounded-lg text-slate-300 hover:text-red-500 hover:bg-red-50 transition-all opacity-0 group-hover:opacity-100">
                      <Icon.Trash />
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );

  // ─────────────────────────── CALENDAR ──────────────────────────────────────
  const CalendarView = () => {
    const year = currentDate.getFullYear(), month = currentDate.getMonth();
    const firstDay = new Date(year, month, 1).getDay();
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const prevDays = new Date(year, month, 0).getDate();
    const todayIso = new Date().toISOString().split("T")[0];

    const days: { day: number; current: boolean; iso: string }[] = [];
    for (let i = firstDay - 1; i >= 0; i--) {
      const d = new Date(year, month - 1, prevDays - i);
      days.push({ day: prevDays - i, current: false, iso: d.toISOString().split("T")[0] });
    }
    for (let i = 1; i <= daysInMonth; i++) {
      const d = new Date(year, month, i);
      days.push({ day: i, current: true, iso: d.toISOString().split("T")[0] });
    }
    let n = 1;
    while (days.length < 42) {
      const d = new Date(year, month + 1, n);
      days.push({ day: n++, current: false, iso: d.toISOString().split("T")[0] });
    }

    return (
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 px-5 py-4 border-b border-slate-100">
          <div>
            <h2 className="text-base font-bold text-slate-900">
              {currentDate.toLocaleString("default", { month: "long" })} {year}
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">Task schedule overview</p>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => setCurrentDate(new Date(year, month - 1, 1))} className="w-8 h-8 flex items-center justify-center rounded-lg bg-slate-50 hover:bg-slate-100 text-slate-600 transition-all"><Icon.ChevronLeft /></button>
            <button onClick={() => setCurrentDate(new Date())} className="px-4 h-8 text-xs font-semibold text-slate-600 bg-slate-50 hover:bg-slate-100 rounded-lg transition-all">Today</button>
            <button onClick={() => setCurrentDate(new Date(year, month + 1, 1))} className="w-8 h-8 flex items-center justify-center rounded-lg bg-slate-50 hover:bg-slate-100 text-slate-600 transition-all"><Icon.ChevronRight /></button>
          </div>
        </div>

        {/* A month grid needs ~620px before the day cells stop holding a task
            title; below that it scrolls sideways as one piece. */}
        <div className="overflow-x-auto">
        <div className="min-w-[620px] sm:min-w-0">
        {/* Day headers */}
        <div className="grid grid-cols-7 border-b border-slate-100">
          {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map(d => (
            <div key={d} className="py-2.5 text-[10px] font-bold text-slate-400 uppercase tracking-widest text-center">{d}</div>
          ))}
        </div>

        {/* Grid */}
        <div className="grid grid-cols-7">
          {days.map((item, idx) => {
            const dayTasks = tasks.filter(t => t.dueDate === item.iso);
            const isToday = item.iso === todayIso;
            const isWeekend = idx % 7 === 0 || idx % 7 === 6;
            return (
              <div key={idx} className={`min-h-[90px] sm:min-h-[120px] border-r border-b border-slate-50 p-2 group transition-colors ${!item.current ? "bg-slate-50/40 opacity-50" : isWeekend ? "bg-slate-50/20" : "hover:bg-blue-50/30"}`}>
                <div className="flex items-center justify-between mb-1.5">
                  <span className={`w-6 h-6 flex items-center justify-center rounded-full text-xs font-semibold transition-colors ${isToday ? "bg-indigo-600 text-white" : "text-slate-500 hover:bg-slate-100 cursor-default"}`}>{item.day}</span>
                  {item.current && (
                    <button onClick={() => openAdd("todo", item.iso)} className="w-5 h-5 flex items-center justify-center rounded text-slate-200 hover:text-indigo-600 hover:bg-indigo-50 transition-all opacity-0 group-hover:opacity-100">
                      <Icon.Plus />
                    </button>
                  )}
                </div>
                <div className="space-y-0.5">
                  {dayTasks.slice(0, 3).map(t => {
                    const pc = priorityMap[t.priority];
                    return (
                      <div key={t.id} onClick={() => openEdit(t)} className={`px-1.5 py-0.5 rounded text-[9px] font-semibold truncate cursor-pointer hover:opacity-80 transition-opacity border ${pc.bg} ${pc.text} ${pc.border}`}>
                        {t.title}
                      </div>
                    );
                  })}
                  {dayTasks.length > 3 && (
                    <div className="text-[9px] text-slate-400 font-medium pl-0.5">+{dayTasks.length - 3} more</div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
        </div>
        </div>
      </div>
    );
  };

  // ─────────────────────────── EMPTY STATE ──────────────────────────────────
  const EmptyState = () => (
    <div className="flex flex-col items-center py-20 text-center">
      <div className="w-16 h-16 rounded-2xl bg-indigo-50 flex items-center justify-center mb-4">
        <svg width="28" height="28" fill="none" stroke="#6366f1" strokeWidth="1.5" viewBox="0 0 24 24"><path d="M9 11l3 3 8-8" /><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" /></svg>
      </div>
      <h3 className="text-base font-semibold text-slate-700 mb-1">No tasks yet</h3>
      <p className="text-sm text-slate-400 mb-6">Create your first task to get started</p>
      <button onClick={() => openAdd()} className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-indigo-600 text-white text-sm font-semibold hover:bg-indigo-700 transition-all shadow-md shadow-indigo-200">
        <Icon.Plus /> New Task
      </button>
    </div>
  );

  // ─────────────────────────── LOADING ──────────────────────────────────────
  // Header, toolbar and a list of task cards — the view the page opens on for
  // whoever is on a phone, and close enough to the board above `lg`.
  if (loading) return (
    <SkeletonRegion label="Loading tasks">
      <div className="min-h-screen bg-[#f5f7fb]">
        <div className="bg-white border-b border-slate-200/60">
          <div className="max-w-[1400px] mx-auto px-4 sm:px-6 xl:px-8">
            <div className="flex items-center justify-between gap-2 h-16">
              <div className="space-y-2">
                <Skeleton className="h-4 w-20 rounded-md" />
                <Skeleton className="h-2.5 w-24 rounded-full" />
              </div>
              <div className="flex items-center gap-2 sm:gap-3">
                <Skeleton className="h-10 w-44 rounded-xl" />
                <Skeleton className="h-10 w-10 sm:w-28 rounded-xl" />
              </div>
            </div>
          </div>
        </div>
        <div className="max-w-[1400px] mx-auto px-4 sm:px-6 xl:px-8 pt-5 pb-4 space-y-3">
          <Skeleton className="h-11 w-full rounded-xl" />
          <div className="flex gap-2 overflow-hidden">
            {[150, 150, 130, 220].map((w, i) => (
              <div key={i} className="skeleton h-11 rounded-xl flex-shrink-0" style={{ width: w }} aria-hidden="true" />
            ))}
          </div>
        </div>
        <div className="max-w-[1400px] mx-auto px-4 sm:px-6 xl:px-8 pb-12 space-y-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="bg-white border border-slate-100 rounded-xl px-4 py-3.5 flex flex-col sm:flex-row sm:items-center gap-3">
              <div className="flex items-center gap-3 flex-1 min-w-0">
                <Skeleton className="w-1 h-10 rounded-full flex-shrink-0" />
                <div className="flex-1 space-y-2">
                  <Skeleton className="h-3.5 w-2/5 rounded-md" />
                  <Skeleton className="h-2.5 w-3/5 rounded-full" />
                </div>
              </div>
              <div className="flex items-center gap-2.5 sm:ml-4 flex-shrink-0">
                <Skeleton className="h-6 w-16 rounded-full" />
                <Skeleton className="h-6 w-20 rounded-full" />
              </div>
            </div>
          ))}
        </div>
      </div>
    </SkeletonRegion>
  );

  const views = [
    { id: "kanban",   label: "Board",    Icon: Icon.Board    },
    { id: "list",     label: "List",     Icon: Icon.List     },
    { id: "table",    label: "Table",    Icon: Icon.Table    },
    { id: "calendar", label: "Calendar", Icon: Icon.Calendar },
  ];

  // ─────────────────────────── RENDER ────────────────────────────────────────
  return (
    <div className="min-h-screen bg-[#f5f7fb]">

      {/* ── Page Header ─────────────────────────────────────────────────── */}
      <div className="bg-white border-b border-slate-200/60 sticky-under-topbar z-20">
        <div className="max-w-[1400px] mx-auto px-4 sm:px-6 xl:px-8">
          <div className="flex items-center justify-between gap-2 h-16">
            {/* Title + count */}
            <div className="flex items-center gap-4">
              <div>
                <h1 className="text-lg font-bold text-slate-900 leading-none">Tasks</h1>
                <p className="text-[11px] text-slate-400 mt-0.5">{filtered.length} of {tasks.length} tasks</p>
              </div>
            </div>

            {/* View tabs + New Task */}
            <div className="flex items-center gap-2 sm:gap-3 min-w-0">
              {/* View switcher — hidden labels on xs */}
              <div className="flex items-center bg-slate-100 rounded-xl p-1 gap-0.5 overflow-x-auto no-scrollbar">
                {views.map(v => (
                  <button
                    key={v.id}
                    onClick={() => setView(v.id as any)}
                    title={v.label}
                    className={`flex items-center gap-1.5 px-2.5 sm:px-3 py-2 rounded-lg text-xs font-semibold transition-all flex-shrink-0 ${view === v.id ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}
                  >
                    <v.Icon />
                    <span className="hidden sm:inline">{v.label}</span>
                  </button>
                ))}
              </div>

              <button
                onClick={() => openAdd()}
                className="flex items-center justify-center gap-2 w-10 h-10 sm:w-auto sm:h-auto sm:px-4 sm:py-2 rounded-xl bg-indigo-600 text-white text-sm font-semibold hover:bg-indigo-700 active:scale-95 transition-all shadow-sm flex-shrink-0"
                aria-label="New task"
              >
                <Icon.Plus />
                <span className="hidden sm:inline">New Task</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* ── Toolbar ─────────────────────────────────────────────────────── */}
      <div className="max-w-[1400px] mx-auto px-4 sm:px-6 xl:px-8 pt-5 pb-4">
        <div className="flex flex-col lg:flex-row lg:flex-wrap gap-3">
          {/* Search */}
          <div className="relative flex-1">
            <div className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none">
              <Icon.Search />
            </div>
            <input
              ref={searchRef}
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search tasks by name, description or lead..."
              className="w-full bg-white border border-slate-200 rounded-xl pl-9 pr-4 py-2.5 text-sm text-slate-700 placeholder:text-slate-400 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all"
            />
            {search && (
              <button onClick={() => setSearch("")} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600">
                <Icon.X />
              </button>
            )}
          </div>

          {/* Filters — a row that scrolls on a phone; wrapped on a desktop. */}
          <div className="flex gap-2 flex-shrink-0 overflow-x-auto no-scrollbar pb-1 lg:flex-wrap lg:overflow-visible lg:pb-0 [&>*]:flex-shrink-0">
            <div className="relative">
              <select
                value={filterPriority}
                onChange={e => setFilterPriority(e.target.value)}
                className="appearance-none bg-white border border-slate-200 rounded-xl pl-3.5 pr-8 py-2.5 text-sm font-medium text-slate-700 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 cursor-pointer transition-all"
              >
                <option value="all">All Priorities</option>
                <option value="high">High Priority</option>
                <option value="medium">Medium Priority</option>
                <option value="low">Low Priority</option>
              </select>
              <div className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none"><Icon.ChevronDown /></div>
            </div>
            <div className="relative">
              <select
                value={filterAssignee}
                onChange={e => setFilterAssignee(e.target.value)}
                className="appearance-none bg-white border border-slate-200 rounded-xl pl-3.5 pr-8 py-2.5 text-sm font-medium text-slate-700 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 cursor-pointer transition-all"
              >
                <option value="all">All Owners</option>
                <option value="me">Assigned to Me</option>
                {teamMembers.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
              </select>
              <div className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none"><Icon.ChevronDown /></div>
            </div>
            {/* Multi-select Status/Timeline */}
            <div className="relative group" tabIndex={0}>
              <button className="flex items-center gap-1.5 appearance-none bg-white border border-slate-200 rounded-xl pl-3.5 pr-2.5 py-2.5 text-sm font-medium text-slate-700 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all whitespace-nowrap">
                {filterTimeline.length === 0 ? "All Status" : `Status (${filterTimeline.length})`}
                <Icon.ChevronDown />
              </button>
              <div className="absolute top-full mt-1.5 left-0 w-44 bg-white border border-slate-200 rounded-xl shadow-lg shadow-slate-200/50 p-2 z-30 opacity-0 invisible group-hover:opacity-100 group-hover:visible group-focus-within:opacity-100 group-focus-within:visible transition-all flex flex-col gap-1">
                {[
                  { id: "pending", label: "Pending" },
                  { id: "overdue", label: "Overdue" },
                  { id: "completed", label: "Completed" }
                ].map(opt => (
                  <label key={opt.id} className="flex items-center gap-2.5 px-2 py-1.5 hover:bg-slate-50 rounded-lg cursor-pointer text-sm text-slate-700 font-medium">
                    <input 
                      type="checkbox" 
                      className="hidden" 
                      checked={filterTimeline.includes(opt.id)}
                      onChange={() => {
                        setFilterTimeline(prev => prev.includes(opt.id) ? prev.filter(v => v !== opt.id) : [...prev, opt.id]);
                      }}
                    />
                    <div className={`w-4 h-4 rounded border flex items-center justify-center transition-colors ${filterTimeline.includes(opt.id) ? "bg-indigo-600 border-indigo-600 text-white" : "border-slate-300 bg-white"}`}>
                      {filterTimeline.includes(opt.id) && <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>}
                    </div>
                    {opt.label}
                  </label>
                ))}
              </div>
            </div>
            {/* Date Range Filter */}
            <div className="flex items-center bg-white border border-slate-200 rounded-xl px-2 py-1.5 focus-within:ring-2 focus-within:ring-indigo-500/20 focus-within:border-indigo-400 transition-all gap-2">
              <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-widest pl-1">Due</span>
              <input 
                type="date" 
                value={filterDateFrom} 
                onChange={e => setFilterDateFrom(e.target.value)} 
                className="appearance-none bg-transparent text-xs font-medium text-slate-700 outline-none w-[124px] cursor-pointer" 
              />
              <span className="text-slate-300">-</span>
              <input 
                type="date" 
                value={filterDateTo} 
                onChange={e => setFilterDateTo(e.target.value)} 
                className="appearance-none bg-transparent text-xs font-medium text-slate-700 outline-none w-[124px] cursor-pointer" 
              />
              {(filterDateFrom || filterDateTo) && (
                <button 
                  onClick={() => { setFilterDateFrom(""); setFilterDateTo(""); }} 
                  className="flex items-center justify-center w-5 h-5 rounded hover:bg-slate-100 text-slate-400 hover:text-slate-600 transition-colors"
                >
                  <Icon.X />
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ── View Content ─────────────────────────────────────────────────── */}
      <div className="max-w-[1400px] mx-auto px-4 sm:px-6 xl:px-8 pb-12">
        {view === "kanban"   && <KanbanView />}
        {view === "list"     && <ListView />}
        {view === "table"    && <TableView />}
        {view === "calendar" && <CalendarView />}
      </div>

      {/* ── Modal ────────────────────────────────────────────────────────── */}
      {showModal && (
        <div
          className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/40 backdrop-blur-sm"
          onClick={() => setShowModal(false)}
        >
          <div
            className="bg-white w-full sm:max-w-lg sm:mx-4 rounded-t-2xl sm:rounded-2xl shadow-2xl max-h-[92vh] overflow-hidden flex flex-col"
            onClick={e => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 flex-shrink-0">
              <div>
                <h2 className="text-base font-bold text-slate-900">{editingTask ? "Edit Task" : "New Task"}</h2>
                <p className="text-xs text-slate-400 mt-0.5">{editingTask ? "Update task details below" : "Add a new task to your workflow"}</p>
              </div>
              <button onClick={() => setShowModal(false)} className="w-8 h-8 flex items-center justify-center rounded-xl bg-slate-100 text-slate-500 hover:bg-slate-200 transition-all">
                <Icon.X />
              </button>
            </div>

            {/* Modal Form */}
            <form onSubmit={handleSubmit} className="overflow-y-auto flex-1 px-6 py-5 space-y-5">
              {/* Title */}
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1.5">Task Name <span className="text-red-400">*</span></label>
                <input
                  required
                  type="text"
                  value={form.title}
                  onChange={e => setForm({ ...form, title: e.target.value })}
                  placeholder="e.g. Follow up with client about proposal"
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all"
                  autoFocus
                />
              </div>

              {/* Description */}
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1.5">Description</label>
                <textarea
                  value={form.description}
                  onChange={e => setForm({ ...form, description: e.target.value })}
                  placeholder="Add notes, steps or context..."
                  rows={3}
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all resize-none"
                />
              </div>

              {/* Assignee + Lead (side by side) */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">Assignee</label>
                  <input
                    list="modal-team-list"
                    type="text"
                    value={form.assignee}
                    onChange={e => setForm({ ...form, assignee: e.target.value })}
                    placeholder="Search name..."
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all"
                  />
                  <datalist id="modal-team-list">{teamMembers.map(m => <option key={m.id} value={m.name} />)}</datalist>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">Linked Lead</label>
                  <input
                    list="modal-lead-list"
                    type="text"
                    value={form.leadName}
                    onChange={e => setForm({ ...form, leadName: e.target.value })}
                    placeholder="Search leads..."
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all"
                  />
                  <datalist id="modal-lead-list">{leadsList.map(l => <option key={l.id} value={l.name} />)}</datalist>
                  {editingTask?.leadId && (
                    <a
                      href={`/leads/${editingTask.leadId}`}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-1.5 flex items-center gap-1.5 text-[11px] font-semibold text-indigo-600 hover:text-indigo-800 transition-colors"
                    >
                      <svg width="11" height="11" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71" /><path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71" /></svg>
                      View Lead: {editingTask.leadName}
                      <svg width="10" height="10" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" viewBox="0 0 24 24"><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6" /><polyline points="15 3 21 3 21 9" /><line x1="10" y1="14" x2="21" y2="3" /></svg>
                    </a>
                  )}
                </div>
              </div>

              {/* Status + Priority */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">Status</label>
                  <div className="relative">
                    <select
                      value={form.status}
                      onChange={e => setForm({ ...form, status: e.target.value as any })}
                      className="w-full appearance-none bg-slate-50 border border-slate-200 rounded-xl pl-4 pr-8 py-2.5 text-sm font-medium text-slate-700 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all cursor-pointer"
                    >
                      <option value="todo">To Do</option>
                      <option value="in_progress">In Progress</option>
                      <option value="review">In Review</option>
                      <option value="done">Done</option>
                    </select>
                    <div className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none"><Icon.ChevronDown /></div>
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">Priority</label>
                  <div className="relative">
                    <select
                      value={form.priority}
                      onChange={e => setForm({ ...form, priority: e.target.value as any })}
                      className="w-full appearance-none bg-slate-50 border border-slate-200 rounded-xl pl-4 pr-8 py-2.5 text-sm font-medium text-slate-700 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all cursor-pointer"
                    >
                      <option value="high">High</option>
                      <option value="medium">Medium</option>
                      <option value="low">Low</option>
                    </select>
                    <div className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none"><Icon.ChevronDown /></div>
                  </div>
                </div>
              </div>

              {/* Due Date + Due Time */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">Due Date</label>
                  <input
                    type="date"
                    value={form.dueDate}
                    onChange={e => setForm({ ...form, dueDate: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm text-slate-700 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">Due Time</label>
                  <input
                    type="time"
                    value={form.dueTime}
                    onChange={e => setForm({ ...form, dueTime: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm text-slate-700 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all"
                  />
                </div>
              </div>

              {/* Tags */}
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1.5">Tags</label>
                <input
                  type="text"
                  value={form.tags}
                  onChange={e => setForm({ ...form, tags: e.target.value })}
                  placeholder="sales, q4, follow-up..."
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all"
                />
              </div>
            </form>

            {/* Modal Footer */}
            <div className="flex items-center gap-3 px-6 py-4 border-t border-slate-100 flex-shrink-0 bg-white">
              {editingTask && (
                <button
                  type="button"
                  onClick={() => deleteTask(editingTask.id)}
                  className="flex items-center gap-2 px-4 py-2.5 rounded-xl border border-red-200 text-red-500 text-sm font-semibold hover:bg-red-50 transition-all"
                >
                  <Icon.Trash /> Delete
                </button>
              )}
              <button
                type="button"
                onClick={() => setShowModal(false)}
                className="flex-1 py-2.5 rounded-xl border border-slate-200 text-slate-600 text-sm font-semibold hover:bg-slate-50 transition-all"
              >
                Cancel
              </button>
              <button
                type="submit"
                form="task-form-hidden"
                onClick={handleSubmit}
                disabled={saving}
                className="flex-1 py-2.5 rounded-xl bg-indigo-600 text-white text-sm font-semibold hover:bg-indigo-700 active:scale-[0.98] transition-all shadow-sm shadow-indigo-200 disabled:opacity-60 flex items-center justify-center gap-2"
              >
                {saving && <Spinner />}
                {saving ? "Saving…" : editingTask ? "Save Changes" : "Create Task"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

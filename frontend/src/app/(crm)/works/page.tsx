"use client";
/**
 * Works — every customer from the site visit to a finished project, by stage.
 *
 * For the three desks that own a stage in the middle of the pipeline: the
 * documentation manager (Documentation S1), the accounts manager (Accounts) and
 * the project manager (Project). The pipeline is split at the viewer's own
 * stage. Upcoming is everything before it, the work on its way to them;
 * Completed is everything past it. Their own stage is in neither list: that is
 * their own module, and the strip links there.
 *
 * The server sorts customers into stages and counts them (leads/works.py), so
 * the numbers on the strip always describe the rows under it. Each stage
 * arrives a page at a time, and "Show more" fetches the next page of that one.
 */
import { APP_SLUG } from "@/lib/config";
import { getApiBase, formatCurrency } from "@/lib/mock-data";

import React, { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import BdeTag from "@/components/BdeTag";
import { PageSkeleton } from "@/components/Skeleton";

type View = "upcoming" | "completed";

type Stage = {
  key: string;
  label: string;
  blurb: string;
  handler_label: string;
  side: "upcoming" | "mine" | "completed";
  count: number;
};
type Step = { stage: string; on: string | null; by: string | null };
type Work = {
  id: number;
  name: string;
  phone: string | null;
  place: string | null;
  district: string | null;
  product: string | null;
  value: string;
  bde_name: string | null;
  stage: string;
  since: string | null;
  handler_name: string | null;
  // Every stage up to the one the customer is in now.
  journey: Step[];
};
type Group = { stage: string; count: number; offset: number; works: Work[]; has_more: boolean };
type Board = {
  desk: { stage: string; label: string; module: string };
  view: View;
  search: string;
  stages: Stage[];
  total: number;
  groups: Group[];
};

// Stage dates arrive as plain days (YYYY-MM-DD) and are read as local dates:
// `new Date("2026-10-25")` is midnight UTC, which west of Greenwich is the 24th.
function asDay(iso: string) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}

const fmtDay = (iso: string | null) =>
  iso ? asDay(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) : null;

function daysSince(iso: string | null) {
  if (!iso) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.max(0, Math.round((today.getTime() - asDay(iso).getTime()) / 86400000));
}

const ago = (n: number) => (n === 0 ? "today" : n === 1 ? "1 day" : `${n} days`);

const rupees = (value: string) => (Number(value) ? `₹${formatCurrency(Number(value))}` : "—");

export default function WorksPage() {
  const domain = APP_SLUG;
  const api = getApiBase(domain);
  const router = useRouter();

  const [view, setView] = useState<View>("upcoming");
  const [stage, setStage] = useState("all");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [board, setBoard] = useState<Board | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [loadingMore, setLoadingMore] = useState<string | null>(null);
  const [open, setOpen] = useState<Work | null>(null);
  // Only the latest request may land: switching tabs or typing quickly must not
  // let an older, slower answer overwrite a newer one.
  const latest = useRef(0);
  const strip = useRef<HTMLDivElement>(null);
  const deskStage = board?.desk.stage;

  // On a phone the strip is wider than the screen; start it with the viewer's
  // own stage in the middle rather than scrolled off to the right.
  useEffect(() => {
    const box = strip.current;
    const mine = box?.querySelector<HTMLElement>("[data-mine]");
    if (box && mine) box.scrollLeft = mine.offsetLeft - (box.clientWidth - mine.offsetWidth) / 2;
  }, [deskStage]);

  // Typing settles for a moment before it becomes a request.
  useEffect(() => {
    const t = setTimeout(() => setQuery(search.trim()), 300);
    return () => clearTimeout(t);
  }, [search]);

  const fetchBoard = useCallback(async (params: Record<string, string>) => {
    const tk = localStorage.getItem(`${domain}_access`);
    if (!tk) {
      router.push("/login");
      return null;
    }
    const r = await fetch(`${api}/api/works/?${new URLSearchParams(params)}`, {
      headers: { Authorization: `Bearer ${tk}` },
    });
    if (r.status === 403) throw new Error("forbidden");
    if (!r.ok) throw new Error("failed");
    return (await r.json()) as Board;
  }, [api, domain, router]);

  useEffect(() => {
    const ticket = ++latest.current;
    setLoading(true);
    fetchBoard({ view, ...(query ? { search: query } : {}) })
      .then(b => {
        if (ticket === latest.current && b) {
          setBoard(b);
          setError("");
        }
      })
      .catch(e => {
        if (ticket !== latest.current) return;
        setError(e.message === "forbidden"
          ? "Works is for the documentation, accounts and project managers."
          : "Couldn't load the works. Check your connection and try again.");
      })
      .finally(() => {
        if (ticket === latest.current) setLoading(false);
      });
  }, [view, query, fetchBoard]);

  const showMore = async (g: Group) => {
    const ticket = latest.current;
    setLoadingMore(g.stage);
    try {
      const next = await fetchBoard({
        view, stage: g.stage, offset: String(g.works.length), ...(query ? { search: query } : {}),
      });
      const page = next?.groups[0];
      // A tab switch or a new search while this was on its way makes it stale.
      if (!page || ticket !== latest.current) return;
      setBoard(b => b && {
        ...b,
        groups: b.groups.map(x => {
          if (x.stage !== g.stage) return x;
          // A customer who arrived between the two pages shifts the rest down
          // by one; skip the row that would otherwise appear twice.
          const seen = new Set(x.works.map(w => w.id));
          return {
            ...x, count: page.count, has_more: page.has_more,
            works: [...x.works, ...page.works.filter(w => !seen.has(w.id))],
          };
        }),
      });
    } catch {
      /* the button stays, and pressing it again retries */
    } finally {
      setLoadingMore(null);
    }
  };

  const switchTo = (v: View, s = "all") => {
    setView(v);
    setStage(s);
  };

  if (!board) {
    if (error) {
      return (
        <div className="p-4 sm:p-6 lg:p-8 max-w-[1200px]">
          <h1 className="text-2xl font-bold text-slate-900">Works</h1>
          <p className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-700">{error}</p>
        </div>
      );
    }
    return <PageSkeleton />;
  }

  const { desk, stages } = board;
  const byKey: Record<string, Stage> = Object.fromEntries(stages.map(s => [s.key, s]));
  const sideTotal = (side: View) => stages.filter(s => s.side === side).reduce((n, s) => n + s.count, 0);
  // While another tab is on its way the board still holds the old one; it is
  // shown faded rather than passed off as the tab just chosen.
  const stale = loading || board.view !== view;
  const groups = board.groups.filter(g => stage === "all" || g.stage === stage);
  const shownTotal = groups.reduce((n, g) => n + g.count, 0);

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-[1200px]">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Works</h1>
        <p className="text-sm text-slate-500 mt-1">
          Every customer from the site visit to a finished project, by stage. Your stage
          is <b className="font-semibold text-slate-700">{desk.label}</b>.
        </p>
      </div>

      {/* The two halves of the pipeline, either side of the viewer's own stage. */}
      <div className="grid grid-cols-2 gap-3 mb-4" role="tablist" aria-label="Works">
        {([
          ["upcoming", "Upcoming works", `Before ${desk.label}`],
          ["completed", "Completed works", `Past ${desk.label}`],
        ] as const).map(([key, title, sub]) => {
          const on = view === key;
          return (
            <button key={key} type="button" role="tab" aria-selected={on} onClick={() => switchTo(key)}
              className={`text-left rounded-2xl border px-4 py-3 sm:px-5 sm:py-4 transition ${
                on ? "bg-indigo-600 border-indigo-600 shadow-sm" : "bg-white border-slate-200 hover:border-indigo-300"}`}>
              <div className="flex items-baseline justify-between gap-2">
                <span className={`text-sm font-bold ${on ? "text-white" : "text-slate-800"}`}>{title}</span>
                <span className={`text-xl sm:text-2xl font-black ${on ? "text-white" : "text-slate-900"}`}>{sideTotal(key)}</span>
              </div>
              <p className={`text-[11px] mt-0.5 ${on ? "text-indigo-100" : "text-slate-400"}`}>{sub}</p>
            </button>
          );
        })}
      </div>

      {/* The whole pipeline in order. A stage on this side filters the list to
          it; one on the other side switches over to it; the viewer's own stage
          opens their module, where that work actually lives. */}
      <div ref={strip} className="relative mb-5 overflow-x-auto rounded-2xl border border-slate-200 bg-white p-2.5 shadow-sm">
        <ol className="flex min-w-max items-center gap-1.5">
          {stages.map((s, i) => {
            const here = s.side === view;
            const picked = here && stage === s.key;
            return (
              <li key={s.key} className="flex items-center gap-1.5">
                {i > 0 && <span className="text-slate-300 text-sm" aria-hidden="true">›</span>}
                {s.side === "mine" ? (
                  <Link href={desk.module} title={`Your stage. Open ${s.label}`} data-mine
                    className="flex flex-col rounded-xl border-2 border-dashed border-amber-300 bg-amber-50 px-3 py-1.5 hover:bg-amber-100/70 transition">
                    <span className="text-[9px] font-bold uppercase tracking-wide text-amber-700">Your stage ↗</span>
                    <span className="text-xs font-bold text-slate-800 whitespace-nowrap">
                      {s.label} <span className="text-amber-700">{s.count}</span>
                    </span>
                  </Link>
                ) : (
                  <button type="button" aria-pressed={picked}
                    onClick={() => (here ? setStage(picked ? "all" : s.key) : switchTo(s.side as View, s.key))}
                    title={here ? (picked ? "Show every stage" : `Show ${s.label} only`) : `Open ${s.label} in ${s.side} works`}
                    className={`flex flex-col rounded-xl border px-3 py-1.5 text-left transition ${
                      picked ? "bg-indigo-600 border-indigo-600"
                        : here ? "bg-white border-slate-200 hover:border-indigo-300"
                          : "bg-slate-50 border-slate-100 opacity-60 hover:opacity-100"}`}>
                    <span className={`text-[9px] font-bold uppercase tracking-wide ${picked ? "text-indigo-100" : "text-slate-400"}`}>
                      {s.side === "upcoming" ? "Upcoming" : "Completed"}
                    </span>
                    <span className={`text-xs font-bold whitespace-nowrap ${picked ? "text-white" : "text-slate-700"}`}>
                      {s.label} <span className={picked ? "text-indigo-100" : "text-slate-400"}>{s.count}</span>
                    </span>
                  </button>
                )}
              </li>
            );
          })}
        </ol>
      </div>

      <div className="mb-5 flex flex-wrap items-center gap-3">
        <input value={search} onChange={e => setSearch(e.target.value)} type="search"
          placeholder="Search name, phone, place or BDE…" aria-label="Search works"
          className="w-full max-w-md bg-white border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all" />
        {stage !== "all" && byKey[stage] && (
          <button type="button" onClick={() => setStage("all")}
            className="inline-flex items-center gap-1.5 rounded-full bg-indigo-50 px-3 py-1.5 text-xs font-semibold text-indigo-700 hover:bg-indigo-100 transition">
            {byKey[stage].label} only <span aria-hidden="true">✕</span>
            <span className="sr-only">: show every stage</span>
          </button>
        )}
      </div>

      {error && <p className="mb-4 text-sm text-rose-600">{error}</p>}

      <div className={`transition-opacity ${stale ? "opacity-50 pointer-events-none" : ""}`} aria-busy={stale}>
        {shownTotal === 0 ? (
          <div className="bg-white border border-dashed border-slate-200 rounded-2xl p-12 text-center text-sm text-slate-400">
            {board.search
              ? `No customers match "${board.search}" here.`
              : board.view === "upcoming"
                ? `Nothing is on its way to ${desk.label} right now.`
                : `Nothing has passed ${desk.label} yet.`}
          </div>
        ) : (
          <div className="space-y-8">
            {groups.map(g => {
              const s = byKey[g.stage];
              return (
                <section key={g.stage} aria-labelledby={`stage-${g.stage}`}>
                  <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
                    <h2 id={`stage-${g.stage}`} className="text-sm font-bold text-slate-800">
                      {s.label} <span className="ml-1 text-xs font-bold text-slate-400">{g.count}</span>
                    </h2>
                    <p className="text-[11px] text-slate-400">{s.blurb}</p>
                  </div>
                  {g.count === 0 ? (
                    <p className="rounded-2xl border border-dashed border-slate-200 px-5 py-3 text-xs text-slate-400">
                      {board.search ? "No matches in this stage." : "Nobody in this stage right now."}
                    </p>
                  ) : (
                    <div className="space-y-2.5">
                      {g.works.map(w => <WorkRow key={w.id} work={w} stage={s} onOpen={() => setOpen(w)} />)}
                    </div>
                  )}
                  {g.has_more && (
                    <button type="button" onClick={() => showMore(g)} disabled={loadingMore === g.stage}
                      className="mt-3 w-full rounded-xl border border-slate-200 bg-white py-2.5 text-xs font-bold text-indigo-600 hover:bg-indigo-50/60 disabled:opacity-60 transition">
                      {loadingMore === g.stage ? "Loading…" : `Show more (${g.count - g.works.length} more)`}
                    </button>
                  )}
                </section>
              );
            })}
          </div>
        )}
      </div>

      {open && <WorkPanel work={open} stages={stages} onClose={() => setOpen(null)} />}
    </div>
  );
}

function WorkRow({ work: w, stage: s, onOpen }: { work: Work; stage: Stage; onOpen: () => void }) {
  const finished = w.stage === "completed";
  const days = daysSince(w.since);
  const where = [w.place, w.district].filter(Boolean).join(", ");
  return (
    <button type="button" onClick={onOpen}
      className="block w-full text-left bg-white border border-slate-200 rounded-2xl shadow-sm px-4 sm:px-5 py-3.5 hover:bg-slate-50/60 hover:border-indigo-200 transition-colors">
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          {/* Name and tag on one line on a desktop; on a phone they wrap rather
              than crushing the tag. */}
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <p className="text-sm font-bold text-slate-900 truncate">{w.name || "—"}</p>
            <BdeTag name={w.bde_name} />
          </div>
          <p className="text-xs text-slate-500 mt-0.5 truncate">
            {[w.phone || "No phone", where || "No location", w.product].filter(Boolean).join(" · ")}
            {/* The value column is hidden on a phone, so it rides along here. */}
            {Number(w.value) > 0 && <span className="sm:hidden"> · {rupees(w.value)}</span>}
          </p>
          <p className="text-[11px] text-slate-400 mt-0.5">
            {/* At the BDE's stages the tag above already names who has it. */}
            {s.handler_label !== "BDE" && (
              <>{s.handler_label}: <span className="font-semibold text-slate-500">{w.handler_name || "Unassigned"}</span> · </>
            )}
            {finished ? "Finished " : "Here since "}{fmtDay(w.since) || "date not recorded"}
            {!finished && days !== null && ` (${ago(days)})`}
          </p>
        </div>
        <div className="flex items-center gap-4 flex-shrink-0">
          <div className="hidden sm:block text-right">
            <p className="text-[10px] text-slate-400 uppercase tracking-wide">Deal Value</p>
            <p className="text-xs font-semibold text-slate-700">{rupees(w.value)}</p>
          </div>
          <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" className="text-slate-300" aria-hidden="true">
            <polyline points="9 18 15 12 9 6" />
          </svg>
        </div>
      </div>
    </button>
  );
}

/** One customer's road through the pipeline: where they are, and when each
 * stage was reached and by whom. Read-only; the work itself is done in each
 * desk's own module. */
function WorkPanel({ work, stages, onClose }: { work: Work; stages: Stage[]; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const at = stages.findIndex(s => s.key === work.stage);
  // A finished project has nowhere further to go: its last stage is done, not
  // one it is still sitting in.
  const finished = work.stage === "completed";
  const steps: Record<string, Step> = Object.fromEntries(work.journey.map(j => [j.stage, j]));
  const where = [work.place, work.district].filter(Boolean).join(", ");
  const facts: [string, string][] = [
    ["System", work.product || "—"],
    ["Deal value", rupees(work.value)],
    ["BDE", work.bde_name || "—"],
    ["Location", where || "—"],
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-3 sm:p-4" onClick={onClose}>
      <div className="bg-white w-full max-w-lg rounded-2xl shadow-2xl max-h-[90vh] overflow-hidden flex flex-col"
        onClick={e => e.stopPropagation()} role="dialog" aria-modal="true" aria-label={`${work.name}: stages`}>
        <div className="flex items-start justify-between gap-3 px-5 sm:px-6 py-4 border-b border-slate-100 flex-shrink-0">
          <div className="min-w-0">
            <h2 className="text-base font-bold text-slate-900 truncate">{work.name || "—"}</h2>
            <p className="text-[11px] text-slate-400 mt-0.5">{work.phone || "No phone"}</p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close" autoFocus
            className="w-8 h-8 shrink-0 flex items-center justify-center rounded-xl bg-slate-100 text-slate-500 hover:bg-slate-200 transition text-sm">
            ✕
          </button>
        </div>

        <div className="overflow-y-auto flex-1 px-5 sm:px-6 py-5 space-y-6">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
            {facts.map(([label, value]) => (
              <div key={label} className="min-w-0">
                <dt className="text-[10px] font-bold uppercase tracking-wide text-slate-400">{label}</dt>
                <dd className="text-sm font-semibold text-slate-700 break-words">{value}</dd>
              </div>
            ))}
          </dl>

          <div>
            <h3 className="text-[11px] font-bold uppercase tracking-wide text-slate-400 mb-3">Stages</h3>
            <ol>
              {stages.map((s, i) => {
                const state = i < at || (i === at && finished) ? "done" : i === at ? "now" : "ahead";
                const step = steps[s.key];
                const days = state === "now" ? daysSince(step?.on ?? null) : null;
                return (
                  <li key={s.key} className="relative flex gap-3 pb-4 last:pb-0">
                    {/* The line down to the next stage, solid as far as the
                        customer has come. */}
                    {i < stages.length - 1 && (
                      <span aria-hidden="true"
                        className={`absolute left-[9px] top-5 bottom-0 w-0.5 ${i < at ? "bg-emerald-300" : "bg-slate-200"}`} />
                    )}
                    <span aria-hidden="true"
                      className={`relative z-10 mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2 ${
                        state === "done" ? "border-emerald-500 bg-emerald-500 text-white"
                          : state === "now" ? "border-indigo-600 bg-white"
                            : "border-slate-200 bg-white"}`}>
                      {state === "done" && (
                        <svg width="10" height="10" fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12" /></svg>
                      )}
                      {state === "now" && <span className="h-2 w-2 rounded-full bg-indigo-600" />}
                    </span>
                    <div className="min-w-0">
                      <p className={`flex flex-wrap items-center gap-1.5 text-sm font-semibold ${state === "ahead" ? "text-slate-400" : "text-slate-800"}`}>
                        {s.label}
                        {state === "now" && (
                          <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-indigo-700">Now</span>
                        )}
                        {s.side === "mine" && (
                          <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-amber-700">Your stage</span>
                        )}
                      </p>
                      <p className="text-[11px] text-slate-500 mt-0.5">
                        {state === "ahead"
                          ? "Not yet"
                          : [
                              `${s.key === "completed" ? "Finished" : "Reached"} ${fmtDay(step?.on ?? null) || "(date not recorded)"}${days !== null ? ` · ${ago(days)}` : ""}`,
                              step?.by,
                            ].filter(Boolean).join(" · ")}
                      </p>
                    </div>
                  </li>
                );
              })}
            </ol>
          </div>
        </div>
      </div>
    </div>
  );
}

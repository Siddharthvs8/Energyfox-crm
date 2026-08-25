"use client";
/**
 * The customer's own tracking page — the one thing in this app a customer sees.
 *
 * Deliberately outside the (crm) route group, so it inherits no sidebar, no auth
 * guard and no CRM chrome: the link arrives by email and has to open on a phone,
 * in one tap, for someone who has never heard of this CRM.
 *
 * It shows stages and dates and nothing else. Everything internal — money,
 * staff, notes — stays on the other side of the API, which is why the endpoint
 * behind this sends so little.
 */
import { useCallback, useEffect, useState } from "react";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";

type Stage = {
  key: string; title: string; blurb: string;
  done: boolean; current: boolean; on: string | null;
};
type Tracking = {
  customer: string; stages: Stage[]; steps_done: number; steps_total: number;
  complete: boolean; started_on: string | null; last_update: string | null;
};

const prettyDate = (iso: string | null) =>
  iso ? new Date(iso + "T00:00:00").toLocaleDateString("en-IN",
    { day: "numeric", month: "short", year: "numeric" }) : null;

function Logo() {
  return (
    <div className="flex items-center gap-2.5">
      <div className="w-9 h-9 rounded-full bg-amber-400 flex items-center justify-center shadow-sm">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#1e293b"
          strokeWidth="2.5" strokeLinecap="round">
          <circle cx="12" cy="12" r="4.5" />
          <path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.2 5.2l1.4 1.4M17.4 17.4l1.4 1.4M18.8 5.2l-1.4 1.4M6.6 17.4l-1.4 1.4" />
        </svg>
      </div>
      <div className="leading-tight">
        <p className="font-black text-slate-900 text-[15px]">EnergyFox</p>
        <p className="text-[11px] text-slate-400">Installation tracking</p>
      </div>
    </div>
  );
}

/** One step of the journey, as a row on a vertical rail. */
function Step({ stage, last }: { stage: Stage; last: boolean }) {
  const state = stage.done ? "done" : stage.current ? "current" : "todo";
  const dot = {
    done: "bg-emerald-500 border-emerald-500 text-white",
    current: "bg-white border-indigo-500 text-indigo-600",
    todo: "bg-white border-slate-200 text-slate-300",
  }[state];

  return (
    <li className="relative flex gap-4 pb-7 last:pb-0">
      {/* The rail joining the dots. It stops at the last step so the line does
          not dangle past the end of the journey. */}
      {!last && (
        <span aria-hidden="true"
          className={`absolute left-[15px] top-8 bottom-0 w-0.5 rounded ${
            stage.done ? "bg-emerald-500" : "bg-slate-200"}`} />
      )}

      <span className={`relative z-10 flex-shrink-0 w-8 h-8 rounded-full border-2
                        flex items-center justify-center ${dot}`}>
        {stage.done ? (
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
            strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <polyline points="20 6 9 17 4 12" />
          </svg>
        ) : stage.current ? (
          // A soft pulse marks the step being worked on now.
          <span className="w-2.5 h-2.5 rounded-full bg-indigo-500 animate-pulse" />
        ) : (
          <span className="w-2 h-2 rounded-full bg-slate-200" />
        )}
      </span>

      <div className="min-w-0 pt-0.5">
        <div className="flex items-center gap-2 flex-wrap">
          <p className={`text-[15px] font-bold ${
            state === "todo" ? "text-slate-400" : "text-slate-900"}`}>{stage.title}</p>
          {stage.current && (
            <span className="text-[10px] font-black uppercase tracking-wide px-2 py-0.5
                             rounded-full bg-indigo-50 text-indigo-600">In progress</span>
          )}
        </div>
        <p className={`text-[13px] mt-0.5 ${
          state === "todo" ? "text-slate-300" : "text-slate-500"}`}>{stage.blurb}</p>
        {stage.on && (
          <p className="text-[12px] font-semibold text-emerald-600 mt-1">
            {prettyDate(stage.on)}
          </p>
        )}
      </div>
    </li>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <main className="min-h-screen bg-slate-50 px-4 py-8 sm:py-14">
      <div className="mx-auto w-full max-w-xl">{children}</div>
    </main>
  );
}

export default function TrackPage({ params }: { params: Promise<{ token: string }> }) {
  const [data, setData] = useState<Tracking | null>(null);
  const [state, setState] = useState<"loading" | "ok" | "expired" | "missing" | "offline">("loading");

  const load = useCallback(async (token: string) => {
    try {
      const r = await fetch(`${getApiBase(APP_SLUG)}/api/track/${token}/`, { cache: "no-store" });
      if (r.status === 410) { setState("expired"); return; }
      if (!r.ok) { setState("missing"); return; }
      setData(await r.json());
      setState("ok");
    } catch {
      // Told apart from a bad link on purpose: "check your connection" is
      // actionable, "this link is not valid" would be a lie.
      setState("offline");
    }
  }, []);

  useEffect(() => { params.then(p => load(p.token)); }, [params, load]);

  if (state === "loading") {
    return (
      <Shell>
        <div className="animate-pulse space-y-4">
          <div className="h-9 w-40 bg-slate-200 rounded" />
          <div className="h-32 bg-slate-200 rounded-2xl" />
          <div className="h-72 bg-slate-200 rounded-2xl" />
        </div>
      </Shell>
    );
  }

  if (state !== "ok" || !data) {
    const copy = {
      expired: ["This link has expired",
                "Your installation is finished and the tracking page has closed. Call us and we will send you a fresh link."],
      missing: ["We could not find that link",
                "It may have been mistyped or replaced. Please use the most recent link we sent you."],
      offline: ["We could not reach the server",
                "Check your connection and try again."],
    }[state as "expired" | "missing" | "offline"];
    return (
      <Shell>
        <div className="mb-6"><Logo /></div>
        <div className="bg-white rounded-2xl border border-slate-100 px-6 py-12 text-center
                        shadow-[0_4px_24px_rgb(0,0,0,0.04)]">
          <p className="text-lg font-black text-slate-900">{copy[0]}</p>
          <p className="text-sm text-slate-500 mt-2 max-w-sm mx-auto">{copy[1]}</p>
        </div>
      </Shell>
    );
  }

  const pct = Math.round((data.steps_done / Math.max(data.steps_total, 1)) * 100);
  // Which step is being worked on now, by position rather than by count. The
  // last two stages — the subsidy claim and the warranty — run side by side, so
  // the finished ones are no longer a run from the top and counting them would
  // name the wrong step ("step 7 of 7" while step 6 is still open).
  const currentIndex = data.stages.findIndex(s => s.current);
  const stepNumber = currentIndex === -1 ? data.steps_total : currentIndex + 1;

  return (
    <Shell>
      <div className="mb-6"><Logo /></div>

      <section className="bg-white rounded-2xl border border-slate-100 p-6 mb-5
                          shadow-[0_4px_24px_rgb(0,0,0,0.04)]">
        <p className="text-[13px] text-slate-500">Hello {data.customer},</p>
        <h1 className="text-xl font-black text-slate-900 mt-0.5">
          {data.complete ? "Your system is installed" : "Your installation is under way"}
        </h1>

        <div className="mt-4">
          <div className="flex items-baseline justify-between text-[12px] mb-1.5">
            <span className="font-bold text-slate-600">
              Step {stepNumber} of {data.steps_total}
            </span>
            <span className="text-slate-400">{pct}% complete</span>
          </div>
          <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
            <div className={`h-full rounded-full transition-all duration-700 ${
              data.complete ? "bg-emerald-500" : "bg-indigo-500"}`}
              style={{ width: `${Math.max(pct, 3)}%` }} />
          </div>
        </div>

        {data.last_update && (
          <p className="text-[12px] text-slate-400 mt-3">
            Last updated {prettyDate(data.last_update)}
          </p>
        )}
      </section>

      <section className="bg-white rounded-2xl border border-slate-100 p-6
                          shadow-[0_4px_24px_rgb(0,0,0,0.04)]">
        <ol className="list-none">
          {data.stages.map((s, i) => (
            <Step key={s.key} stage={s} last={i === data.stages.length - 1} />
          ))}
        </ol>
      </section>

      <p className="text-center text-[12px] text-slate-400 mt-6">
        This page updates itself as each stage is completed — no need to log in.
      </p>
    </Shell>
  );
}

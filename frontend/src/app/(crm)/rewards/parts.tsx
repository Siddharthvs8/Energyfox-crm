"use client";
/** Rewards — the pieces the player's and the admin's views are built from. */
import React, { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  BoardRow, Climb, Contest, Dashboard, IncentiveDeal, Me, MEDALS, Medal, PodiumRow, ReferralMonth, StatementLine, Tier,
  day, dayMonth, daysBetween, excludePayment, includePayment, inr, mediaSrc, num, pts, roleLabel, short, targetFor,
} from "./lib";

// ─── Small things ────────────────────────────────────────────────────────────
const Svg = ({ children, size = 16, className = "" }: { children: React.ReactNode; size?: number; className?: string }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
    strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">{children}</svg>
);
export const Icon = {
  Gift: (p: { size?: number; className?: string }) => (
    <Svg {...p}><rect x="3" y="8" width="18" height="4" rx="1" /><path d="M12 8v13M19 12v7a2 2 0 01-2 2H7a2 2 0 01-2-2v-7" /><path d="M7.5 8a2.5 2.5 0 010-5C11 3 12 8 12 8s1-5 4.5-5a2.5 2.5 0 010 5" /></Svg>),
  Lock: (p: { size?: number; className?: string }) => (
    <Svg {...p}><rect x="4" y="11" width="16" height="10" rx="2" /><path d="M8 11V7a4 4 0 018 0v4" /></Svg>),
  Check: (p: { size?: number; className?: string }) => (<Svg {...p}><path d="M20 6L9 17l-5-5" /></Svg>),
  Trophy: (p: { size?: number; className?: string }) => (
    <Svg {...p}><path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 01-10 0V4z" /><path d="M17 5h2a2 2 0 010 4h-2M7 5H5a2 2 0 000 4h2" /></Svg>),
  Crown: (p: { size?: number; className?: string }) => (
    <Svg {...p}><path d="M3 7l4.5 4L12 4l4.5 7L21 7l-2 12H5L3 7z" /></Svg>),
  Clock: (p: { size?: number; className?: string }) => (<Svg {...p}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></Svg>),
  Chevron: (p: { size?: number; className?: string }) => (<Svg {...p}><path d="M9 18l6-6-6-6" /></Svg>),
  Spark: (p: { size?: number; className?: string }) => (
    <Svg {...p}><path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3z" /></Svg>),
  Rupee: (p: { size?: number; className?: string }) => (<Svg {...p}><path d="M6 4h12M6 9h12M14 20L6 13h3a4 4 0 000-8" /></Svg>),
};

/** A gold coin. */
export const Coin = ({ size = 18 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
    <circle cx="12" cy="12" r="10" fill="#f59e0b" />
    <circle cx="12" cy="12" r="7.2" fill="#fbbf24" stroke="#d97706" strokeWidth="1.2" />
    <path d="M12 8.2l1.1 2.4 2.6.3-1.9 1.8.5 2.6L12 14l-2.3 1.3.5-2.6-1.9-1.8 2.6-.3L12 8.2z" fill="#b45309" />
  </svg>
);

const AVATARS = [
  "from-indigo-500 to-violet-500", "from-sky-500 to-cyan-500", "from-emerald-500 to-teal-500",
  "from-rose-500 to-pink-500", "from-amber-500 to-orange-500", "from-fuchsia-500 to-purple-500",
];
export function Avatar({ initials, id, size = 36, medal }: { initials: string; id: number | null; size?: number; medal?: Medal | "" }) {
  const tone = AVATARS[Math.abs(id || 0) % AVATARS.length];
  const face = (
    <span className={`inline-flex items-center justify-center rounded-full bg-gradient-to-br ${tone} text-white font-bold shrink-0`}
      style={{ width: size, height: size, fontSize: Math.max(10, size * 0.36) }}>{initials}</span>
  );
  if (!medal) return face;
  return (
    <span className={`inline-flex rounded-full p-[3px] bg-gradient-to-br ${MEDALS[medal].ring} shrink-0`}>
      <span className="rounded-full bg-white p-[2px] inline-flex">{face}</span>
    </span>
  );
}

/** Counts up to `value` the first time it is shown — the number arriving is part of the moment. */
export function CountUp({ value, format = pts }: { value: number; format?: (v: number) => string }) {
  const [shown, setShown] = useState(0);
  const from = useRef(0);
  useEffect(() => {
    const start = performance.now(), begin = from.current, change = value - begin, ms = 900;
    let frame = 0;
    const tick = (now: number) => {
      const t = Math.min((now - start) / ms, 1);
      const eased = 1 - Math.pow(1 - t, 3);
      setShown(begin + change * eased);
      if (t < 1) frame = requestAnimationFrame(tick);
      else from.current = value;
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [value]);
  return <span className="tabular-nums">{format(shown)}</span>;
}

function Bar({ value, className = "bg-indigo-500", track = "bg-slate-100", label }: { value: number; className?: string; track?: string; label?: string }) {
  const pct = Math.max(0, Math.min(100, Math.round(value * 100)));
  return (
    <div className={`h-2 w-full rounded-full ${track} overflow-hidden`} role="progressbar"
      aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
      <div className={`h-full rounded-full ${className} transition-[width] duration-1000 ease-out`} style={{ width: `${pct}%` }} />
    </div>
  );
}

export function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <section className={`bg-white border border-slate-200 rounded-3xl shadow-sm ${className}`}>{children}</section>;
}

export function CardHeader({ title, subtitle, right, icon }: { title: string; subtitle?: string; right?: React.ReactNode; icon?: React.ReactNode }) {
  return (
    <header className="flex items-start justify-between gap-3">
      <div className="flex items-start gap-3 min-w-0">
        {icon && <span className="mt-0.5 inline-flex h-9 w-9 items-center justify-center rounded-xl bg-slate-100 text-slate-600 shrink-0">{icon}</span>}
        <div className="min-w-0">
          <h2 className="text-[15px] font-bold text-slate-900">{title}</h2>
          {subtitle && <p className="text-xs text-slate-500 mt-0.5">{subtitle}</p>}
        </div>
      </div>
      {right}
    </header>
  );
}

// ─── The hero ────────────────────────────────────────────────────────────────
export function Hero({ me, month, preview }: { me: Me; month: Dashboard["month"]; preview?: boolean }) {
  const climb = me.tier;
  const first = me.name.split(" ")[0];
  const topped = climb.of > 0 && !climb.next;
  const headline = preview ? `${me.name}'s month`
    : topped ? `Every tier unlocked, ${first}!`
      : num(me.points) > 0 ? `Keep climbing, ${first}` : `Your climb starts here, ${first}`;
  return (
    <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-indigo-600 via-violet-600 to-fuchsia-600 text-white shadow-lg shadow-indigo-200/50">
      <div aria-hidden="true" className="absolute -right-16 -top-20 h-64 w-64 rounded-full bg-white/10 blur-2xl" />
      <div aria-hidden="true" className="absolute -bottom-24 left-1/3 h-56 w-56 rounded-full bg-fuchsia-300/20 blur-3xl" />
      <div className="relative p-5 sm:p-8 grid gap-6 lg:grid-cols-[1fr_auto] lg:items-end">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-white/75">
            <span>{month.label}</span>
            <span className="inline-flex items-center gap-1 rounded-full bg-white/15 px-2 py-0.5 normal-case tracking-normal text-white">
              <Icon.Clock size={12} /> {month.days_left} {month.days_left === 1 ? "day" : "days"} left
            </span>
          </div>
          <h1 className="mt-2 text-lg sm:text-xl font-semibold">{headline}</h1>
          <div className="mt-3 flex items-end gap-2">
            <span className="text-4xl sm:text-6xl font-black leading-none tracking-tight"><CountUp value={num(me.points)} /></span>
            <span className="pb-1 text-sm font-semibold text-white/75">points</span>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-white px-3 py-1 text-xs font-bold text-indigo-700 shadow-sm">
              <Icon.Crown size={13} /> {climb.current ? climb.current.name : "No tier yet"}
            </span>
            <span className="text-xs text-white/80">{climb.reached} of {climb.of} tiers unlocked · {me.deals} {me.deals === 1 ? "deal" : "deals"} paid this month</span>
          </div>
          <div className="mt-5 max-w-xl">
            {climb.of === 0 ? (
              <p className="text-sm text-white/85">The tiers for this month are being set up.</p>
            ) : topped ? (
              <p className="text-sm font-semibold">🎉 You've reached the top of the ladder this month.</p>
            ) : (
              <>
                <div className="flex items-baseline justify-between gap-3 text-sm">
                  <span className="font-semibold"><b className="text-white">{pts(climb.needed)}</b> pts to <b>{climb.next?.name}</b></span>
                  <span className="text-white/75 tabular-nums">{Math.round(climb.progress * 100)}%</span>
                </div>
                <div className="mt-2"><Bar value={climb.progress} className="bg-white" track="bg-white/20" label={`Progress to ${climb.next?.name}`} /></div>
                {climb.next?.reward && (
                  <p className="mt-2 text-xs text-white/85 inline-flex items-center gap-1.5">
                    {climb.next.reward_type === "cash" ? <Icon.Rupee size={13} /> : <Icon.Gift size={13} />} Unlocks {climb.next.reward}
                  </p>
                )}
              </>
            )}
          </div>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 sm:gap-3 lg:w-[520px]">
          <HeroStat label="Rank" value={<>#{me.rank}</>} sub={`of ${me.of}`} />
          <HeroStat label="Coins" value={<span className="inline-flex items-center gap-1.5"><Coin size={20} />{me.coins}</span>} sub="this season" />
          <HeroStat label="Incentives" value={<CountUp value={num(me.incentives.total)} format={v => short(v)} />} sub="₹ this month" />
          <HeroStat label="Referrals" value={<CountUp value={num(me.referrals?.total)} format={v => short(v)} />} sub="₹ this month" />
        </div>
      </div>
    </section>
  );
}

function HeroStat({ label, value, sub }: { label: string; value: React.ReactNode; sub: string }) {
  return (
    <div className="rounded-2xl bg-white/10 backdrop-blur px-3 py-3 sm:px-4 sm:py-4 ring-1 ring-white/15">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-white/70">{label}</p>
      <p className="mt-1 text-xl sm:text-2xl font-black leading-tight">{value}</p>
      <p className="text-[11px] text-white/70">{sub}</p>
    </div>
  );
}

// ─── The ladder ──────────────────────────────────────────────────────────────
export function TierLadder({ tiers, climb, role, points }: { tiers: Tier[]; climb: Climb; role: string; points: string }) {
  if (tiers.length === 0) {
    return (
      <Card className="p-6 text-center">
        <p className="text-sm font-semibold text-slate-700">No tiers yet</p>
        <p className="text-xs text-slate-500 mt-1">The admins are setting up this month's rewards.</p>
      </Card>
    );
  }
  return (
    <Card className="p-5 sm:p-6">
      <CardHeader title="This month's ladder" subtitle="Reach a tier to unlock its reward. The ladder starts again on the 1st."
        icon={<Icon.Gift />}
        right={<span className="text-xs font-semibold text-slate-500 whitespace-nowrap">{climb.reached}/{climb.of} unlocked</span>} />
      <ol className="mt-5 flex gap-3 overflow-x-auto snap-x snap-mandatory pb-1 -mx-1 px-1">
        {tiers.map((t, i) => {
          const target = num(targetFor(t, role));
          const reached = i < climb.reached;
          const next = i === climb.reached;
          const pct = target > 0 ? Math.min(num(points) / target, 1) : 0;
          return (
            <li key={t.id} className={`snap-start shrink-0 w-[200px] sm:w-auto sm:flex-1 sm:min-w-[170px] rounded-2xl border p-4 transition ${
              reached ? "border-emerald-200 bg-emerald-50/70"
                : next ? "border-indigo-300 bg-indigo-50/60 ring-2 ring-indigo-100"
                  : "border-slate-200 bg-slate-50/60"}`}>
              <div className="flex items-center justify-between gap-2">
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Tier {i + 1}</span>
                {reached ? (
                  <span className="inline-flex items-center gap-1 rounded-full bg-emerald-600 px-2 py-0.5 text-[10px] font-bold text-white"><Icon.Check size={11} /> Unlocked</span>
                ) : next ? (
                  <span className="rounded-full bg-indigo-600 px-2 py-0.5 text-[10px] font-bold text-white">Next · {Math.round(pct * 100)}%</span>
                ) : (
                  <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-slate-400"><Icon.Lock size={11} /> Locked</span>
                )}
              </div>
              <p className={`mt-2 text-base font-bold ${reached ? "text-emerald-800" : next ? "text-indigo-900" : "text-slate-700"}`}>{t.name}</p>
              <p className="text-xs text-slate-500 tabular-nums">{pts(target)} pts</p>
              {next && <div className="mt-2"><Bar value={pct} label={`Progress to ${t.name}`} /></div>}
              <TierReward tier={t} state={reached ? "reached" : next ? "next" : "locked"} />
            </li>
          );
        })}
      </ol>
    </Card>
  );
}

/** What a rung pays: cash as an amount, a gift by name and — when the admins
 *  added one — its picture, greyed out until the tier is within reach. */
function TierReward({ tier, state }: { tier: Tier; state: "reached" | "next" | "locked" }) {
  if (!tier.reward) return null;
  if (tier.reward_type === "cash") {
    return (
      <p className={`mt-3 inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-bold tabular-nums ${
        state === "reached" ? "bg-emerald-600 text-white" : "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200"}`}>
        <Icon.Rupee size={12} /> {inr(tier.reward_amount)} cash
      </p>
    );
  }
  return (
    <div className="mt-3">
      {tier.image && (
        <div className="relative overflow-hidden rounded-xl bg-slate-100 ring-1 ring-slate-200/70">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={mediaSrc(tier.image)} alt={tier.reward} loading="lazy"
            className={`h-24 w-full object-cover transition duration-500 ${state === "locked" ? "grayscale opacity-60" : ""}`} />
          {state === "locked" && (
            <span className="absolute inset-0 flex items-center justify-center">
              <span className="rounded-full bg-white/90 p-1.5 text-slate-500 shadow-sm"><Icon.Lock size={14} /></span>
            </span>
          )}
        </div>
      )}
      <p className={`mt-2 flex items-start gap-1.5 text-xs font-medium ${state === "reached" ? "text-emerald-700" : "text-slate-600"}`}>
        <Icon.Gift size={13} className="mt-0.5 shrink-0" /><span>{tier.reward}</span>
      </p>
    </div>
  );
}

// ─── The table ───────────────────────────────────────────────────────────────
export function RankBadge({ rank, points }: { rank: number; points: string | number }) {
  const medal: Medal | null = num(points) > 0 && rank <= 3 ? (["gold", "silver", "bronze"] as Medal[])[rank - 1] : null;
  if (medal) {
    return <span className={`inline-flex h-8 w-8 items-center justify-center rounded-full ${MEDALS[medal].soft} text-base`} title={MEDALS[medal].label}>{MEDALS[medal].emoji}</span>;
  }
  return <span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-slate-100 text-xs font-bold text-slate-500 tabular-nums">{rank}</span>;
}

export function Leaderboard({ rows, title, subtitle, onOpen, showMoney, limit }: {
  rows: BoardRow[]; title: string; subtitle?: string; onOpen?: (user: number) => void; showMoney?: boolean; limit?: number;
}) {
  const [all, setAll] = useState(false);
  const leader = Math.max(...rows.map(r => num(r.points)), 1);
  const visible = limit && !all ? rows.slice(0, limit) : rows;
  const meHidden = limit && !all ? rows.find(r => r.is_me && r.rank > limit) : undefined;
  const Row = ({ r }: { r: BoardRow }) => {
    const body = (
      <div className={`grid grid-cols-[auto_auto_1fr_auto] items-center gap-3 px-3 sm:px-4 py-3 rounded-2xl transition ${
        r.is_me ? "bg-indigo-50 ring-1 ring-indigo-200" : r.is_subject ? "bg-violet-50 ring-1 ring-violet-200" : "hover:bg-slate-50"}`}>
        <RankBadge rank={r.rank} points={r.points} />
        <Avatar initials={r.initials} id={r.user} size={36} />
        <div className="min-w-0">
          <div className="flex items-center gap-1.5 min-w-0">
            <span className="text-sm font-semibold text-slate-900 truncate">{r.name}</span>
            {r.is_me && <span className="rounded-full bg-indigo-600 px-1.5 py-0.5 text-[9px] font-bold uppercase text-white">You</span>}
          </div>
          {/* Wraps between pieces, never inside one, so "Tele caller" stays whole on a phone. */}
          <div className="mt-0.5 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-[11px] text-slate-500 min-w-0">
            <span className="whitespace-nowrap">{roleLabel(r.role)}</span>
            {r.tier && <><span aria-hidden="true">·</span><span className="inline-flex items-center gap-0.5 whitespace-nowrap font-semibold text-violet-700"><Icon.Crown size={11} />{r.tier}</span></>}
            <span aria-hidden="true">·</span><span className="whitespace-nowrap">{r.deals} {r.deals === 1 ? "deal" : "deals"}</span>
          </div>
          <div className="mt-1.5 max-w-[260px]"><Bar value={num(r.points) / leader} className={r.is_me ? "bg-indigo-500" : "bg-slate-300"} label={`${r.name}'s points`} /></div>
        </div>
        <div className="text-right">
          <p className="text-sm font-bold text-slate-900 tabular-nums">{pts(r.points)}</p>
          <p className="text-[10px] text-slate-400">points</p>
          {showMoney && r.incentives !== undefined && num(r.incentives) > 0 && (
            <p className="text-[10px] font-semibold text-emerald-600 tabular-nums">{inr(r.incentives)} inc.</p>
          )}
          {showMoney && r.referrals !== undefined && num(r.referrals) > 0 && (
            <p className="text-[10px] font-semibold text-purple-600 tabular-nums">{inr(r.referrals)} ref.</p>
          )}
        </div>
      </div>
    );
    return onOpen ? (
      <li><button type="button" onClick={() => onOpen(r.user)} className="block w-full text-left" aria-label={`Open ${r.name}'s rewards`}>{body}</button></li>
    ) : <li>{body}</li>;
  };
  return (
    <Card className="p-4 sm:p-5">
      <div className="px-1"><CardHeader title={title} subtitle={subtitle} icon={<Icon.Trophy />} /></div>
      {rows.length === 0 ? (
        <p className="mt-6 mb-2 text-center text-sm text-slate-400">Nobody on the sales team yet.</p>
      ) : (
        <ol className="mt-3 space-y-1">
          {visible.map(r => <Row key={r.user} r={r} />)}
          {meHidden && <><li aria-hidden="true" className="text-center text-slate-300 text-xs">⋯</li><Row r={meHidden} /></>}
        </ol>
      )}
      {limit && rows.length > limit && (
        <button type="button" onClick={() => setAll(v => !v)} className="mt-2 w-full rounded-xl py-2 text-xs font-semibold text-indigo-600 hover:bg-indigo-50">
          {all ? "Show the top only" : `Show all ${rows.length}`}
        </button>
      )}
    </Card>
  );
}

// ─── The podium ──────────────────────────────────────────────────────────────
export function Podium({ title, label, podium }: { title: string; label?: string; podium: PodiumRow[] }) {
  const byMedal = (m: Medal) => podium.find(p => p.medal === m);
  const steps: { medal: Medal; height: string }[] = [
    { medal: "silver", height: "h-14" }, { medal: "gold", height: "h-20" }, { medal: "bronze", height: "h-10" },
  ];
  return (
    <Card className="p-5">
      <CardHeader title={title} subtitle={label} icon={<span className="text-base">🏆</span>} />
      {podium.length === 0 ? (
        <p className="mt-5 text-center text-sm text-slate-400">The first champions are announced when this month ends.</p>
      ) : (
        <div className="mt-5 grid grid-cols-3 items-end gap-2">
          {steps.map(({ medal, height }) => {
            const p = byMedal(medal);
            return (
              <div key={medal} className="flex flex-col items-center text-center min-w-0">
                {p ? (
                  <>
                    <span className="text-xl" aria-label={MEDALS[medal].label}>{MEDALS[medal].emoji}</span>
                    <div className="mt-1"><Avatar initials={p.initials} id={p.user} size={medal === "gold" ? 52 : 42} medal={medal} /></div>
                    <p className="mt-1.5 w-full truncate text-xs font-bold text-slate-900" title={p.name}>{p.name}</p>
                    <p className="text-[11px] text-slate-500 tabular-nums">{short(p.points)} pts</p>
                    {p.prize && <p className={`mt-1 w-full truncate text-[10px] font-semibold ${MEDALS[medal].text}`} title={p.prize}>🎁 {p.prize}</p>}
                    {p.coins > 0 && <p className="mt-0.5 inline-flex items-center gap-0.5 text-[10px] font-bold text-amber-700"><Coin size={11} />+{p.coins}</p>}
                  </>
                ) : <p className="text-[11px] text-slate-300 mb-2">—</p>}
                <div className={`mt-2 w-full rounded-t-xl bg-gradient-to-b ${MEDALS[medal].ring} ${height} flex items-start justify-center pt-1.5 text-sm font-black text-white/90`}>
                  {medal === "gold" ? 1 : medal === "silver" ? 2 : 3}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}

// ─── Incentives ──────────────────────────────────────────────────────────────
export function IncentivesCard({ incentives, preview }: { incentives: { total: string; deals: IncentiveDeal[] }; preview?: boolean }) {
  return (
    <Card className="p-5">
      <CardHeader title="Incentives this month" subtitle="Paid per project when a customer finishes paying." icon={<Icon.Rupee />} />
      <p className="mt-4 text-3xl font-black text-emerald-600"><CountUp value={num(incentives.total)} format={v => inr(v)} /></p>
      {incentives.deals.length === 0 ? (
        <p className="mt-2 text-xs text-slate-500">{preview ? "No incentives earned yet this month." : "Close a deal on a project with an incentive and it lands here the day your customer pays in full."}</p>
      ) : (
        <ul className="mt-3 divide-y divide-slate-100">
          {incentives.deals.map(d => (
            <li key={`${d.lead}-${d.as}`} className="flex items-center justify-between gap-3 py-2.5">
              <div className="min-w-0">
                <p className="text-sm font-semibold text-slate-800 truncate">{d.customer}</p>
                <p className="text-[11px] text-slate-500 truncate">{d.project} · as {roleLabel(d.as)} · paid in full {day(d.paid_on)}</p>
              </div>
              <span className="text-sm font-bold text-emerald-600 tabular-nums">{inr(d.amount)}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

// ─── Referral rewards ────────────────────────────────────────────────────────
/** A person's own referral rewards this month. Shown even when empty, so the
 *  sales team knows referring a customer pays too. */
export function MyReferralsCard({ referrals, preview }: { referrals: { total: string; deals: IncentiveDeal[] }; preview?: boolean }) {
  return (
    <Card className="p-5">
      <CardHeader title="Referral rewards this month" subtitle="For customers you referred who finished paying." icon={<Icon.Gift />} />
      <p className="mt-4 text-3xl font-black text-purple-600"><CountUp value={num(referrals.total)} format={v => inr(v)} /></p>
      {referrals.deals.length === 0 ? (
        <p className="mt-2 text-xs text-slate-500">{preview ? "No referral rewards earned yet this month." : "Refer a customer: when they buy and finish paying, the project's referral reward lands here."}</p>
      ) : (
        <ul className="mt-3 divide-y divide-slate-100">
          {referrals.deals.map(d => (
            <li key={d.lead} className="flex items-center justify-between gap-3 py-2.5">
              <div className="min-w-0">
                <p className="text-sm font-semibold text-slate-800 truncate">{d.customer}</p>
                <p className="text-[11px] text-slate-500 truncate">{d.project} · paid in full {day(d.paid_on)}</p>
              </div>
              <span className="text-sm font-bold text-purple-600 tabular-nums">{inr(d.amount)}</span>
            </li>
          ))}
        </ul>
      )}
      {!preview && (
        <Link href="/referral-rewards" className="mt-3 inline-block text-xs font-semibold text-purple-700 hover:text-purple-900">
          See every customer you referred →
        </Link>
      )}
    </Card>
  );
}

/** One month's referral rewards, person by person, each with the deals that
 *  earned them. Shared by the Rewards page and the Referral Rewards page. */
export function ReferralPeople({ month }: { month: ReferralMonth }) {
  if (month.people.length === 0) {
    return <p className="mt-2 text-xs text-slate-500">No referral rewards earned in {month.label}.</p>;
  }
  return (
    <ul className="mt-3 divide-y divide-slate-100">
      {month.people.map(p => (
        <li key={p.user} className="py-3">
          <div className="flex items-center justify-between gap-3">
            <p className="min-w-0 truncate text-sm font-semibold text-slate-800">
              {p.name} <span className="ml-1 text-[11px] font-medium text-slate-400">{p.role}</span>
            </p>
            <span className="text-sm font-bold text-purple-600 tabular-nums">{inr(p.total)}</span>
          </div>
          <ul className="mt-1 space-y-0.5">
            {p.deals.map(d => (
              <li key={d.lead} className="flex items-center justify-between gap-3 text-[11px] text-slate-500">
                <span className="min-w-0 truncate">{d.customer} · {d.project} · paid in full {day(d.paid_on)}</span>
                <span className="tabular-nums">{inr(d.amount)}</span>
              </li>
            ))}
          </ul>
        </li>
      ))}
    </ul>
  );
}

/** Everyone owed a referral reward, whatever their role, for the admins who
 *  pay them. Last month sits beside this one because rewards are paid after a
 *  month ends — by then this month's list has started again from nothing. */
export function ReferralRewardsCard({ months }: { months: { this_month: ReferralMonth; last_month: ReferralMonth } }) {
  const [which, setWhich] = useState<"this_month" | "last_month">("this_month");
  const month = months[which];
  return (
    <Card className="p-5">
      <CardHeader title="Referral rewards"
        subtitle="Owed to the staff member who referred each customer, once the customer finishes paying."
        icon={<Icon.Gift />} />
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <p className="text-3xl font-black text-purple-600 tabular-nums">{inr(month.total)}</p>
        <div className="inline-flex rounded-xl bg-slate-100 p-1" role="tablist" aria-label="Month">
          {(["this_month", "last_month"] as const).map(key => (
            <button key={key} type="button" role="tab" aria-selected={which === key} onClick={() => setWhich(key)}
              className={`rounded-lg px-3 py-1 text-xs font-semibold transition ${which === key ? "bg-white text-purple-700 shadow-sm" : "text-slate-500 hover:text-slate-800"}`}>
              {months[key].label}
            </button>
          ))}
        </div>
      </div>
      <ReferralPeople month={month} />
      <Link href="/referral-rewards" className="mt-3 inline-block text-xs font-semibold text-purple-700 hover:text-purple-900">
        Earlier months on the Referral Rewards page →
      </Link>
    </Card>
  );
}

// ─── Where the points came from ──────────────────────────────────────────────
const TAKE_OUT_REASONS = ["Paid before this month, verified late", "Not this person's deal", "Entered by mistake"];

/** Every payment behind someone's points this month, newest first. An admin
 *  can take one out of the game, with a reason the player sees, or count it
 *  again. */
export function PointsStatement({ lines, total, monthLabel, admin, onChanged, limit }: {
  lines: StatementLine[]; total: string; monthLabel: string;
  admin?: boolean; onChanged?: () => void; limit?: number;
}) {
  const [all, setAll] = useState(false);
  const counted = lines.filter(l => l.status === "counted").length;
  const visible = limit && !all ? lines.slice(0, limit) : lines;
  return (
    <Card className="p-4 sm:p-5">
      <div className="px-1">
        <CardHeader title="Where the points came from"
          subtitle={`Every payment in ${monthLabel}: money received × share.`}
          icon={<Icon.Rupee />}
          right={
            <div className="shrink-0 text-right">
              <p className="text-sm font-black text-slate-900 tabular-nums">{pts(total)}</p>
              <p className="whitespace-nowrap text-[10px] text-slate-400">from {counted} {counted === 1 ? "payment" : "payments"}</p>
            </div>
          } />
      </div>
      {lines.length === 0 ? (
        <p className="mt-5 mb-2 px-1 text-center text-sm text-slate-400">No payments yet this month. Points arrive the day accounts verify a customer&apos;s money.</p>
      ) : (
        <ol className="mt-3 divide-y divide-slate-100">
          {visible.map(l => <StatementRow key={l.key} line={l} admin={admin} onChanged={onChanged} />)}
        </ol>
      )}
      {limit && lines.length > limit && (
        <button type="button" onClick={() => setAll(v => !v)} className="mt-2 w-full rounded-xl py-2 text-xs font-semibold text-indigo-600 hover:bg-indigo-50">
          {all ? "Show the latest only" : `Show all ${lines.length} payments`}
        </button>
      )}
    </Card>
  );
}

function StatementRow({ line: l, admin, onChanged }: { line: StatementLine; admin?: boolean; onChanged?: () => void }) {
  const [asking, setAsking] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const counted = l.status === "counted";
  // A PO signed in an earlier month than the payment counts in: often money
  // paid back then and verified late — worth an admin's second look.
  const lateBy = l.kind === "first" && l.po_signed && l.po_signed.slice(0, 7) < l.on.slice(0, 7)
    ? daysBetween(l.po_signed, l.on) : 0;
  const dealValue = num(l.deal_value);
  const on = new Date(`${l.on}T00:00:00`);

  const takeOut = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!reason.trim() || busy) return;
    setBusy(true); setError("");
    const r = await excludePayment(l.key, reason.trim());
    setBusy(false);
    if (r.ok) { setAsking(false); setReason(""); onChanged?.(); } else setError(r.error || "");
  };
  const putBack = async () => {
    setBusy(true); setError("");
    const r = await includePayment(l.key);
    setBusy(false);
    if (r.ok) onChanged?.(); else setError(r.error || "");
  };

  return (
    <li className="px-1 py-3">
      <div className="grid grid-cols-[auto_1fr_auto] items-start gap-3">
        <span className="flex w-11 flex-col items-center rounded-xl bg-slate-50 py-1.5 ring-1 ring-slate-100" title={day(l.on)}>
          <span className="text-sm font-black leading-none text-slate-800">{on.getDate()}</span>
          <span className="mt-0.5 text-[10px] font-semibold uppercase text-slate-400">{on.toLocaleDateString("en-IN", { month: "short" })}</span>
        </span>
        <div className="min-w-0">
          <Link href={admin ? `/accounts/${l.lead}` : `/leads/${l.lead}`}
            className="block truncate text-sm font-semibold text-slate-900 hover:text-indigo-600">{l.customer}</Link>
          <p className="mt-0.5 text-[11px] text-slate-600">
            {l.kind === "first" ? "First payment" : "Balance payment"} <b className="font-semibold text-slate-800">{inr(l.amount)}</b>
            {dealValue > 0 && <> of a {inr(dealValue)} deal</>}
            {" · "}{Math.round(num(l.share))}%{l.partner ? `, shared with ${l.partner}` : l.as === "bde" ? ", sold alone" : ""}
          </p>
          <p className="mt-0.5 text-[11px] text-slate-400">
            {[
              l.receipt && `Receipt ${l.receipt}`,
              l.by && `${l.kind === "first" ? "verified" : "recorded"} by ${l.by}`,
              l.booked && `verified again ${dayMonth(l.booked)}`,
              l.receipt_amount && `receipt printed for ${inr(l.receipt_amount)}`,
            ].filter(Boolean).join(" · ")}
          </p>
          {l.kind === "first" && l.po_signed && (lateBy > 0 && admin ? (
            <p className="mt-1 inline-flex rounded-md bg-amber-50 px-1.5 py-0.5 text-[11px] font-medium text-amber-800 ring-1 ring-amber-200">
              PO signed {dayMonth(l.po_signed)}, verified {lateBy} days later
            </p>
          ) : (
            <p className="mt-0.5 text-[11px] text-slate-400">PO signed {dayMonth(l.po_signed)}</p>
          ))}
          {!counted && (
            <p className="mt-1 text-[11px] font-medium text-rose-600">
              Not counted: {l.reason}{l.excluded_by ? ` (${l.excluded_by}${l.excluded_on ? `, ${dayMonth(l.excluded_on)}` : ""})` : ""}
            </p>
          )}
        </div>
        <div className="text-right">
          <p className={`text-sm font-bold tabular-nums ${counted ? "text-emerald-600" : "text-slate-400 line-through"}`}>+{pts(l.points)}</p>
          <p className="text-[10px] text-slate-400">points</p>
          {admin && counted && !asking && (
            <button type="button" onClick={() => setAsking(true)} className="mt-1 whitespace-nowrap text-[11px] font-semibold text-rose-600 hover:underline">Don&apos;t count</button>
          )}
          {admin && l.status === "excluded" && (
            <button type="button" onClick={putBack} disabled={busy} className="mt-1 whitespace-nowrap text-[11px] font-semibold text-indigo-600 hover:underline disabled:opacity-50">
              {busy ? "Counting…" : "Count again"}
            </button>
          )}
        </div>
      </div>
      {asking && (
        <form onSubmit={takeOut} className="animate-fade-in-up mt-3 rounded-2xl bg-rose-50/70 p-3 ring-1 ring-rose-100 sm:ml-14">
          <label htmlFor={`why-${l.key}`} className="text-xs font-semibold text-slate-800">Why shouldn&apos;t this payment count?</label>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {TAKE_OUT_REASONS.map(r => (
              <button key={r} type="button" onClick={() => setReason(r)}
                className={`rounded-full px-2.5 py-1 text-[11px] font-medium ring-1 transition ${reason === r ? "bg-rose-600 text-white ring-rose-600" : "bg-white text-slate-600 ring-slate-200 hover:ring-rose-300"}`}>
                {r}
              </button>
            ))}
          </div>
          <input id={`why-${l.key}`} value={reason} onChange={e => setReason(e.target.value)} maxLength={200} autoFocus
            placeholder="Or write your own reason"
            className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 focus:border-rose-300 focus:outline-none focus:ring-2 focus:ring-rose-100" />
          <p className="mt-1.5 text-[11px] text-slate-500">The payment stays as it is in accounts; only the game stops counting it. The player sees your reason.</p>
          {error && <p className="mt-1 text-[11px] font-medium text-rose-600">{error}</p>}
          <div className="mt-2 flex gap-2">
            <button type="submit" disabled={!reason.trim() || busy}
              className="rounded-xl bg-rose-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-rose-700 disabled:opacity-50">
              {busy ? "Taking it out…" : "Take it out"}
            </button>
            <button type="button" onClick={() => { setAsking(false); setError(""); }}
              className="rounded-xl px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-white">Cancel</button>
          </div>
        </form>
      )}
      {!asking && error && <p className="mt-1 text-right text-[11px] font-medium text-rose-600">{error}</p>}
    </li>
  );
}

// ─── The rewards cabinet ─────────────────────────────────────────────────────
export function Cabinet({ me, tiers }: { me: Me; tiers: Tier[] }) {
  // The ladder climbs, so the rungs reached are the first ones.
  const unlocked = tiers.slice(0, me.tier.reached).filter(t => t.reward);
  return (
    <Card className="p-5">
      <CardHeader title="Your rewards" subtitle={`${me.rewards_total} won in all`} icon={<Icon.Spark />} />
      <p className="mt-4 text-[11px] font-bold uppercase tracking-wider text-slate-400">Unlocked this month</p>
      {unlocked.length === 0 ? (
        <p className="mt-1.5 text-xs text-slate-500">Reach your first tier to unlock a reward.</p>
      ) : (
        <ul className="mt-2 flex flex-wrap gap-1.5">
          {unlocked.map(t => (
            <li key={t.id} className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 py-1 pl-1.5 pr-2.5 text-xs font-semibold text-emerald-700 ring-1 ring-emerald-200">
              {t.reward_type === "cash" ? <Icon.Rupee size={12} />
                : t.image
                  // eslint-disable-next-line @next/next/no-img-element
                  ? <img src={mediaSrc(t.image)} alt="" className="h-5 w-5 rounded-full object-cover" />
                  : <Icon.Gift size={12} />}
              {t.reward}
            </li>
          ))}
        </ul>
      )}
      {(me.history.length > 0 || me.contest_wins.length > 0) && (
        <>
          <p className="mt-5 text-[11px] font-bold uppercase tracking-wider text-slate-400">Won before</p>
          <ul className="mt-2 space-y-2">
            {me.contest_wins.map((w, i) => (
              <li key={`c${i}`} className="rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-900 ring-1 ring-amber-200">
                <b>{w.coin_champion ? "Coin champion" : `#${w.rank}`}</b> in {w.contest || "the contest"}{w.prize ? ` — ${w.prize}` : ""}
              </li>
            ))}
            {me.history.slice(0, 6).map(h => (
              <li key={h.key} className="rounded-xl bg-slate-50 px-3 py-2 text-xs text-slate-600">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-semibold text-slate-800">{h.label}</span>
                  {h.medal && <span className={`font-bold ${MEDALS[h.medal].text}`}>{MEDALS[h.medal].emoji} {MEDALS[h.medal].label}</span>}
                </div>
                {(h.prize || h.coins > 0) && (
                  <p className="mt-0.5">{h.prize}{h.prize && h.coins > 0 ? " · " : ""}{h.coins > 0 && <span className="inline-flex items-center gap-0.5 font-semibold text-amber-700"><Coin size={10} />+{h.coins}</span>}</p>
                )}
                {h.rewards.length > 0 && <p className="mt-0.5 text-slate-500">Tier rewards: {h.rewards.join(", ")}</p>}
              </li>
            ))}
          </ul>
        </>
      )}
    </Card>
  );
}

// ─── The contest ─────────────────────────────────────────────────────────────
export function ContestCard({ contest }: { contest: Contest }) {
  const chip = contest.status === "running" ? `${contest.days_left} ${contest.days_left === 1 ? "day" : "days"} left`
    : contest.status === "upcoming" ? `Starts in ${contest.starts_in} ${contest.starts_in === 1 ? "day" : "days"}`
      : contest.status === "awarded" ? "Winners announced" : "Finished — winners on the 1st";
  const medals: Medal[] = ["gold", "silver", "bronze"];
  return (
    <section className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm">
      <div className="relative bg-gradient-to-br from-slate-900 via-indigo-950 to-violet-900 px-5 sm:px-6 py-5 text-white">
        <div aria-hidden="true" className="absolute right-4 top-2 text-6xl opacity-10 select-none">🏆</div>
        <div className="relative flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-indigo-200">Yearly contest</p>
            <h2 className="mt-1 text-xl font-black">{contest.name}</h2>
            <p className="text-xs text-indigo-200 mt-0.5">{day(contest.start)} – {day(contest.end)}</p>
          </div>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-white/10 px-3 py-1 text-xs font-semibold ring-1 ring-white/20"><Icon.Clock size={13} /> {chip}</span>
        </div>
        <div className="relative mt-4 grid grid-cols-2 sm:grid-cols-4 gap-2">
          {contest.bumpers.map((b, i) => (
            <div key={b.rank} className="rounded-2xl bg-white/10 px-3 py-2.5 ring-1 ring-white/15">
              <p className="text-[11px] font-semibold text-indigo-200">{MEDALS[medals[i]].emoji} {i === 0 ? "1st" : i === 1 ? "2nd" : "3rd"} bumper</p>
              <p className="mt-0.5 text-sm font-bold truncate" title={b.prize}>{b.prize || "To be announced"}</p>
            </div>
          ))}
          <div className="rounded-2xl bg-amber-400/15 px-3 py-2.5 ring-1 ring-amber-300/30">
            <p className="text-[11px] font-semibold text-amber-200 inline-flex items-center gap-1"><Coin size={12} /> Coin champion</p>
            <p className="mt-0.5 text-sm font-bold truncate" title={contest.coin_champion_prize}>{contest.coin_champion_prize || "To be announced"}</p>
          </div>
        </div>
      </div>

      {contest.result && (
        <div className="border-b border-slate-100 bg-amber-50/60 px-5 sm:px-6 py-4">
          <p className="text-xs font-bold uppercase tracking-wider text-amber-800">The winners</p>
          <ul className="mt-2 flex flex-wrap gap-2">
            {contest.result.winners.map(w => (
              <li key={w.rank} className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-slate-800 ring-1 ring-amber-200">
                {MEDALS[medals[w.rank - 1]].emoji} {w.name}{w.prize ? ` — ${w.prize}` : ""}
              </li>
            ))}
            {contest.result.coin_champion?.name && (
              <li className="inline-flex items-center gap-1 rounded-full bg-white px-3 py-1 text-xs font-semibold text-slate-800 ring-1 ring-amber-200">
                <Coin size={12} /> {contest.result.coin_champion.name} ({contest.result.coin_champion.coins} coins){contest.result.coin_champion.prize ? ` — ${contest.result.coin_champion.prize}` : ""}
              </li>
            )}
          </ul>
        </div>
      )}

      <div className="grid gap-5 p-5 sm:p-6 lg:grid-cols-[1fr_280px]">
        <div>
          <p className="text-xs font-bold uppercase tracking-wider text-slate-400">Standings</p>
          <ol className="mt-2 space-y-1">
            {contest.board.map(r => (
              <li key={r.user} className={`grid grid-cols-[auto_auto_1fr_auto] items-center gap-3 rounded-2xl px-3 py-2 ${r.is_subject ? "bg-indigo-50 ring-1 ring-indigo-200" : ""}`}>
                <RankBadge rank={r.rank} points={r.points} />
                <Avatar initials={r.initials} id={r.user} size={30} />
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-slate-900 truncate">{r.name}</p>
                  <p className="text-[11px] text-slate-500">{roleLabel(r.role)}{r.coins > 0 ? ` · ${r.coins} coins` : ""}</p>
                </div>
                <span className="text-sm font-bold text-slate-900 tabular-nums">{short(r.points)}</span>
              </li>
            ))}
          </ol>
        </div>
        <div className="space-y-4">
          {contest.me && (
            <div className="rounded-2xl bg-slate-50 p-4">
              <p className="text-xs font-bold uppercase tracking-wider text-slate-400">Your season</p>
              <p className="mt-1 text-2xl font-black text-slate-900">#{contest.me.rank}</p>
              <p className="text-xs text-slate-500 tabular-nums">{pts(contest.me.points)} points · {contest.me.coins} coins</p>
              {contest.target && contest.me.progress !== null && (
                <div className="mt-3">
                  <div className="flex justify-between text-[11px] text-slate-500"><span>Season goal</span><span className="tabular-nums">{Math.round(contest.me.progress * 100)}% of {short(contest.target)}</span></div>
                  <div className="mt-1"><Bar value={contest.me.progress} className="bg-violet-500" label="Season goal" /></div>
                </div>
              )}
            </div>
          )}
          <div className="rounded-2xl ring-1 ring-amber-200 bg-amber-50/60 p-4">
            <p className="text-xs font-bold uppercase tracking-wider text-amber-800 inline-flex items-center gap-1"><Coin size={13} /> Coin race</p>
            {contest.coin_board.length === 0 ? (
              <p className="mt-1.5 text-xs text-amber-900/70">Each month's top three win 30, 20 and 10 coins. The most coins at the end wins the coin champion's prize.</p>
            ) : (
              <ol className="mt-2 space-y-1.5">
                {contest.coin_board.map((r, i) => (
                  <li key={r.user} className="flex items-center justify-between gap-2 text-xs">
                    <span className={`truncate ${r.is_subject ? "font-bold text-indigo-700" : "text-slate-700"}`}>{i + 1}. {r.name}</span>
                    <span className="inline-flex items-center gap-0.5 font-bold text-amber-700 tabular-nums"><Coin size={11} />{r.coins}</span>
                  </li>
                ))}
              </ol>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

// ─── Hall of fame ────────────────────────────────────────────────────────────
/** `narrow` for a side column: one month to a row instead of three. */
export function HallOfFame({ months, narrow }: { months: Dashboard["hall_of_fame"]; narrow?: boolean }) {
  if (months.length === 0) return null;
  return (
    <Card className="p-5 sm:p-6">
      <CardHeader title="Hall of fame" subtitle="Every month's champions." icon={<Icon.Crown />} />
      <div className={`mt-4 grid gap-3 ${narrow ? "" : "sm:grid-cols-2 lg:grid-cols-3"}`}>
        {months.map(m => (
          <div key={m.key} className="rounded-2xl border border-slate-200 p-4 min-w-0">
            <p className="text-sm font-bold text-slate-900">{m.label}</p>
            <ul className="mt-2 space-y-1.5">
              {m.podium.map(p => (
                <li key={p.medal} className="flex items-center justify-between gap-2 text-xs min-w-0">
                  <span className="truncate text-slate-700" title={p.name}>{MEDALS[p.medal].emoji} {p.name}</span>
                  <span className="font-semibold text-slate-500 tabular-nums whitespace-nowrap">{short(p.points)}</span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </Card>
  );
}

// ─── Moments ─────────────────────────────────────────────────────────────────
/** A banner for a tier unlocked since the last visit, or a medal won last month. */
export function Moments({ me, monthKey, lastMonth, tiers }: { me: Me; monthKey: string; lastMonth: Dashboard["last_month"]; tiers: Tier[] }) {
  const tierKey = `rewards_tiers_${me.user}_${monthKey}`;
  const medal = lastMonth?.podium.find(p => p.user === me.user);
  const medalKey = medal ? `rewards_medal_${me.user}_${lastMonth!.key}` : "";
  const [tierNews, setTierNews] = useState(false);
  const [medalNews, setMedalNews] = useState(false);
  useEffect(() => {
    try {
      const seen = Number(localStorage.getItem(tierKey) || 0);
      setTierNews(me.tier.reached > seen);
      if (medalKey) setMedalNews(!localStorage.getItem(medalKey));
    } catch { /* storage unavailable: no banners, nothing breaks */ }
  }, [tierKey, medalKey, me.tier.reached]);
  const dismissTier = () => { try { localStorage.setItem(tierKey, String(me.tier.reached)); } catch { } setTierNews(false); };
  const dismissMedal = () => { try { localStorage.setItem(medalKey, "1"); } catch { } setMedalNews(false); };
  if (!tierNews && !medalNews) return null;
  return (
    <div className="space-y-3">
      {medalNews && medal && (
        <Banner tone="amber" onClose={dismissMedal}
          title={`${MEDALS[medal.medal].emoji} You won ${MEDALS[medal.medal].label} in ${lastMonth!.label}!`}
          text={[medal.prize, medal.coins ? `+${medal.coins} coins` : ""].filter(Boolean).join(" · ") || "Congratulations!"} />
      )}
      {tierNews && me.tier.current && (
        <Banner tone="violet" onClose={dismissTier}
          title={`🎉 You unlocked ${me.tier.current.name}!`}
          text={me.tier.current.reward ? `Your reward: ${me.tier.current.reward}` : "Keep going — the next tier is waiting."}
          image={tiers.find(t => t.id === me.tier.current?.id)?.image} />
      )}
    </div>
  );
}

function Banner({ tone, title, text, onClose, image }: {
  tone: "amber" | "violet"; title: string; text: string; onClose: () => void; image?: string | null;
}) {
  const look = tone === "amber" ? "from-amber-400 to-orange-500" : "from-violet-500 to-fuchsia-500";
  return (
    <div className={`animate-scale-in flex items-center justify-between gap-3 rounded-2xl bg-gradient-to-r ${look} px-4 py-3 text-white shadow-md`} role="status">
      {image && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={mediaSrc(image)} alt="" className="h-12 w-12 shrink-0 rounded-xl object-cover ring-2 ring-white/40" />
      )}
      <div className="min-w-0 flex-1">
        <p className="text-sm font-bold">{title}</p>
        <p className="text-xs text-white/90">{text}</p>
      </div>
      <button type="button" onClick={onClose} className="shrink-0 rounded-lg bg-white/20 px-3 py-1.5 text-xs font-semibold hover:bg-white/30">Nice!</button>
    </div>
  );
}

// ─── Loading ─────────────────────────────────────────────────────────────────
export function RewardsSkeleton() {
  return (
    <div className="max-w-[1240px] mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6 animate-pulse" aria-busy="true" aria-label="Loading rewards">
      <div className="h-56 rounded-3xl bg-slate-200/70" />
      <div className="h-40 rounded-3xl bg-slate-100" />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 h-96 rounded-3xl bg-slate-100" />
        <div className="h-96 rounded-3xl bg-slate-100" />
      </div>
    </div>
  );
}

"use client";
/**
 * Rewards — a monthly game for the sales team.
 *
 * BDEs and tele callers see their own card: points from money received this
 * month, the tier ladder and what each rung unlocks, where they rank, their
 * incentives, referral rewards and coins, last month's champions and the
 * yearly contest.
 *
 * Admins and super admins see the whole team, can open anyone's card, and set
 * the rules under Configuration.
 */
import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Dashboard, inr, loadDashboard, pts } from "./lib";
import {
  Cabinet, Card, CardHeader, Coin, ContestCard, HallOfFame, Hero, Icon, IncentivesCard,
  Leaderboard, Moments, MyReferralsCard, PointsStatement, Podium, ReferralRewardsCard, RewardsSkeleton, TierLadder,
} from "./parts";
import RewardSettingsForm from "./settings";

const PAGE = "max-w-[1240px] mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6";

export default function RewardsPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<"overview" | "settings">("overview");
  const [open, setOpen] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await loadDashboard();
      if (r.data) { setData(r.data); setError(""); }
      else setError(r.error || "Could not load rewards.");
    } catch { setError("Network error — check your connection and try again."); }
  }, []);
  useEffect(() => { load(); }, [load]);

  if (error) {
    return (
      <div className={PAGE}>
        <Card className="p-10 text-center">
          <p className="text-4xl">🏆</p>
          <p className="mt-3 text-base font-bold text-slate-900">{error}</p>
          <p className="mt-1 text-sm text-slate-500">Rewards is the sales team's game — BDEs and tele callers play, admins run it.</p>
          <Link href="/" className="mt-5 inline-block rounded-xl bg-indigo-600 px-5 py-2 text-sm font-semibold text-white hover:bg-indigo-700">Back to the dashboard</Link>
        </Card>
      </div>
    );
  }
  if (!data) return <RewardsSkeleton />;

  if (!data.is_admin) return <PlayerView data={data} />;
  return (
    <div className={PAGE}>
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-black text-slate-900">Rewards</h1>
          <p className="text-sm text-slate-500 mt-1">A monthly game for BDEs and tele callers — one point for every rupee received.</p>
        </div>
        <div className="inline-flex rounded-2xl bg-slate-100 p-1" role="tablist" aria-label="Rewards views">
          {([["overview", "Overview"], ["settings", "Configuration"]] as const).map(([key, label]) => (
            <button key={key} type="button" role="tab" aria-selected={tab === key} onClick={() => setTab(key)}
              className={`rounded-xl px-4 py-2 text-sm font-semibold transition ${tab === key ? "bg-white text-indigo-700 shadow-sm" : "text-slate-500 hover:text-slate-800"}`}>
              {label}
            </button>
          ))}
        </div>
      </header>
      {tab === "overview"
        ? <AdminOverview data={data} onOpen={setOpen} onConfigure={() => setTab("settings")} />
        : <RewardSettingsForm onSaved={load} />}
      {open !== null && <PlayerModal user={open} onClose={() => setOpen(null)} onChanged={load} />}
    </div>
  );
}

// ─── The player's view ───────────────────────────────────────────────────────
function PlayerView({ data }: { data: Dashboard }) {
  const me = data.me;
  if (!me) return null;
  return (
    <div className={PAGE}>
      <Moments me={me} monthKey={data.month.key} lastMonth={data.last_month} tiers={data.tiers} />
      <Hero me={me} month={data.month} />
      <TierLadder tiers={data.tiers} climb={me.tier} role={me.role} points={me.points} />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-6">
          <Leaderboard rows={data.board} title={`${data.month.label} leaderboard`}
            subtitle="Live — points from money received this month." limit={10} />
          <PointsStatement lines={me.statement} total={me.points} monthLabel={data.month.label} limit={6} />
          {data.contest && <ContestCard contest={data.contest} />}
        </div>
        <div className="space-y-6">
          <Podium title="Last month's champions" label={data.last_month?.label} podium={data.last_month?.podium || []} />
          <IncentivesCard incentives={me.incentives} />
          <MyReferralsCard referrals={me.referrals} />
          <Cabinet me={me} tiers={data.tiers} />
          <HowItWorks rules={data.rules} />
        </div>
      </div>
      <HallOfFame months={data.hall_of_fame} />
    </div>
  );
}

function HowItWorks({ rules }: { rules: Dashboard["rules"] }) {
  const coins = rules.prizes.map(p => p.coins).join(", ");
  return (
    <Card className="p-5">
      <CardHeader title="How it works" icon={<Icon.Spark />} />
      <ul className="mt-3 space-y-2.5 text-xs text-slate-600">
        <li className="flex gap-2"><span>💰</span><span><b className="text-slate-800">1 point for every ₹1</b> your customers pay, in the month they pay it.</span></li>
        <li className="flex gap-2"><span>🤝</span><span>A deal you share is split <b className="text-slate-800">{Math.round(Number(rules.bde_share))}% BDE / {Math.round(Number(rules.telecaller_share))}% tele caller</b>. Sell on your own and it's all yours.</span></li>
        <li className="flex gap-2"><span>🪜</span><span>Reach a tier to unlock its reward. Every tier opens again on the 1st.</span></li>
        <li className="flex gap-2"><span>🏆</span><span>The month's top three win prizes and <span className="inline-flex items-center gap-0.5 font-semibold text-amber-700"><Coin size={11} />{coins}</span> coins.</span></li>
        <li className="flex gap-2"><span>🎯</span><span>Incentives are paid per project when your customer finishes paying.</span></li>
        <li className="flex gap-2"><span>🎁</span><span>Refer a customer and earn the project&apos;s <b className="text-slate-800">referral reward</b> when they finish paying.</span></li>
        <li className="flex gap-2"><span>🧾</span><span>Every payment behind your points is listed under <b className="text-slate-800">Where the points came from</b>.</span></li>
      </ul>
    </Card>
  );
}

// ─── The admin's view ────────────────────────────────────────────────────────
function AdminOverview({ data, onOpen, onConfigure }: { data: Dashboard; onOpen: (user: number) => void; onConfigure: () => void }) {
  const k = data.kpis!;
  const setup = [
    data.tiers.length === 0 && "Set up the tier ladder — targets and the rewards they unlock.",
    !data.contest && "Date the yearly contest and choose its bumper prizes.",
    data.rules.prizes.every(p => !p.prize) && "Choose the monthly prizes for gold, silver and bronze.",
  ].filter(Boolean) as string[];
  return (
    <>
      {setup.length > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-indigo-200 bg-indigo-50 px-5 py-4">
          <div>
            <p className="text-sm font-bold text-indigo-900">Finish setting up the game</p>
            <ul className="mt-1 list-disc pl-5 text-xs text-indigo-800 space-y-0.5">{setup.map(s => <li key={s}>{s}</li>)}</ul>
          </div>
          <button type="button" onClick={onConfigure} className="rounded-xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700">Open configuration</button>
        </div>
      )}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Kpi label="Players" value={String(k.players)} hint="BDEs and tele callers" />
        <Kpi label="Scoring this month" value={String(k.scoring)} hint={`of ${k.players}`} />
        <Kpi label="Points this month" value={pts(k.points)} hint={data.month.label} />
        <Kpi label="Tiers unlocked" value={String(k.tiers_unlocked)} hint="across the team" />
        <Kpi label="Incentives earned" value={inr(k.incentives)} hint="this month" accent />
      </div>
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Leaderboard rows={data.board} title={`${data.month.label} — live table`}
            subtitle={`${data.month.days_left} ${data.month.days_left === 1 ? "day" : "days"} left · click anyone to see every payment behind their points`}
            onOpen={onOpen} showMoney />
        </div>
        <div className="space-y-6">
          {data.referrals && <ReferralRewardsCard months={data.referrals} />}
          <Podium title="Last month's champions" label={data.last_month?.label} podium={data.last_month?.podium || []} />
          <HallOfFame months={data.hall_of_fame} narrow />
        </div>
      </div>
      {data.contest && <ContestCard contest={data.contest} />}
    </>
  );
}

function Kpi({ label, value, hint, accent }: { label: string; value: string; hint: string; accent?: boolean }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">{label}</p>
      <p className={`mt-1 text-xl sm:text-2xl font-black tabular-nums ${accent ? "text-emerald-600" : "text-slate-900"}`}>{value}</p>
      <p className="text-[11px] text-slate-500">{hint}</p>
    </div>
  );
}

function PlayerModal({ user, onClose, onChanged }: { user: number; onClose: () => void; onChanged: () => void }) {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0);
  useEffect(() => {
    let live = true;   // a slower, older answer must not overwrite a newer one
    loadDashboard(user)
      .then(r => {
        if (!live) return;
        if (r.data) { setData(r.data); setError(""); } else setError(r.error || "Could not open that card.");
      })
      .catch(() => { if (live) setError("Network error."); });
    return () => { live = false; };
  }, [user, version]);
  // A payment taken out or put back changes this card and the table behind it.
  const changed = () => { setVersion(v => v + 1); onChanged(); };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  const me = data?.me;
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/50 backdrop-blur-sm p-3 sm:p-6" onClick={onClose}>
      <div className="w-full max-w-5xl space-y-4 rounded-3xl bg-slate-50 p-4 sm:p-6 shadow-2xl" onClick={e => e.stopPropagation()}
        role="dialog" aria-modal="true" aria-label={me ? `${me.name}'s rewards` : "Rewards card"}>
        <div className="flex items-center justify-between">
          <p className="text-sm font-semibold text-slate-500">Player card</p>
          <button type="button" onClick={onClose} className="rounded-xl px-3 py-1.5 text-sm font-semibold text-slate-600 hover:bg-slate-200">Close</button>
        </div>
        {error && <p className="text-sm text-rose-600">{error}</p>}
        {!data && !error && <div className="h-64 rounded-3xl bg-slate-200/70 animate-pulse" />}
        {data && me && (
          <>
            <Hero me={me} month={data.month} preview />
            <TierLadder tiers={data.tiers} climb={me.tier} role={me.role} points={me.points} />
            <PointsStatement lines={me.statement} total={me.points} monthLabel={data.month.label}
              admin onChanged={changed} />
            <div className="grid gap-4 lg:grid-cols-2">
              <IncentivesCard incentives={me.incentives} preview />
              <MyReferralsCard referrals={me.referrals} preview />
              <Cabinet me={me} tiers={data.tiers} />
            </div>
          </>
        )}
      </div>
    </div>
  );
}

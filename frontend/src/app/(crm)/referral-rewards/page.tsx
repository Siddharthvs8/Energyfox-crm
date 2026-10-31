"use client";
/**
 * Referral Rewards — what referring a customer earns, for everyone on the staff.
 *
 * A lead whose source is Referral names the member of staff who sent the
 * customer our way. When that customer buys and finishes paying, the referrer
 * earns the referral reward set on the project they bought. Anyone can refer,
 * whatever their role, so every role has this page.
 *
 * Each person sees the customers they referred and where each reward stands.
 * The admins who pay the rewards also see everyone's, a month at a time.
 */
import React, { useEffect, useState } from "react";
import { day, inr, loadReferrals, num, Referral, ReferralPage } from "../rewards/lib";
import { Card, CardHeader, Icon, ReferralPeople } from "../rewards/parts";

const PAGE = "max-w-[1100px] mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6";

const STATUS: Record<Referral["status"], { label: (r: Referral) => string; cls: string }> = {
  earned: { label: r => `Earned · ${r.earned_on ? day(r.earned_on) : ""}`, cls: "bg-emerald-50 text-emerald-700" },
  waiting: { label: () => "Waiting for full payment", cls: "bg-amber-50 text-amber-700" },
  no_project: { label: () => "No project bought yet", cls: "bg-slate-100 text-slate-500" },
  no_reward: { label: () => "No referral reward on this project", cls: "bg-slate-100 text-slate-500" },
  lost: { label: () => "Deal lost", cls: "bg-rose-50 text-rose-600" },
};

export default function ReferralRewardsPage() {
  const [data, setData] = useState<ReferralPage | null>(null);
  const [error, setError] = useState("");
  // Admins pick a month; "" is this month.
  const [month, setMonth] = useState("");
  const [switching, setSwitching] = useState(false);

  useEffect(() => {
    let live = true;   // a slower, older answer must not overwrite a newer one
    loadReferrals(month || undefined)
      .then(r => {
        if (!live) return;
        if (r.data) { setData(r.data); setError(""); } else setError(r.error || "Could not load referral rewards.");
      })
      .catch(() => { if (live) setError("Network error — check your connection and try again."); })
      .finally(() => { if (live) setSwitching(false); });
    return () => { live = false; };
  }, [month]);

  if (!data) {
    return (
      <div className={PAGE}>
        {error
          ? <p className="rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-700">{error}</p>
          : <div className="h-64 rounded-3xl bg-slate-200/70 animate-pulse" />}
      </div>
    );
  }

  const me = data.me;
  const tiles = [
    { label: "This month", value: me.this_month.total, hint: me.this_month.label },
    { label: "Last month", value: me.last_month.total, hint: me.last_month.label },
    { label: "Earned in total", value: me.earned_total, hint: "every month so far" },
    { label: "Waiting", value: me.waiting_total, hint: "until those customers finish paying" },
  ];

  return (
    <div className={PAGE}>
      <header>
        <h1 className="text-2xl font-bold text-slate-900">Referral Rewards</h1>
        <p className="mt-1 text-sm text-slate-500">
          Refer a customer to the company. When they buy and finish paying, you earn the referral reward set on the
          project they bought.
        </p>
      </header>

      {/* The admins who pay the rewards see everyone's, month by month — first,
          since that is what they come here for. */}
      {data.is_admin && data.month && (
        <Card className="p-5">
          <CardHeader title="Everyone's referral rewards" icon={<Icon.Gift />}
            subtitle="Owed to the staff member who referred each customer, in the month the customer finished paying." />
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
            <p className="text-3xl font-black text-purple-600 tabular-nums">{inr(data.month.total)}</p>
            <select value={month || data.month.key} disabled={switching} aria-label="Month"
              onChange={e => { setSwitching(true); setMonth(e.target.value); }}
              className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700 outline-none focus:ring-2 focus:ring-purple-500/20 disabled:opacity-60">
              {data.months.map(m => <option key={m.key} value={m.key}>{m.label}</option>)}
            </select>
          </div>
          <div className={switching ? "opacity-50 transition-opacity" : "transition-opacity"}>
            <ReferralPeople month={data.month} />
          </div>
        </Card>
      )}

      {data.is_admin && <h2 className="text-sm font-bold text-slate-700 -mb-3">Your own referral rewards</h2>}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {tiles.map(t => (
          <div key={t.label} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">{t.label}</p>
            <p className={`mt-1 text-xl sm:text-2xl font-black tabular-nums ${num(t.value) > 0 ? "text-purple-600" : "text-slate-900"}`}>{inr(t.value)}</p>
            <p className="text-[11px] text-slate-500">{t.hint}</p>
          </div>
        ))}
      </div>

      <Card className="p-5">
        <CardHeader title="Your referrals" icon={<Icon.Gift />}
          subtitle={me.referrals.length
            ? `${me.referrals.length} ${me.referrals.length === 1 ? "customer" : "customers"} you referred, newest first.`
            : undefined} />
        {me.referrals.length === 0 ? (
          <p className="mt-3 text-sm text-slate-500">
            You haven&apos;t referred anyone yet. When a lead&apos;s source is Referral and it names you under
            Referred By, it shows up here.
          </p>
        ) : (
          <ul className="mt-3 divide-y divide-slate-100">
            {me.referrals.map(r => {
              const s = STATUS[r.status];
              return (
                <li key={r.lead} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:justify-between">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-slate-800">{r.customer}</p>
                    <p className="text-[11px] text-slate-500">
                      {[r.referred_on ? `Referred ${day(r.referred_on)}` : null, r.stage, r.project].filter(Boolean).join(" · ")}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-3">
                    <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${s.cls}`}>{s.label(r)}</span>
                    {r.reward !== null && num(r.reward) > 0 && (
                      <span className={`text-sm font-bold tabular-nums ${r.status === "earned" ? "text-purple-600" : "text-slate-400"}`}>
                        {inr(r.reward)}
                      </span>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </Card>
    </div>
  );
}

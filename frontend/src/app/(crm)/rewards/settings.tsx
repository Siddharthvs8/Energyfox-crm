"use client";
/** Rewards → Configuration: the rules of the game, admins only. */
import React, { useEffect, useMemo, useRef, useState } from "react";
import { RewardType, Settings, loadSettings, mediaSrc, pts, saveSettings, uploadGiftImage } from "./lib";
import { Card, CardHeader, Coin, Icon } from "./parts";

/** A tier as it is being edited. Both kinds of reward are kept while the admin
 * switches between them; only the chosen one is saved. */
type TierDraft = {
  key: string; name: string; target: string; target_telecaller: string;
  reward_type: RewardType; reward: string; reward_amount: string;
  reward_image: string; reward_image_url: string;
};
type Draft = {
  bde_share: string;
  gold_prize: string; silver_prize: string; bronze_prize: string;
  gold_coins: string; silver_coins: string; bronze_coins: string;
  contest_name: string; contest_start: string; contest_end: string; contest_target: string;
  bumper_first: string; bumper_second: string; bumper_third: string; coin_champion_prize: string;
  tiers: TierDraft[];
};

const clean = (v: string | number | null | undefined) =>
  v === null || v === undefined || v === "" ? "" : String(Number(v));
let keySeq = 0;
const newKey = () => `t${++keySeq}`;

function toDraft(s: Settings): Draft {
  return {
    bde_share: clean(s.bde_share),
    gold_prize: s.gold_prize, silver_prize: s.silver_prize, bronze_prize: s.bronze_prize,
    gold_coins: String(s.gold_coins), silver_coins: String(s.silver_coins), bronze_coins: String(s.bronze_coins),
    contest_name: s.contest_name, contest_start: s.contest_start || "", contest_end: s.contest_end || "",
    contest_target: clean(s.contest_target),
    bumper_first: s.bumper_first, bumper_second: s.bumper_second, bumper_third: s.bumper_third,
    coin_champion_prize: s.coin_champion_prize,
    tiers: s.tiers.map(t => ({
      key: newKey(), name: t.name, target: clean(t.target), target_telecaller: clean(t.target_telecaller),
      reward_type: t.reward_type || "gift", reward: t.reward, reward_amount: clean(t.reward_amount),
      reward_image: t.reward_image || "", reward_image_url: t.reward_image_url || "",
    })),
  };
}

function toPayload(d: Draft) {
  const orNull = (v: string) => (v.trim() === "" ? null : v.trim());
  return {
    bde_share: d.bde_share || "0",
    gold_prize: d.gold_prize.trim(), silver_prize: d.silver_prize.trim(), bronze_prize: d.bronze_prize.trim(),
    gold_coins: Number(d.gold_coins || 0), silver_coins: Number(d.silver_coins || 0), bronze_coins: Number(d.bronze_coins || 0),
    contest_name: d.contest_name.trim(), contest_start: orNull(d.contest_start), contest_end: orNull(d.contest_end),
    contest_target: orNull(d.contest_target),
    bumper_first: d.bumper_first.trim(), bumper_second: d.bumper_second.trim(), bumper_third: d.bumper_third.trim(),
    coin_champion_prize: d.coin_champion_prize.trim(),
    tiers: d.tiers.map(t => ({
      name: t.name.trim(), target: t.target || "0", target_telecaller: orNull(t.target_telecaller),
      reward_type: t.reward_type,
      ...(t.reward_type === "cash"
        ? { reward: "", reward_amount: orNull(t.reward_amount), reward_image: null }
        : { reward: t.reward.trim(), reward_amount: null, reward_image: t.reward_image || null }),
    })),
  };
}

const sameDraft = (a: Draft | null, b: Draft | null) =>
  !!a && !!b && JSON.stringify(toPayload(a)) === JSON.stringify(toPayload(b));

const FIELD = "w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800 outline-none transition focus:border-indigo-400 focus:bg-white focus:ring-2 focus:ring-indigo-500/20";
const LABEL = "block text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1.5";

export default function RewardSettingsForm({ onSaved }: { onSaved: () => void }) {
  const [base, setBase] = useState<Draft | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [startedOn, setStartedOn] = useState("");
  const [errors, setErrors] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [flash, setFlash] = useState("");
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    loadSettings().then(s => {
      if (!s) { setFailed(true); return; }
      const d = toDraft(s);
      setBase(d); setDraft(d); setStartedOn(s.program_start);
    });
  }, []);

  const dirty = useMemo(() => !sameDraft(base, draft), [base, draft]);

  if (failed) return <Card className="p-6 text-sm text-rose-600">The reward settings could not be loaded.</Card>;
  if (!draft) return <div className="h-96 rounded-3xl bg-slate-100 animate-pulse" />;

  const set = (patch: Partial<Draft>) => setDraft(d => (d ? { ...d, ...patch } : d));
  const setTier = (i: number, patch: Partial<TierDraft>) =>
    setDraft(d => (d ? { ...d, tiers: d.tiers.map((t, n) => (n === i ? { ...t, ...patch } : t)) } : d));
  const moveTier = (i: number, by: number) => setDraft(d => {
    if (!d) return d;
    const tiers = [...d.tiers];
    const j = i + by;
    if (j < 0 || j >= tiers.length) return d;
    [tiers[i], tiers[j]] = [tiers[j], tiers[i]];
    return { ...d, tiers };
  });
  const addTier = () => setDraft(d => {
    if (!d) return d;
    const last = d.tiers[d.tiers.length - 1];
    const target = last ? String(Math.round(Number(last.target || 0) * 1.5) || 100000) : "100000";
    const tc = last?.target_telecaller ? String(Math.round(Number(last.target_telecaller) * 1.5)) : "";
    return { ...d, tiers: [...d.tiers, {
      key: newKey(), name: `Tier ${d.tiers.length + 1}`, target, target_telecaller: tc,
      // A new rung pays the way the one below it does.
      reward_type: last?.reward_type || "cash", reward: "", reward_amount: "", reward_image: "", reward_image_url: "",
    }] };
  });
  const removeTier = (i: number) => setDraft(d => (d ? { ...d, tiers: d.tiers.filter((_, n) => n !== i) } : d));

  const share = Math.max(0, Math.min(100, Number(draft.bde_share || 0)));
  const callerShare = 100 - share;

  const fillYear = (kind: "fy" | "calendar") => {
    const now = new Date();
    if (kind === "fy") {
      const startYear = now.getMonth() >= 3 ? now.getFullYear() : now.getFullYear() - 1;
      set({ contest_start: `${startYear}-04-01`, contest_end: `${startYear + 1}-03-31`,
            contest_name: draft.contest_name || `FY ${startYear}–${String(startYear + 1).slice(2)} Championship` });
    } else {
      const y = now.getFullYear();
      set({ contest_start: `${y}-01-01`, contest_end: `${y}-12-31`, contest_name: draft.contest_name || `${y} Championship` });
    }
  };

  const save = async () => {
    setSaving(true); setErrors([]); setFlash("");
    try {
      const r = await saveSettings(toPayload(draft) as never);
      if (!r.ok) { setErrors(r.errors?.length ? r.errors : ["The settings could not be saved."]); return; }
      const d = toDraft(r.data!);
      setBase(d); setDraft(d);
      setFlash("Saved. The team sees the new rules straight away.");
      onSaved();
    } catch { setErrors(["Network error — nothing was saved."]); }
    finally { setSaving(false); }
  };

  return (
    <div className="space-y-6 pb-28">
      {/* ── Tiers ── */}
      <Card className="p-5 sm:p-6">
        <CardHeader title="Tier ladder" icon={<Icon.Gift />}
          subtitle="One point for every rupee received. Each tier unlocks its reward; the ladder starts again on the 1st." />
        <div className="mt-5 space-y-3">
          {draft.tiers.length === 0 && (
            <p className="rounded-2xl border border-dashed border-slate-200 p-6 text-center text-sm text-slate-500">
              No tiers yet. Add the first one — the team will see it on their Rewards page at once.
            </p>
          )}
          {draft.tiers.map((t, i) => (
            <div key={t.key} className="rounded-2xl border border-slate-200 p-4">
              <div className="flex items-center justify-between gap-2">
                <span className="inline-flex items-center gap-2 text-xs font-bold text-slate-500">
                  <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-indigo-600 text-[11px] text-white">{i + 1}</span>
                  Tier {i + 1}
                </span>
                <div className="flex items-center gap-1">
                  <button type="button" onClick={() => moveTier(i, -1)} disabled={i === 0} aria-label="Move up"
                    className="rounded-lg px-2 py-1 text-xs text-slate-500 hover:bg-slate-100 disabled:opacity-30">↑</button>
                  <button type="button" onClick={() => moveTier(i, 1)} disabled={i === draft.tiers.length - 1} aria-label="Move down"
                    className="rounded-lg px-2 py-1 text-xs text-slate-500 hover:bg-slate-100 disabled:opacity-30">↓</button>
                  <button type="button" onClick={() => removeTier(i)} aria-label={`Remove tier ${i + 1}`}
                    className="rounded-lg px-2 py-1 text-xs font-semibold text-rose-500 hover:bg-rose-50">Remove</button>
                </div>
              </div>
              <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <div>
                  <label className={LABEL} htmlFor={`tier-name-${t.key}`}>Name</label>
                  <input id={`tier-name-${t.key}`} value={t.name} onChange={e => setTier(i, { name: e.target.value })} className={FIELD} placeholder="e.g. Gold" />
                </div>
                <RewardPicker tier={t} index={i} onChange={patch => setTier(i, patch)} />
                <div>
                  <label className={LABEL} htmlFor={`tier-target-${t.key}`}>Target (points)</label>
                  <input id={`tier-target-${t.key}`} type="number" min="1" value={t.target} onChange={e => setTier(i, { target: e.target.value })} className={FIELD} />
                  {Number(t.target) > 0 && <p className="mt-1 text-[11px] text-slate-400 tabular-nums">₹{pts(t.target)} received</p>}
                </div>
                <div>
                  <label className={LABEL} htmlFor={`tier-tc-${t.key}`}>Tele caller target</label>
                  <input id={`tier-tc-${t.key}`} type="number" min="1" value={t.target_telecaller}
                    onChange={e => setTier(i, { target_telecaller: e.target.value })} className={FIELD} placeholder="Same as target" />
                </div>
              </div>
            </div>
          ))}
        </div>
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <button type="button" onClick={addTier} disabled={draft.tiers.length >= 10}
            className="rounded-xl border border-indigo-200 bg-indigo-50 px-4 py-2 text-sm font-semibold text-indigo-700 hover:bg-indigo-100 disabled:opacity-40">
            + Add tier
          </button>
          {draft.tiers.some(t => !t.target_telecaller) && callerShare > 0 && callerShare < 100 && (
            <p className="text-xs text-slate-500 max-w-md">
              Tele callers earn {callerShare}% of a shared deal. A lower tele caller target keeps the same rewards within their reach.
            </p>
          )}
        </div>
      </Card>

      {/* ── Points split ── */}
      <Card className="p-5 sm:p-6">
        <CardHeader title="Points split" icon={<Icon.Rupee />}
          subtitle="How a deal's points are shared when a tele caller and a BDE both worked it." />
        <div className="mt-5 grid gap-5 lg:grid-cols-2">
          <div>
            <label className={LABEL} htmlFor="bde-share">BDE share</label>
            <div className="flex items-center gap-3">
              <input id="bde-share-range" type="range" min="0" max="100" step="5" value={share}
                onChange={e => set({ bde_share: e.target.value })} className="flex-1 accent-indigo-600" aria-label="BDE share" />
              <div className="relative w-24">
                <input id="bde-share" type="number" min="0" max="100" value={draft.bde_share}
                  onChange={e => set({ bde_share: e.target.value })} className={`${FIELD} pr-7`} />
                <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-sm text-slate-400">%</span>
              </div>
            </div>
            <p className="mt-2 text-xs text-slate-500">Tele caller share: <b className="text-slate-700">{callerShare}%</b></p>
          </div>
          <div className="rounded-2xl bg-slate-50 p-4 text-sm text-slate-600">
            <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">For example</p>
            <p className="mt-1.5">₹1,00,000 received on a shared deal:</p>
            <p className="mt-1 font-semibold text-slate-800">BDE {pts(share * 1000)} pts · Tele caller {pts(callerShare * 1000)} pts</p>
            <p className="mt-2 text-xs text-slate-500">A BDE who sold on their own earns all 1,00,000.</p>
          </div>
        </div>
      </Card>

      {/* ── Monthly champions ── */}
      <Card className="p-5 sm:p-6">
        <CardHeader title="Monthly champions" icon={<span className="text-base">🏆</span>}
          subtitle="When a month ends its top three are announced to the whole team." />
        <div className="mt-5 space-y-3">
          {([["gold", "🥇 Gold", "gold_prize", "gold_coins"], ["silver", "🥈 Silver", "silver_prize", "silver_coins"],
             ["bronze", "🥉 Bronze", "bronze_prize", "bronze_coins"]] as const).map(([key, label, prize, coins]) => (
            <div key={key} className="grid gap-3 sm:grid-cols-[140px_1fr_140px] sm:items-end">
              <p className="text-sm font-bold text-slate-800 sm:pb-2.5">{label}</p>
              <div>
                <label className={LABEL} htmlFor={prize}>Prize</label>
                <input id={prize} value={draft[prize]} onChange={e => set({ [prize]: e.target.value } as Partial<Draft>)} className={FIELD} placeholder="e.g. Weekend getaway" />
              </div>
              <div>
                <label className={LABEL} htmlFor={coins}><span className="inline-flex items-center gap-1"><Coin size={11} /> Coins</span></label>
                <input id={coins} type="number" min="0" value={draft[coins]} onChange={e => set({ [coins]: e.target.value } as Partial<Draft>)} className={FIELD} />
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* ── The contest ── */}
      <Card className="p-5 sm:p-6">
        <CardHeader title="Yearly contest" icon={<Icon.Trophy />}
          subtitle="The top three by points over these dates win the bumper prizes; the most coins wins the coin champion's prize." />
        <div className="mt-4 flex flex-wrap gap-2">
          <button type="button" onClick={() => fillYear("fy")} className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-50">This financial year (Apr–Mar)</button>
          <button type="button" onClick={() => fillYear("calendar")} className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-50">This calendar year</button>
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="lg:col-span-2">
            <label className={LABEL} htmlFor="contest-name">Name</label>
            <input id="contest-name" value={draft.contest_name} onChange={e => set({ contest_name: e.target.value })} className={FIELD} placeholder="e.g. FY 2026–27 Championship" />
          </div>
          <div>
            <label className={LABEL} htmlFor="contest-start">Starts</label>
            <input id="contest-start" type="date" value={draft.contest_start} onChange={e => set({ contest_start: e.target.value })} className={FIELD} />
          </div>
          <div>
            <label className={LABEL} htmlFor="contest-end">Ends</label>
            <input id="contest-end" type="date" value={draft.contest_end} min={draft.contest_start || undefined}
              onChange={e => set({ contest_end: e.target.value })} className={FIELD} />
          </div>
          {(["bumper_first", "bumper_second", "bumper_third"] as const).map((k, i) => (
            <div key={k}>
              <label className={LABEL} htmlFor={k}>{["🥇 1st", "🥈 2nd", "🥉 3rd"][i]} bumper prize</label>
              <input id={k} value={draft[k]} onChange={e => set({ [k]: e.target.value } as Partial<Draft>)} className={FIELD} placeholder={["e.g. Foreign trip", "e.g. iPhone", "e.g. Smart TV"][i]} />
            </div>
          ))}
          <div>
            <label className={LABEL} htmlFor="coin-champion"><span className="inline-flex items-center gap-1"><Coin size={11} /> Coin champion prize</span></label>
            <input id="coin-champion" value={draft.coin_champion_prize} onChange={e => set({ coin_champion_prize: e.target.value })} className={FIELD} placeholder="e.g. Gold coin" />
          </div>
          <div className="sm:col-span-2 lg:col-span-2">
            <label className={LABEL} htmlFor="contest-target">Season goal (optional)</label>
            <input id="contest-target" type="number" min="1" value={draft.contest_target} onChange={e => set({ contest_target: e.target.value })} className={FIELD} placeholder="Points everyone is aiming for" />
            <p className="mt-1 text-[11px] text-slate-400">Shown to each player as their progress for the season.</p>
          </div>
        </div>
      </Card>

      {startedOn && (
        <p className="text-center text-xs text-slate-400">
          The game began in {new Date(`${startedOn}T00:00:00`).toLocaleDateString("en-IN", { month: "long", year: "numeric" })}; months before that are not crowned.
        </p>
      )}

      {/* ── Save bar ── */}
      {/* Above the phone's bottom tab bar, and clear of the sidebar (15rem) on
          large screens. */}
      <div className="fixed inset-x-0 z-30 bottom-[calc(var(--mobile-tabbar-h)_+_var(--safe-bottom))] lg:bottom-0 lg:left-60">
        <div className="mx-auto max-w-[1240px] px-4 sm:px-6 lg:px-8 pb-4">
          {errors.length > 0 && (
            <div className="mb-2 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 shadow-sm" role="alert">
              {errors.map((e, i) => <p key={i}>{e}</p>)}
            </div>
          )}
          <div className={`flex items-center justify-between gap-3 rounded-2xl border px-4 py-3 shadow-lg backdrop-blur transition ${
            dirty ? "border-indigo-200 bg-white/95" : "border-slate-200 bg-white/90"}`}>
            <p className="text-sm text-slate-600">{flash && !dirty ? <span className="text-emerald-600 font-semibold">✓ {flash}</span> : dirty ? "You have unsaved changes." : "Everything is saved."}</p>
            <div className="flex items-center gap-2">
              <button type="button" onClick={() => { setDraft(base); setErrors([]); }} disabled={!dirty || saving}
                className="rounded-xl px-4 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-100 disabled:opacity-40">Discard</button>
              <button type="button" onClick={save} disabled={!dirty || saving}
                className="rounded-xl bg-indigo-600 px-5 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-700 disabled:opacity-40">
                {saving ? "Saving…" : "Save changes"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── A tier's reward: cash or a gift ─────────────────────────────────────────
function RewardPicker({ tier, index, onChange }: { tier: TierDraft; index: number; onChange: (patch: Partial<TierDraft>) => void }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const cash = tier.reward_type === "cash";

  const choose = async (file: File | undefined) => {
    if (!file) return;
    setError("");
    if (!/^image\/(png|jpe?g|webp)$/.test(file.type)) { setError("Use a JPG, PNG or WebP picture."); return; }
    if (file.size > 5 * 1024 * 1024) { setError("Keep the picture under 5 MB."); return; }
    setUploading(true);
    try {
      const r = await uploadGiftImage(file);
      if (r.ok) onChange({ reward_image: r.path || "", reward_image_url: r.url || "" });
      else setError(r.error || "The picture could not be uploaded.");
    } catch { setError("Network error — the picture was not uploaded."); }
    finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";   // so the same file can be chosen again
    }
  };

  return (
    <div>
      {/* The switch sits in the label row, so the field below lines up with
          the tier's other fields. */}
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <label className="text-[10px] font-bold uppercase tracking-wider text-slate-500"
          htmlFor={cash ? `tier-amount-${tier.key}` : `tier-reward-${tier.key}`}>Reward</label>
        <div role="radiogroup" aria-label={`Tier ${index + 1} reward`} className="-my-1 inline-flex rounded-lg bg-slate-100 p-0.5">
          {(["cash", "gift"] as const).map(kind => (
            <button key={kind} type="button" role="radio" aria-checked={tier.reward_type === kind}
              onClick={() => { onChange({ reward_type: kind }); setError(""); }}
              className={`rounded-md px-2 py-0.5 text-[11px] font-semibold transition ${tier.reward_type === kind
                ? "bg-white text-indigo-700 shadow-sm" : "text-slate-500 hover:text-slate-800"}`}>
              {kind === "cash" ? "💵 Cash" : "🎁 Gift"}
            </button>
          ))}
        </div>
      </div>
      {cash ? (
        <>
          <div className="relative">
            <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm text-slate-400">₹</span>
            <input id={`tier-amount-${tier.key}`} type="number" min="1" inputMode="numeric" value={tier.reward_amount}
              onChange={e => onChange({ reward_amount: e.target.value })} className={`${FIELD} pl-7`} placeholder="Amount" />
          </div>
          {Number(tier.reward_amount) > 0 && <p className="mt-1 text-[11px] text-slate-400 tabular-nums">₹{pts(tier.reward_amount)} cash</p>}
        </>
      ) : (
        <>
          <input id={`tier-reward-${tier.key}`} value={tier.reward} onChange={e => onChange({ reward: e.target.value })}
            className={FIELD} placeholder="e.g. Smartwatch" maxLength={200} />
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5">
            {tier.reward_image_url ? (
              <>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={mediaSrc(tier.reward_image_url)} alt={tier.reward || "The gift"}
                  className="h-12 w-12 shrink-0 rounded-xl object-cover ring-1 ring-slate-200" />
                <button type="button" onClick={() => fileRef.current?.click()} disabled={uploading}
                  className="text-xs font-semibold text-indigo-600 hover:underline disabled:opacity-50">
                  {uploading ? "Uploading…" : "Change photo"}
                </button>
                <button type="button" onClick={() => onChange({ reward_image: "", reward_image_url: "" })} disabled={uploading}
                  className="text-xs font-semibold text-rose-500 hover:underline disabled:opacity-50">Remove</button>
              </>
            ) : (
              <button type="button" onClick={() => fileRef.current?.click()} disabled={uploading}
                className="inline-flex items-center gap-1.5 rounded-xl border border-dashed border-slate-300 px-3 py-1.5 text-xs font-semibold text-slate-600 transition hover:border-indigo-300 hover:text-indigo-700 disabled:opacity-50">
                {uploading ? "Uploading…" : <>📷 Add a photo <span className="font-normal text-slate-400">(optional)</span></>}
              </button>
            )}
            <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" className="hidden"
              aria-label={`Photo of the gift for tier ${index + 1}`} onChange={e => choose(e.target.files?.[0])} />
          </div>
          {error && <p className="mt-1 text-[11px] font-medium text-rose-600" role="alert">{error}</p>}
        </>
      )}
    </div>
  );
}

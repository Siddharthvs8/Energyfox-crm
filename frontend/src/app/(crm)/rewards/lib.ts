/** Rewards — shapes the API returns, formatting, and the two calls. */
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";
import { compactINR } from "@/lib/format";

export type Medal = "gold" | "silver" | "bronze";

export type Tier = {
  id: number; name: string; reward: string;
  target: string; target_telecaller: string | null;
};

export type TierRef = { id: number; name: string; reward: string; target: string };

export type Climb = {
  reached: number; of: number;
  current: TierRef | null; next: TierRef | null;
  rewards: string[]; needed: string | null; progress: number;
};

export type BoardRow = {
  rank: number; user: number; name: string; initials: string; role: string;
  points: string; deals: number; tier: string | null; tiers_reached: number;
  is_me: boolean; is_subject: boolean; incentives?: string;
};

export type PodiumRow = {
  medal: Medal; rank: number; user: number | null; name: string; initials: string;
  role: string; points: string; prize: string; coins: number;
};

export type IncentiveDeal = {
  lead: number; customer: string; project: string; amount: string;
  as: "bde" | "tele_caller"; paid_on: string;
};

export type HistoryRow = {
  key: string; label: string; rank: number; points: string; medal: Medal | "";
  prize: string; coins: number; rewards: string[]; tier: string;
};

export type Me = {
  user: number; name: string; role: string; rank: number; of: number;
  points: string; deals: number; tier: Climb;
  incentives: { total: string; deals: IncentiveDeal[] };
  coins: number; rewards_total: number;
  history: HistoryRow[];
  contest_wins: { contest: string; rank: number | null; prize: string; coin_champion?: boolean }[];
};

export type ContestRow = {
  rank: number; user: number; name: string; initials: string; role: string;
  points: string; coins: number; is_subject: boolean;
};

export type Contest = {
  name: string; start: string; end: string;
  status: "upcoming" | "running" | "finished" | "awarded";
  days_left: number; starts_in: number; target: string | null;
  bumpers: { rank: number; prize: string }[];
  coin_champion_prize: string;
  board: ContestRow[]; coin_board: ContestRow[];
  me: { rank: number; points: string; coins: number; progress: number | null } | null;
  result: {
    winners: { rank: number; user: number; name: string; points: string; prize: string }[];
    coin_champion: { user?: number; name?: string; coins?: number; prize?: string };
  } | null;
};

export type Dashboard = {
  is_admin: boolean;
  viewer: { id: number; name: string; role: string };
  month: { key: string; label: string; start: string; end: string; days_left: number };
  rules: {
    bde_share: string; telecaller_share: string;
    prizes: { rank: number; medal: Medal; prize: string; coins: number }[];
    coin_champion_prize: string;
  };
  tiers: Tier[];
  board: BoardRow[];
  me: Me | null;
  last_month: { key: string; label: string; podium: PodiumRow[] } | null;
  hall_of_fame: { key: string; label: string; podium: PodiumRow[] }[];
  contest: Contest | null;
  kpis: { players: number; scoring: number; points: string; tiers_unlocked: number; incentives: string } | null;
};

export type Settings = {
  bde_share: string; telecaller_share: string;
  gold_prize: string; silver_prize: string; bronze_prize: string;
  gold_coins: number; silver_coins: number; bronze_coins: number;
  program_start: string;
  contest_name: string; contest_start: string | null; contest_end: string | null;
  contest_target: string | null;
  bumper_first: string; bumper_second: string; bumper_third: string;
  coin_champion_prize: string;
  tiers: { id?: number; name: string; reward: string; target: string; target_telecaller: string | null }[];
  updated_at: string;
};

// ── Formatting ──
export const num = (v: string | number | null | undefined) => Number(v || 0);
/** Points in Indian grouping: 1,25,000 */
export const pts = (v: string | number | null | undefined) => Math.round(num(v)).toLocaleString("en-IN");
export const inr = (v: string | number | null | undefined) => "₹" + Math.round(num(v)).toLocaleString("en-IN");
/** Short form for tight spaces: 12.5 L — the space unbreakable, so "L" never wraps away. */
export const short = (v: string | number | null | undefined) =>
  compactINR(Math.round(num(v))).replace(" ", " ");
export const roleLabel = (r: string) => (r === "bde" ? "BDE" : r === "tele_caller" ? "Tele caller" : r);
export const day = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });

/** A tier's target for someone in `role` — tele callers may climb a lower ladder. */
export const targetFor = (t: Tier, role: string) =>
  role === "tele_caller" && t.target_telecaller ? t.target_telecaller : t.target;

export const MEDALS: Record<Medal, { emoji: string; label: string; ring: string; soft: string; text: string }> = {
  gold:   { emoji: "🥇", label: "Gold",   ring: "from-amber-300 to-yellow-500", soft: "bg-amber-50",  text: "text-amber-700" },
  silver: { emoji: "🥈", label: "Silver", ring: "from-slate-300 to-slate-500",  soft: "bg-slate-100", text: "text-slate-700" },
  bronze: { emoji: "🥉", label: "Bronze", ring: "from-orange-300 to-orange-600", soft: "bg-orange-50", text: "text-orange-700" },
};

// ── The two calls ──
async function call(path: string, init?: RequestInit) {
  const token = localStorage.getItem(`${APP_SLUG}_access`);
  return fetch(`${getApiBase(APP_SLUG)}/api/rewards/${path}`, {
    ...init,
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json", ...(init?.headers || {}) },
  });
}

export async function loadDashboard(user?: number): Promise<{ data?: Dashboard; status: number; error?: string }> {
  const r = await call(user ? `?user=${user}` : "");
  const body = await r.json().catch(() => ({}));
  return r.ok ? { data: body, status: r.status } : { status: r.status, error: body.error || "Could not load rewards." };
}

export async function loadSettings(): Promise<Settings | null> {
  const r = await call("settings/");
  return r.ok ? r.json() : null;
}

export async function saveSettings(body: Partial<Settings>): Promise<{ ok: boolean; data?: Settings; errors?: string[] }> {
  const r = await call("settings/", { method: "PUT", body: JSON.stringify(body) });
  const data = await r.json().catch(() => ({}));
  if (r.ok) return { ok: true, data };
  return { ok: false, errors: flattenErrors(data) };
}

/** DRF errors, nested or not, as plain sentences. */
function flattenErrors(body: unknown, prefix = ""): string[] {
  if (body == null) return [];
  if (typeof body === "string") return [prefix ? `${prefix}: ${body}` : body];
  if (Array.isArray(body)) {
    return body.flatMap((item, i) =>
      typeof item === "object" && item !== null && !Array.isArray(item)
        ? flattenErrors(item, `Tier ${i + 1}`)
        : flattenErrors(item, prefix));
  }
  if (typeof body === "object") {
    return Object.entries(body as Record<string, unknown>).flatMap(([key, value]) =>
      flattenErrors(value, key === "non_field_errors" || key === "tiers" || key === "detail" ? prefix
        : prefix ? `${prefix} ${key.replace(/_/g, " ")}` : key.replace(/_/g, " ")));
  }
  return [];
}

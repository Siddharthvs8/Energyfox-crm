// ─── Default lead status metadata ─────────────────────────────────────────────
export const DEFAULT_STATUS_META: Record<string, { label: string; bg: string; text: string; dot: string; hex: string }> = {
  new:                { label: "New",               bg: "bg-indigo-50",  text: "text-indigo-700",  dot: "bg-indigo-400",  hex: "#6366f1" },
  follow_up:          { label: "Follow up",         bg: "bg-amber-50",   text: "text-amber-700",   dot: "bg-amber-400",   hex: "#f59e0b" },
  positive:           { label: "Positive",          bg: "bg-cyan-50",    text: "text-cyan-700",    dot: "bg-cyan-500",    hex: "#06b6d4" },
  interested:         { label: "Interested",        bg: "bg-lime-50",    text: "text-lime-700",    dot: "bg-lime-500",    hex: "#84cc16" },
  not_interested:     { label: "Not Interested",    bg: "bg-rose-50",    text: "text-rose-700",    dot: "bg-rose-500",    hex: "#f43f5e" },
  converted:          { label: "Converted",         bg: "bg-emerald-50", text: "text-emerald-700", dot: "bg-emerald-500", hex: "#10b981" },
};

// Rotating palette for custom statuses (Tailwind classes + hex)
const CUSTOM_COLOR_PALETTE = [
  { bg: "bg-teal-50",    text: "text-teal-700",    dot: "bg-teal-500",    hex: "#14b8a6" },
  { bg: "bg-purple-50",  text: "text-purple-700",  dot: "bg-purple-500",  hex: "#a855f7" },
  { bg: "bg-blue-50",    text: "text-blue-700",     dot: "bg-blue-500",    hex: "#3b82f6" },
  { bg: "bg-green-50",   text: "text-green-700",    dot: "bg-green-500",   hex: "#22c55e" },
  { bg: "bg-rose-50",    text: "text-rose-700",     dot: "bg-rose-400",    hex: "#fb7185" },
  { bg: "bg-indigo-50",  text: "text-indigo-700",   dot: "bg-indigo-400",  hex: "#818cf8" },
  { bg: "bg-orange-50",  text: "text-orange-700",   dot: "bg-orange-400",  hex: "#fb923c" },
  { bg: "bg-cyan-50",    text: "text-cyan-700",     dot: "bg-cyan-400",    hex: "#22d3ee" },
];

export type StatusMeta = { label: string; bg: string; text: string; dot: string; hex: string };
export type StatusMetaMap = Record<string, StatusMeta>;

/**
 * Given an array of custom statuses from the API (each has { value, label }),
 * merge them with the default STATUS_META. Custom statuses get a colour from the palette.
 */
export function buildStatusMeta(
  customStatuses: { value: string; label: string }[]
): StatusMetaMap {
  const merged: StatusMetaMap = { ...DEFAULT_STATUS_META };
  customStatuses.forEach((s, i) => {
    if (!merged[s.value]) {
      const palette = CUSTOM_COLOR_PALETTE[i % CUSTOM_COLOR_PALETTE.length];
      merged[s.value] = { label: s.label, ...palette };
    }
  });
  return merged;
}

/**
 * Build a flat {value, label} array from a StatusMetaMap, suitable for <select> options.
 */
export function buildStatusOptions(meta: StatusMetaMap) {
  return Object.entries(meta).map(([value, m]) => ({ value, label: m.label }));
}

/**
 * Fallback meta for unknown statuses (renders as a neutral grey badge).
 */
export const FALLBACK_STATUS_META: StatusMeta = {
  label: "Unknown",
  bg: "bg-slate-100",
  text: "text-slate-600",
  dot: "bg-slate-400",
  hex: "#94a3b8",
};

export function getLatestNote(notes: string | null | undefined): string {
  if (!notes) return "No notes added yet.";
  const trimmed = notes.trim();
  if (!trimmed) return "No notes added yet.";

  // Split by double newlines to get blocks
  const blocks = trimmed.split(/\r?\n\s*\r?\n/).map(b => b.trim()).filter(Boolean);
  if (blocks.length === 0) return "No notes added yet.";

  const lastBlock = blocks[blocks.length - 1];

  // If the last block contains multiple clean notes appended with single newlines,
  // split it by single newlines
  const lines = lastBlock.split(/\r?\n/).map(l => l.trim()).filter(Boolean);
  if (lines.length <= 1) return lastBlock;

  // Check if the last line is a note, and the line before it is a timestamp
  const lastLine = lines[lines.length - 1];
  const secondToLastLine = lines[lines.length - 2];
  const isTimestamp = /^\[\d{1,2}\s+[A-Za-z]{3}\s+\d{4},\s+\d{1,2}:\d{2}\s+[ap]m\]$/i.test(secondToLastLine);

  if (isTimestamp) {
    return `${secondToLastLine}\n${lastLine}`;
  }

  return lastLine;
}


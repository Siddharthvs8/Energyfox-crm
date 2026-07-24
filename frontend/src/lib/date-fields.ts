/**
 * Helpers for date fields that are stored as free text (completion-doc and
 * warranty form JSON) but edited with a native <input type="date"> picker.
 *
 * The picker only accepts ISO (yyyy-mm-dd); the documents print dd/mm/yyyy.
 * Existing records may hold either format, so both directions are lenient.
 */

/** Format a stored value for an <input type="date"> (returns "" if unparseable). */
export function toISODate(value: string | null | undefined): string {
  const v = String(value || "").trim();
  if (!v) return "";
  if (/^\d{4}-\d{2}-\d{2}$/.test(v)) return v;                 // already ISO
  const m = v.match(/^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$/);    // dd/mm/yyyy
  if (m) {
    const [, d, mo, y] = m;
    return `${y}-${mo.padStart(2, "0")}-${d.padStart(2, "0")}`;
  }
  return "";
}

/** Format a stored value for printing on a document (dd/mm/yyyy). */
export function toDisplayDate(value: string | null | undefined): string {
  const v = String(value || "").trim();
  if (!v) return "";
  const m = v.match(/^(\d{4})-(\d{2})-(\d{2})$/);              // ISO
  if (m) {
    const [, y, mo, d] = m;
    return `${d}/${mo}/${y}`;
  }
  return v;                                                    // already dd/mm/yyyy
}

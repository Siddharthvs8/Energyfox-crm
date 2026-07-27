/**
 * Night mode.
 *
 * A `dark` class on <html> switches on the override layer at the bottom of
 * globals.css, which remaps the light utilities the app is written in. The choice
 * is a personal display preference, so it lives in localStorage per browser
 * rather than on the server (unlike the org-wide accent theme in themes.ts).
 */
const KEY = "energyfox_night_mode";

export function isNightMode(): boolean {
  if (typeof document === "undefined") return false;
  return document.documentElement.classList.contains("dark");
}

/** Stored choice, or the OS preference the first time round. */
export function preferredNightMode(): boolean {
  if (typeof window === "undefined") return false;
  const saved = localStorage.getItem(KEY);
  if (saved === "on") return true;
  if (saved === "off") return false;
  return !!window.matchMedia?.("(prefers-color-scheme: dark)").matches;
}

export function applyNightMode(on: boolean, remember = true) {
  if (typeof document === "undefined") return;
  document.documentElement.classList.toggle("dark", on);
  if (remember) localStorage.setItem(KEY, on ? "on" : "off");
}

/** Call once on mount so a reload keeps the last choice. */
export function initNightMode() {
  applyNightMode(preferredNightMode(), false);
}

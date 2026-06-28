/**
 * Accent-colour themes for the app chrome (sidebar, buttons, focus rings, accents).
 *
 * The super admin picks one under Settings; it is stored on OrgSettings.theme and
 * applied app-wide by overriding the `--accent-*` CSS variables (see globals.css)
 * on <html> via {@link applyTheme}. The app stays light-mode.
 */
export type ThemeKey = "indigo" | "violet" | "emerald" | "rose" | "amber" | "sky";

export type ThemePreset = {
  key: ThemeKey;
  label: string;
  primary: string;
  primaryHover: string;
  secondary: string;
  gradient: string;
  ring: string; // focus ring rgba
  soft: string; // soft tint (active backgrounds)
};

export const THEMES: ThemePreset[] = [
  { key: "indigo", label: "Indigo", primary: "#6366f1", primaryHover: "#818cf8", secondary: "#06b6d4",
    gradient: "linear-gradient(135deg, #6366f1 0%, #06b6d4 100%)", ring: "rgba(99,102,241,0.35)", soft: "rgba(99,102,241,0.12)" },
  { key: "violet", label: "Violet", primary: "#7c3aed", primaryHover: "#8b5cf6", secondary: "#d946ef",
    gradient: "linear-gradient(135deg, #7c3aed 0%, #d946ef 100%)", ring: "rgba(124,58,237,0.35)", soft: "rgba(124,58,237,0.12)" },
  { key: "emerald", label: "Emerald", primary: "#059669", primaryHover: "#10b981", secondary: "#14b8a6",
    gradient: "linear-gradient(135deg, #059669 0%, #14b8a6 100%)", ring: "rgba(5,150,105,0.35)", soft: "rgba(5,150,105,0.12)" },
  { key: "rose", label: "Rose", primary: "#e11d48", primaryHover: "#f43f5e", secondary: "#fb7185",
    gradient: "linear-gradient(135deg, #e11d48 0%, #fb7185 100%)", ring: "rgba(225,29,72,0.35)", soft: "rgba(225,29,72,0.12)" },
  { key: "amber", label: "Amber", primary: "#d97706", primaryHover: "#f59e0b", secondary: "#f59e0b",
    gradient: "linear-gradient(135deg, #d97706 0%, #f59e0b 100%)", ring: "rgba(217,119,6,0.35)", soft: "rgba(217,119,6,0.12)" },
  { key: "sky", label: "Sky", primary: "#0284c7", primaryHover: "#0ea5e9", secondary: "#06b6d4",
    gradient: "linear-gradient(135deg, #0284c7 0%, #06b6d4 100%)", ring: "rgba(2,132,199,0.35)", soft: "rgba(2,132,199,0.12)" },
];

export const DEFAULT_THEME: ThemeKey = "indigo";

export function getThemePreset(key?: string | null): ThemePreset {
  return THEMES.find(t => t.key === key) || THEMES[0];
}

/** Apply a theme by overriding the global `--accent-*` CSS variables on <html>. */
export function applyTheme(key?: string | null) {
  if (typeof document === "undefined") return;
  const t = getThemePreset(key);
  const r = document.documentElement.style;
  r.setProperty("--accent-primary", t.primary);
  r.setProperty("--accent-primary-hover", t.primaryHover);
  r.setProperty("--accent-secondary", t.secondary);
  r.setProperty("--accent-gradient", t.gradient);
  r.setProperty("--accent-ring", t.ring);
  r.setProperty("--accent-soft", t.soft);
}

"use client";
/**
 * The site's Google Maps location.
 *
 * Pinned by the BDE on the site visit (leads/[id]/SiteVisitSection) — one tap
 * takes the device's own position — and read by the stages that go out to the
 * site: purchase & logistics and the project team, on their customer cards and
 * in "View site visit details". The links open Google Maps itself, which on a
 * phone is the Maps app, directions included.
 */
import React from "react";

/** The location fields of a site visit, as the API sends them. */
export type SiteLocationData = {
  site_latitude?: string | number | null;
  site_longitude?: string | number | null;
  site_location_accuracy?: number | null;
  site_location_source?: string | null;
  site_location_captured_at?: string | null;
  site_location_captured_by_name?: string | null;
};

export type Pin = { lat: number; lng: number };

/** Past this the device was guessing: indoors, or a laptop placing itself by Wi-Fi. */
export const LOW_ACCURACY_METRES = 100;

const blank = (v: unknown) => v === null || v === undefined || String(v).trim() === "";

/** The pin, or null when the site visit has none. */
export function pinOf(loc?: SiteLocationData | null): Pin | null {
  if (!loc || blank(loc.site_latitude) || blank(loc.site_longitude)) return null;
  const lat = Number(loc.site_latitude);
  const lng = Number(loc.site_longitude);
  return Number.isFinite(lat) && Number.isFinite(lng) ? { lat, lng } : null;
}

const at = (p: Pin) => `${p.lat},${p.lng}`;
export const mapsUrl = (p: Pin) => `https://www.google.com/maps/search/?api=1&query=${at(p)}`;
export const directionsUrl = (p: Pin) => `https://www.google.com/maps/dir/?api=1&destination=${at(p)}`;
const embedUrl = (p: Pin) => `https://maps.google.com/maps?q=${at(p)}&z=17&output=embed`;

/** "10.016789, 76.345679" */
export const coordsLabel = (p: Pin) => `${p.lat.toFixed(6)}, ${p.lng.toFixed(6)}`;

/** How the pin was taken, by whom and when — the line under it. */
export function pinNote(loc: SiteLocationData): string {
  const parts: string[] = [];
  if (loc.site_location_source === "gps") {
    parts.push(loc.site_location_accuracy != null
      ? `Device location, accurate to ±${loc.site_location_accuracy} m` : "Device location");
  } else if (loc.site_location_source === "manual") {
    parts.push("Entered by hand");
  }
  if (loc.site_location_captured_by_name) parts.push(`by ${loc.site_location_captured_by_name}`);
  if (loc.site_location_captured_at) {
    parts.push(new Date(loc.site_location_captured_at).toLocaleString("en-IN", {
      day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit",
    }));
  }
  return parts.join(" · ");
}

export const isLowAccuracy = (loc: SiteLocationData) =>
  loc.site_location_source === "gps" && (loc.site_location_accuracy ?? 0) > LOW_ACCURACY_METRES;

/** The pin on a small Google map. */
export function SiteMap({ pin, className = "h-48" }: { pin: Pin; className?: string }) {
  return (
    <iframe title="Site location on Google Maps" src={embedUrl(pin)} loading="lazy"
      referrerPolicy="no-referrer-when-downgrade"
      className={`w-full rounded-xl border border-slate-200 bg-slate-100 ${className}`} />
  );
}

const linkCls =
  "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition whitespace-nowrap";

/** Open in Google Maps, and Directions to it from wherever the reader is. */
export function SiteLocationLinks({ pin }: { pin: Pin }) {
  return (
    <div className="flex flex-wrap gap-2">
      <a href={mapsUrl(pin)} target="_blank" rel="noreferrer"
        className={`${linkCls} bg-indigo-600 text-white hover:bg-indigo-700`}>
        <svg width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M12 21s-7-6.2-7-11.5A7 7 0 0 1 19 9.5C19 14.8 12 21 12 21z" /><circle cx="12" cy="9.5" r="2.5" />
        </svg>
        Open in Google Maps
      </a>
      <a href={directionsUrl(pin)} target="_blank" rel="noreferrer"
        className={`${linkCls} bg-white border border-slate-300 text-slate-700 hover:bg-slate-50`}>
        <svg width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M3 11l18-8-8 18-2-8-8-2z" />
        </svg>
        Directions
      </a>
    </div>
  );
}

/** A customer card's "Site Location" cell, for the stages after the site visit. */
export function SiteLocationCell({ loc }: { loc?: SiteLocationData | null }) {
  const pin = pinOf(loc);
  return (
    <div className="sm:col-span-2 lg:col-span-3">
      <p className="text-[10px] text-slate-400 uppercase tracking-wide">Site Location (Google Maps)</p>
      {pin && loc ? (
        <div className="mt-1 space-y-1.5">
          <SiteLocationLinks pin={pin} />
          <p className="text-[11px] text-slate-500">
            <span className="font-mono text-slate-600">{coordsLabel(pin)}</span>
            {pinNote(loc) ? ` · ${pinNote(loc)}` : ""}
          </p>
          {isLowAccuracy(loc) && (
            <p className="text-[11px] font-semibold text-amber-700">
              Low accuracy — the pin may be off by up to {loc.site_location_accuracy} m.
            </p>
          )}
        </div>
      ) : (
        <p className="text-sm font-medium text-slate-300">Not pinned on the site visit</p>
      )}
    </div>
  );
}

/**
 * Coordinates typed or pasted by hand: "10.016789, 76.345679", or a Google
 * Maps link with the place in it. A short maps.app.goo.gl link only names the
 * place on Google's side, so it cannot be read here — "short-link" says so.
 */
export function parsePin(raw: string): Pin | "short-link" | null {
  const text = raw.trim();
  if (!text) return null;
  if (/(maps\.app\.goo\.gl|goo\.gl\/maps)/i.test(text)) return "short-link";
  const n = "(-?\\d{1,3}(?:\\.\\d+)?)";
  const patterns = [
    // A place's own pin, in the data part of a link. Comes before "@", which
    // is only where the map was centred when the link was copied.
    new RegExp(`!3d${n}!4d${n}`),
    new RegExp(`@${n},${n}`),
    new RegExp(`[?&](?:q|query|ll|destination|center)=${n}(?:,|%2C)\\s*${n}`, "i"),
    new RegExp(`^${n}\\s*[,\\s]\\s*${n}$`),
  ];
  for (const re of patterns) {
    const m = text.match(re);
    if (!m) continue;
    const lat = Number(m[1]);
    const lng = Number(m[2]);
    if (Math.abs(lat) <= 90 && Math.abs(lng) <= 180 && !(lat === 0 && lng === 0)) return { lat, lng };
  }
  return null;
}

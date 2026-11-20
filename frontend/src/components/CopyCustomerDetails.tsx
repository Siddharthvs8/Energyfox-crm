"use client";
/**
 * "Copy customer details" — who the customer is, the plant, where to go and how
 * to reach them, as one block of text on the clipboard, ready to paste into a
 * message to the crew. Sits beside "View site visit details" on the purchase &
 * logistics and project pages:
 *
 *   name  : Resmi M
 *   kw  : 5kw Flat
 *   address  : Keezhayikonam Venjaramoodu P.O Thiruvananthapuram,695607
 *   phone number  : 8921734513
 *   location  : https://www.google.com/maps/search/?api=1&query=8.900612,76.716713
 *
 * The location is the pin the BDE took on the site visit, as a Google Maps link
 * that opens the Maps app on a phone.
 */
import React, { useEffect, useRef, useState } from "react";
import { mapsUrl, pinOf, type SiteLocationData } from "@/components/SiteLocation";

/** What the text is built from: the lead, and its site visit. */
export type CustomerDetails = {
  name: string;
  phone?: string | null;
  installation_location?: string | null;
  /** The lead's "Location" — a place, such as Kochi. */
  location?: string | null;
  district?: string | null;
  siteVisit?: (SiteLocationData & {
    plant_capacity?: string | null;
    feasible_capacity?: string | null;
    roof_type?: string | null;
    rcc_roof_types?: string[] | null;
  }) | null;
};

const ROOFS: Record<string, string> = { rcc: "RCC", sheet: "Sheet", mixed: "Mixed" };
const RCC_KINDS: Record<string, string> = { flat: "Flat", slope: "Slope", tiled: "Tiled", non_linear: "Non linear" };

/** "5kw Flat": the plant's capacity and the roof it goes on. The capacity is
 *  the site visit's plant capacity, or its feasible capacity when that is all
 *  there is — the same fallback Documentation Stage 1 uses. */
export function plantLine(sv?: CustomerDetails["siteVisit"]): string {
  const raw = String(sv?.plant_capacity || sv?.feasible_capacity || "").trim();
  // "5", "5kw", "5 kW", "5 kWp" all read as "5kw"; anything else ("5000 W")
  // is left as the BDE wrote it rather than guessed at.
  const kw = raw.match(/^(\d+(?:\.\d+)?)\s*(?:k\s*w\s*p?)?$/i);
  const capacity = kw ? `${kw[1]}kw` : raw;
  const kinds = sv?.roof_type === "rcc" ? (sv.rcc_roof_types || []).map(k => RCC_KINDS[k] || k) : [];
  const roof = kinds.length ? kinds.join("/") : sv?.roof_type ? ROOFS[sv.roof_type] || sv.roof_type : "";
  return [capacity, roof].filter(Boolean).join(" ");
}

/** Where the system goes: the installation location, or failing that the
 *  lead's place and district. */
export function addressLine(c: Pick<CustomerDetails, "installation_location" | "location" | "district">): string {
  const installAt = (c.installation_location || "").trim();
  if (installAt) return installAt;
  const place = (c.location || "").trim();
  const district = (c.district || "").trim();
  // The district only when the place does not already name it.
  const addDistrict = district && !place.toLowerCase().includes(district.toLowerCase());
  return [place, addDistrict ? district : ""].filter(Boolean).join(", ");
}

/** The block of text, in the shape the crews are sent. */
export function customerDetailsText(c: CustomerDetails): string {
  const pin = pinOf(c.siteVisit);
  const lines: [string, string][] = [
    ["name", c.name],
    ["kw", plantLine(c.siteVisit)],
    ["address", addressLine(c)],
    ["phone number", c.phone || ""],
    ["location", pin ? mapsUrl(pin) : "Not pinned on the site visit"],
  ];
  return lines.map(([label, value]) => `${label}  : ${value.trim() || "—"}`).join("\n");
}

/** The clipboard, with the older route kept for browsers without the new one. */
async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch { /* fall through to the older route */ }
  try {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    const copied = document.execCommand("copy");
    document.body.removeChild(area);
    return copied;
  } catch {
    return false;
  }
}

export default function CopyCustomerDetails(props: CustomerDetails) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  const reset = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (reset.current) clearTimeout(reset.current); }, []);

  const copy = async () => {
    const copied = await copyText(customerDetailsText(props));
    setState(copied ? "copied" : "failed");
    if (reset.current) clearTimeout(reset.current);
    reset.current = setTimeout(() => setState("idle"), 2500);
  };

  return (
    <button type="button" onClick={copy}
      title="Name, capacity, address, phone and map link — copied, ready to paste"
      className={`inline-flex items-center gap-1.5 px-3 py-1.5 bg-white border rounded-lg text-xs font-semibold transition ${
        state === "copied" ? "border-emerald-300 text-emerald-700"
          : state === "failed" ? "border-rose-300 text-rose-600"
            : "border-slate-300 text-slate-700 hover:bg-slate-50"}`}>
      {state === "copied" ? (
        <svg width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M5 12.5l4.5 4.5L19 7.5" />
        </svg>
      ) : (
        <svg width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24" aria-hidden="true">
          <rect x="9" y="9" width="11" height="11" rx="2" /><path d="M5 15V5a2 2 0 0 1 2-2h10" />
        </svg>
      )}
      <span aria-live="polite">
        {state === "copied" ? "Copied" : state === "failed" ? "Could not copy" : "Copy customer details"}
      </span>
    </button>
  );
}

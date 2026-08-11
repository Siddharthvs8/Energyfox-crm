"use client";
import { useEffect, useState } from "react";
import { getApiBase } from "@/lib/mock-data";
import { APP_SLUG } from "@/lib/config";

/**
 * The active districts from Settings → Districts.
 *
 * The lead forms pick from this rather than taking free text, so a district
 * typed by hand lands in the same place an imported one does. The stored value
 * is still the name — see leads.models.District — so a lead filed under a
 * district that is later renamed or switched off keeps the text it had.
 */
export function useDistricts(): { districts: string[]; loading: boolean } {
  const [districts, setDistricts] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const token = typeof window !== "undefined"
      ? localStorage.getItem(`${APP_SLUG}_access`) : null;
    if (!token) { setLoading(false); return; }

    fetch(`${getApiBase(APP_SLUG)}/api/districts/?active=true`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(r => (r.ok ? r.json() : []))
      .then(d => {
        if (cancelled) return;
        const rows = Array.isArray(d) ? d : d.results || [];
        setDistricts(rows.map((x: any) => x.name).filter(Boolean));
      })
      .catch(() => { /* the picker falls back to whatever the lead already has */ })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, []);

  return { districts, loading };
}

/**
 * The options a district picker should offer for a given lead.
 *
 * The configured list, plus whatever the lead is already filed under if that is
 * no longer on it — otherwise opening an old lead and saving would quietly drop
 * a district nobody meant to clear.
 */
export function districtOptions(configured: string[], current?: string | null): string[] {
  const value = (current || "").trim();
  if (!value) return configured;
  return configured.some(d => d.toLowerCase() === value.toLowerCase())
    ? configured
    : [...configured, value];
}

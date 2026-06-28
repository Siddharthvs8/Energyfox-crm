"use client";
import { useState, useEffect } from "react";
import { getApiBase } from "@/lib/mock-data";
import { APP_SLUG } from "@/lib/config";
import {
  buildStatusMeta,
  buildStatusOptions,
  DEFAULT_STATUS_META,
  StatusMetaMap,
  FALLBACK_STATUS_META,
} from "@/lib/lead-statuses";

export type StatusOption = { value: string; label: string };

interface UseLeadStatusesReturn {
  statusMeta: StatusMetaMap;
  statusOptions: StatusOption[];
  getStatusMeta: (status: string) => StatusMetaMap[string];
  loading: boolean;
}

/**
 * Fetches the merged list of standard + custom lead statuses from the API.
 * Falls back to default statuses if the fetch fails or the user is unauthenticated.
 *
 * The optional argument is ignored (kept for call-site compatibility).
 */
export function useLeadStatuses(_domain?: string): UseLeadStatusesReturn {
  const domain = APP_SLUG;
  const [statusMeta, setStatusMeta] = useState<StatusMetaMap>(DEFAULT_STATUS_META);
  const [statusOptions, setStatusOptions] = useState<StatusOption[]>(
    buildStatusOptions(DEFAULT_STATUS_META)
  );
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!domain) return;

    let cancelled = false;

    const fetchStatuses = async () => {
      const token =
        typeof window !== "undefined"
          ? localStorage.getItem(`${domain}_access`)
          : null;

      if (!token) {
        setLoading(false);
        return;
      }

      try {
        const r = await fetch(`${getApiBase(domain)}/api/leads/statuses/`, {
          headers: { Authorization: `Bearer ${token}` },
        });

        if (!r.ok) throw new Error("Failed to fetch statuses");

        const data: { value: string; label: string }[] = await r.json();

        if (cancelled) return;

        // Separate standard from custom statuses for the merge
        const customOnly = data.filter(
          (s) => !DEFAULT_STATUS_META[s.value]
        );
        const merged = buildStatusMeta(customOnly);
        setStatusMeta(merged);
        setStatusOptions(buildStatusOptions(merged));
      } catch {
        // Keep defaults on error — no-op
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    fetchStatuses();

    return () => {
      cancelled = true;
    };
  }, [domain]);

  const getStatusMeta = (status: string) =>
    statusMeta[status] ?? FALLBACK_STATUS_META;

  return { statusMeta, statusOptions, getStatusMeta, loading };
}

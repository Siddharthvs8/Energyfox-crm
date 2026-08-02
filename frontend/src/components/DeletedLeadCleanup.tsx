"use client";
/**
 * Cleanup control for a deleted lead's leftovers in a downstream module.
 *
 * Trashing a lead hides it from the Leads page but leaves the rows it had
 * already created in documentation, accounts, purchase, project and liasoning —
 * where they cannot be opened, because the detail page will not serve a trashed
 * lead. This marks those rows and lets an admin clear them out module by module.
 *
 * The button only renders for a lead the server has flagged `lead_deleted`, and
 * the endpoint refuses anything still active, so a live customer cannot be
 * pulled out of a workflow with it.
 */
import React, { useState } from "react";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";

export type ModuleKey =
  | "documentation" | "documentation-stage2" | "accounts"
  | "purchase" | "project" | "liasoning";

/** The amber "deleted" chip shown next to the customer's name. */
export function DeletedLeadBadge() {
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-50 border border-amber-200 text-amber-700 text-[10px] font-bold uppercase tracking-wide">
      Lead deleted
    </span>
  );
}

export default function DeletedLeadCleanup({ leadId, module, name, onRemoved, className }: {
  leadId: number | string;
  module: ModuleKey;
  name?: string;
  onRemoved?: () => void;
  className?: string;
}) {
  const [busy, setBusy] = useState(false);

  const remove = async (e: React.MouseEvent) => {
    // These rows usually sit inside a link to the (unopenable) detail page.
    e.preventDefault();
    e.stopPropagation();
    const who = name ? `"${name}"` : "this customer";
    if (!confirm(
      `Remove ${who} from this module?\n\n` +
      `The lead has been deleted, so this only clears the leftover data it had ` +
      `here. It cannot be undone.`
    )) return;

    setBusy(true);
    try {
      const token = localStorage.getItem(`${APP_SLUG}_access`);
      const r = await fetch(
        `${getApiBase(APP_SLUG)}/api/leads/${leadId}/remove-from-module/?module=${module}`,
        { method: "DELETE", headers: { Authorization: `Bearer ${token}` } },
      );
      const d = await r.json().catch(() => ({}));
      if (!r.ok) { alert(d.error || "Could not remove it."); return; }
      onRemoved?.();
    } catch {
      alert("Network error while removing it.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <button onClick={remove} disabled={busy}
      title="Clear this deleted lead's leftover data from this module"
      className={className ||
        "px-2.5 py-1 rounded-lg bg-rose-600 text-white text-[11px] font-bold hover:bg-rose-700 transition disabled:opacity-40"}>
      {busy ? "Removing…" : "Delete"}
    </button>
  );
}

"use client";
/**
 * The customer's tracking link, from the documentation desk's side.
 *
 * Appears once Documentation Stage 1 is complete — before that the customer
 * would open a tracker with nothing on it. Generating is deliberately explicit
 * rather than automatic: handing a customer a live link is a small promise, and
 * the person making it should be the one who decides when.
 *
 * The link is created once and reused. Re-generating would silently break the
 * one already sitting in the customer's inbox, so the button only ever hands
 * back the same address.
 */
import { useCallback, useEffect, useState } from "react";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";

type Link = {
  exists: boolean; url?: string; token?: string; revoked?: boolean; is_live?: boolean;
  expires_at?: string | null; view_count?: number; last_viewed_at?: string | null;
  last_sent_at?: string | null;
  // Only on the reply to generating: whether it also reached the customer.
  sent?: boolean; sent_to?: string; send_error?: string | null;
};

const when = (iso?: string | null) =>
  iso ? new Date(iso).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) : null;

export default function TrackingLinkPanel({ leadId, customerEmail }: {
  leadId: number;
  customerEmail?: string | null;
}) {
  const api = getApiBase(APP_SLUG);
  const [link, setLink] = useState<Link | null>(null);
  const [busy, setBusy] = useState<"" | "make" | "send" | "revoke">("");
  const [copied, setCopied] = useState(false);
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);

  const auth = useCallback(() => ({
    "Content-Type": "application/json",
    Authorization: `Bearer ${localStorage.getItem(`${APP_SLUG}_access`)}`,
  }), []);

  const load = useCallback(async () => {
    try {
      const r = await fetch(`${api}/api/leads/${leadId}/tracking-link/`, { headers: auth() });
      if (r.ok) setLink(await r.json());
    } catch { /* the panel simply offers to generate */ }
  }, [api, leadId, auth]);

  useEffect(() => { load(); }, [load]);

  const call = async (path: string, kind: "make" | "send" | "revoke", body?: any) => {
    setBusy(kind); setNote(null);
    try {
      const r = await fetch(`${api}/api/leads/${leadId}/tracking-link${path}`, {
        method: "POST", headers: auth(), body: JSON.stringify(body || {}),
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok && !d.url) { setNote({ ok: false, text: d.error || "That did not work." }); return; }
      setLink(d);
      if (kind === "send") {
        setNote(d.sent
          ? { ok: true, text: `Sent to ${d.to}.` }
          : { ok: false, text: d.error || "The email could not be sent." });
      }
      // Generating emails the link on its own. Say either way: an unsent link
      // is still a working link, but only if somebody knows to send it.
      if (kind === "make") {
        setNote(d.sent
          ? { ok: true, text: `Link generated and emailed to ${d.sent_to}.` }
          // The reason is a sentence from the server or the mail host, which may
          // or may not already end in a full stop — trimmed so it never doubles.
          : { ok: false, text: `Link generated, but not emailed — ${
              (d.send_error || "the email could not be sent").replace(/\.\s*$/, "")
            }. Copy it below and send it yourself.` });
      }
    } catch {
      setNote({ ok: false, text: "Network error — nothing changed." });
    } finally { setBusy(""); }
  };

  const copy = async () => {
    if (!link?.url) return;
    try {
      await navigator.clipboard.writeText(link.url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      setNote({ ok: false, text: "Could not copy — select the link and copy it by hand." });
    }
  };

  return (
    <div className="mt-6 bg-white border border-slate-200 rounded-2xl px-5 py-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-xs font-bold text-indigo-600 uppercase tracking-wide">
            Customer tracking link
          </h3>
          <p className="text-[11px] text-slate-400 mt-0.5">
            A page the customer can open to follow their installation — no login needed.
            Generating it emails it to them.
          </p>
        </div>
        {!link?.exists && (
          <button onClick={() => call("/", "make")} disabled={busy === "make"}
            className="px-4 py-2 rounded-xl bg-indigo-600 text-white text-xs font-bold
                       hover:bg-indigo-700 disabled:opacity-50 transition">
            {busy === "make" ? "Generating & sending…" : "Generate & send tracking link"}
          </button>
        )}
      </div>

      {link?.exists && (
        <>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <code className="flex-1 min-w-[220px] text-[12px] bg-slate-50 border border-slate-200
                             rounded-lg px-3 py-2 text-slate-700 truncate" title={link.url}>
              {link.url}
            </code>
            <button onClick={copy}
              className="px-3 py-2 rounded-lg border border-slate-200 text-xs font-bold
                         text-slate-600 hover:bg-slate-50 transition">
              {copied ? "Copied ✓" : "Copy"}
            </button>
            <a href={link.url} target="_blank" rel="noreferrer"
              className="px-3 py-2 rounded-lg border border-slate-200 text-xs font-bold
                         text-slate-600 hover:bg-slate-50 transition">
              Open
            </a>
            <button onClick={() => call("/send", "send")} disabled={busy === "send"}
              title={customerEmail ? `Email ${customerEmail}` : "This customer has no email on file"}
              className="px-3 py-2 rounded-lg bg-slate-800 text-white text-xs font-bold
                         hover:bg-slate-900 disabled:opacity-50 transition">
              {busy === "send" ? "Sending…" : "Re-send email"}
            </button>
          </div>

          <div className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-slate-400">
            {/* Whether the customer ever opened it is the only evidence the
                address was right and the mail arrived. */}
            <span>
              {link.view_count
                ? `Opened ${link.view_count} time${link.view_count === 1 ? "" : "s"}${
                    link.last_viewed_at ? ` · last ${when(link.last_viewed_at)}` : ""}`
                : "Not opened yet"}
            </span>
            {link.last_sent_at && <span>Emailed {when(link.last_sent_at)}</span>}
            {link.expires_at && <span>Expires {when(link.expires_at)}</span>}
            <button onClick={() => call("/revoke", "revoke")} disabled={busy === "revoke"}
              className="ml-auto font-semibold text-rose-500 hover:text-rose-700 disabled:opacity-50">
              {link.revoked ? "Restore link" : "Revoke link"}
            </button>
          </div>

          {link.revoked && (
            <p className="mt-2 text-[11px] font-semibold text-rose-600">
              Revoked — the customer now sees “this link is not valid”.
            </p>
          )}
        </>
      )}

      {note && (
        <p className={`mt-2.5 text-[12px] font-medium ${
          note.ok ? "text-emerald-600" : "text-rose-600"}`}>{note.text}</p>
      )}
    </div>
  );
}

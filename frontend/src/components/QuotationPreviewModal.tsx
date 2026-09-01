"use client";
/**
 * The quotation as the customer will receive it.
 *
 * Not a rendering of the figures a second time — the actual PDF, built by the
 * same call that Download and Send use. Anything else would be a preview of
 * something nobody is ever sent, and the one thing a preview has to be is the
 * document itself.
 *
 * Opened from the Quotation module's list and from a lead's own page.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";
import { buildProformaPdf, proformaFileName } from "@/lib/proformaPdf";

export default function QuotationPreviewModal({ quotation, onClose, onSent }: {
  /** null closes it; an object opens it on that quotation. */
  quotation: { id: number; number: string; lead_name?: string | null } | null;
  onClose: () => void;
  onSent?: () => void;
}) {
  const api = getApiBase(APP_SLUG);
  const token = () => localStorage.getItem(`${APP_SLUG}_access`);

  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"" | "send">("");
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);
  // Kept so Download and Send reuse the built document rather than rebuilding
  // it — and so the object URL can be released when this closes.
  const docRef = useRef<any>(null);

  const build = useCallback(async (id: number) => {
    setError(null); setUrl(null); setNote(null);
    try {
      const r = await fetch(`${api}/api/quotations/${id}/document/`, {
        headers: { Authorization: `Bearer ${token()}` } });
      if (!r.ok) { setError("Could not load this quotation."); return; }
      const doc = await buildProformaPdf(await r.json());
      docRef.current = doc;
      setUrl(URL.createObjectURL(doc.output("blob")));
    } catch {
      setError("Could not build the document.");
    }
  }, [api]);

  useEffect(() => {
    if (quotation) build(quotation.id);
  }, [quotation, build]);

  // A blob URL outlives the component unless it is revoked, and a few of these
  // left behind is a few PDFs held in memory for the rest of the session.
  useEffect(() => () => { if (url) URL.revokeObjectURL(url); }, [url]);

  if (!quotation) return null;

  const fileName = `${proformaFileName(quotation.number, quotation.lead_name ?? null)}.pdf`;

  const download = () => docRef.current?.save(fileName);

  const send = async () => {
    if (!docRef.current) return;
    setBusy("send"); setNote(null);
    try {
      const fd = new FormData();
      fd.append("pdf", docRef.current.output("blob"), fileName);
      fd.append("channels", "email");
      const r = await fetch(`${api}/api/quotations/${quotation.id}/send/`, {
        method: "POST", headers: { Authorization: `Bearer ${token()}` }, body: fd });
      const d = await r.json().catch(() => ({}));
      setNote(d.sent
        ? { ok: true, text: `Sent to ${d.sent_to || "the customer"}.` }
        : { ok: false, text: d.error || (d.failures || []).join(" ") || "Could not send it." });
      if (d.sent) onSent?.();
    } catch { setNote({ ok: false, text: "Could not send this quotation." }); }
    finally { setBusy(""); }
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={onClose}>
      <div className="bg-white rounded-2xl w-full max-w-4xl h-[90vh] flex flex-col shadow-xl"
        onClick={e => e.stopPropagation()}>
        <div className="px-6 py-4 border-b border-slate-100 flex flex-wrap items-center gap-3">
          <div className="min-w-0">
            <h2 className="text-base font-black text-slate-900 truncate">{quotation.number}</h2>
            {quotation.lead_name && (
              <p className="text-[11px] text-slate-400 truncate">{quotation.lead_name}</p>
            )}
          </div>
          <div className="ml-auto flex items-center gap-2">
            {/* Not every browser embeds a PDF — some hand it to a plugin, some
                refuse entirely. This is the way out that always works. */}
            <a href={url || undefined} target="_blank" rel="noreferrer"
              className={`px-4 py-2 rounded-xl border border-slate-200 text-xs font-bold transition ${
                url ? "text-slate-600 hover:bg-slate-50" : "text-slate-300 pointer-events-none"}`}>
              Open in tab
            </a>
            <button onClick={download} disabled={!url}
              className="px-4 py-2 rounded-xl border border-slate-200 text-xs font-bold text-slate-600 hover:bg-slate-50 disabled:opacity-40 transition">
              Download
            </button>
            <button onClick={send} disabled={!url || busy === "send"}
              className="px-4 py-2 rounded-xl bg-slate-800 text-white text-xs font-bold hover:bg-slate-900 disabled:opacity-40 transition">
              {busy === "send" ? "Sending…" : "Send"}
            </button>
            <button onClick={onClose} title="Close"
              className="p-2 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition">
              <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2"
                strokeLinecap="round" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12" /></svg>
            </button>
          </div>
        </div>

        {note && (
          <p className={`px-6 py-2 text-[12px] font-medium ${
            note.ok ? "text-emerald-600" : "text-rose-600"}`}>{note.text}</p>
        )}

        <div className="flex-1 min-h-0 bg-slate-100 rounded-b-2xl overflow-hidden">
          {error ? (
            <div className="h-full flex items-center justify-center text-sm text-rose-600">{error}</div>
          ) : url ? (
            <iframe src={url} title={`Quotation ${quotation.number}`}
              className="w-full h-full border-0" />
          ) : (
            <div className="h-full flex items-center justify-center text-sm text-slate-400">
              Building the document…
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

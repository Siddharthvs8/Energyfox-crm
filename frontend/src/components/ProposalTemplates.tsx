"use client";
/**
 * The proposal artwork, one approved document per system type.
 *
 * Here rather than in a settings screen because this is where system types are
 * chosen: someone setting up a project for a new type is the person who needs
 * to notice its template is missing.
 *
 * It has to be uploadable from the CRM at all, because the file lives in the
 * database and not in the code — it does not travel with a deployment, so every
 * environment needs its own copy. Without this the only way in was the Django
 * admin, which is not where anyone would look.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";

type Row = {
  system_type: string;
  system_type_display: string;
  uploaded: boolean;
  file_name?: string;
  uploaded_at?: string;
  uploaded_by_name?: string | null;
  pdf?: string;
};

const when = (iso?: string) =>
  iso ? new Date(iso).toLocaleDateString("en-IN", { dateStyle: "medium" }) : "";

export default function ProposalTemplates() {
  const api = getApiBase(APP_SLUG);
  const token = () => localStorage.getItem(`${APP_SLUG}_access`);

  const [rows, setRows] = useState<Row[]>([]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);
  // One input per row, so "Upload" opens the picker for that type alone.
  const pickers = useRef<Record<string, HTMLInputElement | null>>({});

  const load = useCallback(async () => {
    try {
      const r = await fetch(`${api}/api/quotation-templates/status/`, {
        headers: { Authorization: `Bearer ${token()}` } });
      if (r.ok) setRows(await r.json());
    } catch { /* the panel simply shows nothing */ }
  }, [api]);

  useEffect(() => { load(); }, [load]);

  const upload = async (systemType: string, file: File) => {
    setBusy(systemType); setNote(null);
    try {
      const fd = new FormData();
      fd.append("system_type", systemType);
      fd.append("pdf", file);
      const r = await fetch(`${api}/api/quotation-templates/`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token()}` },
        body: fd,
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) {
        const why = d.pdf?.[0] || d.detail || d.error
          || Object.values(d).flat().join(" ") || "Could not upload it.";
        setNote({ ok: false, text: why });
        return;
      }
      setNote({ ok: true, text: `${d.system_type_display} template uploaded.` });
      await load();
    } catch {
      setNote({ ok: false, text: "Network error — nothing was uploaded." });
    } finally { setBusy(null); }
  };

  const missing = rows.filter(r => !r.uploaded).length;

  return (
    <div className="bg-white border border-slate-200 rounded-2xl px-5 py-4 mb-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-xs font-bold text-indigo-600 uppercase tracking-wide">
            Proposal templates
          </h3>
          <p className="text-[11px] text-slate-400 mt-0.5">
            The designed document each system type&rsquo;s quotation is built on.
            {missing > 0 && ` ${missing} still to upload.`}
          </p>
        </div>
        <button onClick={() => setOpen(!open)}
          className="text-xs font-bold text-indigo-600 hover:text-indigo-800 transition">
          {open ? "Hide" : "Manage"}
        </button>
      </div>

      {open && (
        <div className="mt-4 space-y-2">
          {rows.map(row => (
            <div key={row.system_type}
              className="flex flex-wrap items-center gap-x-4 gap-y-2 border border-slate-100 rounded-xl px-4 py-3">
              <div className="min-w-0">
                <p className="text-sm font-semibold text-slate-900">{row.system_type_display}</p>
                <p className="text-[11px] text-slate-400 truncate">
                  {row.uploaded
                    ? `${row.file_name}${row.uploaded_at ? ` · ${when(row.uploaded_at)}` : ""}`
                      + (row.uploaded_by_name ? ` · ${row.uploaded_by_name}` : "")
                    : "No template — quotations of this type cannot produce a document."}
                </p>
              </div>
              <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wide ${
                row.uploaded ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>
                {row.uploaded ? "Ready" : "Missing"}
              </span>
              <div className="ml-auto flex items-center gap-3 text-xs font-bold">
                {row.uploaded && row.pdf && (
                  <a href={row.pdf} target="_blank" rel="noreferrer"
                    className="text-slate-500 hover:text-slate-800">View</a>
                )}
                <button onClick={() => pickers.current[row.system_type]?.click()}
                  disabled={busy === row.system_type}
                  className="text-indigo-600 hover:text-indigo-800 disabled:opacity-40">
                  {busy === row.system_type ? "Uploading…" : row.uploaded ? "Replace" : "Upload"}
                </button>
                <input type="file" accept="application/pdf,.pdf" className="hidden"
                  ref={el => { pickers.current[row.system_type] = el; }}
                  onChange={e => {
                    const file = e.target.files?.[0];
                    // Cleared so choosing the same file twice still fires.
                    e.target.value = "";
                    if (file) upload(row.system_type, file);
                  }} />
              </div>
            </div>
          ))}
        </div>
      )}

      {note && (
        <p className={`mt-3 text-[12px] font-medium ${
          note.ok ? "text-emerald-600" : "text-rose-600"}`}>{note.text}</p>
      )}
    </div>
  );
}

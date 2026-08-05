"use client";
import React, { useState } from "react";

/**
 * The outgoing email signature, in two forms.
 *
 * The plain one is what a mail client that refuses HTML will show, so it is
 * always sent. The HTML one is optional: set it and the CRM sends an HTML part
 * as well, with logo, links and formatting. Leave it blank and the plain text is
 * used for both.
 */
export default function EmailSignatureEditor({ plain, html, onPlain, onHtml }: {
  plain: string; html: string;
  onPlain: (v: string) => void;
  onHtml: (v: string) => void;
}) {
  // Opens on whichever one is already in use.
  const [mode, setMode] = useState<"plain" | "html">(html.trim() ? "html" : "plain");
  const [preview, setPreview] = useState(true);

  const inputCls = "w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition";

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-2">
        <label className="block text-sm font-semibold text-slate-700">Email Signature</label>
        <div className="inline-flex rounded-xl bg-slate-100 p-1">
          {([["plain", "Plain text"], ["html", "HTML"]] as const).map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => setMode(key)}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-colors ${
                mode === key ? "bg-white text-indigo-600 shadow-sm" : "text-slate-500 hover:text-slate-700"
              }`}
            >
              {label}
              {/* Which one is actually filled in, so the tabs are not a guess. */}
              {key === "html" && html.trim() && <span className="ml-1.5 text-emerald-500">●</span>}
            </button>
          ))}
        </div>
      </div>

      {mode === "plain" ? (
        <>
          <textarea rows={3} value={plain}
            onChange={(e) => onPlain(e.target.value)}
            placeholder={"Regards,\nEnergyFox Consultants Pvt Ltd\n9526 396 823 · energyfox.in"}
            className={inputCls} />
          <p className="text-xs text-slate-400 mt-2">
            Appended to every email the CRM sends. Always sent, so a client that blocks HTML still
            sees a signature.
          </p>
        </>
      ) : (
        <>
          <textarea rows={8} value={html} spellCheck={false}
            onChange={(e) => onHtml(e.target.value)}
            placeholder={'<p style="margin:0;font-family:Arial,sans-serif;font-size:13px;color:#334155">\n  Regards,<br>\n  <b>EnergyFox Consultants Pvt Ltd</b><br>\n  <a href="tel:+919526396823">9526 396 823</a> ·\n  <a href="https://energyfox.in">energyfox.in</a>\n</p>'}
            className={`${inputCls} font-mono text-[12px] leading-relaxed`} />
          <div className="flex flex-wrap items-center gap-3 mt-2">
            <p className="text-xs text-slate-400 flex-1 min-w-[240px]">
              Used for the HTML part of the message. Leave it blank to send the plain signature only.
              Inline <code className="text-slate-500">style=</code> attributes survive mail clients;
              stylesheets and scripts do not.
            </p>
            <button type="button" onClick={() => setPreview(v => !v)}
              className="px-3 py-1.5 rounded-lg bg-slate-100 text-slate-600 text-[11px] font-bold hover:bg-slate-200 transition whitespace-nowrap">
              {preview ? "Hide preview" : "Show preview"}
            </button>
          </div>
          {preview && html.trim() && (
            <div className="mt-3">
              <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wide mb-1.5">Preview</p>
              {/* The admin wrote this markup and it is going out in their own
                  mail, so it is rendered as-is — escaping it would defeat the
                  point of an HTML signature. */}
              <div className="bg-white border border-slate-200 rounded-xl px-4 py-3 overflow-x-auto"
                dangerouslySetInnerHTML={{ __html: html }} />
              <p className="text-[11px] text-slate-400 mt-1.5">
                Mail clients vary — send a test email to see how it really lands.
              </p>
            </div>
          )}
        </>
      )}
    </div>
  );
}

"use client";
import React, { useState } from "react";

/* A document slot that accepts PDFs/files directly, or images dropped in to be
   stitched into a single PDF. Used by the BDE site visit and Documentation
   Stage 1 so both render the purchase order / agreement slots identically.

   Presentational only — the caller supplies the file list and the upload
   handler, so each stage keeps its own storage and permission rules. */

const IMAGE_RE = /\.(jpe?g|png|webp|gif|bmp)$/i;
export const isImageFile = (f: File) => f.type.startsWith("image/") || IMAGE_RE.test(f.name);

/** Stitch images into one PDF file (lazily loads jsPDF). */
export async function generatePdfFromImages(images: File[], fileName: string): Promise<File> {
  const { jsPDF } = await import("jspdf");
  const doc = new jsPDF({ unit: "pt", format: "a4" });
  const pageW = doc.internal.pageSize.getWidth();
  const pageH = doc.internal.pageSize.getHeight();
  for (let i = 0; i < images.length; i++) {
    const dataUrl: string = await new Promise((res, rej) => {
      const fr = new FileReader();
      fr.onload = () => res(fr.result as string);
      fr.onerror = rej;
      fr.readAsDataURL(images[i]);
    });
    const dims: { w: number; h: number } = await new Promise((res, rej) => {
      const im = new Image();
      im.onload = () => res({ w: im.naturalWidth, h: im.naturalHeight });
      im.onerror = rej;
      im.src = dataUrl;
    });
    const ratio = Math.min(pageW / dims.w, pageH / dims.h);
    const w = dims.w * ratio;
    const h = dims.h * ratio;
    if (i > 0) doc.addPage();
    const fmt = dataUrl.startsWith("data:image/png") ? "PNG" : "JPEG";
    doc.addImage(dataUrl, fmt, (pageW - w) / 2, (pageH - h) / 2, w, h);
  }
  return new File([doc.output("blob")], fileName, { type: "application/pdf" });
}

const labelCls = "block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5";
const addBtnCls = (disabled: boolean) =>
  `inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-semibold transition ${disabled ? "bg-slate-100 text-slate-400 cursor-not-allowed" : "bg-slate-100 text-slate-700 hover:bg-slate-200 cursor-pointer"}`;

export default function PdfDropField({ docType, label, disabled, busy, addFiles, children }: {
  docType: string;
  label: string;
  disabled: boolean;
  busy: boolean;
  addFiles: (docType: string, files: File[]) => void | Promise<void>;
  /** The already-uploaded file list for this slot. */
  children?: React.ReactNode;
}) {
  const [images, setImages] = useState<File[]>([]);
  const [generating, setGenerating] = useState(false);
  const [dragActive, setDragActive] = useState(false);

  const addImages = (list: FileList | File[] | null) => {
    if (!list) return;
    const imgs = Array.from(list).filter(isImageFile);
    if (imgs.length) setImages(prev => [...prev, ...imgs]);
    else if (Array.from(list).length) alert("Please drop image files (JPG/PNG) here — use “Attach PDF / file(s)” for PDFs.");
  };

  const generate = async () => {
    if (!images.length) return;
    setGenerating(true);
    try {
      const pdf = await generatePdfFromImages(images, `${docType}.pdf`);
      await addFiles(docType, [pdf]);
      setImages([]);
    } catch { alert("Could not generate the PDF from those images."); }
    finally { setGenerating(false); }
  };

  return (
    <div className="sm:col-span-2 lg:col-span-3 border border-slate-200 rounded-xl p-4 bg-slate-50/60">
      <label className={labelCls}>{label}</label>
      {children}
      <div className="grid sm:grid-cols-2 gap-3">
        <div>
          <p className="text-[10px] text-slate-400 mb-1">Attach PDF / file(s)</p>
          <label className={addBtnCls(disabled || busy)}>
            {busy ? "Uploading…" : "+ Add file(s)"}
            <input type="file" accept="application/pdf,image/*" multiple disabled={disabled || busy} className="hidden"
              onChange={e => { const fs = Array.from(e.target.files || []); e.currentTarget.value = ""; addFiles(docType, fs); }} />
          </label>
        </div>
        <div>
          <p className="text-[10px] text-slate-400 mb-1">Or drop images → generate PDF</p>
          <div
            onDragEnter={e => { if (disabled) return; e.preventDefault(); e.stopPropagation(); setDragActive(true); }}
            onDragOver={e => { if (disabled) return; e.preventDefault(); e.stopPropagation(); e.dataTransfer.dropEffect = "copy"; setDragActive(true); }}
            onDragLeave={e => { if (disabled) return; e.preventDefault(); e.stopPropagation(); setDragActive(false); }}
            onDrop={e => { if (disabled) return; e.preventDefault(); e.stopPropagation(); setDragActive(false); addImages(e.dataTransfer.files); }}
            className={`rounded-lg border-2 border-dashed px-3 py-4 min-h-[180px] flex flex-col items-center justify-center text-center text-[11px] transition-colors ${disabled ? "border-slate-200 text-slate-300" : dragActive ? "border-indigo-400 bg-indigo-50 text-indigo-600" : "border-slate-300 text-slate-500"}`}
          >
            <label className={disabled ? "cursor-default" : "cursor-pointer text-indigo-600 font-semibold"}>
              Drag &amp; drop images or <span className="underline">browse</span>
              <input type="file" accept="image/*" multiple disabled={disabled} className="hidden"
                onChange={e => { addImages(e.target.files); e.currentTarget.value = ""; }} />
            </label>
            {images.length > 0 && <p className="mt-1 text-slate-600">{images.length} image(s) ready</p>}
          </div>
          {images.length > 0 && !disabled && (
            <button type="button" onClick={generate} disabled={generating || busy}
              className="mt-2 px-3 py-1.5 bg-indigo-600 text-white rounded-lg text-[11px] font-semibold hover:bg-indigo-700 disabled:opacity-50">
              {generating ? "Generating…" : `Generate PDF (${images.length})`}
            </button>
          )}
        </div>
      </div>
      {busy && <span className="text-[10px] font-semibold text-indigo-600">Uploading…</span>}
    </div>
  );
}

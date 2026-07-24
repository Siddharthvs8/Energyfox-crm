/**
 * Loads the Energyfox logo lockup as a data URL so jsPDF can embed it in the
 * documents the CRM generates (completion docs, warranty certificate).
 *
 * Returns null if the asset can't be read — callers fall back to drawing the
 * wordmark as text, so document generation never fails over a missing image.
 */
export type PdfLogo = { dataUrl: string; width: number; height: number };

let cached: PdfLogo | null | undefined;

export async function loadEnergyfoxLogo(): Promise<PdfLogo | null> {
  if (cached !== undefined) return cached;
  try {
    const r = await fetch("/energyfox-logo.png");
    if (!r.ok) throw new Error("logo not found");
    const blob = await r.blob();
    const dataUrl: string = await new Promise((res, rej) => {
      const fr = new FileReader();
      fr.onload = () => res(fr.result as string);
      fr.onerror = rej;
      fr.readAsDataURL(blob);
    });
    const dims: { width: number; height: number } = await new Promise(res => {
      const im = new Image();
      im.onload = () => res({ width: im.width, height: im.height });
      im.onerror = () => res({ width: 0, height: 0 });
      im.src = dataUrl;
    });
    cached = dims.width ? { dataUrl, ...dims } : null;
  } catch {
    cached = null;
  }
  return cached;
}

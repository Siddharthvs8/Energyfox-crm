/**
 * The quotation document — one way to get it, for everywhere that needs it.
 *
 * There are four places a customer's proposal is produced: previewed, opened in
 * a tab, downloaded, and emailed. They must all hand over the same file. When
 * each fetched and built its own, switching the preview to the branded template
 * left Download and Send quietly producing the old plain document — the
 * customer received something nobody had looked at.
 *
 * So the document is fetched here and nowhere else. It is rendered on the
 * server because it is built on the company's approved artwork, and that
 * template is a file that lives there.
 */
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";

/** Raised when the server declines to build the document, carrying its reason. */
export class ProposalUnavailable extends Error {}

export async function fetchProposal(quotationId: number): Promise<Blob> {
  const r = await fetch(
    `${getApiBase(APP_SLUG)}/api/quotations/${quotationId}/proposal/`,
    { headers: { Authorization: `Bearer ${localStorage.getItem(`${APP_SLUG}_access`)}` } },
  );
  if (!r.ok) {
    // The usual reason is a system type with no template uploaded yet, and the
    // server says which — worth passing on rather than replacing with "failed".
    const detail = await r.json().catch(() => ({}));
    throw new ProposalUnavailable(detail.error || `Could not build the document (${r.status}).`);
  }
  return r.blob();
}

/** Named for the customer as well as the number, matching what the server stores. */
export function proposalFileName(number: string, party?: string | null) {
  const clean = (v: string) => v.replace(/[\\/:*?"<>|]+/g, "-").replace(/\s+/g, " ").trim();
  const who = party ? ` - ${clean(party).slice(0, 60)}` : "";
  return `${clean(number) || "quotation"}${who}.pdf`;
}

/** Hand the blob to the browser as a download, then release the object URL. */
export function saveBlob(blob: Blob, fileName: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = fileName;
  a.click();
  // Revoked on the next tick: released immediately, some browsers cancel the
  // download that has only just started.
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

/**
 * The purchase order, drawn to the company's own template: letterhead, the
 * supplier block, bill-to / ship-to, the spares table with its transportation
 * charge, and the tax and total rows beneath it.
 *
 * Every figure comes from the server (see the `document` action) so the printed
 * document and the stored order can never disagree; this file only lays them
 * out. Drawn on an explicit mm grid for the same reason the proforma is — the
 * form has fixed columns, and a flowing table would drift away from it.
 */
import { BRAND_LOGO } from "./brandLogo";

export type PurchaseOrderData = {
  company: {
    name: string; address: string; phone: string; email: string;
    gst: string; cin: string; logo: string | null;
    signature: string | null; seal: string | null;
  };
  order: { number: string; fy: string; date: string | null; status: string };
  supplier: {
    name: string; address: string; gstin: string; pan: string; iec: string;
    contact_person: string; contact_number: string; email: string;
  };
  bill_to: { name: string; address: string; gstin: string };
  ship_to: { address: string; phone: string };
  lines: {
    sl: number; type_of_spare: string; description: string; part_code: string;
    unit_price: string; quantity: string; base_amount: string;
  }[];
  totals: {
    goods: string; transportation: string; taxable: string;
    tax_label: string; tax_percent: string; tax_amount: string;
    total: string; in_words: string;
  };
  terms: { taxes: string; delivery: string };
};

/** Amounts print with two decimals, the way the form is filled in by hand. */
const money = (v: any) => {
  const n = Number(v);
  return Number.isFinite(n) ? n.toFixed(2) : String(v ?? "");
};

const dmy = (iso: string | null) => {
  if (!iso) return "";
  const [y, m, d] = iso.split("-");
  return `${d}-${m}-${y}`;
};

/** Fetch an image as a data URI; returns null so missing artwork never breaks the PDF. */
async function dataUri(url: string | null): Promise<string | null> {
  if (!url) return null;
  if (url.startsWith("data:")) return url;
  try {
    const r = await fetch(url);
    if (!r.ok) return null;
    const blob = await r.blob();
    return await new Promise<string>((resolve, reject) => {
      const fr = new FileReader();
      fr.onload = () => resolve(String(fr.result));
      fr.onerror = reject;
      fr.readAsDataURL(blob);
    });
  } catch { return null; }
}

export async function buildPurchaseOrderPdf(d: PurchaseOrderData): Promise<any> {
  const { jsPDF } = await import("jspdf");
  const doc = new jsPDF({ unit: "mm", format: "a4" });

  const L = 12, R = 198;                 // page margins (A4 is 210 wide)
  const W = R - L;
  let y = 12;

  const NAVY: [number, number, number] = [26, 35, 66];
  const ORANGE: [number, number, number] = [247, 148, 29];

  const text = (t: string, x: number, yy: number, opts?: any) => doc.text(String(t ?? ""), x, yy, opts);
  const box = (x: number, yy: number, w: number, h: number) => doc.rect(x, yy, w, h);
  const size = (n: number) => doc.setFontSize(n);
  const bold = (on = true) => doc.setFont("helvetica", on ? "bold" : "normal");

  /** Right-align a value in its cell, shrinking it if the cell is too narrow. */
  const fitRight = (t: string, right: number, yy: number, maxW: number) => {
    const s = String(t ?? "");
    const start = doc.getFontSize();
    while (doc.getFontSize() > 5 && doc.getTextWidth(s) > maxW) doc.setFontSize(doc.getFontSize() - 0.25);
    text(s, right, yy, { align: "right" });
    doc.setFontSize(start);
  };

  /** Centred counterpart, for the narrow columns. */
  const fitCentre = (t: string, centre: number, yy: number, maxW: number) => {
    const s = String(t ?? "");
    const start = doc.getFontSize();
    while (doc.getFontSize() > 5 && doc.getTextWidth(s) > maxW) doc.setFontSize(doc.getFontSize() - 0.25);
    text(s, centre, yy, { align: "center" });
    doc.setFontSize(start);
  };

  /** Artwork scaled to fit its box rather than stretched; failures are skipped. */
  const placeImage = (uri: string, bx: number, by: number, bw: number, bh: number) => {
    let w = bw, h = bh;
    try {
      const p = doc.getImageProperties(uri);
      const scale = Math.min(bw / p.width, bh / p.height);
      w = p.width * scale; h = p.height * scale;
    } catch { /* unknown dimensions: fill the box */ }
    const kind = /^data:image\/(\w+)/.exec(uri)?.[1]?.toUpperCase() || "PNG";
    try {
      doc.addImage(uri, kind === "JPG" ? "JPEG" : kind, bx + (bw - w) / 2, by + (bh - h) / 2, w, h,
                   undefined, "FAST");
    } catch { /* ignore */ }
  };

  doc.setLineWidth(0.2);
  doc.setDrawColor(60);

  /* ── Letterhead: logo left, registration numbers right, banded rule under ── */
  const logo = (await dataUri(d.company.logo)) || BRAND_LOGO;
  if (logo) placeImage(logo, L, y, 62, 18);

  size(9); bold();
  doc.setTextColor(...ORANGE); text("CIN", R - 46, y + 5);
  doc.setTextColor(...NAVY);   text(`: ${d.company.cin || ""}`, R - 38, y + 5);
  doc.setTextColor(...ORANGE); text("GST", R - 46, y + 10);
  doc.setTextColor(...NAVY);   text(`: ${d.company.gst || ""}`, R - 38, y + 10);
  doc.setTextColor(0);
  bold(false);

  y += 21;
  doc.setFillColor(...NAVY);   doc.rect(L, y, W, 1.6, "F");
  doc.setFillColor(...ORANGE); doc.rect(L, y + 1.8, W, 1.2, "F");
  y += 10;

  /* ── Title, then the order's own number and date ── */
  size(13); bold();
  text("PURCHASE ORDER", L + W / 2, y, { align: "center" });
  bold(false); size(9.5);
  text(`PO NO:${d.order.number || ""}`, L + 110, y + 7);
  text(`PO Date:${dmy(d.order.date)}`, L + 110, y + 12);
  y += 12;

  /* ── Supplier ── */
  size(9.5); bold();
  text("To,", L, y);
  text(d.supplier.name || "", L, y + 5);
  bold(false);
  size(8.5);
  let sy = y + 10.5;
  const addr = doc.splitTextToSize(d.supplier.address || "", 76);
  addr.slice(0, 4).forEach((l: string) => { text(l, L + 1, sy); sy += 3.8; });
  text(`India PAN No:${d.supplier.pan || ""}`, L, sy); sy += 3.8;
  text(`IEC Code:${d.supplier.iec || ""}`, L, sy); sy += 3.8;
  text(`GST No:${d.supplier.gstin || ""}`, L, sy); sy += 3.8;

  /* ── Bill to | Ship to ── */
  y = sy + 5;
  const MID = L + W / 2 + 8;
  size(9.5); bold();
  text("Bill to Party:", L, y);
  text("Ship to Party:", MID, y);

  size(8.5);
  let by = y + 5;
  bold();
  text(d.bill_to.name || "", L, by);
  const billAddr = doc.splitTextToSize(d.bill_to.address || "", 82);
  let ly = by + 4.2;
  billAddr.slice(0, 4).forEach((l: string) => { text(l, L, ly); ly += 4.2; });

  const shipAddr = doc.splitTextToSize(d.ship_to.address || "", 82);
  let ry = by;
  shipAddr.slice(0, 4).forEach((l: string) => { text(l, MID, ry); ry += 4.2; });
  if (d.ship_to.phone) { text(`Ph No:${d.ship_to.phone}`, MID, ry); ry += 4.2; }
  bold(false);

  y = Math.max(ly, ry) + 4;

  /* ── The spares table ──
     Fixed columns, because the form has fixed columns. */
  const COL = [14, 24, 52, 26, 22, 24, 24];             // = 186 = W
  const X: number[] = [L];
  COL.forEach(w => X.push(X[X.length - 1] + w));
  const RIGHT = X[7];
  const HEAD_H = 10;

  size(8.5); bold();
  box(L, y, W, HEAD_H);
  X.slice(1, 7).forEach(x => doc.line(x, y, x, y + HEAD_H));
  const heads = ["SL\nNO", "Type of\nSpare", "Description", "Part Code", "Unit\nPrice", "Quantity", "Base\nAmount"];
  heads.forEach((h, i) => {
    const parts = h.split("\n");
    const centre = X[i] + COL[i] / 2;
    const top = y + (parts.length === 1 ? 6.2 : 4.2);
    parts.forEach((p, n) => fitCentre(p, centre, top + n * 3.6, COL[i] - 2));
  });
  y += HEAD_H;
  bold(false);

  /* Line rows. Each is one product; the row height is fixed so the printed form
     keeps its shape whether it carries one line or ten. */
  const ROW_H = 9;
  d.lines.forEach(li => {
    box(L, y, W, ROW_H);
    X.slice(1, 7).forEach(x => doc.line(x, y, x, y + ROW_H));
    const mid = y + 5.8;
    fitCentre(String(li.sl), X[0] + COL[0] / 2, mid, COL[0] - 2);
    text(li.type_of_spare || "", X[1] + 2, mid);
    text(doc.splitTextToSize(li.description || "", COL[2] - 4)[0] || "", X[2] + 2, mid);
    text(li.part_code || "", X[3] + 2, mid);
    fitRight(money(li.unit_price), X[5] - 2, mid, COL[4] - 4);
    fitRight(money(li.quantity), X[6] - 2, mid, COL[5] - 4);
    fitRight(money(li.base_amount), RIGHT - 2, mid, COL[6] - 4);
    y += ROW_H;
  });

  /* Transportation is charged on the order, not on any line — it gets the
     description column and an amount, with the rest left blank. */
  if (Number(d.totals.transportation) > 0) {
    box(L, y, W, ROW_H);
    X.slice(1, 7).forEach(x => doc.line(x, y, x, y + ROW_H));
    text("Transportation", X[2] + 2, y + 5.8);
    fitRight(money(d.totals.transportation), RIGHT - 2, y + 5.8, COL[6] - 4);
    y += ROW_H;
  }

  /* TOTAL: the label spans the left of the table, the figure keeps its column. */
  const TOTAL_H = 8;
  box(L, y, W, TOTAL_H);
  doc.line(X[4], y, X[4], y + TOTAL_H);
  doc.line(X[5], y, X[5], y + TOTAL_H);
  doc.line(X[6], y, X[6], y + TOTAL_H);
  bold();
  text("TOTAL", X[0] + COL[0] / 2 + 32, y + 5.4, { align: "center" });
  fitRight(money(d.totals.taxable), RIGHT - 2, y + 5.4, COL[6] - 4);
  bold(false);
  y += TOTAL_H;

  /* ── In words on the left; tax then grand total stacked on the right ── */
  const FOOT_H = 9;
  box(L, y, X[5] - L, FOOT_H * 2);                       // the words cell, two rows tall
  box(X[5], y, RIGHT - X[5], FOOT_H);                    // tax row
  box(X[5], y + FOOT_H, RIGHT - X[5], FOOT_H);           // total row
  doc.line(X[6], y, X[6], y + FOOT_H * 2);

  size(8.5); bold();
  text("In Words:", L + 2, y + 5.4);
  bold(false);
  const words = doc.splitTextToSize(`${d.totals.in_words}`, X[5] - L - 6);
  let wy = y + FOOT_H + 4;
  words.slice(0, 2).forEach((l: string) => { text(l, L + 2, wy); wy += 3.8; });

  bold();
  fitCentre(`${d.totals.tax_label}${Number(d.totals.tax_percent)}%`, (X[5] + X[6]) / 2, y + 5.4, COL[5] - 3);
  fitRight(money(d.totals.tax_amount), RIGHT - 2, y + 5.4, COL[6] - 4);
  fitCentre("Total", (X[5] + X[6]) / 2, y + FOOT_H + 4, COL[5] - 3);
  fitCentre("Amount", (X[5] + X[6]) / 2, y + FOOT_H + 7.4, COL[5] - 3);
  fitRight(money(d.totals.total), RIGHT - 2, y + FOOT_H + 5.6, COL[6] - 4);
  bold(false);
  y += FOOT_H * 2 + 10;

  /* ── Terms on the left, the sign-off on the right ── */
  size(9.5); bold();
  text("Terms and Conditions:", L, y);
  doc.line(L, y + 1, L + doc.getTextWidth("Terms and Conditions:"), y + 1);   // underlined
  bold(false);
  size(9);
  text(`Taxes:${d.terms.taxes || ""}`, L, y + 7);
  text(`Delivery:${d.terms.delivery || ""}`, L, y + 12);

  size(9.5);
  text(`For ${d.company.name}`, MID - 6, y + 2);
  const [sig, seal] = await Promise.all([dataUri(d.company.signature), dataUri(d.company.seal)]);
  if (sig) placeImage(sig, MID - 6, y + 5, 34, 16);
  if (seal) placeImage(seal, MID + 32, y + 4, 26, 26);

  return doc;
}

/** Filename the document is downloaded / attached under, matching the filed copies. */
export const purchaseOrderFileName = (d: { number: string; fy: string; supplier?: string }) =>
  `Purchase order of ${d.supplier || "supplier"} ${d.fy} ${d.number}.pdf`.replace(/[\\/:*?"<>|]/g, "-");

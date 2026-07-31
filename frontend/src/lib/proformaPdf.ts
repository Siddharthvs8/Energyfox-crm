/**
 * Proforma invoice PDF — a faithful reproduction of the EnergyFox printed
 * template (EF/26-27/PI009 and friends).
 *
 * The layout is drawn as an explicit grid of ruled boxes rather than with a
 * table plugin, because the original is a bordered form whose row heights,
 * column widths and label/value split have to match exactly. Coordinates are in
 * millimetres on A4 portrait; `X` holds the column edges every section aligns to.
 */
import { RUPEE_FONT_BASE64, RUPEE_FONT_FILE, RUPEE_FONT_NAME } from "./rupeeFont";

export type ProformaData = {
  company: {
    name: string; address: string; phone: string; email: string;
    gst: string; cin: string; pan: string;
    logo: string | null; signature: string | null; seal: string | null;
  };
  bank: { name: string; account_name: string; ifsc: string; account_number: string; branch: string };
  invoice: { number: string; date: string | null; efc_ref_no: string; status: string };
  customer: { name: string; gstin: string; contact_person: string; contact_number: string; address: string; state: string };
  ship_to: { name: string; address: string; state: string; gstin: string };
  lines: { sl_no: number; particulars: string; hsn: string; qty: string; unit: string;
           taxable: string; gst_rate: string; tax: string; total: string }[];
  hsn_summary: { hsn: string; rate: string; taxable: string; cgst: string; sgst: string }[];
  totals: { taxable: string; discount: string; tax: string; invoice_value: string;
            round_off: string; grand_total: string; in_words: string };
  terms: string[];
};

/** ₹-style grouping with two decimals, as the printed document shows. */
const inr = (v: any) => {
  const n = Number(v || 0);
  return n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

/** Quantities and rates print as entered — "13" and "5", not "13.00" and "5.00". */
const trim0 = (v: any) => {
  const s = String(v ?? "").trim();
  return s.includes(".") ? s.replace(/\.?0+$/, "") : s;
};

const dmy = (iso: string | null) => {
  if (!iso) return "";
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y}`;
};

/** Fetch an image as a data URI; returns null so a missing logo never breaks the PDF. */
async function dataUri(url: string | null): Promise<string | null> {
  if (!url) return null;
  // The server inlines artwork so the page never has to fetch it cross-origin;
  // a plain URL is only a fallback, and fetching it may well be blocked.
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

export async function buildProformaPdf(d: ProformaData): Promise<any> {
  const { jsPDF } = await import("jspdf");
  const doc = new jsPDF({ unit: "mm", format: "a4" });

  const L = 10, R = 200;                 // page margins (A4 is 210 wide)
  const W = R - L;
  let y = 10;

  const line = (x1: number, y1: number, x2: number, y2: number) => doc.line(x1, y1, x2, y2);
  const box = (x: number, yy: number, w: number, h: number) => doc.rect(x, yy, w, h);
  const text = (t: string, x: number, yy: number, opts?: any) => doc.text(String(t ?? ""), x, yy, opts);
  // The original sets everything from the title bar down to the address blocks
  // in a serif face, and the table from "( Amount in INR )" onward in a sans one.
  let FACE = "helvetica";
  const face = (f: "times" | "helvetica") => { FACE = f; doc.setFont(f, "normal"); };
  const bold = (on = true) => doc.setFont(FACE, on ? "bold" : "normal");
  const size = (n: number) => doc.setFontSize(n);

  // The standard-14 fonts have no rupee sign, so it gets its own one-glyph font.
  doc.addFileToVFS(RUPEE_FONT_FILE, RUPEE_FONT_BASE64);
  doc.addFont(RUPEE_FONT_FILE, RUPEE_FONT_NAME, "normal");

  /**
   * Right-align a value inside its cell, shrinking it if the cell is too narrow.
   * Amounts here run from hundreds to crores, so a fixed size would let a long
   * figure run over the neighbouring column.
   */
  const fitRight = (t: string, right: number, yy: number, maxW: number) => {
    const s = String(t ?? "");
    const start = doc.getFontSize();
    while (doc.getFontSize() > 5 && doc.getTextWidth(s) > maxW) {
      doc.setFontSize(doc.getFontSize() - 0.25);
    }
    text(s, right, yy, { align: "right" });
    doc.setFontSize(start);
  };

  /** Centred counterpart of fitRight, for codes that fill their column. */
  const fitCentre = (t: string, centre: number, yy: number, maxW: number) => {
    const str = String(t ?? "");
    const start = doc.getFontSize();
    while (doc.getFontSize() > 5 && doc.getTextWidth(str) > maxW) {
      doc.setFontSize(doc.getFontSize() - 0.25);
    }
    text(str, centre, yy, { align: "center" });
    doc.setFontSize(start);
  };

  /** The Taxable cell prints accounting-style: ₹ flush left, amount flush right. */
  const rupeeAmount = (amount: string, left: number, right: number, yy: number) => {
    const wasBold = doc.getFont().fontStyle === "bold";
    doc.setFont(RUPEE_FONT_NAME, "normal");
    text("₹", left + 2, yy);
    doc.setFont(FACE, wasBold ? "bold" : "normal");
    fitRight(amount, right - 2, yy, right - left - 6);
  };

  /**
   * Draw artwork centred in a box, scaled to fit rather than stretched — the
   * logo is far wider than it is tall, and filling the box would squash it.
   * Anything unreadable is skipped so the document still prints.
   */
  const placeImage = (uri: string, bx: number, by: number, bw: number, bh: number) => {
    const padW = bw - 3, padH = bh - 3;
    let w = padW, h = padH;
    try {
      const p = doc.getImageProperties(uri);
      const scale = Math.min(padW / p.width, padH / p.height);
      w = p.width * scale;
      h = p.height * scale;
    } catch { /* unknown dimensions: fill the box */ }
    const kind = /^data:image\/(\w+)/.exec(uri)?.[1]?.toUpperCase() || "PNG";
    try {
      doc.addImage(uri, kind === "JPG" ? "JPEG" : kind,
                   bx + (bw - w) / 2, by + (bh - h) / 2, w, h, undefined, "FAST");
    } catch { /* ignore */ }
  };

  doc.setLineWidth(0.2);
  doc.setDrawColor(120);

  /* ── Header: logo left, company block right ── */
  size(7.5);
  const addrLines = doc.splitTextToSize(d.company.address || "", 60).slice(0, 3);
  // 6.5mm for the name, then 3.2mm per address line and per meta row, plus padding.
  const headerH = Math.max(30, 8 + (addrLines.length + 5) * 3.2 + 2.5);
  const logo = await dataUri(d.company.logo);
  if (logo) {
    const boxX = L + 2, boxY = y + 2, boxW = 64, boxH = headerH - 4;
    placeImage(logo, boxX, boxY, boxW, boxH);
    doc.setDrawColor(180);
    doc.roundedRect(boxX, boxY, boxW, boxH, 2, 2);
    doc.setDrawColor(120);
  }
  size(11); bold();
  text(d.company.name, L + 78, y + 6);
  bold(false); size(7.5);
  let ay = y + 10.5;
  addrLines.forEach((l: string) => { text(l, L + 78, ay); ay += 3.2; });
  const meta: [string, string][] = [
    ["Tel", d.company.phone], ["Email", d.company.email],
    ["GST NO", d.company.gst], ["CIN NO", d.company.cin], ["PAN", d.company.pan],
  ];
  meta.forEach(([k, v]) => {
    text(k, L + 78, ay); text(":", L + 96, ay); text(v || "", L + 100, ay);
    ay += 3.2;
  });
  y += headerH;

  /* ── Title bar ── */
  face("times");
  doc.setFillColor(31, 46, 74);
  doc.rect(L, y, W, 7, "F");
  doc.setTextColor(255); size(12); bold();
  text("PROFORMA INVOICE", L + W / 2, y + 5, { align: "center" });
  doc.setTextColor(0);
  y += 7;

  /* ── Details: invoice (left) | customer (right) ── */
  const MID = L + W / 2;               // the document's central divide
  const secH = 6;
  const bandFill = () => { doc.setFillColor(31, 46, 74); };

  bandFill();
  doc.rect(L, y, W / 2, secH, "F");
  doc.rect(MID, y, W / 2, secH, "F");
  doc.setTextColor(255); size(8.5); bold();
  text("Proforma Invoice Details", L + 3, y + 4);
  text("Customer name:", MID + 3, y + 4);
  bold(false);
  text(d.customer.name, MID + 40, y + 4);
  doc.setTextColor(0);
  y += secH;

  const detailRows: [string, string, string, string][] = [
    ["Proforma Invoice No.:", d.invoice.number, "GSTIN:", d.customer.gstin],
    ["Proforma Invoice Date:", dmy(d.invoice.date), "Contact Person:", d.customer.contact_person],
    ["EFC Ref No.:", d.invoice.efc_ref_no, "Contact Number:", d.customer.contact_number],
  ];
  size(8);
  detailRows.forEach(([k1, v1, k2, v2]) => {
    box(L, y, W / 2, secH); box(MID, y, W / 2, secH);
    line(L + 45, y, L + 45, y + secH); line(MID + 42, y, MID + 42, y + secH);
    bold(); text(k1, L + 3, y + 4); text(k2, MID + 3, y + 4);
    bold(false); text(v1, L + 48, y + 4); text(v2, MID + 45, y + 4);
    y += secH;
  });

  /* ── Billed to | Shipped to ── */
  bandFill();
  doc.rect(L, y, W / 2, secH, "F"); doc.rect(MID, y, W / 2, secH, "F");
  doc.setTextColor(255); bold(); size(8.5);
  text("Customer Details / Billed To:", L + W / 4, y + 4, { align: "center" });
  text("Shipped to:", MID + W / 4, y + 4, { align: "center" });
  doc.setTextColor(0);
  y += secH;

  size(8);
  const wrapAddr = (a: string) => doc.splitTextToSize(a || "", W / 2 - 28).slice(0, 3);
  const addrRows = Math.max(wrapAddr(d.customer.address).length,
                            wrapAddr(d.ship_to.address).length, 1);
  // Name + Address block + State + GST No., with the address free to run to
  // three lines before it is truncated.
  const addrH = 9 + addrRows * 3.6 + 2.5 + 4.5 + 4.5 + 2;
  box(L, y, W / 2, addrH); box(MID, y, W / 2, addrH);
  const addrBlock = (x: number, party: { name: string; address: string; state: string; gstin: string }) => {
    let ry = y + 4.5;
    bold(); text("Name:", x + 3, ry); bold(); text(party.name, x + 22, ry);
    ry += 4.5;
    bold(); text("Address:", x + 3, ry);
    bold();
    const wrapped = wrapAddr(party.address);
    let wy = ry;
    wrapped.forEach((l: string) => { text(l, x + 22, wy); wy += 3.6; });
    ry = Math.max(ry + 4.5, wy + 2.5);
    bold(); text("State:", x + 3, ry); text(party.state || "", x + 22, ry);
    ry += 4.5;
    bold(); text("GST No.:", x + 3, ry); text(party.gstin || "", x + 22, ry);
  };
  addrBlock(L, { name: d.customer.name, address: d.customer.address, state: d.customer.state, gstin: d.customer.gstin });
  addrBlock(MID, d.ship_to);
  y += addrH;

  /* ── "( Amount in INR )" ── */
  face("helvetica");
  size(7.5); bold(false); doc.setFont("helvetica", "italic");
  text("( Amount in INR)", R - 2, y + 3.5, { align: "right" });
  doc.setFont("helvetica", "normal");
  y += 5;

  /* ── Line items ── */
  // Column edges, matching the printed proportions.
  // Widths are driven by the money columns: "2,36,000.00" alone needs ~15mm at
  // 8pt, so Taxable / Tax / Total get room rather than overrunning each other.
  const X = [L, L + 7.6, L + 60, L + 74, L + 85, L + 96, L + 118, L + 131, L + 148, R];
  const heads = ["Sl No", "Particulars", "HSN", "Qty", "Unit", "Taxable", "GST Rate", "Tax", "Total"];
  const headH = 7;

  size(7.5); bold();
  heads.forEach((h, i) => {
    box(X[i], y, X[i + 1] - X[i], headH);
    if (i === 1) text(h, X[i] + 1.5, y + 4.5);          // Particulars: flush left
    else text(h, (X[i] + X[i + 1]) / 2, y + 4.5, { align: "center" });
  });
  y += headH;

  // Always draw at least two body rows, as the blank second row in the template.
  const bodyRows = Math.max(d.lines.length, 2);
  const rowH = 12;
  bold(false); size(8);
  for (let r = 0; r < bodyRows; r++) {
    const li = d.lines[r];
    for (let i = 0; i < heads.length; i++) box(X[i], y, X[i + 1] - X[i], rowH);
    if (li) {
      const mid = y + rowH / 2 + 1;
      text(String(li.sl_no), (X[0] + X[1]) / 2, mid, { align: "center" });
      // A long description wraps inside its column rather than running over
      // the HSN cell; three lines is all the row height allows.
      bold();
      const desc = doc.splitTextToSize(li.particulars || "", X[2] - X[1] - 4).slice(0, 3);
      const top = mid - ((desc.length - 1) * 3.2) / 2;
      desc.forEach((ln: string, n: number) =>
        text(ln, (X[1] + X[2]) / 2, top + n * 3.2, { align: "center" }));
      bold(false);
      fitCentre(li.hsn || "", (X[2] + X[3]) / 2, mid, X[3] - X[2] - 2);
      text(trim0(li.qty), (X[3] + X[4]) / 2, mid, { align: "center" });
      text(li.unit || "", (X[4] + X[5]) / 2, mid, { align: "center" });
      rupeeAmount(inr(li.taxable), X[5], X[6], mid);
      text(trim0(li.gst_rate), X[7] - 2, mid, { align: "right" });
      fitRight(inr(li.tax), X[8] - 2, mid, X[8] - X[7] - 3);
      fitRight(inr(li.total), X[9] - 2, mid, X[9] - X[8] - 3);
    } else {
      const mid = y + rowH / 2 + 1;
      text(String(r + 1), (X[0] + X[1]) / 2, mid, { align: "center" });
      text("-", (X[3] + X[4]) / 2, mid, { align: "center" });
      rupeeAmount("-", X[5], X[6], mid);          // the template shows "₹ -" here
      text("-", X[7] - 2, mid, { align: "right" });
      text("-", X[8] - 2, mid, { align: "right" });
      text("-", X[9] - 2, mid, { align: "right" });
    }
    y += rowH;
  }

  /* ── Total invoice value ── */
  const totH = 7;
  box(L, y, X[6] - L, totH); box(X[6], y, X[7] - X[6], totH);
  box(X[7], y, X[8] - X[7], totH); box(X[8], y, R - X[8], totH);
  bold(); size(8);
  text("Total Invoice value", L + 3, y + 4.7);
  fitRight(inr(d.totals.invoice_value), R - 2, y + 4.7, R - X[8] - 3);
  y += totH + 3;

  /* ── HSN details ── */
  // The strip right of the HSN columns carries the Round Off / Grand Total
  // labels beside their amounts, so it needs room for both.
  const H = [L, L + 29, L + 71, L + 84, L + 107, L + 127, R];
  const LBL = L + 148;                 // labels end here, amounts sit to the right
  bold(); size(8.5);
  box(L, y, W, 6);
  const cap = "HSN DETAILS", capW = doc.getTextWidth(cap), capX = L + W / 2;
  text(cap, capX, y + 4.2, { align: "center" });
  line(capX - capW / 2, y + 5, capX + capW / 2, y + 5);      // underlined in the original
  y += 6;

  doc.setFillColor(31, 46, 74);
  doc.rect(L, y, H[5] - L, 6, "F");
  doc.setTextColor(255); size(7.5);
  ["HSN / SAC", "Taxable Value", "RATE", "CGST", "SGST"].forEach((h, i) => {
    line(H[i], y, H[i], y + 6);
    text(h, (H[i] + H[i + 1]) / 2, y + 4, { align: "center" });
  });
  doc.setTextColor(0);
  box(H[5], y, R - H[5], 6);
  y += 6;

  bold(false); size(8);
  const hsnRows = Math.max(d.hsn_summary.length, 1);
  for (let r = 0; r < hsnRows; r++) {
    const row = d.hsn_summary[r];
    for (let i = 0; i < 5; i++) box(H[i], y, H[i + 1] - H[i], 6);
    box(H[5], y, R - H[5], 6);
    if (row) {
      fitCentre(row.hsn, (H[0] + H[1]) / 2, y + 4, H[1] - H[0] - 2);
      fitRight(inr(row.taxable), H[2] - 2, y + 4, H[2] - H[1] - 3);
      text(trim0(row.rate), (H[3] - 2), y + 4, { align: "right" });
      fitRight(inr(row.cgst), H[4] - 2, y + 4, H[4] - H[3] - 3);
      fitRight(inr(row.sgst), H[5] - 2, y + 4, H[5] - H[4] - 3);
    }
    y += 6;
  }

  // Round-off row, then the grand total, both right-labelled as in the original.
  for (let i = 0; i < 5; i++) box(H[i], y, H[i + 1] - H[i], 6);
  box(H[5], y, R - H[5], 6);
  text("-", H[4] - 2, y + 4, { align: "right" });
  text("-", H[5] - 2, y + 4, { align: "right" });
  line(LBL, y, LBL, y + 6);
  bold(); text("Round Off :", LBL - 2, y + 4, { align: "right" });
  bold(false); fitRight(inr(d.totals.round_off), R - 2, y + 4, R - LBL - 3);
  y += 6;

  for (let i = 0; i < 5; i++) box(H[i], y, H[i + 1] - H[i], 7);
  box(H[5], y, R - H[5], 7);
  bold(); size(8);
  text("-", (H[0] + H[1]) / 2, y + 4.7, { align: "center" });
  text("-", H[2] - 2, y + 4.7, { align: "right" });
  text("0.00", H[3] - 2, y + 4.7, { align: "right" });
  text("-", H[4] - 2, y + 4.7, { align: "right" });
  line(LBL, y, LBL, y + 7);
  text("Grand Total :", LBL - 2, y + 4.7, { align: "right" });
  doc.setTextColor(226, 24, 115);      // the magenta the original prints it in
  size(11);
  fitRight(inr(d.totals.grand_total), R - 2, y + 5, R - LBL - 3);
  doc.setTextColor(0);
  y += 7;

  /* ── Amount in words ── */
  box(L, y, W, 7);
  size(8); doc.setFont("helvetica", "bolditalic");
  text(`( Amount in Words -${d.totals.in_words} )`, L + W / 2, y + 4.7, { align: "center" });
  doc.setFont("helvetica", "normal");
  y += 7;

  /* ── Bank details + terms (left, stacked) | signature (right, one tall cell) ── */
  const bankH = 30, termsH = 12, footH = bankH + termsH;
  box(L, y, W / 2, bankH);            // bank details
  box(L, y + bankH, W / 2, termsH);   // terms, directly beneath it
  box(MID, y, W / 2, footH);          // signature block spans both
  size(9); bold();
  text("Bank Account Details:", L + W / 4, y + 5.5, { align: "center" });
  size(8);
  const bankRows: [string, string][] = [
    ["Bank", d.bank.name], ["Account Name", d.bank.account_name], ["IFSC", d.bank.ifsc],
    ["Account Number", d.bank.account_number], ["Branch", d.bank.branch],
  ];
  let by = y + 11;
  bankRows.forEach(([k, v]) => {
    bold(); text(k, L + 32, by, { align: "right" });
    text(":", L + 35, by);
    text(v || "", L + 40, by);
    by += 4.6;
  });

  doc.setFont("helvetica", "italic"); size(7.5);
  text("Certified that the particulars given above are true and correct",
       MID + W / 4, y + 6, { align: "center" });
  doc.setFont("helvetica", "bold");
  text(`For ${d.company.name}`, MID + W / 4, y + 10.5, { align: "center" });
  doc.setFont("helvetica", "normal");

  const [sig, seal] = await Promise.all([dataUri(d.company.signature), dataUri(d.company.seal)]);
  if (sig) placeImage(sig, MID + 12, y + 13, 32, 15);
  if (seal) placeImage(seal, MID + 50, y + 12, 22, 22);
  size(8); bold();
  text("AUTHORISED SIGNATORY", MID + W / 4, y + footH - 2.5, { align: "center" });

  /* ── Terms, in the lower-left cell ── */
  size(8); bold();
  text("Terms and Conditions", L + 3, y + bankH + 4.5);
  doc.setFont("helvetica", "bolditalic");
  d.terms.forEach((t, i) => text(`${i + 1}.${t}`, L + 3, y + bankH + 9 + i * 3.6));
  doc.setFont("helvetica", "normal");
  y += footH;

  return doc;
}

/** Filename the document is downloaded / attached under. */
export const proformaFileName = (number: string) =>
  `${(number || "proforma").replace(/\//g, "-")}.pdf`;

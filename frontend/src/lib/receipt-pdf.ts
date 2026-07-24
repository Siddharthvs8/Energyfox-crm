/**
 * Generates the Energyfox money-receipt voucher PDF, matching the printed
 * template (letterhead, RECEIPT VOUCHER title, the key:value rows, bank details,
 * signature & seal). Data comes from the backend ReceiptVoucher + org details.
 */
import { loadEnergyfoxLogo } from "./pdf-logo";
import { getApiBase } from "./mock-data";
import { APP_SLUG } from "./config";

export type ReceiptData = {
  number: string;
  date: string;               // ISO
  amount: number | string;
  amount_in_words: string;
  on_account_of: string;
  payment_mode: string;
  received_from: string;
  address: string;
};

export type ReceiptOrg = {
  company_name?: string;
  cin?: string;
  gst?: string;
  signature?: string | null;
  seal?: string | null;
  bank_name?: string;
  bank_account?: string;
  bank_ifsc?: string;
  bank_branch?: string;
  address?: string;
  phone?: string;
  website?: string;
  email?: string;
};

async function loadImg(u?: string | null): Promise<{ dataUrl: string; fmt: "PNG" | "JPEG"; w: number; h: number } | null> {
  if (!u) return null;
  try {
    const r = await fetch(u);
    if (!r.ok) return null;
    const b = await r.blob();
    const dataUrl: string = await new Promise((res, rej) => {
      const fr = new FileReader(); fr.onload = () => res(fr.result as string); fr.onerror = rej; fr.readAsDataURL(b);
    });
    const dims: { w: number; h: number } = await new Promise(res => {
      const im = new Image(); im.onload = () => res({ w: im.width, h: im.height }); im.onerror = () => res({ w: 1, h: 1 }); im.src = dataUrl;
    });
    return { dataUrl, fmt: b.type.includes("png") ? "PNG" : "JPEG", w: dims.w, h: dims.h };
  } catch { return null; }
}

const money = (n: number | string) => {
  const v = Math.round((parseFloat(String(n)) || 0));
  return v.toLocaleString("en-IN");
};

export async function generateReceiptPdf(rec: ReceiptData, org: ReceiptOrg) {
  const { jsPDF } = await import("jspdf");
  const doc = new jsPDF("p", "pt", "a4");
  const W = doc.internal.pageSize.getWidth();
  const H = doc.internal.pageSize.getHeight();
  const ORANGE: [number, number, number] = [247, 148, 29];
  const NAVY: [number, number, number] = [26, 35, 66];
  const SLATE: [number, number, number] = [51, 65, 85];

  const [logo, sig, seal] = await Promise.all([
    loadEnergyfoxLogo(), loadImg(org.signature), loadImg(org.seal),
  ]);

  // ── Header ──
  if (logo) {
    const h = 46, w = (logo.width / logo.height) * h;
    doc.addImage(logo.dataUrl, "PNG", 40, 26, w, h);
  } else {
    doc.setFont("helvetica", "bold"); doc.setFontSize(22); doc.setTextColor(...ORANGE);
    doc.text("Energyfox", 40, 50);
    doc.setFont("helvetica", "normal"); doc.setFontSize(10); doc.setTextColor(148, 163, 184);
    doc.text("Consultants Pvt Ltd", 40, 65);
  }
  doc.setFont("helvetica", "bold"); doc.setFontSize(8.5); doc.setTextColor(...NAVY);
  const rightLines = [
    `CIN : ${org.cin || ""}`,
    `GST : ${org.gst || ""}`,
    ...doc.splitTextToSize(org.address || "", 220),
  ];
  rightLines.forEach((ln: string, i: number) => doc.text(ln, W - 40, 34 + i * 12, { align: "right" }));
  doc.setFillColor(...NAVY); doc.rect(0, 96, W, 5, "F");
  doc.setFillColor(...ORANGE); doc.rect(0, 101, W, 2.5, "F");

  // ── Title ──
  doc.setFont("helvetica", "bold"); doc.setFontSize(20); doc.setTextColor(30, 41, 59);
  doc.text("RECEIPT VOUCHER", W / 2, 165, { align: "center" });
  const tw = doc.getTextWidth("RECEIPT VOUCHER");
  doc.setDrawColor(30, 41, 59); doc.setLineWidth(1); doc.line(W / 2 - tw / 2, 170, W / 2 + tw / 2, 170);

  // ── Key : value rows ──
  const dateStr = rec.date
    ? new Date(rec.date).toLocaleDateString("en-GB").replace(/\//g, "-")
    : "";
  const rows: [string, string][] = [
    ["Date", dateStr],
    ["Voucher No", rec.number],
    ["Received from", rec.received_from],
    ["Address", rec.address],
    ["Sum of Rupees", `${money(rec.amount)}/-`],
    ["In Words", rec.amount_in_words],
    ["On Account of", rec.on_account_of],
    ["Mode of Payment", rec.payment_mode],
  ];
  let y = 220;
  doc.setFontSize(11.5);
  for (const [k, v] of rows) {
    doc.setFont("helvetica", "normal"); doc.setTextColor(...SLATE);
    doc.text(k, 90, y);
    doc.text(":", 235, y);
    const lines = doc.splitTextToSize(String(v || ""), W - 260 - 90);
    doc.text(lines, 255, y);
    y += Math.max(26, lines.length * 16 + 8);
  }

  // ── Thank you + sign-off ──
  y = Math.max(y + 20, H - 260);
  doc.setFont("helvetica", "bold"); doc.setFontSize(10.5); doc.setTextColor(30, 41, 59);
  doc.text("Thank you for your business", 90, y);
  doc.setFont("helvetica", "normal"); doc.setTextColor(...SLATE);
  doc.text("Sincerely", W - 130, y, { align: "center" });
  doc.setFont("helvetica", "bold"); doc.setTextColor(30, 41, 59);
  doc.text(`For M/S ${org.company_name || "EnergyFox Consultants Pvt Ltd"}`,
    W - 130, y + 16, { align: "center" });

  // Signature & seal, side by side on the right.
  const imgY = y + 26;
  if (seal) {
    const h = 78, w = (seal.w / seal.h) * h;
    try { doc.addImage(seal.dataUrl, seal.fmt, W - 210, imgY, w, h); } catch {}
  }
  if (sig) {
    const h = 55, w = Math.min(120, (sig.w / sig.h) * h);
    try { doc.addImage(sig.dataUrl, sig.fmt, W - 130, imgY + 10, w, h); } catch {}
  }

  // ── Bank details (bottom-left) ──
  let by = H - 150;
  doc.setFont("helvetica", "bold"); doc.setFontSize(11); doc.setTextColor(30, 41, 59);
  doc.text("Account Details", 90, by);
  by += 18;
  doc.setFontSize(10);
  const bank: [string, string][] = [
    ["Bank", org.bank_name || ""],
    ["Account Number", org.bank_account || ""],
    ["IFSC", org.bank_ifsc || ""],
    ["BRANCH", org.bank_branch || ""],
  ];
  for (const [k, v] of bank) {
    doc.setFont("helvetica", "bold"); doc.setTextColor(...SLATE); doc.text(k, 60, by);
    doc.text(":", 180, by);
    doc.text(String(v), 200, by);
    by += 16;
  }

  // ── Footer band ──
  doc.setDrawColor(...NAVY); doc.setLineWidth(1.2);
  doc.line(40, H - 44, W - 40, H - 44);
  doc.setFont("helvetica", "bold"); doc.setFontSize(9); doc.setTextColor(...NAVY);
  doc.text(org.phone || "", 60, H - 28);
  doc.text(org.website || "", W / 2, H - 28, { align: "center" });
  doc.text(org.email || "", W - 60, H - 28, { align: "right" });

  const safe = (rec.number || "receipt").replace(/[^\w-]+/g, "_");
  doc.save(`Receipt_${safe}.pdf`);
}

/** Fetch a lead's receipts and render one as a PDF. Selects by receiptId, else
 *  the initial (verification) receipt. Returns false if nothing matched. */
export async function downloadLeadReceipt(
  leadId: number | string,
  opts: { receiptId?: number; initial?: boolean } = {},
): Promise<boolean> {
  const token = localStorage.getItem(`${APP_SLUG}_access`);
  const r = await fetch(`${getApiBase(APP_SLUG)}/api/leads/${leadId}/receipts/`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!r.ok) { alert("Could not load the receipt."); return false; }
  const data = await r.json();
  const list: (ReceiptData & { id: number; is_initial: boolean })[] = data.receipts || [];
  const rec = opts.receiptId != null
    ? list.find(x => x.id === opts.receiptId)
    : opts.initial
      ? list.find(x => x.is_initial)
      : list[0];
  if (!rec) { alert("No receipt has been generated for this payment yet."); return false; }
  await generateReceiptPdf(rec, data.org || {});
  return true;
}

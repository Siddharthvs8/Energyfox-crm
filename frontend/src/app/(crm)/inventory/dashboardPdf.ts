/**
 * Inventory Dashboard → PDF.
 *
 * A data report rather than a picture of the screen: every figure the page shows
 * is written out as text in tables, so the file stays small, the numbers can be
 * copied out of it, and it reads the same whatever the window was doing when it
 * was exported.
 *
 * The period the figures cover is printed under the title — a dashboard export
 * with no date range on it is a page of numbers nobody can place later.
 */

type Summary = Record<string, any>;

const inr = (v: any) =>
  `Rs. ${Number(v || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const plain = (v: any) => String(v ?? "—");

/** A filename that says what it is and when it was taken. */
export const dashboardFileName = (d: Summary) => {
  const span = (d.period_label || "all-time").replace(/[\\/:*?"<>|]+/g, "-").replace(/\s+/g, " ").trim();
  return `Inventory Dashboard - ${span}.pdf`;
};

export async function exportInventoryDashboardPdf(d: Summary) {
  const { jsPDF } = await import("jspdf");
  const autoTable = (await import("jspdf-autotable")).default;

  const doc = new jsPDF({ unit: "mm", format: "a4" });
  const L = 14;
  const NAVY: [number, number, number] = [31, 46, 74];

  doc.setFont("helvetica", "bold");
  doc.setFontSize(16);
  doc.text("Inventory Dashboard", L, 18);

  doc.setFont("helvetica", "normal");
  doc.setFontSize(9);
  doc.setTextColor(110);
  doc.text(`Movements: ${d.period_label || "All time"}`, L, 24);
  doc.text(
    `Generated ${new Date().toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}`,
    L, 28.5);
  doc.setTextColor(0);

  let y = 35;
  const table = (head: string[], body: (string | number)[][], title?: string) => {
    if (title) {
      doc.setFont("helvetica", "bold");
      doc.setFontSize(11);
      doc.text(title, L, y);
      y += 2;
    }
    autoTable(doc, {
      startY: y + 2,
      head: [head],
      body: body.length ? body : [["—", ...head.slice(1).map(() => "")]],
      theme: "grid",
      styles: { fontSize: 8.5, cellPadding: 2 },
      headStyles: { fillColor: NAVY, fontSize: 8.5 },
      margin: { left: L, right: L },
    });
    y = (doc as any).lastAutoTable.finalY + 8;
  };

  // ── Stock on hand ──
  // Called out as current on purpose: it is the one block the period does not
  // touch, and a reader comparing two exports needs to know that.
  table(["Stock on hand (current)", "Value"], [
    ["Items", plain(d.sku_count ?? 0)],
    ["Stock value", inr(d.total_value)],
    ["Low stock items", plain(d.reorder_count ?? 0)],
  ]);

  // ── The period's own figures ──
  table([`Movements — ${d.period_label || "All time"}`, "Value"], [
    ["Purchases received", inr(d.period_purchases)],
    ["Dispatched", inr(d.period_sales)],
    ["Goods receipts", plain(d.receipt_count ?? 0)],
    ["Dispatches", plain(d.dispatch_count ?? 0)],
    ["Proforma invoices", plain(d.quote_count ?? 0)],
    ["Open proforma value", inr(d.open_quote_value)],
  ]);

  const status: [string, number][] = Object.entries(d.quote_status || {}) as any;
  if (status.length) {
    table(["Proforma status", "Count"],
          status.map(([k, n]) => [k.charAt(0).toUpperCase() + k.slice(1), plain(n)]));
  }

  const monthly: any[] = d.monthly || [];
  if (monthly.length) {
    table(["Month", "Purchases", "Sales"],
          monthly.map(m => [plain(m.name), inr(m.purchases), inr(m.sales)]),
          "Purchases vs sales");
  }

  const alerts: any[] = d.reorder_alerts || [];
  table(["Code", "Item", "In stock", "Reorder at"],
        alerts.map(a => [
          plain(a.code),
          `${a.brand || ""} ${a.model_name || ""}`.trim() || "—",
          `${Number(a.closing_stock ?? 0)} ${a.unit || ""}`.trim(),
          plain(Number(a.reorder_level ?? 0)),
        ]),
        "Low stock — at or below the reorder level");

  const byCategory: any[] = d.by_category || [];
  if (byCategory.length) {
    table(["Category", "Stock value"],
          byCategory.map(c => [plain(c.name), inr(c.value)]),
          "Stock value by category");
  }

  const levels: any[] = d.stock_levels || [];
  if (levels.length) {
    table(["Code", "In stock", "Reorder at", "Status"],
          levels.map(i => [
            plain(i.code),
            `${Number(i.closing_stock ?? 0)} ${i.unit || ""}`.trim(),
            plain(Number(i.reorder_level ?? 0)),
            plain(i.status),
          ]),
          "All items");
  }

  // Page numbers last, once the page count is known.
  const pages = doc.getNumberOfPages();
  for (let p = 1; p <= pages; p++) {
    doc.setPage(p);
    doc.setFontSize(8);
    doc.setTextColor(140);
    doc.text(`Page ${p} of ${pages}`, 200, 290, { align: "right" });
  }

  doc.save(dashboardFileName(d));
}

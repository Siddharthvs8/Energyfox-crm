/**
 * Company Performance → PDF.
 *
 * A real report rather than a photograph of the screen: the tables are written
 * as text, so the numbers can be copied out, the file stays small and it prints
 * cleanly. The one thing a screenshot would give that text cannot — the chart —
 * is carried over as the chart's own SVG, redrawn at twice the size, so it is
 * the same plot the page shows rather than a blurry crop of it.
 *
 * Capturing the page with html2canvas was the obvious route and does not work
 * here: this is Tailwind v4, whose palette computes to lab() colours that
 * html2canvas 1.4.1 cannot parse, so the capture comes out with the colours
 * wrong. The chart is exempt because recharts sets its fills as plain hex
 * attributes on the SVG.
 *
 * Everything on the page goes in, including the People tabs that are not
 * on screen at the time — an export that quietly dropped two of the three
 * boards would be worse than no export.
 */

type Row = Record<string, any>;
type Ranked = {
  rows: Row[]; count: number; best: Row | null; worst: Row | null;
  only_earner?: boolean; without_revenue: string[];
  unattributed_revenue?: string; unattributed_deals?: number;
};

/** jsPDF's standard fonts are WinAnsi and have no rupee sign, so money is
 *  written the way the Inventory export writes it. */
const inr = (v: any) =>
  `Rs. ${Number(v || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;

const pct = (v: any) => `${Number(v || 0)}%`;

export const performanceFileName = (d: Row) => {
  const span = String(d?.period_label || "All time").replace(/[\\/:*?"<>|]+/g, "-").trim();
  return `Company Performance - ${span}.pdf`;
};

/**
 * The plot itself, not a legend chip.
 *
 * Recharts draws the legend's colour swatches as `svg.recharts-surface` as well,
 * and in this version they sit *before* the plot in the DOM — so taking the
 * first match hands back a 14px square of flat colour, which is precisely what
 * the first build of this export put in the PDF. Take the largest instead, and
 * treat anything chip-sized as "no chart found".
 */
export function findChartSvg(root: ParentNode | null): SVGElement | null {
  if (!root) return null;
  let best: SVGElement | null = null;
  let area = 0;
  root.querySelectorAll<SVGElement>("svg.recharts-surface").forEach(svg => {
    const r = svg.getBoundingClientRect();
    if (r.width * r.height > area) {
      area = r.width * r.height;
      best = svg;
    }
  });
  return area >= 10000 ? best : null;
}

/**
 * The chart, as a PNG at twice its screen size.
 *
 * Returns null rather than throwing: a missing plot is a smaller loss than a
 * failed export, so the caller carries on without it.
 */
async function svgToPng(svg: SVGElement | null): Promise<{ data: string; w: number; h: number } | null> {
  if (!svg) return null;
  try {
    const box = svg.getBoundingClientRect();
    const w = Math.ceil(box.width), h = Math.ceil(box.height);
    if (!w || !h) return null;

    const clone = svg.cloneNode(true) as SVGElement;
    clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    clone.setAttribute("width", String(w));
    clone.setAttribute("height", String(h));
    // Fonts come from the page's stylesheet, which a serialised SVG does not
    // carry with it; without this the axis labels fall back to a serif face.
    clone.setAttribute("style", "font-family: Helvetica, Arial, sans-serif;");

    const markup = new XMLSerializer().serializeToString(clone);
    const url = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(markup)}`;

    const img = await new Promise<HTMLImageElement>((resolve, reject) => {
      const el = new Image();
      el.onload = () => resolve(el);
      el.onerror = reject;
      el.src = url;
    });

    const scale = 2;
    const canvas = document.createElement("canvas");
    canvas.width = w * scale;
    canvas.height = h * scale;
    const ctx = canvas.getContext("2d");
    if (!ctx) return null;
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.scale(scale, scale);
    ctx.drawImage(img, 0, 0, w, h);
    return { data: canvas.toDataURL("image/png"), w, h };
  } catch {
    return null;
  }
}

export async function exportCompanyPerformancePdf(d: Row, chartSvg: SVGElement | null) {
  const { jsPDF } = await import("jspdf");
  const autoTable = (await import("jspdf-autotable")).default;

  const doc = new jsPDF({ unit: "mm", format: "a4" });
  const L = 14;
  const PAGE_W = 210, PAGE_H = 297;
  const W = PAGE_W - L * 2;
  const NAVY: [number, number, number] = [31, 46, 74];
  const GREEN: [number, number, number] = [16, 133, 96];

  const chart = await svgToPng(chartSvg);

  // ── Header ──
  doc.setFont("helvetica", "bold");
  doc.setFontSize(17);
  doc.text("Company Performance", L, 18);

  doc.setFont("helvetica", "normal");
  doc.setFontSize(9);
  doc.setTextColor(110);
  doc.text(String(d.period_label || "All time"), L, 24);
  doc.text("Leads counted by when they arrived, money by when the deal was won.", L, 28.5);
  doc.text(
    `Generated ${new Date().toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}`,
    L, 33);
  doc.setTextColor(0);
  doc.setDrawColor(225);
  doc.line(L, 36, L + W, 36);

  let y = 43;

  const room = (needed: number) => {
    if (y + needed > PAGE_H - 18) {
      doc.addPage();
      y = 20;
    }
  };

  const heading = (text: string, sub?: string) => {
    room(16);
    doc.setFont("helvetica", "bold");
    doc.setFontSize(11.5);
    doc.setTextColor(0);
    doc.text(text, L, y);
    y += sub ? 4.5 : 2;
    if (sub) {
      doc.setFont("helvetica", "normal");
      doc.setFontSize(8);
      doc.setTextColor(120);
      doc.text(sub, L, y);
      doc.setTextColor(0);
      y += 1.5;
    }
  };

  const table = (head: string[], body: (string | number)[][], opts: Row = {}) => {
    autoTable(doc, {
      startY: y + 2,
      head: [head],
      body: body.length ? body : [[{ content: "Nothing in this window", colSpan: head.length,
                                     styles: { halign: "center", textColor: 130 } } as any]],
      theme: "grid",
      styles: { fontSize: 8, cellPadding: 1.8, overflow: "linebreak" },
      headStyles: { fillColor: NAVY, fontSize: 8, halign: "left" },
      margin: { left: L, right: L },
      ...opts,
    });
    y = (doc as any).lastAutoTable.finalY + 7;
  };

  const note = (text: string) => {
    const lines = doc.splitTextToSize(text, W);
    room(lines.length * 3.6 + 4);
    doc.setFont("helvetica", "italic");
    doc.setFontSize(7.5);
    doc.setTextColor(125);
    doc.text(lines, L, y - 2);
    doc.setTextColor(0);
    doc.setFont("helvetica", "normal");
    y += lines.length * 3.4 + 3;
  };

  // ── Headline ──
  const h = d.headline || {};
  heading("Headline");
  table(["", "", "", ""], [
    ["Leads", String(h.leads ?? 0), "Revenue (received)", inr(h.revenue)],
    ["Converted", String(h.converted ?? 0), "Billed (invoiced)", inr(h.billed)],
    ["Closed deals", String(h.closed_deals ?? 0), "Outstanding", inr(h.outstanding)],
    ["Lost", String(h.lost ?? 0), "Discounts given", inr(h.discounts)],
    ["Close rate", pct(h.close_rate), "Average deal", inr(h.avg_deal_value)],
    ["Conversion rate", pct(h.conversion_rate), "Average days to close", String(h.avg_days_to_close ?? 0)],
    ["Projects completed (all time)", String(h.completed_projects ?? 0), "", ""],
  ], {
    head: [],
    styles: { fontSize: 8.5, cellPadding: 2 },
    columnStyles: {
      0: { fontStyle: "bold", cellWidth: 46 },
      1: { cellWidth: 22, halign: "right" },
      2: { fontStyle: "bold", cellWidth: 52 },
      3: { halign: "right" },
    },
  });

  // ── The chart ──
  if (chart) {
    const drawH = Math.min((chart.h / chart.w) * W, 95);
    const drawW = (chart.w / chart.h) * drawH;
    room(drawH + 16);
    heading("Leads and revenue", `Month by month - ${d.period_label || "All time"}`);
    doc.addImage(chart.data, "PNG", L, y + 1, Math.min(drawW, W), drawH, undefined, "FAST");
    y += drawH + 5;
    // The legend is HTML on the page, so it is not inside the SVG we captured.
    doc.setFillColor(165, 180, 252);
    doc.rect(L, y - 2.6, 3, 3, "F");
    doc.setFillColor(...GREEN);
    doc.rect(L + 22, y - 2.6, 3, 3, "F");
    doc.setFontSize(8);
    doc.setTextColor(90);
    doc.setFillColor(30, 41, 59);
    doc.rect(L + 48, y - 2.6, 3, 3, "F");
    doc.text("Leads", L + 4.5, y);
    doc.text("Revenue", L + 26.5, y);
    doc.text("Running total", L + 52.5, y);
    doc.setTextColor(0);
    y += 8;
  }

  // ── Funnel ──
  heading("Where the business falls away", "Each step is a subset of the one above it");
  table(["Stage", "Count", "Of leads"],
    (d.funnel || []).map((f: Row) => [f.stage, f.count, pct(f.of_leads)]),
    { columnStyles: { 1: { halign: "right", cellWidth: 28 }, 2: { halign: "right", cellWidth: 28 } } });

  // ── Against last period ──
  const cmp = d.comparison;
  if (cmp) {
    heading("Against last period", `Same stretch of ${cmp.label}`);
    table(["Metric", "Now", "Before", "Change"],
      (cmp.metrics || []).map((m: Row) => [
        m.label,
        m.is_money ? inr(m.now) : String(m.now),
        m.is_money ? inr(m.before) : String(m.before),
        m.change_pct === null
          ? (m.from_nothing ? "new" : "-")
          : `${m.change_pct > 0 ? "+" : ""}${m.change_pct}%`,
      ]),
      { columnStyles: { 1: { halign: "right", cellWidth: 34 }, 2: { halign: "right", cellWidth: 34 },
                        3: { halign: "right", cellWidth: 26 } } });
  }

  // ── Growth pace ──
  const gr = d.growth;
  if (gr) {
    heading("Growth pace", "Month on month, over the last year");
    table(["Month", "Revenue", "Change on the month before"],
      (gr.points || []).map((pt: Row) => [
        pt.name, inr(pt.revenue),
        pt.growth_pct === null ? "-" : `${pt.growth_pct > 0 ? "+" : ""}${pt.growth_pct}%`,
      ]),
      { columnStyles: { 1: { halign: "right", cellWidth: 40 }, 2: { halign: "right", cellWidth: 50 } } });
    const bits: string[] = [];
    if (gr.average_pace !== null) bits.push(`Average ${gr.average_pace}% a month over ${gr.months_measured} month(s).`);
    if (gr.best_month) bits.push(`Best month ${gr.best_month.name} (${inr(gr.best_month.revenue)}).`);
    if (gr.recent_vs_earlier_pct !== null && gr.recent_vs_earlier_pct !== undefined)
      bits.push(`The recent half is ${Math.abs(gr.recent_vs_earlier_pct)}% ${gr.recent_vs_earlier_pct >= 0 ? "above" : "below"} the earlier half.`);
    if (bits.length) note(bits.join(" "));
  }

  // ── Projection ──
  const proj = d.projections;
  if (proj) {
    heading("Projection", `Run rate to ${proj.period_ends}`);
    table(["", ""], [
      ["Revenue so far", inr(proj.revenue_so_far)],
      ["Per day", inr(proj.revenue_per_day)],
      ["Projected for the period", inr(proj.projected_revenue)],
      ["Projected closed deals", String(proj.projected_closed_deals)],
      ["Projected leads", String(proj.projected_leads)],
      ["Days elapsed / total", `${proj.days_elapsed} / ${proj.days_total}`],
      ["Open pipeline", `${inr(proj.open_pipeline_value)} (${proj.open_leads} leads)`],
      ["Weighted by close rate", inr(proj.pipeline_weighted_value)],
    ], { head: [], columnStyles: { 0: { fontStyle: "bold", cellWidth: 70 }, 1: { halign: "right" } } });
    note(proj.assumption);
  }

  // ── What stands out ──
  const findings: Row[] = d.findings || [];
  if (findings.length) {
    heading("What stands out", "Read off the figures in this report");
    table(["", "Finding"], findings.map((f: Row) => [f.kind, f.text]),
      { columnStyles: { 0: { cellWidth: 24, fontStyle: "bold" } } });
  }
  if (d.ai_suggestions) {
    heading("Suggested next steps", "Written by AI from the figures above - check before acting");
    const lines = doc.splitTextToSize(String(d.ai_suggestions), W);
    room(lines.length * 4 + 6);
    doc.setFont("helvetica", "normal");
    doc.setFontSize(8.5);
    doc.text(lines, L, y + 2);
    y += lines.length * 4 + 6;
  }

  // ── Money in ──
  const c = d.collection || {};
  heading("Money in", "How the closed deals were paid, and what has actually landed");
  table(["Payment mode", "Deals", "Collected"],
    (c.by_mode || []).map((m: Row) => [m.label, m.count, inr(m.amount)]),
    { columnStyles: { 1: { halign: "right", cellWidth: 26 }, 2: { halign: "right", cellWidth: 40 } } });
  table(["", ""], [
    ["Fully paid deals", String(c.fully_paid ?? 0)],
    ["Part paid deals", String(c.partially_paid ?? 0)],
    ["Billed (net of discount)", inr(c.billed)],
    ["Collected", inr(c.collected)],
    ["Collected of billed", pct(c.collection_rate)],
  ], { head: [], columnStyles: { 0: { fontStyle: "bold", cellWidth: 70 }, 1: { halign: "right" } } });

  // ── Delivery ──
  const dl = d.delivery || {};
  heading("Delivery", "Of the deals won in this window, how many have been built");
  table(["", ""], [
    ["Deals won", String(dl.won ?? 0)],
    ["Completed", String(dl.completed ?? 0)],
    ["In progress", String(dl.in_progress ?? 0)],
    ["Not started", String(dl.not_started ?? 0)],
    ["Completion rate", pct(dl.completion_rate)],
    ["Average days to build", String(dl.avg_days_to_complete ?? 0)],
  ], { head: [], columnStyles: { 0: { fontStyle: "bold", cellWidth: 70 }, 1: { halign: "right" } } });

  // ── Losses ──
  const lost = d.lost || {};
  heading("Where deals are lost",
    `${lost.count ?? 0} lost, worth ${inr(lost.value)} - counted by when they were written off`);
  table(["Reason", "Deals", "Value"],
    (lost.reasons || []).map((r: Row) => [r.name, r.count, inr(r.value)]),
    { columnStyles: { 1: { halign: "right", cellWidth: 26 }, 2: { halign: "right", cellWidth: 40 } } });
  table(["How far they got", "Deals", "Value"],
    (lost.by_stage || []).map((r: Row) => [r.label, r.count, inr(r.value)]),
    { columnStyles: { 1: { halign: "right", cellWidth: 26 }, 2: { halign: "right", cellWidth: 40 } } });

  // ── What we sell ──
  const seg = d.segments || {};
  heading("What we sell", "Recorded at the site visit, so deals without one show as not recorded");
  table(["Connection type", "Deals", "Revenue"],
    (seg.by_connection || []).map((r: Row) => [r.name, r.count, inr(r.revenue)]),
    { columnStyles: { 1: { halign: "right", cellWidth: 26 }, 2: { halign: "right", cellWidth: 40 } } });
  table(["Roof type", "Deals", "Revenue"],
    (seg.by_roof || []).map((r: Row) => [r.name, r.count, inr(r.revenue)]),
    { columnStyles: { 1: { halign: "right", cellWidth: 26 }, 2: { halign: "right", cellWidth: 40 } } });

  // ── A ranked group ──
  const MONEY_COLS = {
    1: { halign: "right" as const, cellWidth: 20 },
    2: { halign: "right" as const, cellWidth: 20 },
    3: { halign: "right" as const, cellWidth: 22 },
    4: { halign: "right" as const, cellWidth: 30 },
    5: { halign: "right" as const, cellWidth: 30 },
  };

  const ranked = (title: string, sub: string, g: Ranked | undefined, one: string, unit: string) => {
    if (!g) return;
    heading(title, sub);

    room(12);
    doc.setFontSize(8.5);
    if (g.best) {
      doc.setFont("helvetica", "bold");
      doc.setTextColor(...GREEN);
      doc.text(`Most revenue: ${g.best.name} - ${inr(g.best.revenue)}`, L, y + 2);
      doc.setTextColor(180, 110, 20);
      doc.text(
        g.worst ? `Least revenue: ${g.worst.name} - ${inr(g.worst.revenue)}`
                : `Only one ${one} has earned in this window`,
        L + W / 2, y + 2);
      doc.setTextColor(0);
      doc.setFont("helvetica", "normal");
    } else {
      doc.setTextColor(130);
      doc.text(`No ${one} has brought in revenue in this window yet.`, L, y + 2);
      doc.setTextColor(0);
    }
    y += 6;

    table(["Name", "Leads", "Closed", "Close rate", "Revenue", "Billed"],
      g.rows.map(r => [
        r.name + (r.role ? ` (${r.role})` : r.manager_name ? ` (${r.manager_name})` : ""),
        r.leads, r.closed_deals, pct(r.close_rate), inr(r.revenue), inr(r.billed),
      ]),
      { columnStyles: MONEY_COLS });

    if (g.count > g.rows.length) {
      note(`Showing the top ${g.rows.length} of ${g.count} ${unit} by revenue.`);
    }
    if (g.without_revenue?.length) {
      note(`No revenue in this window: ${g.without_revenue.join(", ")}.`);
    }
    if (Number(g.unattributed_revenue || 0) > 0) {
      note(`${inr(g.unattributed_revenue)} from ${g.unattributed_deals} deal` +
           `${g.unattributed_deals === 1 ? "" : "s"} is not counted above - nobody who worked ` +
           `those leads is on a branch.`);
    }
  };

  ranked("Branches", "Ranked by revenue in this window", d.branches, "branch", "branches");
  ranked("Teams", "Ranked by revenue in this window", d.teams, "team", "teams");

  // Every tab, not only the one that happened to be open.
  ranked("People - Everyone", "Everyone who worked a lead in this window - owner, BDE or tele caller",
    d.employees, "person", "people");
  note("A deal worked by a BDE and a tele caller is credited to both, so these rows add up to " +
       "more than the company total. Each row is what that person had a hand in, not a slice " +
       "of the revenue.");
  ranked("People - BDEs", "Business development executives, ranked by revenue", d.bdes, "BDE", "BDEs");
  ranked("People - Tele Callers", "Tele callers, ranked by revenue", d.tele_callers,
    "tele caller", "tele callers");

  // ── Pipeline, sources, districts ──
  heading("Where the work is sitting", "Right now, whatever the window");
  table(["Stage", "Leads"],
    (d.pipeline || []).map((p: Row) => [p.label, p.count]),
    { columnStyles: { 1: { halign: "right", cellWidth: 30 } } });

  const cut = (title: string, rows: Row[] = []) => {
    heading(title, "By revenue");
    table(["Name", "Leads", "Closed", "Close rate", "Revenue"],
      rows.map(r => [r.name, r.leads, r.closed_deals, pct(r.close_rate), inr(r.revenue)]),
      { columnStyles: { 1: { halign: "right", cellWidth: 22 }, 2: { halign: "right", cellWidth: 22 },
                        3: { halign: "right", cellWidth: 24 }, 4: { halign: "right", cellWidth: 34 } } });
  };
  cut("Sources", d.sources);
  cut("Districts", d.districts);

  // ── Footer on every page ──
  const pages = doc.getNumberOfPages();
  for (let i = 1; i <= pages; i++) {
    doc.setPage(i);
    doc.setDrawColor(230);
    doc.line(L, PAGE_H - 14, L + W, PAGE_H - 14);
    doc.setFont("helvetica", "normal");
    doc.setFontSize(7);
    doc.setTextColor(140);
    doc.text(
      "Won means closed - a deal counts once the money has reached accounts - and revenue is " +
      "what was actually received, not what was invoiced.", L, PAGE_H - 10);
    doc.text(`Page ${i} of ${pages}`, L + W, PAGE_H - 10, { align: "right" });
    doc.setTextColor(0);
  }

  doc.save(performanceFileName(d));
}

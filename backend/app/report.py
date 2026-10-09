"""Executive report: structured content + PDF rendering."""
import io

import pandas as pd

from .utils import fmt_money, pct


def build_report(sess) -> dict:
    kp = {k["key"]: k for k in sess.kpis}
    cur = sess.currency
    money = lambda x: fmt_money(x, cur)
    ins = sess.insights
    by = lambda *t: [i for i in ins if i["type"] in t]
    s = {}
    parts = []
    if "revenue" in kp:
        parts.append(f"Total revenue is {money(kp['revenue']['value'])} from {kp['orders']['value']:,} orders (average order value {money(kp['aov']['value'])}).")
    if "growth" in kp:
        parts.append(f"Revenue changed {kp['growth']['value'] * 100:+.1f}% month over month.")
    if "margin" in kp:
        parts.append(f"Profit margin is {kp['margin']['value'] * 100:.1f}%.")
    risks = by("risk")
    if risks:
        parts.append(f"{len(risks)} risk(s) were flagged; the most important: {risks[0]['text']}")
    if not parts:
        parts.append("The dataset did not contain enough recognisable business columns for a financial summary.")
    s["Executive Summary"] = parts

    def kpi_lines(group):
        out = []
        for k in sess.kpis:
            if k["group"] == group:
                v = k["value"]
                out.append(f"{k['label']}: " + (money(v) if k["unit"] == "currency" else pct(v) if k["unit"] == "percent" else f"{v:,.1f} days" if k["unit"] == "days" else f"{v:,}" if isinstance(v, int) else str(v) if k["unit"] == "text" else f"{v:,.2f}"))
        return out

    s["Business Performance"] = kpi_lines("Sales") + kpi_lines("Profit") + [i["text"] for i in by("growth")]
    s["Customer Insights"] = kpi_lines("Customers") + [i["text"] for i in ins if i["title"] in ("Customer Concentration", "Customer Spread", "Repeat Purchasing")]
    s["Product Insights"] = kpi_lines("Products") + [i["text"] for i in ins if i["title"].startswith(("Top Product", "Top Category", "High Sales", "Loss-making", "Most Profitable", "Weakest"))]
    s["Operational Insights"] = kpi_lines("Operations") + [i["text"] for i in ins if i["title"] in ("Delivery Delays", "Delivery Performance", "High Cancellations/Returns", "Order Fulfilment")]
    s["Key Risks"] = [i["text"] for i in risks] or ["No significant risks detected."]
    s["Opportunities"] = [i["text"] for i in by("opportunity")] or ["No specific opportunities detected with the available columns."]
    s["Recommendations"] = [f"[{r['priority']}] {r['title']} - {r['action']} (Evidence: {r['evidence']})" for r in sess.recs]
    if sess.rca.get("enabled") and sess.rca.get("cases"):
        c = sess.rca["cases"][0]
        s["Root Cause Highlights"] = [c["problem"]] + [f"{f['factor']} - {f['evidence']}" for f in c["factors"][:5]]
    s = {k: [x for x in v if x] for k, v in s.items()}
    return s


def render_pdf(sess) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer

    def esc(t):
        return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("₹", "Rs ").replace("€", "EUR ").replace("£", "GBP ")

    st = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=st["Title"], textColor=colors.HexColor("#0d1b2a"), fontSize=22, alignment=0)
    h2 = ParagraphStyle("h2", parent=st["Heading2"], textColor=colors.HexColor("#0b7a75"), spaceBefore=12)
    body = ParagraphStyle("b", parent=st["BodyText"], fontSize=10, leading=14)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm, title="InsightPilot Executive Report")
    story = [Paragraph("InsightPilot - Executive Report", h1),
             Paragraph(esc(f"Dataset: {sess.filename} | {sess.summary['rows_after']:,} rows after cleaning | Data quality {sess.quality['score']}/100"), body), Spacer(1, 6)]
    chart = _chart_png(sess)
    for title, items in build_report(sess).items():
        story.append(Paragraph(title, h2))
        story.append(ListFlowable([ListItem(Paragraph(esc(i), body), leftIndent=10) for i in items], bulletType="bullet", start="-", leftIndent=12))
        if title == "Business Performance" and chart:
            story += [Spacer(1, 6), Image(io.BytesIO(chart), width=170 * mm, height=65 * mm)]
    story += [Spacer(1, 10), Paragraph(esc("All figures were calculated from the uploaded dataset. Simulation outputs (if any) are estimates, not guarantees."), ParagraphStyle("f", parent=body, textColor=colors.grey, fontSize=8))]
    doc.build(story)
    return buf.getvalue()


def _chart_png(sess):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from .analytics import complete_months, monthly
        if not sess.caps["date"] or not sess.caps["revenue"]:
            return None
        mo = monthly(sess.model)
        if len(mo) < 2:
            return None
        fig, ax = plt.subplots(figsize=(8, 3))
        ax.plot([str(i) for i in mo.index], mo["revenue"], color="#0b7a75", lw=2)
        ax.fill_between(range(len(mo)), mo["revenue"], color="#0b7a75", alpha=.12)
        ax.set_title("Monthly revenue", fontsize=10, loc="left")
        ax.set_xticks(range(0, len(mo), max(1, len(mo) // 8)))
        ax.set_xticklabels([str(i) for i in mo.index][::max(1, len(mo) // 8)], fontsize=7, rotation=0)
        ax.tick_params(axis="y", labelsize=7)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        b = io.BytesIO()
        fig.tight_layout()
        fig.savefig(b, format="png", dpi=160)
        plt.close(fig)
        return b.getvalue()
    except Exception:
        return None

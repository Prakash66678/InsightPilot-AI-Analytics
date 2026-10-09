"""Recommendation engine: each item cites its finding, evidence, business impact and action."""
from .utils import fmt_money, pct


def build_recommendations(facts: dict, rca: dict, cur: str = "") -> list:
    money = lambda x: fmt_money(x, cur)
    recs = []

    def add(priority, title, finding, evidence, impact, action):
        recs.append({"id": f"r{len(recs) + 1}", "priority": priority, "title": title, "finding": finding, "evidence": evidence, "impact": impact, "action": action})

    lm = facts.get("low_margin")
    if lm:
        add("High", f"Improve profitability of {lm['name']}", f"{lm['name']} is #{lm['rank']} by revenue but has a thin margin.",
            f"Margin {pct(lm['margin'])} vs {pct(lm['overall'])} overall on {money(lm['revenue'])} revenue.",
            f"Reaching the overall margin would add roughly {money(lm['gap_profit'])} profit on current volume.",
            "Renegotiate supplier cost, raise price modestly, or reduce discounting on this product.")
    dm = facts.get("discount_margin")
    if dm and dm["hi_margin"] < dm["lo_margin"] - 0.02:
        add("High", "Review the discount strategy", "Heavily discounted orders earn clearly lower margin.",
            f"Orders at 15%+ discount: {pct(dm['hi_margin'])} margin vs {pct(dm['lo_margin'])} at 5% or less; {dm['hi_share'] * 100:.0f}% of orders are heavily discounted.",
            "Cutting unnecessary deep discounts protects margin; use the Decision Simulator to test the volume trade-off.",
            "Cap discounts, target them at slow-moving products, and test lower tiers.")
    g = facts.get("growth")
    if g and g["change"] <= -0.05 and rca.get("enabled") and rca.get("cases"):
        c = rca["cases"][0]
        top = next((f for f in c["factors"] if f["impact"] is not None and f["factor"].split(":")[0] not in ("Orders", "Average order value")), None)
        add("High", f"Recover revenue lost in {g['last']}", f"Revenue fell {abs(g['change']) * 100:.1f}% month over month.",
            top["evidence"] if top else c["problem"], f"Revenue dropped from {money(c['revenue_before'])} to {money(c['revenue_after'])}.",
            top["action"] if top else "Work through the Root Cause Analysis factors, starting with the largest contributor.")
    ro = facts.get("region_opp")
    if ro:
        add("Medium", f"Raise order value in {ro['name']}", "Strong demand but low spend per order.",
            f"{ro['orders']:,} orders at {money(ro['aov'])} average vs {money(ro['overall_aov'])} overall.",
            f"Closing half the AOV gap could add about {money(ro['orders'] * (ro['overall_aov'] - ro['aov']) / 2)} revenue.",
            "Introduce bundles, minimum-basket offers and upsells for this region.")
    ru = facts.get("region_under")
    if ru:
        add("Medium", f"Focus marketing on {ru['name']}", f"{ru['name']} is well below the average region.",
            f"{money(ru['revenue'])} vs {money(ru['avg'])} average per region.", f"Reaching the regional average would add about {money(ru['avg'] - ru['revenue'])}.",
            "Run a localized campaign, check product availability and delivery coverage there.")
    c = facts.get("concentration")
    if c and c["top10_share"] >= 0.35:
        add("Medium", "Reduce dependence on top customers", "A small group of customers drives a large share of revenue.",
            f"Top 10% of customers ({c['k']:,}) = {c['top10_share'] * 100:.1f}% of revenue.", "Losing a few key accounts would hit revenue disproportionately.",
            "Launch a loyalty/retention programme for top customers and grow the mid-tier.")
    d = facts.get("delivery")
    if d and d["worst"] > 1.15 * d["avg"] and d["worst"] - d["avg"] >= 0.5:
        add("Medium", "Fix delivery delays", "Delivery time spiked above normal.",
            f"{d['worst_month']}: {d['worst']:.1f} days vs {d['avg']:.1f} average (latest month {d['latest']:.1f}).", "Slow delivery tends to raise cancellations and hurt repeat purchase.",
            "Audit courier performance and warehouse capacity in the affected period.")
    ca = facts.get("cancel")
    if ca and (ca["cancel_rate"] > 0.08 or ca["return_rate"] > 0.08):
        add("Medium", "Cut cancellations and returns", "Cancellation/return rates are high.",
            f"Cancelled {pct(ca['cancel_rate'])}, returned {pct(ca['return_rate'])}" + (f"; worst region {ca['worst_region']}." if ca.get("worst_region") else "."),
            "Every cancelled or returned order is lost revenue plus handling cost.", "Investigate stock accuracy, product descriptions and delivery promises.")
    lp = facts.get("loss_products")
    if lp:
        add("High", "Fix or retire loss-making products", f"{len(lp)} product(s) have negative total profit.", ", ".join(lp), "Each sale of these products reduces total profit.",
            "Reprice, renegotiate cost, or remove them from the catalogue.")
    if not recs:
        add("Low", "Keep monitoring", "No significant risks were detected with the available columns.", "All calculated indicators were within normal ranges.", "n/a",
            "Add more columns (cost, discount, status, dates) to unlock deeper analysis.")
    order = {"High": 0, "Medium": 1, "Low": 2}
    recs.sort(key=lambda r: order[r["priority"]])
    for i, r in enumerate(recs, 1):
        r["id"] = f"r{i}"
    return recs

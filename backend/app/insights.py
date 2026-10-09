"""Insight engine: every statement is computed from the data; nothing is templated without numbers."""
import numpy as np
import pandas as pd

from .analytics import complete_months, group_table, monthly, n_orders, valid
from .utils import fmt_money, pct


def generate_insights(m: pd.DataFrame, caps: dict, cur: str = ""):
    ins, facts = [], {}
    if m.empty or len(m) < 5:
        return [{"id": "small", "type": "info", "title": "Not enough data", "text": "The dataset has too few rows to produce reliable insights.", "evidence": []}], facts
    v = valid(m)
    money = lambda x: fmt_money(x, cur)
    gt = lambda col: group_table(v, col).drop(index="Unknown", errors="ignore")   # 'Unknown' is a fill label, not a real group

    def add(type_, title, text, evidence=None):
        ins.append({"id": f"i{len(ins) + 1}", "type": type_, "title": title, "text": text, "evidence": evidence or []})

    if not caps["revenue"]:
        add("info", "Revenue not available", "No revenue/sales column was found, so financial insights are disabled.")
        return ins, facts
    total = float(v["revenue"].sum())
    tp = float(v["profit"].sum()) if caps["profit"] else None
    overall_margin = tp / total if (tp is not None and total) else None
    mo, partial = complete_months(monthly(m)) if caps["date"] else (pd.DataFrame(), False)

    # 1. growth
    if len(mo) >= 2 and mo["revenue"].iloc[-2] > 0:
        last, prev = mo.index[-1], mo.index[-2]
        chg = mo["revenue"].iloc[-1] / mo["revenue"].iloc[-2] - 1
        facts["growth"] = {"change": chg, "last": str(last), "prev": str(prev)}
        add("growth" if chg >= 0 else "risk", "Revenue Growth" if chg >= 0 else "Revenue Decline",
            f"Revenue {'increased' if chg >= 0 else 'decreased'} {abs(chg) * 100:.1f}% in {last} compared with {prev}.",
            [f"{prev}: {money(mo['revenue'].iloc[-2])}", f"{last}: {money(mo['revenue'].iloc[-1])}"] + (["The latest partial month was excluded from this comparison."] if partial else []))
        if len(mo) >= 6:
            h = len(mo) // 2
            a, b = mo["revenue"].iloc[:h].mean(), mo["revenue"].iloc[h:].mean()
            if a > 0:
                add("growth" if b >= a else "risk", "Long-term Trend",
                    f"Average monthly revenue in the later half of the data ({money(b)}) is {abs(b / a - 1) * 100:.1f}% {'higher' if b >= a else 'lower'} than in the earlier half ({money(a)}).")
        # biggest monthly drop
        pc = mo["revenue"].pct_change().dropna()
        if len(pc) and pc.min() <= -0.15:
            mth = pc.idxmin()
            facts["decline_month"] = str(mth)
            add("risk", "Sharp Monthly Drop", f"Revenue fell {abs(pc.min()) * 100:.1f}% in {mth} versus the previous month - the largest drop in the data.",
                ["See Root Cause Analysis for the contributing factors."])
        # seasonality
        if len(mo) >= 12:
            idx = mo.groupby(mo.index.month)["revenue"].mean()
            idx = idx / idx.mean()
            pk = idx.idxmax()
            if idx.max() >= 1.2:
                name = pd.Period(year=2000, month=int(pk), freq="M").strftime("%B")
                add("info", "Seasonal Peak", f"{name} is the strongest month of the year, running {(idx.max() - 1) * 100:.0f}% above the average month.")

    # 2. top dimensions
    for col, label in (("category", "Category"), ("region", "Region"), ("product", "Product"), ("country", "Country"), ("city", "City")):
        if caps[col]:
            t = gt(col)
            if len(t) >= 2:
                top = t.iloc[0]
                share = top.revenue / total
                facts[f"top_{col}"] = {"name": str(t.index[0]), "share": share}
                add("top", f"Top {label}", f"{t.index[0]} generated the highest revenue ({money(top.revenue)}, {share * 100:.1f}% of the total).",
                    [f"#2: {t.index[1]} ({money(t.iloc[1].revenue)})"])

    # 3. customer concentration
    if caps["customer_id"]:
        cr = v.groupby("customer_id")["revenue"].sum().sort_values(ascending=False)
        if len(cr) >= 20:
            k = max(1, int(round(len(cr) * 0.1)))
            share = cr.head(k).sum() / cr.sum()
            n80 = int((cr.cumsum() / cr.sum() < 0.8).sum() + 1)
            facts["concentration"] = {"top10_share": share, "k": k, "n": len(cr), "n80": n80}
            if share >= 0.35:
                add("risk", "Customer Concentration", f"The top 10% of customers ({k:,} of {len(cr):,}) generate {share * 100:.1f}% of revenue.",
                    [f"{n80:,} customers account for 80% of revenue."])
            else:
                add("info", "Customer Spread", f"Revenue is fairly spread out: the top 10% of customers contribute {share * 100:.1f}% of the total.")
        oc = v.groupby("customer_id")["order_id"].nunique() if caps["order_id"] else v.groupby("customer_id").size()
        if len(oc) >= 20:
            rep = (oc >= 2).mean()
            add("info", "Repeat Purchasing", f"{rep * 100:.1f}% of customers have ordered more than once.")
            facts["repeat_rate"] = rep

    # 4. product profitability
    if caps["product"] and caps["profit"]:
        pt = gt("product")
        if len(pt) >= 5 and overall_margin is not None:
            top_n = max(3, int(len(pt) * 0.4))
            hv = pt.head(top_n)
            cand = hv[(hv.margin < overall_margin - 0.08) | (hv.margin < overall_margin * 0.5)].sort_values("margin")
            if len(cand):
                p = cand.index[0]
                r = cand.iloc[0]
                rank = list(pt.index).index(p) + 1
                facts["low_margin"] = {"name": str(p), "margin": float(r.margin), "revenue": float(r.revenue), "rank": rank,
                                       "overall": overall_margin, "gap_profit": float(r.revenue * (overall_margin - r.margin))}
                add("risk", "High Sales, Low Profit", f"{p} ranks #{rank} by revenue but earns only {pct(r.margin)} margin versus {pct(overall_margin)} overall.",
                    [f"Revenue {money(r.revenue)}, profit {money(r.profit)}", f"If it matched the overall margin, profit would be about {money(r.revenue * (overall_margin - r.margin))} higher."])
            loss = pt[pt.profit < 0]
            if len(loss):
                facts["loss_products"] = [str(i) for i in loss.index[:5]]
                add("risk", "Loss-making Products", f"{len(loss)} product(s) lose money overall, e.g. {loss.index[0]} ({money(loss.iloc[0].profit)}).")
            best = pt.sort_values("margin", ascending=False)
            add("info", "Most Profitable Margin", f"{best.index[0]} has the best margin at {pct(best.iloc[0].margin)}.")
    if caps["category"] and caps["profit"]:
        ct = gt("category")
        if len(ct) >= 2:
            lo = ct.sort_values("margin").iloc[0]
            add("info", "Weakest Category Margin", f"{ct.sort_values('margin').index[0]} has the lowest category margin at {pct(lo.margin)}.")

    # 5. regional performance
    if caps["region"]:
        rt = gt("region")
        if len(rt) >= 2:
            mean_rev = rt["revenue"].mean()
            low = rt.sort_values("revenue").iloc[0]
            lname = rt.sort_values("revenue").index[0]
            overall_aov = total / n_orders(v)
            if low.revenue < 0.75 * mean_rev:
                facts["region_under"] = {"name": str(lname), "revenue": float(low.revenue), "avg": float(mean_rev)}
                add("risk", "Underperforming Region", f"{lname} is underperforming: {money(low.revenue)} revenue, {(1 - low.revenue / mean_rev) * 100:.0f}% below the average region ({money(mean_rev)}).")
            opp = rt[(rt.orders >= rt["orders"].mean()) & (rt.aov <= 0.9 * overall_aov)]
            if len(opp):
                o = opp.sort_values("orders", ascending=False).iloc[0]
                oname = opp.sort_values("orders", ascending=False).index[0]
                facts["region_opp"] = {"name": str(oname), "orders": int(o.orders), "aov": float(o.aov), "overall_aov": float(overall_aov)}
                add("opportunity", "Regional Opportunity", f"{oname} has strong order volume ({int(o.orders):,} orders) but a lower average order value ({money(o.aov)} vs {money(overall_aov)} overall).",
                    ["Upselling or bundling here could lift revenue without needing more customers."])

    # 6. discount vs margin
    if caps["discount"] and caps["profit"]:
        vv = v[(v["revenue"] > 0) & v["discount"].notna()].copy()
        if len(vv) >= 100:
            vv["mg"] = vv["profit"] / vv["revenue"]
            hi, lo = vv[vv["discount"] >= 0.15], vv[vv["discount"] <= 0.05]
            corr = vv["discount"].corr(vv["mg"])
            if len(hi) >= 30 and len(lo) >= 30:
                mh, ml = hi["profit"].sum() / hi["revenue"].sum(), lo["profit"].sum() / lo["revenue"].sum()
                facts["discount_margin"] = {"hi_margin": mh, "lo_margin": ml, "corr": corr, "hi_share": len(hi) / len(vv)}
                if mh < ml - 0.02:
                    add("risk", "Discounts Erode Margin", f"Orders discounted 15% or more earn {pct(mh)} margin versus {pct(ml)} for orders discounted 5% or less.",
                        [f"Correlation between discount and order margin: {corr:.2f}", f"{len(hi) / len(vv) * 100:.0f}% of orders carry a discount of 15% or more."])
                else:
                    add("info", "Discounts and Margin", f"Higher discounts do not noticeably reduce margin here ({pct(mh)} at 15%+ vs {pct(ml)} at 5% or less).")

    # 7. delivery
    if caps["delivery_days"] and len(mo) >= 3 and "delivery_days" in mo:
        dd = mo["delivery_days"].dropna()
        if len(dd) >= 3:
            avg = m["delivery_days"].mean()
            worst = dd.idxmax()
            facts["delivery"] = {"avg": float(avg), "worst_month": str(worst), "worst": float(dd.max()), "latest": float(dd.iloc[-1])}
            if dd.max() > 1.15 * avg and dd.max() - avg >= 0.5:
                add("risk", "Delivery Delays", f"Average delivery time peaked at {dd.max():.1f} days in {worst}, {(dd.max() / avg - 1) * 100:.0f}% above the overall average of {avg:.1f} days.",
                    [f"Latest month: {dd.iloc[-1]:.1f} days"])
            else:
                add("info", "Delivery Performance", f"Delivery time is stable at about {avg:.1f} days on average.")

    # 8. cancellations / returns
    if caps["status"]:
        cr_, rr = m["is_cancelled"].mean(), m["is_returned"].mean()
        facts["cancel"] = {"cancel_rate": float(cr_), "return_rate": float(rr)}
        ev = []
        if caps["region"] and m["is_cancelled"].any():
            by = m.groupby("region")["is_cancelled"].mean().sort_values(ascending=False)
            if len(by) >= 2 and by.iloc[0] >= 1.3 * cr_:
                ev.append(f"{by.index[0]} has the highest cancellation rate ({pct(by.iloc[0])}).")
                facts["cancel"]["worst_region"] = str(by.index[0])
        if cr_ > 0.08 or rr > 0.08:
            add("risk", "High Cancellations/Returns", f"{pct(cr_)} of orders are cancelled and {pct(rr)} are returned.", ev)
        else:
            add("info", "Order Fulfilment", f"Cancellation rate is {pct(cr_)} and return rate is {pct(rr)}.", ev)

    # 9. ratings
    if caps["rating"]:
        add("info", "Customer Rating", f"Average rating is {m['rating'].mean():.2f}.")

    order = {"risk": 0, "opportunity": 1, "growth": 2, "top": 3, "info": 4}
    ins.sort(key=lambda i: order.get(i["type"], 9))
    return ins, facts

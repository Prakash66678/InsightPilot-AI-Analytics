"""Root cause analysis: decomposes a revenue change using only the dataset's own numbers."""
import numpy as np
import pandas as pd

from .analytics import complete_months, monthly, n_orders
from .utils import fmt_money


def _contrib(A, B, dim):
    ra = A.groupby(dim)["revenue"].sum()
    rb = B.groupby(dim)["revenue"].sum()
    d = rb.sub(ra, fill_value=0)
    pc = (rb.sub(ra, fill_value=0) / ra.reindex(d.index).replace(0, np.nan))
    return pd.DataFrame({"before": ra.reindex(d.index).fillna(0), "after": rb.reindex(d.index).fillna(0), "delta": d, "pct": pc})


def _case(m, caps, cur, curr, prev):
    money = lambda x: fmt_money(x, cur)
    v = m[m["valid"] & m["date"].notna()]
    A, B = v[v["month"] == prev], v[v["month"] == curr]
    ra, rb = A["revenue"].sum(), B["revenue"].sum()
    total_delta = rb - ra
    chg = total_delta / ra if ra else 0
    up = total_delta >= 0
    na, nb = n_orders(A), n_orders(B)
    aova, aovb = ra / na if na else 0, rb / nb if nb else 0
    orders_effect, aov_effect = (nb - na) * aova, (aovb - aova) * nb
    factors, actions = [], []

    def share(x):
        return f"{abs(x / total_delta) * 100:.0f}% of the {'increase' if up else 'decrease'}" if total_delta else ""

    factors.append({"factor": f"Orders {'increased' if nb >= na else 'decreased'} {abs(nb / na - 1) * 100:.1f}%" if na else "Orders changed",
                    "evidence": f"{na:,} orders in {prev} -> {nb:,} in {curr}; volume effect {money(orders_effect)} ({share(orders_effect)})",
                    "impact": float(orders_effect), "action": "Review traffic, acquisition and retention activity for the period." if nb < na else "Check that the extra volume is sustainable (stock, delivery capacity)."})
    factors.append({"factor": f"Average order value {'rose' if aovb >= aova else 'fell'} {abs(aovb / aova - 1) * 100:.1f}%" if aova else "AOV changed",
                    "evidence": f"AOV {money(aova)} -> {money(aovb)}; value effect {money(aov_effect)} ({share(aov_effect)})",
                    "impact": float(aov_effect), "action": "Review pricing, discounting and product mix." if aovb < aova else "Keep the upsell/mix drivers that lifted order value."})

    top_dims = []
    for dim, label in (("category", "Category"), ("region", "Region"), ("product", "Product"), ("city", "City"), ("country", "Country")):
        if caps.get(dim):
            c = _contrib(A, B, dim)
            if len(c) < 2:
                continue
            row = c.sort_values("delta", ascending=up).iloc[0] if not up else c.sort_values("delta", ascending=False).iloc[0]
            name = c.sort_values("delta", ascending=up).index[0] if not up else c.sort_values("delta", ascending=False).index[0]
            if total_delta and np.sign(row.delta) == np.sign(total_delta):
                top_dims.append((abs(row.delta / total_delta), dim, label, name, row))
    top_dims.sort(key=lambda t: -t[0])
    chart = None
    for sh, dim, label, name, row in top_dims[:3]:
        pcs = f"{row.pct * 100:+.0f}%" if pd.notna(row.pct) else "new"
        factors.append({"factor": f"{label} {name}: revenue {pcs}",
                        "evidence": f"{money(row.before)} -> {money(row.after)} ({money(row.delta)}); accounts for {sh * 100:.0f}% of the total change",
                        "impact": float(row.delta),
                        "action": f"Investigate {label.lower()} '{name}': stock availability, pricing, competitor or campaign changes."})
    if top_dims:  # drill down inside the biggest contributor
        _, dim, label, name, _ = top_dims[0]
        A2, B2 = A[A[dim] == name], B[B[dim] == name]
        for d2, l2 in (("category", "category"), ("product", "product"), ("region", "region")):
            if d2 != dim and caps.get(d2):
                c2 = _contrib(A2, B2, d2).sort_values("delta", ascending=up)
                if len(c2) and np.sign(c2.iloc[0].delta) == np.sign(total_delta):
                    r2 = c2.iloc[0]
                    factors.append({"factor": f"Within {name}, {l2} {c2.index[0]} moved most ({r2.pct * 100:+.0f}%)" if pd.notna(r2.pct) else f"Within {name}, {l2} {c2.index[0]} moved most",
                                    "evidence": f"{money(r2.before)} -> {money(r2.after)} ({money(r2.delta)})", "impact": float(r2.delta),
                                    "action": f"Prioritise a closer look at {c2.index[0]} in {name}."})
                    break
        c = _contrib(A, B, dim).sort_values("delta")
        chart = {"title": f"Revenue change by {label.lower()} ({prev} -> {curr})", "labels": [str(i) for i in c.index], "values": [float(x) for x in c["delta"]]}

    # operational signals
    ma, mb = m[m["month"] == prev], m[m["month"] == curr]
    if caps.get("status") and len(ma) and len(mb):
        ca, cb = ma["is_cancelled"].mean(), mb["is_cancelled"].mean()
        if cb - ca >= 0.02 or (not up and cb > ca * 1.3 and cb - ca >= 0.01):
            factors.append({"factor": f"Cancellation rate rose from {ca * 100:.1f}% to {cb * 100:.1f}%", "evidence": f"{int(mb['is_cancelled'].sum()):,} cancelled orders in {curr} vs {int(ma['is_cancelled'].sum()):,} in {prev}",
                            "impact": None, "action": "Check stock-outs and fulfilment failures behind cancellations."})
    if caps.get("delivery_days"):
        da, db = ma["delivery_days"].mean(), mb["delivery_days"].mean()
        if pd.notna(da) and pd.notna(db) and db > da * 1.15 and db - da >= 0.5:
            factors.append({"factor": f"Delivery time increased from {da:.1f} to {db:.1f} days", "evidence": f"+{(db / da - 1) * 100:.0f}% month over month", "impact": None,
                            "action": "Review logistics partners and warehouse capacity - slow delivery often drives cancellations."})
    if caps.get("discount"):
        xa, xb = A["discount"].mean(), B["discount"].mean()
        if pd.notna(xa) and pd.notna(xb) and abs(xb - xa) >= 0.01:
            factors.append({"factor": f"Average discount {'rose' if xb > xa else 'fell'} from {xa * 100:.1f}% to {xb * 100:.1f}%", "evidence": "Discount level shifts demand and margin.", "impact": None,
                            "action": "Re-check whether the discount level is delivering volume that justifies its margin cost."})
    for f in factors:
        if f["action"] not in actions:
            actions.append(f["action"])
    return {"problem": f"Revenue {'increased' if up else 'decreased'} {abs(chg) * 100:.1f}% in {curr} (vs {prev})", "direction": "up" if up else "down",
            "period": str(curr), "previous": str(prev), "change_pct": float(chg), "revenue_before": float(ra), "revenue_after": float(rb),
            "factors": factors, "actions": actions[:5], "chart": chart}


def run_rca(m: pd.DataFrame, caps: dict, cur: str = "") -> dict:
    if not caps["date"]:
        return {"enabled": False, "reason": "Your dataset does not contain a date column, so root cause analysis (which compares periods) is disabled."}
    if not caps["revenue"]:
        return {"enabled": False, "reason": "No revenue column was found, so there is no revenue change to investigate."}
    mo, partial = complete_months(monthly(m))
    if len(mo) < 2:
        return {"enabled": False, "reason": "At least two complete months of data are needed to compare periods."}
    pc = mo["revenue"].pct_change().dropna()
    cases, seen = [], set()
    latest = pc.index[-1]
    if abs(pc.iloc[-1]) >= 0.05:
        seen.add(latest)
    drops = pc[pc <= -0.10]
    if len(drops):
        seen.add(drops.index[-1])
    for per in sorted(seen, reverse=True)[:3]:
        cases.append(_case(m, caps, cur, per, per - 1))
    msg = None if cases else f"No major revenue change found - the largest month-over-month swing was {pc.abs().max() * 100:.1f}%."
    return {"enabled": True, "cases": cases, "message": msg,
            "disclaimer": "These factors show where in your data the change happened. Causes outside the dataset (competitors, supply issues, campaigns) cannot be confirmed from it."}

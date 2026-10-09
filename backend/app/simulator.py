"""What-if simulator. Deterministic, transparent assumptions, always labelled as an estimate."""
import numpy as np
import pandas as pd

from .analytics import n_orders, valid

DEFAULT_ELASTICITY = -1.2


def estimate_elasticity(m: pd.DataFrame):
    """Within-product log-log slope of units on net price; falls back to a labelled assumption."""
    need = {"quantity", "revenue"}
    if not need <= set(m.columns) or "discount" not in m:
        return DEFAULT_ELASTICITY, "assumed"
    v = valid(m)
    v = v[(v["quantity"] > 0) & v["discount"].notna() & (v["discount"] < 0.95)]
    if len(v) < 200 or v["discount"].nunique() < 3:
        return DEFAULT_ELASTICITY, "assumed"
    x = np.log(1 - v["discount"])
    y = np.log(v["quantity"])
    if "product" in v:
        x = x - x.groupby(v["product"]).transform("mean")
        y = y - y.groupby(v["product"]).transform("mean")
    if x.std() < 1e-6:
        return DEFAULT_ELASTICITY, "assumed"
    slope = float((x * y).sum() / (x * x).sum())
    if not (-3.5 <= slope <= -0.2):
        return DEFAULT_ELASTICITY, "assumed"
    return round(slope, 2), "estimated from your data"


def config(m: pd.DataFrame, caps: dict) -> dict:
    ok = caps["revenue"] and caps["quantity"] is not None
    controls = {
        "discount": {"enabled": bool(caps["discount"] and caps["revenue"]), "reason": None if caps["discount"] and caps["revenue"] else "Needs a discount column and a revenue column."},
        "price": {"enabled": bool(caps["revenue"]), "reason": None if caps["revenue"] else "Needs a revenue column."},
        "quantity": {"enabled": bool(caps["revenue"]), "reason": None if caps["revenue"] else "Needs a revenue column."},
        "marketing": {"enabled": bool(caps["marketing"] and caps["revenue"]), "reason": None if caps["marketing"] else "Your dataset has no marketing-spend column, so its effect cannot be estimated."},
        "conversion": {"enabled": bool(caps["conversion"] and caps["revenue"]), "reason": None if caps["conversion"] else "Your dataset has no conversion-rate (or visits) column, so this cannot be simulated."},
    }
    base = baseline(m, caps) if caps["revenue"] else None
    return {"enabled": bool(caps["revenue"]), "controls": controls, "baseline": base,
            "reason": None if caps["revenue"] else "A revenue column is required for the simulator."}


def baseline(m, caps):
    v = valid(m)
    rev = float(v["revenue"].sum())
    orders = n_orders(v)
    units = float(v["quantity"].sum()) if caps["quantity"] else None
    cost = float(v["cost"].sum()) if caps["cost"] else (rev - float(v["profit"].sum()) if caps["profit"] else None)
    disc = float(v["discount"].mean()) if caps["discount"] else 0.0
    mk = float(v["marketing"].sum()) if caps["marketing"] else 0.0
    el, src = estimate_elasticity(m)
    return {"revenue": rev, "orders": orders, "units": units, "cost": cost, "profit": (rev - cost) if cost is not None else None,
            "margin": ((rev - cost) / rev) if (cost is not None and rev) else None, "avg_discount": disc, "marketing": mk,
            "elasticity": el, "elasticity_source": src}


def _scenario(b, d1, price_chg, qty_chg, mk_chg, conv_chg):
    d0 = b["avg_discount"]
    f = ((1 - d1) / (1 - d0 if d0 < 1 else 1)) * (1 + price_chg)
    demand = (max(f, 0.01) ** b["elasticity"]) * (1 + qty_chg) * (1 + conv_chg)
    if b["marketing"] > 0 and mk_chg:
        demand *= 1 + 0.10 * np.log1p(mk_chg) if mk_chg > -1 else 0.5      # diminishing returns, assumption
    rev = b["revenue"] * f * demand
    out = {"revenue": rev, "orders": b["orders"] * demand, "units": (b["units"] * demand) if b["units"] is not None else None}
    if b["cost"] is not None:
        cost = b["cost"] * demand + b["marketing"] * mk_chg
        out["cost"] = cost
        out["profit"] = rev - cost
        out["margin"] = (rev - cost) / rev if rev else None
    return out


def simulate(m, caps, p: dict) -> dict:
    if not caps["revenue"]:
        return {"enabled": False, "reason": "A revenue column is required for the simulator."}
    b = baseline(m, caps)
    cfg = config(m, caps)["controls"]
    d1 = b["avg_discount"] if not cfg["discount"]["enabled"] else float(p.get("discount_pct", b["avg_discount"] * 100)) / 100
    price = float(p.get("price_change_pct", 0)) / 100 if cfg["price"]["enabled"] else 0.0
    qty = float(p.get("quantity_change_pct", 0)) / 100 if cfg["quantity"]["enabled"] else 0.0
    mk = float(p.get("marketing_change_pct", 0)) / 100 if cfg["marketing"]["enabled"] else 0.0
    cv = float(p.get("conversion_change_pct", 0)) / 100 if cfg["conversion"]["enabled"] else 0.0
    d1 = min(max(d1, 0.0), 0.9)
    s = _scenario(b, d1, price, qty, mk, cv)
    curve = []
    if cfg["discount"]["enabled"]:
        for d in range(0, 36, 2):
            c = _scenario(b, d / 100, price, qty, mk, cv)
            curve.append({"discount": d, "revenue": c["revenue"], "profit": c.get("profit")})
    deltas = {k: (s[k] - b[k]) if (s.get(k) is not None and b.get(k) is not None) else None for k in ("revenue", "orders", "profit")}
    return {"enabled": True, "label": "ESTIMATED / SIMULATION", "baseline": b, "scenario": s, "delta": deltas, "curve": curve,
            "assumptions": [
                f"Price elasticity of demand = {b['elasticity']} ({b['elasticity_source']}).",
                "Unit cost stays constant, so total cost scales with units sold.",
                "Estimates are directional, not guaranteed forecasts; real results depend on competitors, stock and seasonality.",
            ] + (["Marketing uplift assumes diminishing returns (0.10 x ln(1 + spend change))."] if cfg["marketing"]["enabled"] else [])}

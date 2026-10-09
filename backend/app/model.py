"""Builds a standardised analysis frame from whatever columns the user's dataset has."""
import numpy as np
import pandas as pd


def build_model(df: pd.DataFrame, roles: dict):
    m = pd.DataFrame(index=df.index)
    notes = []
    for role, col in roles.items():
        m[role] = df[col]

    # discount -> fraction 0..1
    if "discount" in m:
        mx = m["discount"].max()
        if pd.notna(mx) and mx > 1.0:
            m["discount"] = m["discount"] / 100.0
        m["discount"] = m["discount"].clip(0, 1)

    # revenue
    if "revenue" not in m and "quantity" in m and "price" in m:
        m["revenue"] = m["quantity"] * m["price"] * (1 - m["discount"].fillna(0) if "discount" in m else 1)
        notes.append("No revenue column found; revenue was calculated as Quantity x Unit price (after discount).")

    # cost
    if "cost" in m and "unit cost" in roles.get("cost", "").lower() and "quantity" in m:
        m["cost"] = m["cost"] * m["quantity"]
        notes.append("Cost column looks like a unit cost; multiplied by quantity to get total cost.")

    # profit
    if "profit" not in m and "revenue" in m and "cost" in m:
        m["profit"] = m["revenue"] - m["cost"]
        notes.append("No profit column found; profit was calculated as Revenue - Cost.")

    # status flags
    if "status" in m:
        st = m["status"].astype(str).str.lower()
        m["is_cancelled"] = st.str.contains("cancel")
        m["is_returned"] = st.str.contains("return|refund|rto")
        m["valid"] = ~(m["is_cancelled"] | m["is_returned"])
        if m["is_cancelled"].any() or m["is_returned"].any():
            notes.append("Cancelled and returned orders are excluded from revenue, profit and customer KPIs; they are used for cancellation/return rates.")
    else:
        m["is_cancelled"] = False
        m["is_returned"] = False
        m["valid"] = True

    # dates
    if "date" in m:
        m["month"] = m["date"].dt.to_period("M")
    if "delivery_days" not in m and "date" in m and "delivery_date" in m:
        d = (m["delivery_date"] - m["date"]).dt.days.astype(float)
        d[d < 0] = np.nan
        d[m["is_cancelled"]] = np.nan
        m["delivery_days"] = d

    caps = {k: (k in m.columns) for k in
            ["order_id", "customer_id", "product", "category", "region", "country", "city", "status", "payment",
             "revenue", "quantity", "price", "cost", "profit", "date", "delivery_days", "discount", "rating",
             "marketing", "conversion"]}
    if not caps["date"]:
        notes.append("Your dataset does not contain a usable date column, so time-series analysis (trends, growth, root cause) has been disabled.")
    if not caps["revenue"]:
        notes.append("No revenue/sales column could be identified (and it cannot be derived from quantity x price), so revenue KPIs are disabled.")
    return m, caps, notes

"""Column-role detection. Works from column names + data types, never fixed names."""
import re

import pandas as pd

KEYWORDS = {
    "order_id": [("order id", 9), ("order no", 8), ("order number", 8), ("invoice no", 7), ("invoice number", 7), ("invoice", 5), ("transaction id", 8), ("txn id", 7)],
    "customer_id": [("customer id", 9), ("cust id", 8), ("customer no", 8), ("customer number", 8), ("customer code", 8), ("client id", 8), ("customer", 6), ("user id", 6), ("buyer", 5), ("customer name", 7)],
    "product": [("product name", 9), ("product", 8), ("item name", 8), ("item", 6), ("sku", 5), ("product id", 5)],
    "category": [("category", 8), ("product category", 9), ("department", 5), ("product type", 6), ("segment", 4)],
    "revenue": [("revenue", 9), ("sales amount", 9), ("total amount", 9), ("total sales", 9), ("net sales", 9), ("sales", 8), ("order value", 8), ("line total", 8), ("amount", 6), ("gmv", 7), ("turnover", 7), ("total price", 7), ("total", 4)],
    "quantity": [("quantity", 9), ("qty", 9), ("units sold", 9), ("order quantity", 9), ("units", 7), ("volume", 4)],
    "price": [("unit price", 9), ("price per unit", 9), ("selling price", 8), ("price", 7), ("mrp", 5), ("rate", 3)],
    "cost": [("total cost", 9), ("cogs", 9), ("cost price", 8), ("unit cost", 8), ("cost", 8), ("expense", 4)],
    "profit": [("net profit", 9), ("gross profit", 9), ("profit", 9), ("margin", 5), ("earnings", 3)],
    "date": [("order date", 10), ("purchase date", 9), ("transaction date", 9), ("invoice date", 8), ("sale date", 8), ("date", 7), ("ordered at", 6), ("created at", 5), ("timestamp", 5)],
    "delivery_date": [("delivery date", 10), ("delivered date", 9), ("ship date", 8), ("shipping date", 8), ("shipped date", 8), ("delivered at", 8), ("received date", 8), ("dispatch date", 7)],
    "delivery_days": [("delivery days", 9), ("delivery time", 9), ("shipping days", 8), ("days to deliver", 8), ("lead time", 6)],
    "region": [("region", 9), ("territory", 6), ("zone", 6), ("area", 5), ("state", 5), ("market", 4)],
    "country": [("country", 9), ("nation", 6)],
    "city": [("city", 9), ("town", 6), ("district", 4)],
    "discount": [("discount pct", 9), ("discount percent", 9), ("discount rate", 9), ("discount", 9), ("disc", 6), ("promo", 4)],
    "status": [("order status", 10), ("delivery status", 8), ("status", 9), ("fulfillment", 5)],
    "payment": [("payment method", 10), ("payment type", 9), ("payment mode", 9), ("pay mode", 8), ("payment", 8)],
    "rating": [("rating", 9), ("review score", 8), ("stars", 6), ("satisfaction", 6), ("csat", 6), ("score", 3)],
    "marketing": [("marketing spend", 10), ("ad spend", 10), ("marketing cost", 9), ("campaign cost", 8), ("promotion spend", 8), ("advertising", 8)],
    "conversion": [("conversion rate", 10), ("conversion", 8), ("cvr", 6)],
}
NUMERIC = {"revenue", "quantity", "price", "cost", "profit", "discount", "rating", "marketing", "conversion", "delivery_days"}
DATES = {"date", "delivery_date"}
CATEGORICAL = {"product", "category", "region", "country", "city", "status", "payment"}

LABELS = {
    "order_id": "Order ID", "customer_id": "Customer", "product": "Product", "category": "Category",
    "revenue": "Revenue / Sales", "quantity": "Quantity", "price": "Unit price", "cost": "Cost",
    "profit": "Profit", "date": "Order date", "delivery_date": "Delivery date", "delivery_days": "Delivery days",
    "region": "Region", "country": "Country", "city": "City", "discount": "Discount", "status": "Status",
    "payment": "Payment", "rating": "Rating", "marketing": "Marketing spend", "conversion": "Conversion rate",
}


def _norm(name: str) -> str:
    n = re.sub(r"([a-z])([A-Z])", r"\1 \2", str(name))      # camelCase -> words
    n = re.sub(r"[^a-zA-Z0-9]+", " ", n).lower().strip()
    return re.sub(r"\s+", " ", n)


def _score(n: str, role: str) -> float:
    best = 0.0
    padded = f" {n} "
    for kw, w in KEYWORDS[role]:
        if n == kw:
            best = max(best, 100 + w)
        elif f" {kw} " in padded:
            best = max(best, w * 5 + (len(kw) / max(len(n), 1)) * 10)
    if role == "category" and "sub" in n.split():
        best *= 0.5
    return best


def _compatible(s: pd.Series, role: str) -> bool:
    if role in NUMERIC:
        return pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s)
    if role in DATES:
        return pd.api.types.is_datetime64_any_dtype(s)
    if role in CATEGORICAL:
        return not pd.api.types.is_datetime64_any_dtype(s) and not (pd.api.types.is_numeric_dtype(s) and s.nunique() > 25)
    return True


def detect_roles(df: pd.DataFrame, threshold: float = 22.0):
    """Return ({role: column}, [{role, column, confidence}])."""
    cands = []
    for col in df.columns:
        n = _norm(col)
        for role in KEYWORDS:
            sc = _score(n, role)
            if sc >= threshold and _compatible(df[col], role):
                cands.append((sc, role, col))
    cands.sort(key=lambda t: -t[0])
    roles, used, conf = {}, set(), []
    for sc, role, col in cands:
        if role in roles or col in used:
            continue
        roles[role] = col
        used.add(col)
        conf.append({"role": role, "label": LABELS[role], "column": col,
                     "confidence": "high" if sc >= 60 else "medium" if sc >= 40 else "low"})
    return roles, conf

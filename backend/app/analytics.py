"""KPI engine, chart builder and shared aggregation helpers."""
import numpy as np
import pandas as pd


# ----------------------------------------------------------------------------- helpers
def n_orders(d: pd.DataFrame) -> int:
    return int(d["order_id"].nunique()) if "order_id" in d else int(len(d))


def valid(m):
    return m[m["valid"]]


def monthly(m: pd.DataFrame) -> pd.DataFrame:
    if "date" not in m or "revenue" not in m:
        return pd.DataFrame()
    v = m[m["valid"] & m["date"].notna()]
    if v.empty:
        return pd.DataFrame()
    g = v.groupby("month")
    out = pd.DataFrame({"revenue": g["revenue"].sum()})
    out["orders"] = g["order_id"].nunique() if "order_id" in v else g.size()
    if "profit" in v:
        out["profit"] = g["profit"].sum()
    if "delivery_days" in v:
        out["delivery_days"] = g["delivery_days"].mean()
    out["last_day"] = g["date"].max().dt.day
    return out.sort_index()


def complete_months(mo: pd.DataFrame):
    """Drop a trailing partial month so growth rates are not distorted."""
    if len(mo) >= 3:
        last = mo.index[-1]
        if mo["last_day"].iloc[-1] < last.days_in_month - 2:
            return mo.iloc[:-1], True
    return mo, False


def group_table(v: pd.DataFrame, col: str) -> pd.DataFrame:
    g = v.groupby(col)
    t = pd.DataFrame({"revenue": g["revenue"].sum()})
    t["orders"] = g["order_id"].nunique() if "order_id" in v else g.size()
    if "quantity" in v:
        t["units"] = g["quantity"].sum()
    if "profit" in v:
        t["profit"] = g["profit"].sum()
        t["margin"] = t["profit"] / t["revenue"].replace(0, np.nan)
    t["aov"] = t["revenue"] / t["orders"].replace(0, np.nan)
    return t.sort_values("revenue", ascending=False)


# ----------------------------------------------------------------------------- filters
def apply_filters(m: pd.DataFrame, f: dict) -> pd.DataFrame:
    if not f:
        return m
    mask = pd.Series(True, index=m.index)
    if "date" in m:
        if f.get("date_from"):
            mask &= m["date"] >= pd.to_datetime(f["date_from"])
        if f.get("date_to"):
            mask &= m["date"] <= pd.to_datetime(f["date_to"]) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    for key in ("region", "category", "product", "customer_id", "status", "country", "city", "payment"):
        vals = f.get(key)
        if vals and key in m:
            mask &= m[key].astype(str).isin([str(x) for x in vals])
    return m[mask]


def filter_options(m: pd.DataFrame) -> dict:
    opts = {}
    for key, label in (("region", "Region"), ("category", "Category"), ("product", "Product"), ("status", "Status"),
                       ("country", "Country"), ("city", "City"), ("customer_id", "Customer")):
        if key in m:
            vals = sorted(m[key].dropna().astype(str).unique().tolist())
            opts[key] = {"label": label, "values": vals[:400], "truncated": len(vals) > 400}
    if "date" in m and m["date"].notna().any():
        opts["date"] = {"label": "Date", "min": m["date"].min().date().isoformat(), "max": m["date"].max().date().isoformat()}
    return opts


# ----------------------------------------------------------------------------- KPIs
def compute_kpis(m: pd.DataFrame, caps: dict) -> list:
    k = []

    def add(group, key, label, value, unit, hint=None):
        if value is None or (isinstance(value, float) and (np.isnan(value) or np.isinf(value))):
            return
        k.append({"group": group, "key": key, "label": label, "value": value, "unit": unit, "hint": hint})

    if m.empty:
        return k
    v = valid(m)
    total_orders_all = n_orders(m)
    orders = n_orders(v)

    if caps["revenue"]:
        rev = float(v["revenue"].sum())
        add("Sales", "revenue", "Total Revenue", rev, "currency", "Cancelled/returned orders excluded" if caps["status"] else None)
        add("Sales", "orders", "Orders", orders, "number")
        add("Sales", "aov", "Average Order Value", rev / orders if orders else None, "currency")
        if caps["quantity"]:
            add("Sales", "units", "Units Sold", float(v["quantity"].sum()), "number")
        mo, partial = complete_months(monthly(m)) if caps["date"] else (pd.DataFrame(), False)
        if len(mo) >= 2 and mo["revenue"].iloc[-2] > 0:
            g = mo["revenue"].iloc[-1] / mo["revenue"].iloc[-2] - 1
            add("Sales", "growth", "Revenue Growth (MoM)", g, "percent", f"{mo.index[-1]} vs {mo.index[-2]}")
            prev_year = mo.index[-1] - 12
            if prev_year in mo.index and mo.loc[prev_year, "revenue"] > 0:
                add("Sales", "growth_yoy", "Revenue Growth (YoY)", mo["revenue"].iloc[-1] / mo.loc[prev_year, "revenue"] - 1, "percent", f"{mo.index[-1]} vs {prev_year}")
        if len(mo):
            best = mo["revenue"].idxmax()
            add("Sales", "best_month", "Best Month", str(best), "text", None)
        if caps["date"] and v["date"].notna().any():
            days = max((v["date"].max() - v["date"].min()).days + 1, 1)
            add("Sales", "daily_rev", "Avg Daily Revenue", rev / days, "currency")

    if caps["customer_id"]:
        cust = v.groupby("customer_id")
        nc = int(cust.ngroups)
        add("Customers", "customers", "Total Customers", nc, "number")
        oc = cust["order_id"].nunique() if caps["order_id"] else cust.size()
        repeat = int((oc >= 2).sum())
        add("Customers", "repeat", "Repeat Customers", repeat, "number", f"{repeat / nc:.0%} of customers ordered 2+ times" if nc else None)
        if caps["date"] and v["date"].notna().any():
            first = cust["date"].min()
            last_month = v["date"].max().to_period("M")
            add("Customers", "new", "New Customers (latest month)", int((first.dt.to_period("M") == last_month).sum()), "number", f"First order in {last_month}")
        if caps["revenue"] and nc:
            add("Customers", "cust_value", "Avg Customer Value", float(v["revenue"].sum()) / nc, "currency")

    if caps["revenue"] and caps["product"]:
        pt = group_table(v, "product")
        if len(pt):
            add("Products", "top_product", "Top Product", str(pt.index[0]), "text", None)
            add("Products", "n_products", "Products Sold", int(len(pt)), "number")
    if caps["revenue"] and caps["category"]:
        ct = group_table(v, "category")
        if len(ct):
            add("Products", "top_category", "Top Category", str(ct.index[0]), "text", None)

    if caps["delivery_days"] and m["delivery_days"].notna().any():
        add("Operations", "delivery", "Avg Delivery Time", float(m["delivery_days"].mean()), "days")
    if caps["status"]:
        add("Operations", "cancel_rate", "Cancellation Rate", float(m["is_cancelled"].mean()), "percent")
        if m["is_returned"].any():
            add("Operations", "return_rate", "Return Rate", float(m["is_returned"].mean()), "percent")
        st = m["status"].astype(str).str.lower()
        done = st.str.contains("deliver|complete|fulfil|closed")
        if done.any():
            add("Operations", "completion", "Order Completion Rate", float(done.mean()), "percent")
        add("Operations", "orders_all", "Orders Placed (incl. cancelled)", total_orders_all, "number")
    if caps["rating"]:
        add("Operations", "rating", "Average Rating", float(m["rating"].mean()), "number")

    if caps["profit"]:
        pr = float(v["profit"].sum())
        add("Profit", "profit", "Total Profit", pr, "currency")
        if caps["revenue"] and v["revenue"].sum():
            add("Profit", "margin", "Profit Margin", pr / float(v["revenue"].sum()), "percent")
        if caps["cost"]:
            add("Profit", "cost", "Total Cost", float(v["cost"].sum()), "currency")
        add("Profit", "profit_order", "Avg Profit per Order", pr / orders if orders else None, "currency")
        if caps["product"]:
            pp = v.groupby("product")["profit"].sum().sort_values(ascending=False)
            if len(pp):
                add("Profit", "top_profit", "Most Profitable Product", str(pp.index[0]), "text")
                add("Profit", "loss_products", "Loss-making Products", int((pp < 0).sum()), "number")
    return k


# ----------------------------------------------------------------------------- charts
def _bar(id_, title, labels, values, fmt="currency", type_="bar", span=1, sub=None, name="Revenue", extra=None):
    c = {"id": id_, "title": title, "type": type_, "labels": [str(x) for x in labels],
         "series": [{"name": name, "data": [float(x) if pd.notna(x) else None for x in values]}], "format": fmt, "span": span, "subtitle": sub}
    if extra:
        c.update(extra)
    return c


def build_charts(m: pd.DataFrame, caps: dict) -> list:
    ch = []
    if m.empty:
        return ch
    v = valid(m)
    has_rev = caps["revenue"]

    if caps["date"] and has_rev:
        mo = monthly(m)
        if len(mo):
            labels = [str(i) for i in mo.index]
            ch.append(_bar("rev_time", "Revenue over time (monthly)", labels, mo["revenue"], "currency", "area", 2))
            ch.append(_bar("orders_time", "Orders over time (monthly)", labels, mo["orders"], "number", "line", 1, name="Orders"))
            vd = v[v["date"].notna()]
            daily = vd.groupby(vd["date"].dt.normalize())["revenue"].sum().sort_index().tail(90)
            if len(daily) >= 7:
                ch.append(_bar("rev_daily", "Daily revenue (last 90 days)", [d.date().isoformat() for d in daily.index], daily.values, "currency", "area", 2))
    if has_rev and caps["category"]:
        ct = group_table(v, "category").head(12)
        ch.append(_bar("rev_cat", "Revenue by category", ct.index, ct["revenue"], "currency", "donut"))
    if has_rev and caps["region"]:
        rt = group_table(v, "region").head(15)
        ch.append(_bar("rev_region", "Revenue by region", rt.index, rt["revenue"], "currency", "bar"))
    if has_rev and caps["country"]:
        rt = group_table(v, "country").head(12)
        ch.append(_bar("rev_country", "Revenue by country", rt.index, rt["revenue"], "currency", "bar"))
    if has_rev and caps["city"]:
        rt = group_table(v, "city").head(12)
        ch.append(_bar("rev_city", "Revenue by city", rt.index, rt["revenue"], "currency", "bar"))
    if has_rev and caps["product"]:
        pt = group_table(v, "product")
        ch.append(_bar("top_products", "Top 10 products by revenue", pt.head(10).index, pt.head(10)["revenue"], "currency", "hbar"))
        if len(pt) > 10:
            bt = pt.tail(10).sort_values("revenue")
            ch.append(_bar("bottom_products", "Bottom 10 products by revenue", bt.index, bt["revenue"], "currency", "hbar"))
        if "margin" in pt and len(pt) >= 3:
            pts = [{"x": float(r.revenue), "y": float(r.margin * 100), "label": str(i)} for i, r in pt.iterrows() if pd.notna(r.margin)]
            ch.append({"id": "prod_scatter", "title": "Product revenue vs profit margin", "type": "scatter", "points": pts,
                       "xFormat": "currency", "yFormat": "percentSimple", "xLabel": "Revenue", "yLabel": "Margin %", "span": 2,
                       "subtitle": "Products bottom-right sell a lot but earn little"})
    if has_rev and caps["customer_id"]:
        cr = v.groupby("customer_id")["revenue"].sum().sort_values(ascending=False)
        if len(cr) >= 5:
            bins = pd.qcut(cr.rank(method="first"), 5, labels=["Top 20%", "60-80%", "40-60%", "20-40%", "Bottom 20%"][::-1]) if False else None
            q = pd.qcut(cr.rank(method="first", ascending=False), 5, labels=["Top 20%", "Next 20%", "Middle 20%", "Next 20% ", "Bottom 20%"])
            share = cr.groupby(q, observed=True).sum() / cr.sum() * 100
            ch.append(_bar("cust_dist", "Share of revenue by customer segment", share.index, share.values, "percentSimple", "bar", 1, name="% of revenue",
                           sub="Customers ranked by revenue and split into fifths"))
            top = cr.head(10)
            ch.append({"id": "top_customers", "title": "Top 10 customers", "type": "table", "span": 1,
                       "columns": ["Customer", "Revenue", "Share"], "formats": ["text", "currency", "percent"],
                       "rows": [[str(i), float(x), float(x / cr.sum())] for i, x in top.items()]})
    if caps["profit"] and caps["category"]:
        ct = group_table(v, "category").sort_values("profit", ascending=False)
        ch.append(_bar("profit_cat", "Profit by category", ct.index, ct["profit"], "currency", "bar", 1, name="Profit"))
    elif caps["profit"] and caps["product"]:
        pt = group_table(v, "product").sort_values("profit", ascending=False).head(10)
        ch.append(_bar("profit_prod", "Profit by product (top 10)", pt.index, pt["profit"], "currency", "hbar", 1, name="Profit"))
    if caps["status"]:
        vc = m["status"].astype(str).value_counts()
        ch.append(_bar("status", "Order status distribution", vc.index, vc.values, "number", "donut", 1, name="Orders"))
    if caps["delivery_days"] and m["delivery_days"].notna().any():
        if caps["date"]:
            mo = monthly(m)
            if "delivery_days" in mo and len(mo):
                ch.append(_bar("delivery_time", "Average delivery time by month (days)", [str(i) for i in mo.index], mo["delivery_days"], "days", "line", 1, name="Days"))
        d = m["delivery_days"].dropna()
        edges = [0, 2, 4, 6, 8, 10, 15, 1e9]
        labs = ["0-2", "3-4", "5-6", "7-8", "9-10", "11-15", "15+"]
        cnt = pd.cut(d, edges, labels=labs, include_lowest=True).value_counts().reindex(labs)
        ch.append(_bar("delivery_dist", "Delivery performance (days to deliver)", labs, cnt.values, "number", "bar", 1, name="Orders"))
    if caps["discount"] and caps["profit"] and has_rev:
        vv = v[v["revenue"] > 0]
        bands = pd.cut(vv["discount"], [-0.001, 0.0, 0.05, 0.10, 0.15, 0.20, 1.0], labels=["0%", "1-5%", "6-10%", "11-15%", "16-20%", "20%+"])
        gm = vv.groupby(bands, observed=True).apply(lambda d: d["profit"].sum() / d["revenue"].sum() * 100)
        if len(gm) >= 2:
            ch.append(_bar("disc_margin", "Profit margin by discount level", gm.index, gm.values, "percentSimple", "bar", 1, name="Margin %"))
    return ch

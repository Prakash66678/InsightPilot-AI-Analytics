"""Realistic synthetic e-commerce dataset with built-in patterns (and light, deliberate mess)."""
import numpy as np
import pandas as pd

PRODUCTS = [
    # name, category, unit price, cost ratio, popularity
    ("Laptop Pro 14", "Electronics", 78000, 0.78, 0.45), ("Smartphone X2", "Electronics", 42000, 0.80, 0.9),
    ("Wireless Earbuds Pro", "Electronics", 6500, 0.76, 3.2), ("4K Smart TV 43", "Electronics", 36000, 0.76, 0.6),
    ("Fitness Smartwatch", "Electronics", 12500, 0.72, 1.4),
    ("Running Shoes Flex", "Fashion", 4200, 0.52, 2.4), ("Denim Jacket", "Fashion", 3100, 0.48, 1.6),
    ("Cotton Kurta Set", "Fashion", 1800, 0.45, 2.8), ("Leather Handbag", "Fashion", 5600, 0.50, 1.0),
    ("Sunglasses Aero", "Fashion", 2300, 0.42, 1.5),
    ("Air Fryer 5L", "Home & Kitchen", 7200, 0.66, 1.8), ("Non-stick Cookware Set", "Home & Kitchen", 3400, 0.58, 2.0),
    ("Memory Foam Pillow", "Home & Kitchen", 1500, 0.50, 2.6), ("LED Desk Lamp", "Home & Kitchen", 1200, 0.54, 2.2),
    ("Robot Vacuum", "Home & Kitchen", 21000, 0.74, 0.35),
    ("Vitamin C Serum", "Beauty", 950, 0.35, 3.0), ("Hair Dryer Ionic", "Beauty", 2600, 0.55, 1.4),
    ("Perfume Eau 100ml", "Beauty", 3800, 0.40, 1.2), ("Face Wash Gel", "Beauty", 420, 0.38, 4.0),
    ("Yoga Mat Pro", "Sports", 1900, 0.50, 2.0), ("Dumbbell Set 20kg", "Sports", 4800, 0.62, 1.1),
    ("Cricket Bat Willow", "Sports", 6800, 0.60, 0.7), ("Protein Powder 2kg", "Sports", 3200, 0.64, 1.7),
    ("Badminton Racket Pair", "Sports", 2700, 0.55, 1.3),
]
REGIONS = {"North": 1.0, "South": 1.25, "East": 0.7, "West": 1.1, "Central": 0.6}


def generate_demo(seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    months = pd.period_range("2025-01", "2026-09", freq="M")
    season = {1: .9, 2: .85, 3: .95, 4: .95, 5: 1.0, 6: .95, 7: 1.0, 8: 1.0, 9: 1.1, 10: 1.35, 11: 1.45, 12: 1.3}
    n_cust = 2200
    cust_w = rng.pareto(1.6, n_cust) + 1
    cust_w /= cust_w.sum()
    cust_ids = np.array([f"C{10000 + i}" for i in range(n_cust)])
    pop = np.array([p[4] for p in PRODUCTS])
    rows = []
    oid = 100000
    for i, per in enumerate(months):
        base = 330 * (1 + 0.025 * i) * season[per.month]
        n = int(rng.normal(base, base * 0.04))
        days = per.days_in_month
        for _ in range(n):
            region = rng.choice(list(REGIONS), p=np.array(list(REGIONS.values())) / sum(REGIONS.values()))
            w = pop.copy()
            if region == "South":                       # South buys cheaper items -> lower AOV
                w = w * np.where(np.array([p[2] for p in PRODUCTS]) < 5000, 1.7, 0.8)
            pi = rng.choice(len(PRODUCTS), p=w / w.sum())
            name, cat, price, cr, _ = PRODUCTS[pi]
            day = int(rng.integers(1, days + 1))
            od = pd.Timestamp(year=per.year, month=per.month, day=day)
            disc = rng.choice([0, .05, .10, .15, .20, .25], p=[.30, .18, .20, .15, .12, .05])
            if name in ("Wireless Earbuds Pro", "Smartphone X2"):
                disc = min(.25, disc + .10)
            lam = (1.1 if price < 5000 else 0.55) * (1 + 3.0 * disc)
            qty = 1 + rng.poisson(lam)
            # incident: from Jul 2026, Electronics in South collapses (stock-out) and delivery slows everywhere
            incident = per >= pd.Period("2026-07", "M")
            if incident and cat == "Electronics" and region == "South" and rng.random() < 0.93:
                continue
            if incident and region == "South" and rng.random() < 0.30:
                continue
            unit = price * rng.normal(1, 0.015)
            revenue = round(qty * unit * (1 - disc), 2)
            cost = round(qty * price * cr * rng.normal(1, 0.02), 2)
            status = rng.choice(["Delivered", "Cancelled", "Returned"], p=[.90, .06, .04])
            if incident and region == "South":
                status = rng.choice(["Delivered", "Cancelled", "Returned"], p=[.80, .15, .05])
            dd = max(1, rng.normal(4.2 + (2.5 if region == "Central" else 0) + (2.2 if incident else 0), 1.3))
            deliv = od + pd.Timedelta(days=int(round(dd)))
            if od > pd.Timestamp("2026-09-24"):
                status = "Shipped"
            rows.append([f"ORD-{oid}", od, rng.choice(cust_ids, p=cust_w), name, cat, region, int(qty), round(unit, 2),
                         revenue, cost, round(revenue - cost, 2), disc, status, deliv,
                         rng.choice(["UPI", "Credit Card", "Debit Card", "COD", "Net Banking"], p=[.38, .24, .14, .16, .08])])
            oid += 1
    df = pd.DataFrame(rows, columns=["Order ID", "Order Date", "Customer ID", "Product", "Category", "Region", "Quantity",
                                     "Unit Price", "Revenue", "Cost", "Profit", "Discount", "Order Status", "Delivery Date", "Payment Method"])
    df["Order Date"] = df["Order Date"].dt.strftime("%Y-%m-%d")
    df["Delivery Date"] = pd.to_datetime(df["Delivery Date"]).dt.strftime("%Y-%m-%d")
    df["Discount"] = (df["Discount"] * 100).round().astype(int).astype(str) + "%"
    df["Revenue"] = df["Revenue"].map(lambda x: f"₹{x:,.2f}")
    df["Unit Price"] = df["Unit Price"].map(lambda x: f"₹{x:,.2f}")
    # --- deliberate, mild data-quality problems so the cleaning engine has real work to do
    n = len(df)
    pick = lambda k: rng.choice(n, k, replace=False)
    df.loc[pick(int(n * .015)), "Region"] = np.nan
    df.loc[pick(int(n * .008)), "Quantity"] = np.nan
    df.loc[pick(40), "Region"] = df.loc[pick(40), "Region"].astype(str).str.upper()
    df.loc[pick(30), "Category"] = " " + df["Category"].iloc[pick(30)].values + " "
    neg = pick(25)
    df.loc[neg, "Quantity"] = -df.loc[neg, "Quantity"].abs()
    df.loc[pick(10), "Order Date"] = "not available"
    df = pd.concat([df, df.sample(int(n * .012), random_state=1)], ignore_index=True)
    return df.sample(frac=1, random_state=3).reset_index(drop=True)

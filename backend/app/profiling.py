"""Column profiling + data quality score."""
import numpy as np
import pandas as pd

ID_WORDS = ("id", "code", "no", "number", "sku", "key")


def infer_kind(s: pd.Series, name: str) -> str:
    import re
    if pd.api.types.is_bool_dtype(s):
        return "boolean"
    if pd.api.types.is_datetime64_any_dtype(s):
        return "datetime"
    words = re.split(r"[^a-z]+", str(name).lower())
    nn = s.dropna()
    uniq = nn.nunique()
    ratio = uniq / max(len(nn), 1)
    if pd.api.types.is_numeric_dtype(s):
        if any(w in ID_WORDS for w in words) and ratio > 0.5:
            return "id"
        return "numeric"
    if any(w in ID_WORDS for w in words) and ratio > 0.5:
        return "id"
    if uniq <= 50 or ratio < 0.5:
        return "categorical"
    return "text"


def profile_df(df: pd.DataFrame) -> dict:
    cols = []
    for c in df.columns:
        s = df[c]
        kind = infer_kind(s, c)
        nn = s.dropna()
        miss = int(s.isna().sum())
        info = {"name": str(c), "kind": kind, "dtype": str(s.dtype), "missing": miss,
                "missing_pct": round(miss / max(len(s), 1) * 100, 2), "unique": int(nn.nunique()),
                "sample": [str(x) for x in nn.head(3).tolist()], "stats": {}}
        try:
            if kind == "numeric" and len(nn):
                info["stats"] = {"min": nn.min(), "max": nn.max(), "mean": nn.mean(), "median": nn.median(),
                                 "std": nn.std() if len(nn) > 1 else 0, "q25": nn.quantile(.25), "q75": nn.quantile(.75),
                                 "zeros": int((nn == 0).sum()), "negatives": int((nn < 0).sum())}
            elif kind == "datetime" and len(nn):
                info["stats"] = {"min": nn.min().date().isoformat(), "max": nn.max().date().isoformat(),
                                 "span_days": int((nn.max() - nn.min()).days)}
            elif kind in ("categorical", "boolean", "id") and len(nn):
                vc = nn.astype(str).value_counts().head(5)
                info["stats"] = {"top": [{"value": k, "count": int(v)} for k, v in vc.items()]}
            elif kind == "text" and len(nn):
                info["stats"] = {"avg_length": float(nn.astype(str).str.len().mean())}
        except Exception:
            info["stats"] = {}
        cols.append(info)
    cells = max(df.shape[0] * df.shape[1], 1)
    miss_total = int(df.isna().sum().sum())
    return {
        "rows": int(df.shape[0]), "columns": int(df.shape[1]),
        "duplicate_rows": int(df.duplicated().sum()),
        "missing_cells": miss_total, "missing_pct": round(miss_total / cells * 100, 2),
        "memory_mb": round(float(df.memory_usage(deep=True).sum()) / 1e6, 2),
        "column_profiles": cols,
    }


def quality_score(raw: pd.DataFrame, stats: dict) -> dict:
    rows, ncols = max(len(raw), 1), max(raw.shape[1], 1)
    cells = rows * ncols
    miss_pct = stats["missing_cells_raw"] / cells * 100
    dup_pct = stats.get("duplicates", 0) / rows * 100
    invalid = stats["negatives"] + stats["invalid_dates"]
    inv_pct = invalid / cells * 100
    comps = [
        ("Completeness", 30, min(30, miss_pct * 1.5), f"{miss_pct:.1f}% of cells are missing"),
        ("Uniqueness", 20, min(20, dup_pct * 2), f"{stats.get('duplicates', 0)} duplicate rows ({dup_pct:.1f}%)"),
        ("Validity", 20, min(20, inv_pct * 8), f"{invalid} invalid values (negative quantities/prices, unreadable dates)"),
        ("Type consistency", 15, min(15, len(stats["converted_cols"]) / ncols * 30), f"{len(stats['converted_cols'])} column(s) stored as text but holding numbers/dates"),
        ("Structure", 15, min(15, 5 * len(stats["empty_cols"]) + 5 * stats["dup_cols"]), f"{len(stats['empty_cols'])} empty and {stats['dup_cols']} duplicate-named column(s)"),
    ]
    score = max(0, round(100 - sum(c[2] for c in comps)))
    return {"score": score,
            "grade": "Excellent" if score >= 90 else "Good" if score >= 75 else "Fair" if score >= 55 else "Poor",
            "components": [{"name": n, "max": mx, "lost": round(l, 1), "earned": round(mx - l, 1), "detail": d} for n, mx, l, d in comps]}

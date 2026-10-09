"""Automatic cleaning. The original DataFrame is never modified; every change is logged."""
import io
import os
import re
import warnings

import numpy as np
import pandas as pd

from .utils import DataError

NA_TOKENS = {"", "na", "n/a", "nan", "null", "none", "-", "--", "?", "#n/a", "nil", "missing", "undefined"}
CUR_SYMBOLS = "₹$€£¥"
NONNEG_HINTS = ("quantity", "qty", "units", "price", "cost", "discount", "rate")
DATE_HINTS = ("date", "time", "day", "created", "at")
ID_HINTS = ("id", "code", "no", "number", "sku", "key")


# ----------------------------------------------------------------------------- reading
def read_upload(filename: str, content: bytes):
    """Return (DataFrame, warnings). Raises DataError with a user-friendly message."""
    ext = os.path.splitext(filename or "")[1].lower()
    if not content:
        raise DataError("The file is empty. Please upload a file that contains data.")
    notes = []
    dup_header = 0
    try:
        if ext in (".csv", ".txt", ".tsv"):
            df = None
            for enc in ("utf-8-sig", "latin-1"):
                try:
                    df = pd.read_csv(io.BytesIO(content), sep=None, engine="python", encoding=enc)
                    head = pd.read_csv(io.BytesIO(content), sep=None, engine="python", encoding=enc, header=None, nrows=1)
                    break
                except UnicodeDecodeError:
                    continue
            if df is None:
                raise DataError("The file could not be decoded as text. Is it really a CSV?")
        elif ext in (".xlsx", ".xls"):
            xl = pd.ExcelFile(io.BytesIO(content))
            df, head = None, None
            for sheet in xl.sheet_names:
                d = xl.parse(sheet)
                if d.dropna(how="all").shape[0] > 0 and d.shape[1] > 0:
                    df, head = d, xl.parse(sheet, header=None, nrows=1)
                    if len(xl.sheet_names) > 1:
                        notes.append(f"Workbook has {len(xl.sheet_names)} sheets; analysed the first one with data ('{sheet}').")
                    break
            if df is None:
                raise DataError("The workbook has no sheet with data.")
        else:
            raise DataError(f"Unsupported file type '{ext or 'unknown'}'. Please upload a CSV, XLSX or XLS file.")
    except DataError:
        raise
    except pd.errors.EmptyDataError:
        raise DataError("The file is empty. Please upload a file that contains data.")
    except Exception as e:  # corrupted files, bad zip, parser errors
        raise DataError(f"The file could not be read - it may be corrupted or not a valid {ext.upper().strip('.')} file. ({type(e).__name__})")

    df = df.dropna(how="all")
    if df.shape[0] == 0 or df.shape[1] == 0:
        raise DataError("The file contains no data rows.")
    try:
        names = [str(x) for x in head.iloc[0].tolist()]
        dup_header = len(names) - len(set(names))
    except Exception:
        pass
    if dup_header:
        notes.append(f"{dup_header} duplicate column name(s) found; the later copies were renamed by the reader (e.g. 'Sales.1').")
    if len(df) < 10:
        notes.append("Very small dataset (fewer than 10 rows): statistics and insights will be limited.")
    return df.reset_index(drop=True), notes, dup_header


# ----------------------------------------------------------------------------- helpers
def _parse_numeric(s: pd.Series):
    """Parse strings like '₹1,200', '(45)', '12%' -> numbers. Returns (series, ratio_parsed, currency, had_pct)."""
    nn = s.notna()
    txt = s[nn].astype(str).str.strip()
    cur = None
    syms = txt.str.findall(f"[{CUR_SYMBOLS}]").explode().dropna()
    if len(syms):
        cur = syms.value_counts().index[0]
    had_pct = bool(txt.str.endswith("%").mean() > 0.5) if len(txt) else False
    t = txt.str.replace(r"(?i)\b(inr|usd|eur|gbp|rs\.?)\b", "", regex=True)
    neg = t.str.match(r"^\(.*\)$")
    t = t.str.replace(f"[{CUR_SYMBOLS}%,\\s()]", "", regex=True)
    num = pd.to_numeric(t, errors="coerce")
    num[neg] = -num[neg].abs()
    out = pd.Series(np.nan, index=s.index, dtype="float64")
    out[nn] = num
    ratio = float(num.notna().mean()) if len(num) else 0.0
    return out, ratio, cur, had_pct


def _parse_dates(s: pd.Series):
    nn = s.notna()
    txt = s[nn].astype(str).str.strip()
    best = None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for dayfirst in (False, True):
            try:
                p = pd.to_datetime(txt, errors="coerce", dayfirst=dayfirst, format="mixed")
            except Exception:
                p = pd.to_datetime(txt, errors="coerce", dayfirst=dayfirst)
            if best is None or p.notna().sum() > best.notna().sum():
                best = p
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    out[nn] = best
    return out, (float(best.notna().mean()) if len(best) else 0.0)


def _is_text(s):
    return pd.api.types.is_object_dtype(s) or pd.api.types.is_string_dtype(s)


# ----------------------------------------------------------------------------- main
def clean_dataframe(raw: pd.DataFrame, dup_header: int = 0):
    df = raw.copy()
    log = []
    stats = dict(invalid_dates=0, negatives=0, converted_cols=[], empty_cols=[], dup_cols=dup_header,
                 missing_cells_raw=0, currency=None, pct_cols=[])

    def add(step, column, detail, count=None):
        log.append({"step": step, "column": column, "detail": detail, "count": None if count is None else int(count)})

    rows_before = len(df)

    # raw missing (including text tokens such as "-" or "?")
    miss = int(df.isna().sum().sum())
    for c in df.columns:
        if _is_text(df[c]):
            miss += int(df[c].dropna().astype(str).str.strip().str.lower().isin(NA_TOKENS - {""}).sum())
    stats["missing_cells_raw"] = miss

    # 1. column names
    new_cols, seen = [], {}
    for i, c in enumerate(df.columns):
        n = re.sub(r"\s+", " ", str(c)).strip() or f"Unnamed_{i + 1}"
        if n != str(c):
            add("Column name", str(c), f"Renamed to '{n}'")
        if n in seen:
            seen[n] += 1
            n = f"{n}_{seen[n]}"
        else:
            seen[n] = 1
        new_cols.append(n)
    df.columns = new_cols

    # 2. empty columns
    empty = [c for c in df.columns if df[c].isna().all()]
    if empty:
        df = df.drop(columns=empty)
        stats["empty_cols"] = empty
        for c in empty:
            add("Empty column", c, "Dropped (no values)")

    # 3. whitespace + NA tokens
    for c in df.columns:
        if not _is_text(df[c]):
            continue
        s = df[c]
        nn = s.notna()
        txt = s[nn].astype(str)
        stripped = txt.str.strip().str.replace(r"\s+", " ", regex=True)
        changed = int((stripped != txt).sum())
        tok = stripped.str.lower().isin(NA_TOKENS)
        s = s.copy()
        s[nn] = stripped.where(~tok, np.nan)
        df[c] = s
        if changed:
            add("Whitespace", c, "Trimmed leading/trailing/double spaces", changed)
        if tok.sum():
            add("Missing tokens", c, "Converted placeholders such as 'N/A' or '-' to empty", int(tok.sum()))

    # 4. type conversion
    for c in list(df.columns):
        s = df[c]
        if not _is_text(s) or s.notna().sum() == 0:
            continue
        num, ratio, cur, had_pct = _parse_numeric(s)
        if ratio >= 0.85:
            bad = int(s.notna().sum() - num.notna().sum())
            df[c] = num
            stats["converted_cols"].append(c)
            if cur and not stats["currency"]:
                stats["currency"] = cur
            if had_pct:
                stats["pct_cols"].append(c)
            detail = "Converted text to numbers" + (f" (currency symbol '{cur}' removed)" if cur else "") + (" (percent sign removed)" if had_pct else "")
            add("Data type", c, detail, s.notna().sum())
            if bad:
                add("Invalid values", c, "Values that could not be read as numbers were set to empty", bad)
            continue
        lname = c.lower()
        d, dr = _parse_dates(s)
        need = 0.5 if any(h in re.split(r"[^a-z]+", lname) for h in DATE_HINTS) else 0.9
        if dr >= need:
            bad = int(s.notna().sum() - d.notna().sum())
            df[c] = d
            stats["converted_cols"].append(c)
            stats["invalid_dates"] += bad
            add("Data type", c, "Converted text to dates", d.notna().sum())
            if bad:
                add("Invalid dates", c, "Unreadable dates were set to empty (kept out of time-series analysis)", bad)
    # currency symbol also sometimes lives in numeric-looking text we already converted; default none
    if stats["currency"]:
        add("Currency", "-", f"Detected currency symbol '{stats['currency']}' - used for display", None)

    # 5. invalid negatives
    for c in df.columns:
        if pd.api.types.is_numeric_dtype(df[c]) and any(h in c.lower() for h in NONNEG_HINTS):
            n = int((df[c] < 0).sum())
            if n:
                df.loc[df[c] < 0, c] = np.nan
                stats["negatives"] += n
                add("Invalid values", c, "Negative values are not valid for this field; set to empty", n)

    # 6. consistent categories (case / spacing variants)
    for c in df.columns:
        s = df[c]
        if not _is_text(s) or s.notna().sum() == 0:
            continue
        if s.nunique() > max(60, int(0.05 * len(s))):
            continue
        key = s.dropna().astype(str).str.lower()
        raw_counts = s.dropna().astype(str).value_counts()
        groups = {}
        for val in raw_counts.index:
            groups.setdefault(val.lower(), []).append(val)
        mapping = {v: g[0] for g in groups.values() if len(g) > 1 for v in g}  # g[0] = most frequent
        if mapping:
            n = int(s.isin([v for v, t in mapping.items() if v != t]).sum())
            df[c] = s.replace({v: t for v, t in mapping.items() if v != t})
            add("Inconsistent categories", c, f"Merged spelling/case variants into one label ({len(mapping)} variants -> {len(groups)} labels)", n)

    # 7. duplicates
    dups = int(df.duplicated().sum())
    if dups:
        df = df.drop_duplicates().reset_index(drop=True)
        add("Duplicates", "-", "Removed exact duplicate rows (original file untouched)", dups)

    # 8. missing values
    handled = 0
    for c in df.columns:
        s = df[c]
        m = int(s.isna().sum())
        if m == 0 or len(s) == 0:
            continue
        idlike = any(h in re.split(r"[^a-z]+", c.lower()) for h in ID_HINTS) or s.nunique() > 0.9 * len(s)
        if idlike:
            add("Missing values", c, "Left empty (identifier column)", m)
        elif pd.api.types.is_numeric_dtype(s):
            if m / len(s) <= 0.05:
                df[c] = s.fillna(s.median())
                handled += m
                add("Missing values", c, f"Filled with median ({s.median():,.2f})", m)
            else:
                add("Missing values", c, f"{m / len(s):.0%} missing - too many to fill safely, left empty", m)
        elif pd.api.types.is_datetime64_any_dtype(s):
            add("Missing values", c, "Left empty (rows excluded from time-series only)", m)
        else:
            if m / len(s) <= 0.5:
                df[c] = s.fillna("Unknown")
                handled += m
                add("Missing values", c, "Filled with 'Unknown'", m)
            else:
                add("Missing values", c, f"{m / len(s):.0%} missing - left empty", m)

    summary = {
        "rows_before": rows_before, "rows_after": len(df), "duplicates_removed": dups,
        "missing_handled": handled, "columns_transformed": len(stats["converted_cols"]),
        "invalid_values_fixed": stats["negatives"] + stats["invalid_dates"],
        "columns_before": raw.shape[1], "columns_after": df.shape[1],
    }
    stats["duplicates"] = dups
    return df.reset_index(drop=True), log, summary, stats

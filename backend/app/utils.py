"""Shared helpers: JSON-safe conversion and number formatting."""
import datetime as dt
import math

import numpy as np
import pandas as pd


class DataError(Exception):
    """Raised for problems the user can fix (bad file, empty data...)."""


def jsonable(o):
    if o is pd.NaT or o is None:
        return None
    if isinstance(o, dict):
        return {str(k): jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set)):
        return [jsonable(x) for x in o]
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(o, pd.Period):
        return str(o)
    if isinstance(o, (pd.Timestamp, dt.datetime, dt.date)):
        return o.isoformat()
    return o


def fmt_num(x, digits=1):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/a"
    a = abs(x)
    for lim, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if a >= lim:
            return f"{x / lim:.{digits}f}{suf}"
    return f"{x:,.0f}" if a >= 100 else f"{x:,.{digits}f}".rstrip("0").rstrip(".") if a < 100 and x != int(x) else f"{x:,.0f}"


def fmt_money(x, cur=""):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/a"
    s = fmt_num(abs(x), 2 if abs(x) >= 1000 else 1)
    return f"{'-' if x < 0 else ''}{cur}{s}"


def pct(x, digits=1):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/a"
    return f"{x * 100:.{digits}f}%"

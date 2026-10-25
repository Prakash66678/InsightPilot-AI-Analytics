"""InsightPilot API (FastAPI). Serves the frontend from ../frontend as well, so one command runs everything."""
import io
import json
import os
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from fastapi import Body, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import ai
from .analytics import apply_filters, build_charts, compute_kpis, filter_options
from .cleaning import clean_dataframe, read_upload
from .demo import generate_demo
from .detection import detect_roles
from .insights import generate_insights
from .model import build_model
from .profiling import profile_df, quality_score
from .rca import run_rca
from .recommendations import build_recommendations
from .report import build_report, render_pdf
from .simulator import config as sim_config, simulate
from .utils import DataError, jsonable

app = FastAPI(title="InsightPilot", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
MAX_BYTES = int(os.getenv("MAX_UPLOAD_MB", "50")) * 1024 * 1024


@dataclass
class Session:
    id: str
    filename: str
    original: pd.DataFrame
    cleaned: pd.DataFrame
    log: list
    summary: dict
    quality: dict
    profile_original: dict
    profile_cleaned: dict
    roles: dict
    role_conf: list
    currency: str
    model: pd.DataFrame
    caps: dict
    notes: list
    warnings: list
    kpis: list = field(default_factory=list)
    insights: list = field(default_factory=list)
    facts: dict = field(default_factory=dict)
    rca: dict = field(default_factory=dict)
    recs: list = field(default_factory=list)


SESSIONS: "OrderedDict[str, Session]" = OrderedDict()   # in-memory, newest last (max 8)


def J(o):
    return JSONResponse(jsonable(o))


@app.exception_handler(DataError)
async def data_error(_, exc: DataError):
    return JSONResponse({"error": str(exc)}, status_code=400)


def process(filename: str, raw: pd.DataFrame, warnings_: list, dup_header: int) -> Session:
    cleaned, log, summary, stats = clean_dataframe(raw, dup_header)
    roles, conf = detect_roles(cleaned)
    cur = stats["currency"] or ""
    model, caps, notes = build_model(cleaned, roles)
    s = Session(id=uuid.uuid4().hex[:12], filename=filename, original=raw, cleaned=cleaned, log=log, summary=summary,
                quality=quality_score(raw, stats), profile_original=profile_df(raw), profile_cleaned=profile_df(cleaned),
                roles=roles, role_conf=conf, currency=cur, model=model, caps=caps, notes=notes, warnings=warnings_)
    if not any(pd.api.types.is_numeric_dtype(cleaned[c]) for c in cleaned.columns):
        s.notes.append("Your dataset has no numeric columns, so KPIs and charts that need numbers are disabled. Profiling and the Data Explorer still work.")
    s.kpis = compute_kpis(model, caps)
    s.insights, s.facts = generate_insights(model, caps, cur)
    s.rca = run_rca(model, caps, cur) if caps["revenue"] else {"enabled": False, "reason": "No revenue column was detected."}
    s.recs = build_recommendations(s.facts, s.rca, cur)
    SESSIONS[s.id] = s
    while len(SESSIONS) > 8:
        SESSIONS.popitem(last=False)
    return s


def get(sid: str) -> Session:
    s = SESSIONS.get(sid)
    if not s:
        raise HTTPException(404, "Session expired or not found. Please upload your dataset again.")
    return s


def overview(s: Session) -> dict:
    return {"id": s.id, "filename": s.filename, "currency": s.currency, "summary": s.summary, "quality": s.quality,
            "profile_original": s.profile_original, "profile_cleaned": s.profile_cleaned, "roles": s.role_conf,
            "caps": s.caps, "notes": s.notes, "warnings": s.warnings, "log_size": len(s.log)}


def build_chat_context(s: Session) -> dict:
    columns = []
    for c in s.cleaned.columns:
        series = s.cleaned[c]
        item = {"name": str(c), "dtype": str(series.dtype), "non_null": int(series.notna().sum()), "sample_values": []}
        if series.notna().any():
            item["sample_values"] = [None if pd.isna(v) else str(v) for v in series.dropna().head(5).astype(str).tolist()]
        if pd.api.types.is_numeric_dtype(series):
            vals = series.dropna()
            if len(vals):
                item["stats"] = {"min": float(vals.min()), "max": float(vals.max()), "mean": float(vals.mean())}
        elif pd.api.types.is_datetime64_any_dtype(series):
            vals = series.dropna()
            if len(vals):
                item["stats"] = {"min": str(vals.min().date()), "max": str(vals.max().date())}
        else:
            top = series.dropna().astype(str).value_counts().head(5)
            if len(top):
                item["top_values"] = [{"value": str(k), "count": int(v)} for k, v in top.items()]
        columns.append(item)

    evidence = []
    for k in s.kpis[:10]:
        label = k.get("label")
        value = k.get("value")
        unit = k.get("unit")
        if label is not None and value is not None:
            evidence.append(f"{label}: {value} {unit if unit not in ('currency', 'number', 'text', 'days', 'percent', 'percentSimple') else ''}".strip())

    return {
        "dataset_name": s.filename,
        "row_count": int(len(s.cleaned)),
        "column_count": int(len(s.cleaned.columns)),
        "currency": s.currency or "unknown",
        "quality_score": s.quality.get("score") if isinstance(s.quality, dict) else None,
        "roles": s.role_conf,
        "columns": columns,
        "kpis": [{"label": k.get("label"), "value": k.get("value"), "unit": k.get("unit")} for k in s.kpis],
        "insights": [{"title": i.get("title"), "text": i.get("text"), "type": i.get("type")} for i in s.insights],
        "facts": s.facts,
        "notes": s.notes,
        "warnings": s.warnings,
        "evidence": evidence,
    }


# ----------------------------------------------------------------------------- routes
@app.get("/api/health")
def health():
    return {"status": "ok", "ai": ai.status()}


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    content = await file.read()
    if len(content) > MAX_BYTES:
        raise DataError(f"File is larger than {MAX_BYTES // 1024 // 1024} MB.")
    raw, warns, dup = read_upload(file.filename or "", content)
    return J(overview(process(file.filename, raw, warns, dup)))


@app.post("/api/demo")
def demo():
    return J(overview(process("demo_ecommerce.csv", generate_demo(), ["Demo dataset: synthetic e-commerce orders (Jan 2025 - Sep 2026) with deliberate data-quality issues."], 0)))


@app.get("/api/session/{sid}/overview")
def get_overview(sid: str):
    return J(overview(get(sid)))


@app.get("/api/session/{sid}/cleaning-log")
def cleaning_log(sid: str):
    return J(get(sid).log)


@app.post("/api/session/{sid}/dashboard")
def dashboard(sid: str, filters: dict = Body(default={})):
    s = get(sid)
    f = apply_filters(s.model, filters)
    return J({"kpis": compute_kpis(f, s.caps), "charts": build_charts(f, s.caps), "filters": filter_options(s.model),
              "rows": int(len(f)), "total_rows": int(len(s.model)), "notes": s.notes, "currency": s.currency})


@app.get("/api/session/{sid}/insights")
def insights(sid: str):
    s = get(sid)
    return J({"insights": s.insights, "notes": s.notes})


@app.get("/api/session/{sid}/rca")
def rca(sid: str):
    return J(get(sid).rca)


@app.get("/api/session/{sid}/simulator")
def simulator_cfg(sid: str):
    s = get(sid)
    return J(sim_config(s.model, s.caps))


@app.post("/api/session/{sid}/simulate")
def simulate_ep(sid: str, params: dict = Body(default={})):
    s = get(sid)
    return J(simulate(s.model, s.caps, params))


@app.get("/api/session/{sid}/recommendations")
def recommendations(sid: str):
    return J({"recommendations": get(sid).recs})


@app.get("/api/session/{sid}/report")
def report(sid: str):
    s = get(sid)
    return J({"sections": build_report(s), "filename": s.filename, "quality": s.quality["score"]})


@app.post("/api/session/{sid}/ai-summary")
def ai_summary(sid: str):
    s = get(sid)
    return J(ai.explain({"kpis": [{k["label"]: k["value"]} for k in s.kpis], "insights": [i["text"] for i in s.insights],
                        "rca": [c["problem"] + " | " + "; ".join(f["factor"] for f in c["factors"][:4]) for c in s.rca.get("cases", [])],
                        "recommendations": [r["title"] for r in s.recs]}))


@app.post("/api/session/{sid}/chat")
def ai_chat(sid: str, payload: dict = Body(default={})):
    s = get(sid)
    question = str((payload or {}).get("question", "")).strip()
    if not question:
        raise HTTPException(400, "Please ask a question about the current dataset.")
    history = payload.get("history") or []
    result = ai.answer_question(question, build_chat_context(s), history=history)
    return J({"answer": result.get("answer"), "message": result.get("message"), "provider": result.get("provider"), "enabled": result.get("enabled"), "evidence": result.get("evidence", [])})


def _page(df: pd.DataFrame, q, sort, direction, page, size, flt):
    d = df
    if q:
        mask = pd.Series(False, index=d.index)
        for c in d.columns:
            mask |= d[c].astype(str).str.contains(q, case=False, na=False, regex=False)
        d = d[mask]
    for f in flt:
        c, op, val = f.get("col"), f.get("op", "contains"), str(f.get("value", ""))
        if c not in d.columns or val == "":
            continue
        col = d[c]
        try:
            if op == "equals":
                d = d[col.astype(str).str.lower() == val.lower()]
            elif op in ("gt", "lt") and pd.api.types.is_numeric_dtype(col):
                d = d[col > float(val)] if op == "gt" else d[col < float(val)]
            else:
                d = d[col.astype(str).str.contains(val, case=False, na=False, regex=False)]
        except ValueError:
            pass
    if sort in d.columns:
        d = d.sort_values(sort, ascending=(direction != "desc"), na_position="last")
    total = len(d)
    sl = d.iloc[(page - 1) * size: page * size]
    rows = [[None if pd.isna(v) else (v.strftime("%Y-%m-%d") if isinstance(v, pd.Timestamp) else v) for v in r] for r in sl.itertuples(index=False, name=None)]
    return {"columns": [str(c) for c in d.columns], "rows": rows, "total": total, "page": page, "page_size": size}


@app.get("/api/session/{sid}/data")
def data(sid: str, which: str = "cleaned", q: str = "", sort: str = "", dir: str = "asc", page: int = 1, page_size: int = Query(50, le=200), filters: str = "[]"):
    s = get(sid)
    df = s.original if which == "original" else s.cleaned
    try:
        flt = json.loads(filters)
    except Exception:
        flt = []
    return J(_page(df, q, sort, dir, max(page, 1), page_size, flt))


def _csv(df: pd.DataFrame, name: str):
    return Response(df.to_csv(index=False).encode("utf-8-sig"), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/api/session/{sid}/download/{kind}")
def download(sid: str, kind: str):
    s = get(sid)
    base = Path(s.filename).stem
    if kind == "original":
        return _csv(s.original, f"{base}_original.csv")
    if kind == "cleaned":
        return _csv(s.cleaned, f"{base}_cleaned.csv")
    if kind == "kpis":
        return _csv(pd.DataFrame([{"group": k["group"], "kpi": k["label"], "value": k["value"], "unit": k["unit"]} for k in s.kpis]), f"{base}_kpis.csv")
    if kind == "cleaning-log":
        return _csv(pd.DataFrame(s.log), f"{base}_cleaning_log.csv")
    if kind == "report":
        return Response(render_pdf(s), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{base}_executive_report.pdf"'})
    raise HTTPException(404, "Unknown download type")


FRONT = Path(__file__).resolve().parents[2] / "frontend"
if FRONT.exists():
    app.mount("/", StaticFiles(directory=str(FRONT), html=True), name="frontend")


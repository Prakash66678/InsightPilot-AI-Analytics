# InsightPilot - Business Decision Intelligence Platform

Upload a CSV/XLSX/XLS file and get profiling, cleaning, KPIs, an interactive dashboard, calculated insights,
root cause analysis, a what-if simulator, recommendations and an executive PDF - all in one web app.
No Excel, SQL Server, Power BI or notebooks required. Every number comes from the uploaded data.

## Run it (about 2 minutes)

Requires Python 3.10+.

    cd backend
    python -m venv .venv
    # Windows: .venv\Scripts\activate      macOS/Linux: source .venv/bin/activate
    pip install -r requirements.txt
    uvicorn app.main:app --port 8000

Open http://localhost:8000 - click **Use Demo Dataset**, or upload `sample_data/demo_ecommerce.csv`
(or your own file). The backend serves the frontend, so there is nothing else to start.

## Project structure

    insightpilot/
      backend/
        requirements.txt
        app/
          main.py             FastAPI routes, in-memory sessions, CSV/PDF downloads
          cleaning.py         reading files + automatic cleaning (+ cleaning log)
          profiling.py        column profiles + data quality score
          detection.py        column-role detection from names and types
          model.py            standardised analysis frame (revenue, profit, status flags...)
          analytics.py        KPI engine, filters, chart builder
          insights.py         business insight engine
          rca.py              root cause analysis (orders vs AOV vs category/region/product)
          simulator.py        what-if simulator (elasticity estimated from data or assumed)
          recommendations.py  recommendation engine
          report.py           executive report + PDF
          ai.py               optional AI explanation layer (env-var keys, backend only)
          demo.py             realistic demo dataset generator
      frontend/               index.html, styles.css, app.js, vendor/chart.umd.js (works offline)
      sample_data/demo_ecommerce.csv

## How it works

1. **Upload** -> the original DataFrame is stored untouched; a separate cleaned copy is made.
2. **Cleaning** trims spaces, converts currency/percent/date text, merges case variants, removes
   duplicates and invalid negatives, fills small gaps (median / "Unknown"). Every step is in the log.
3. **Detection** maps columns to business roles (revenue, quantity, date, region...) by name and type.
   KPIs and charts that need a missing role are skipped, with a message explaining why.
4. **Analysis** runs on a standardised frame. Cancelled/returned orders are excluded from revenue,
   profit and customer KPIs when a status column exists.
5. **AI (optional)**: set `ANTHROPIC_API_KEY`, `GROQ_API_KEY` or `GEMINI_API_KEY` (optionally
   `AI_PROVIDER`, `AI_MODEL`) in the backend environment. The AI only rewrites calculated findings
   in plain language; the app works fully without it.

   https://insightpilot-ai-analytics.onrender.com
   

## Notes and limits

- Sessions live in server memory (last 8 uploads); restarting the server clears them. Max upload 50 MB
  (`MAX_UPLOAD_MB`).
- The simulator is directional. Price elasticity is estimated from your data when there is enough
  discount variation, otherwise a labelled assumption of -1.2 is used. Marketing and conversion
  controls stay disabled unless the dataset has those columns.
- Column detection is name-based; if a column is misread, rename it (e.g. "Total Amount") and re-upload.
- A PDF report uses plain ASCII currency labels (Rs, EUR, GBP) for font compatibility.

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

















how to run these 

I'll give you a complete, copy-paste guide to run your InsightPilot AI Analytics project in VS Code after a few days, even after shutting down your computer.

You do not need to repeat the setup every time. Once the packages are installed, you usually only need to open the project, activate the virtual environment, and start the backend.

# InsightPilot — Complete Startup Guide

## Part 1: Start the backend

Follow these steps in order every time you want to run the project locally.

### Step 1. Open VS Code

Open VS Code, then open your InsightPilot project folder.

Your project path is:

```
D:\relatedtostudy\banner\insightpilot\insightpilot
```

Open the terminal in VS Code:

* Click Terminal in the top menu.

* Select New Terminal.

* Make sure the terminal is PowerShell.

### Step 2. Go to the backend folder

Copy and run:

PowerShell

```
cd D:\relatedtostudy\banner\insightpilot\insightpilot\backend
```

### Step 3. Allow script activation

You encountered a PowerShell execution-policy error previously. Run this command in each new PowerShell session before activating the environment:

PowerShell

```
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

This applies only to the current PowerShell process.

### Step 4. Activate the virtual environment

PowerShell

```
.\.venv\Scripts\Activate.ps1
```

Check that the terminal begins with `(.venv)`, for example:

```
(.venv) PS D:\relatedtostudy\banner\insightpilot\insightpilot\backend>
```

### Step 5. Start the backend server

PowerShell

```
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

You should see:

```
Application startup complete.
Uvicorn running on http://0.0.0.0:8000
```

Backend started successfully

Keep this terminal open while using the local application. Do not press `Ctrl + C` until you want to stop the server.

## Part 2: Test your backend

Open this link in your computer's browser:

[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

If the FastAPI documentation page appears, the local backend is responding.

## Part 3: Run the frontend

Your backend and frontend may be separate processes. If your frontend runs locally using Node.js, open a second VS Code terminal and navigate to the frontend folder.

Your exact frontend folder and startup command have not yet been confirmed. First, check your project structure using this command in the second terminal:

PowerShell

```
cd D:\relatedtostudy\banner\insightpilot\insightpilot
dir
```

Look for files such as `package.json`, `vite.config.js`, or `frontend`.

* If `package.json` is in the project root, inspect its scripts before choosing the frontend startup command.

* If the frontend is in a separate folder, navigate into that folder first.

Do not run `npm run dev` until you confirm where the frontend is configured.

## Part 4: Open your application

Your deployed website is:

[InsightPilot — Render](https://insightpilot-ai-analytics.onrender.com)

Remember that your local backend at `127.0.0.1:8000` and your public Render website are two different environments. Running the local backend does not automatically fix the backend connection on the public website; that may require deploying the backend separately and configuring the frontend API URL.

## Part 5: Stop the project safely

When you finish working:

1. Go to the terminal running Uvicorn.

2. Press `Ctrl + C`.

3. Close VS Code if you want.

Next time, repeat Parts 1 and 2. You do not need to recreate the virtual environment each time.

## Quick startup commands to save for later

Once your environment is created, these are the essential commands for the backend. Run them one at a time in PowerShell:

COMMAND 1 — Open backend folder

PowerShell

```
cd D:\relatedtostudy\banner\insightpilot\insightpilot\backend
```

Copy command 1

COMMAND 2 — Allow activation

PowerShell

```
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Copy command 2

COMMAND 3 — Activate environment

PowerShell

```
.\.venv\Scripts\Activate.ps1
```

Copy command 3

COMMAND 4 — Start server

PowerShell

```
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Copy command 4

My recommendation: Save this guide in a text file named `START_INSIGHTPILOT.txt` inside your project folder. That way, you can follow the same steps whenever you return to the project.



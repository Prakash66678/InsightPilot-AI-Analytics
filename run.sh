#!/usr/bin/env bash
cd "$(dirname "$0")/backend" && python3 -m venv .venv 2>/dev/null; source .venv/bin/activate && pip install -q -r requirements.txt && uvicorn app.main:app --port 8000

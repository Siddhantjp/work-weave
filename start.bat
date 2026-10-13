@echo off
rem Starts the app at http://localhost:8000 (build the frontend first: cd frontend ^rem Starts the app at http://localhost:8000  (no background scraping or LLM calls until you search)^rem Starts the app at http://localhost:8000  (no background scraping or LLM calls until you search) npm run build)
cd /d "%~dp0backend"
..\.venv\Scripts\python -m uvicorn app.api:app --port 8000

@echo off
setlocal
conda run -n campus-scheduler uvicorn app.api_server:app --host 0.0.0.0 --port 8000

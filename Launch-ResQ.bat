@echo off
title ResQ Disaster Response Desktop Runner
echo ========================================================
echo   Launching ResQ Emergency Response Desktop Platform
echo ========================================================
echo.

set ROOT_DIR=%~dp0
set BACKEND_DIR=%ROOT_DIR%backend
set FRONTEND_DIR=%ROOT_DIR%frontend

echo [1/2] Checking backend API server...
curl -s http://127.0.0.1:8000/api/health >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Starting local FastAPI backend server...
    start "ResQ API Server" /min cmd /c "cd /d "%BACKEND_DIR%" && venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000"
    timeout /t 3 /nobreak >nul
) else (
    echo Backend is already running on http://127.0.0.1:8000.
)

echo [2/2] Launching ResQ Desktop App...
start "" "%FRONTEND_DIR%\release\win-unpacked\ResQ Emergency Response.exe"

echo.
echo Application started!


@echo off
cd /d "%~dp0"

set PORT=8000
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do (
  echo Port %PORT% is already in use by PID %%a.
  echo Stop it with: taskkill /PID %%a /F
  echo Or close the other backend terminal and try again.
  exit /b 1
)

echo Starting backend on http://127.0.0.1:%PORT%
echo Wait for: [startup] IDP engine preloaded
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port %PORT%

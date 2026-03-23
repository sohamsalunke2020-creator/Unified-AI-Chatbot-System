@echo off
setlocal
cd /d %~dp0

REM Ensure logs directory exists
if not exist "logs" mkdir "logs"

echo Starting Streamlit at http://127.0.0.1:8502
echo Logs: %CD%\logs\streamlit_console.log

set "LOG=logs\streamlit_console.log"

REM If Streamlit is already running, don't start a second instance.
for /f "delims=" %%h in ('powershell -NoProfile -Command "try { (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8502/_stcore/health -TimeoutSec 1).Content } catch { '' }"') do set "HEALTH=%%h"
if /i "%HEALTH%"=="ok" (
  echo Streamlit is already running at http://127.0.0.1:8502
  start "" "http://127.0.0.1:8502"
  echo Press any key to close this window...
  pause >nul
  exit /b 0
)

REM Prefer venv python so PATH/activation never matters
if exist "venv\Scripts\python.exe" (
  set "PY=venv\Scripts\python.exe"
  set "SCRIPTS=venv\Scripts"
) else if exist ".venv-5\Scripts\python.exe" (
  set "PY=.venv-5\Scripts\python.exe"
  set "SCRIPTS=.venv-5\Scripts"
) else if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
  set "SCRIPTS=.venv\Scripts"
) else (
  set "PY=python"
  set "SCRIPTS="
)

REM Prepend venv scripts to PATH so any child process uses the venv interpreter.
if not "%SCRIPTS%"=="" set "PATH=%CD%\%SCRIPTS%;%PATH%"

set "FLAGS=--server.address 127.0.0.1 --server.port 8502 --server.headless true --server.fileWatcherType none --server.enableCORS false --server.enableXsrfProtection false --server.enableWebsocketCompression false"

for /f "delims=" %%a in ('powershell -NoProfile -Command "Get-Date -Format 'yyyy-MM-dd HH:mm:ss'"') do set "TS=%%a"
echo.>>"%LOG%"
echo ===== %TS% : starting streamlit =====>>"%LOG%"
echo Using Python: %PY%

REM Run via python -m so the console stays attached when double-clicked.
%PY% -u -m streamlit run "ui\streamlit_app.py" %FLAGS% 1>>"%LOG%" 2>&1

set "EXITCODE=%ERRORLEVEL%"
echo.
echo Streamlit process exited with code %EXITCODE%.
echo Showing last 60 log lines from %LOG%:
powershell -NoProfile -Command "Get-Content '%LOG%' -Tail 60"
echo.
echo Press any key to close this window...
pause >nul

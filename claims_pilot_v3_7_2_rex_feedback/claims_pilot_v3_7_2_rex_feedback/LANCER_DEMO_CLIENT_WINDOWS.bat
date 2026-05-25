@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

if not exist logs mkdir logs
set LOGFILE=logs\lancement_claimspilot_demo.log

echo ============================================ > "%LOGFILE%"
echo ClaimsPilot V3.6.7 - demo client locale >> "%LOGFILE%"
echo Date: %date% %time% >> "%LOGFILE%"
echo Dossier: %cd% >> "%LOGFILE%"
echo ============================================ >> "%LOGFILE%"

echo.
echo ClaimsPilot V3.6.7 - demo client locale
echo ---------------------------------------
echo.

set PYTHON_EXE=
for /f "delims=" %%i in ('py -3.12 -c "import sys; print(sys.executable)" 2^>nul') do set PYTHON_EXE=%%i
if not defined PYTHON_EXE (
  for /f "delims=" %%i in ('python -c "import sys; assert sys.version_info.major==3 and sys.version_info.minor==12; print(sys.executable)" 2^>nul') do set PYTHON_EXE=%%i
)
if not defined PYTHON_EXE (
  echo Python 3.12 est introuvable.
  echo Journal: %LOGFILE%
  pause
  exit /b 1
)

if not exist .venv "%PYTHON_EXE%" -m venv .venv >> "%LOGFILE%" 2>&1
".venv\Scripts\python.exe" -m pip install --upgrade pip >> "%LOGFILE%" 2>&1
".venv\Scripts\python.exe" -m pip install -r requirements.txt >> "%LOGFILE%" 2>&1
if errorlevel 1 (
  echo Erreur lors de l'installation des dependances. Consulte: %LOGFILE%
  pause
  exit /b 1
)

echo Lancement demo client...
echo Adresse: http://localhost:8501
start "" http://localhost:8501
".venv\Scripts\python.exe" -m streamlit run demo_client.py --server.port 8501 --server.address 127.0.0.1
pause

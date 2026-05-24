@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

if not exist logs mkdir logs
set LOGFILE=logs\lancement_claimspilot_expert.log

echo ============================================ > "%LOGFILE%"
echo ClaimsPilot V3.6.7 - interface expert locale >> "%LOGFILE%"
echo Date: %date% %time% >> "%LOGFILE%"
echo Dossier: %cd% >> "%LOGFILE%"
echo ============================================ >> "%LOGFILE%"

echo.
echo ClaimsPilot V3.6.7 - interface expert locale
echo ---------------------------------------------
echo.

set PYTHON_EXE=
for /f "delims=" %%i in ('py -3.12 -c "import sys; print(sys.executable)" 2^>nul') do set PYTHON_EXE=%%i

if not defined PYTHON_EXE (
  for /f "delims=" %%i in ('python -c "import sys; assert sys.version_info.major==3 and sys.version_info.minor==12; print(sys.executable)" 2^>nul') do set PYTHON_EXE=%%i
)

if not defined PYTHON_EXE (
  echo ERREUR: Python 3.12 est introuvable. >> "%LOGFILE%"
  echo Python 3.12 est introuvable.
  echo Installe Python 3.12 puis relance ce fichier.
  echo Journal: %LOGFILE%
  pause
  exit /b 1
)

echo Python utilise: %PYTHON_EXE%
echo Python utilise: %PYTHON_EXE% >> "%LOGFILE%"
echo.

if not exist .venv (
  echo Creation de l'environnement local .venv...
  echo Creation de l'environnement local .venv... >> "%LOGFILE%"
  "%PYTHON_EXE%" -m venv .venv >> "%LOGFILE%" 2>&1
  if errorlevel 1 (
    echo Erreur lors de la creation de l'environnement local.
    echo Consulte le journal: %LOGFILE%
    pause
    exit /b 1
  )
)

echo Verification / installation des dependances...
echo Cette etape peut prendre 1 a 3 minutes la premiere fois.
echo Verification / installation des dependances... >> "%LOGFILE%"
".venv\Scripts\python.exe" -m pip install --upgrade pip >> "%LOGFILE%" 2>&1
if errorlevel 1 (
  echo Erreur pip upgrade. Consulte le journal: %LOGFILE%
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt >> "%LOGFILE%" 2>&1
if errorlevel 1 (
  echo ERREUR installation dependances >> "%LOGFILE%"
  echo Erreur lors de l'installation des dependances.
  echo Consulte le journal: %LOGFILE%
  pause
  exit /b 1
)

echo.
echo Lancement de l'interface expert complete...
echo Garde cette fenetre ouverte pendant l'utilisation.
echo Adresse: http://localhost:8501
echo.
echo Lancement de ClaimsPilot expert... >> "%LOGFILE%"
start "" http://localhost:8501
".venv\Scripts\python.exe" -m streamlit run app.py --server.port 8501 --server.address 127.0.0.1

echo.
echo L'application s'est arretee.
echo Consulte le journal si besoin: %LOGFILE%
pause

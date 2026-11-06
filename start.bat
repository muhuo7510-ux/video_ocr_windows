@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0"

echo ========================================
echo   Video OCR - Local (Windows)
echo ========================================
echo.

if not exist "setup_env.py" (
  echo [ERROR] Missing setup_env.py. Please re-extract the whole ZIP.
  echo Do not copy only start.bat into an old folder.
  goto :finish
)

set "BASE_PY="
if exist ".venv\Scripts\python.exe" set "BASE_PY=%CD%\.venv\Scripts\python.exe"
if not defined BASE_PY (
  where py >nul 2>nul
  if not errorlevel 1 set "BASE_PY=py -3"
)
if not defined BASE_PY (
  where python >nul 2>nul
  if not errorlevel 1 set "BASE_PY=python"
)
if not defined BASE_PY (
  echo [ERROR] Python was not found. Install Python 3.10-3.12 from python.org.
  echo During installation check Add python.exe to PATH.
  goto :finish
)

echo Using initial Python: %BASE_PY%
%BASE_PY% "%CD%\setup_env.py"
if errorlevel 1 (
  echo.
  echo [ERROR] Setup failed. The error above explains which step failed.
  echo See diagnose_last.txt for OCR details if that file exists.
  echo If a DLL error remains, install the official Microsoft VC++ x64 redistributable:
  echo https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist
  goto :finish
)

set "VENV_PY=%CD%\.venv\Scripts\python.exe"
echo.
echo [OK] OCR runtime loaded successfully.
echo Starting web UI at http://127.0.0.1:7860
echo.
"%VENV_PY%" "%CD%\app.py"
if errorlevel 1 echo [ERROR] The web UI stopped with an error. See the message above.

:finish
echo.
echo Setup has stopped. Please copy any error above if you need help.
pause
endlocal

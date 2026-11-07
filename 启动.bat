@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0"
echo ========================================
echo   Video OCR - Local (bundled Python 3.11)
echo ========================================
set "PY=%~dp0python\python.exe"
if not exist "%PY%" (
  echo [ERROR] Missing python\python.exe. Re-extract the whole ZIP.
  goto :finish
)
set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHONSTARTUP="
set "VIRTUAL_ENV="
set "CONDA_PREFIX="
set "CONDA_DEFAULT_ENV="
set "CONDA_SHLVL="
set "PYTHONNOUSERSITE=1"
set "PYTHONUTF8=1"
rem Minimal PATH: bundled python + Windows + ffmpeg location only (drops Anaconda)
set "FFDIR="
for /f "delims=" %%F in ('where ffmpeg 2^>nul') do if not defined FFDIR set "FFDIR=%%~dpF"
set "PATH=%~dp0python;%SystemRoot%\system32;%SystemRoot%;%SystemRoot%\System32\Wbem"
if defined FFDIR set "PATH=%PATH%;%FFDIR%"
if not defined FFDIR echo [WARN] ffmpeg not found, OpenCV fallback will be used.
"%PY%" "%~dp0bootstrap.py"
if errorlevel 1 (
  echo [ERROR] Setup failed. If a DLL error appears, install VC++ x64:
  echo https://aka.ms/vs/17/release/vc_redist.x64.exe
  goto :finish
)
echo Starting web UI at http://127.0.0.1:7860
"%PY%" "%~dp0app.py"
if errorlevel 1 echo [ERROR] The web UI stopped with an error.
:finish
echo.
pause
endlocal

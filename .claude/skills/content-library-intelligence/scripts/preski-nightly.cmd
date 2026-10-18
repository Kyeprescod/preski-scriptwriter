@echo off
rem Preski Library nightly run. Unattended: scan new clips, then one small harvest batch. Read-only on your photos.
rem Log: %USERPROFILE%\preski-library\nightly.log  (newest run at the bottom)
setlocal
set "HERE=%~dp0"
if not defined CLIL_LIB set "CLIL_LIB=%USERPROFILE%\preski-library"
set "LIB=%CLIL_LIB%"
set "LOG=%LIB%\nightly.log"
set "PY=python"
if exist "%LIB%\venv\Scripts\python.exe" (set "PY=%LIB%\venv\Scripts\python.exe") else (where py >nul 2>nul && set "PY=py -3")
set "SRC="
if exist "%LIB%\source.txt" set /p SRC=<"%LIB%\source.txt"
if not defined SRC set "SRC=%USERPROFILE%\Pictures\iCloud Photos\Photos"
if not exist "%LIB%\test_passed.json" (
  >>"%LOG%" echo [%date% %time%] SKIPPED: run preski-menu.cmd option 3 once first so the safe test can pass.
  exit /b 0
)
>>"%LOG%" echo.
>>"%LOG%" echo ===== %date% %time% =====
%PY% "%HERE%clil.py" --lib "%LIB%" scan "%SRC%" >>"%LOG%" 2>&1
%PY% "%HERE%clil.py" --lib "%LIB%" harvest --limit 50 --max-mb 100 >>"%LOG%" 2>&1
%PY% "%HERE%clil.py" --lib "%LIB%" report >>"%LOG%" 2>&1
exit /b 0

@echo off
rem All-night mode: leave the laptop plugged in and on. Works through the library until morning (about 8 hours).
rem Needs your Gemini key set once:  setx GEMINI_API_KEY "your-key"   (then open a NEW window)
setlocal
set "HERE=%~dp0"
if not defined CLIL_LIB set "CLIL_LIB=%USERPROFILE%\preski-library"
set "PY=python"
if exist "%CLIL_LIB%\venv\Scripts\python.exe" (set "PY=%CLIL_LIB%\venv\Scripts\python.exe") else (where py >nul 2>nul && set "PY=py -3")
echo All-night mode started. Leave this window open. Progress: %CLIL_LIB%\overnight.log and the Library page on your phone.
%PY% "%HERE%overnight.py" --lib "%CLIL_LIB%" --hours 8
echo.
echo Finished. Last lines of the log:
powershell -NoProfile -Command "Get-Content '%CLIL_LIB%\overnight.log' -Tail 6"
pause

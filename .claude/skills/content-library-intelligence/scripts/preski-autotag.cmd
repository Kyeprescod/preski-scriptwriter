@echo off
rem Preski auto-tagging. Runs unattended whenever the laptop is on (scheduled every 30 min by preski-schedule-tagging.cmd).
rem Uses the Claude Code CLI (claude -p) with your Claude Pro login. One small batch per run, capped per day so it cannot drain your plan.
setlocal EnableDelayedExpansion
set "HERE=%~dp0"
if not defined CLIL_LIB set "CLIL_LIB=%USERPROFILE%\preski-library"
set "LIB=%CLIL_LIB%"
set "LOG=%LIB%\autotag.log"
set "STATE=%LIB%\autotag_state"
set "MAXRUNS=8"
if not exist "%STATE%" mkdir "%STATE%"
if not exist "%LIB%\autotag" mkdir "%LIB%\autotag"
set "PY=python"
if exist "%LIB%\venv\Scripts\python.exe" (set "PY=%LIB%\venv\Scripts\python.exe") else (where py >nul 2>nul && set "PY=py -3")

rem one run at a time
if exist "%STATE%\running.lock" (
  for /f %%A in ('powershell -NoProfile -Command "if ((Get-Item '%STATE%\running.lock').LastWriteTime -lt (Get-Date).AddMinutes(-40)) {1} else {0}"') do if "%%A"=="0" exit /b 0
)
echo x>"%STATE%\running.lock"

rem today's counters
for /f %%D in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set "TODAY=%%D"
set "RUNS=0"
if exist "%STATE%\runs_%TODAY%.txt" set /p RUNS=<"%STATE%\runs_%TODAY%.txt"
if exist "%STATE%\paused_%TODAY%.txt" ( del "%STATE%\running.lock" & exit /b 0 )
if !RUNS! GEQ %MAXRUNS% ( del "%STATE%\running.lock" & exit /b 0 )

where claude >nul 2>nul
if errorlevel 1 (
  >>"%LOG%" echo [%date% %time%] Claude Code is not installed: run  irm https://claude.ai/install.ps1 ^| iex  in PowerShell, then  claude  once to sign in.
  del "%STATE%\running.lock" & exit /b 0
)

rem anything left to tag?
%PY% "%HERE%clil.py" --lib "%LIB%" pending --type video --limit 1 >"%STATE%\peek.json" 2>nul
findstr /C:"asset_id" "%STATE%\peek.json" >nul
if errorlevel 1 ( >>"%LOG%" echo [%date% %time%] Nothing waiting to tag. & del "%STATE%\running.lock" & exit /b 0 )

set /a RUNS+=1
>"%STATE%\runs_%TODAY%.txt" echo !RUNS!
>>"%LOG%" echo ===== %date% %time%  run !RUNS! of %MAXRUNS% today =====

cd /d "%HERE%\..\..\..\.."
claude -p "Read %HERE%autotag-prompt.txt and follow it. Python: %PY%. clil.py: %HERE%clil.py. Library: %LIB%. Autotag folder: %LIB%\autotag. Command prefix: %PY% %HERE%clil.py --lib %LIB%" --add-dir "%LIB%" --add-dir "%HERE%." --allowedTools "Bash" "Read" "Write" --max-turns 80 >>"%LOG%" 2>&1
if errorlevel 1 (
  >>"%LOG%" echo [%date% %time%] Claude stopped with an error ^(often the plan's usage limit^). Pausing until tomorrow.
  >"%STATE%\paused_%TODAY%.txt" echo paused
)
del "%STATE%\running.lock"
exit /b 0

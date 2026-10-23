@echo off
rem Starts the phone page (clips, approvals, library + Gemini tagging) minimised. Link saved in preski-library\phone-link.txt
setlocal
set "HERE=%~dp0"
if not defined CLIL_LIB set "CLIL_LIB=%USERPROFILE%\preski-library"
set "PY=python"
if exist "%CLIL_LIB%\venv\Scripts\python.exe" (set "PY=%CLIL_LIB%\venv\Scripts\python.exe") else (where py >nul 2>nul && set "PY=py -3")
start "Preski phone page" /min %PY% "%HERE%share_server.py" "%CLIL_LIB%\for-phone"

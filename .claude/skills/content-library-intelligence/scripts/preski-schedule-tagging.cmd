@echo off
rem One-time: makes Windows try to tag a small batch every 30 minutes, whenever the laptop is on and you are signed in.
rem Needs Claude Code installed and signed in (open PowerShell, run:  claude  once).
rem To stop:  schtasks /Delete /TN "Preski Library Auto-Tag" /F
schtasks /Create /TN "Preski Library Auto-Tag" /TR "\"%~dp0preski-autotag.cmd\"" /SC MINUTE /MO 30 /F
if errorlevel 1 (echo Could not create the schedule - send the text above to Claude.) else (echo Done. Tagging runs every 30 minutes while the laptop is on. Progress: preski-library\autotag.log)
pause

@echo off
rem One-time: makes Windows run preski-nightly.cmd every night at 02:00 (only while you are logged in).
rem To stop it later:  schtasks /Delete /TN "Preski Library Nightly" /F
schtasks /Create /TN "Preski Library Nightly" /TR "\"%~dp0preski-nightly.cmd\"" /SC DAILY /ST 02:00 /F
if errorlevel 1 (echo Could not create the schedule - send the text above to Claude.) else (echo Done. It will run every night at 2am. Leave the laptop on and plugged in.)
pause

@echo off
rem One-time: starts the phone page automatically when you sign in to Windows, so it is always there when the laptop is on.
rem Windows will ask once to let Python use your private network: click Allow. To stop:  schtasks /Delete /TN "Preski Phone Page" /F
schtasks /Create /TN "Preski Phone Page" /TR "\"%~dp0preski-phone.cmd\"" /SC ONLOGON /F
if errorlevel 1 (echo Could not create the task - send the text above to Claude.) else (echo Done. The phone page now starts every time you sign in. Your link is in preski-library\phone-link.txt after the next sign-in.)
pause

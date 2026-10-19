@echo off
setlocal EnableDelayedExpansion
rem Preski Library menu. Double-click this file. Read-only on your photos/videos.
rem Keeps going if a step fails and always shows the result, so the window never just vanishes.

set "HERE=%~dp0"
set "CLIL=%HERE%clil.py"
if not defined CLIL_LIB set "CLIL_LIB=%USERPROFILE%\preski-library"
set "LIB=%CLIL_LIB%"
set "SRCFILE=%LIB%\source.txt"
if not exist "%LIB%" mkdir "%LIB%"

rem --- find Python: the private venv from setup first, then py, then python ---
set "PY="
if exist "%LIB%\venv\Scripts\python.exe" set "PY=%LIB%\venv\Scripts\python.exe"
if not defined PY (
  where py >nul 2>nul && set "PY=py -3"
)
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo Python was not found. Install it from https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^), then double-click this file again.
  pause
  exit /b 1
)

rem --- first run: install the picture libraries if they are missing ---
%PY% -c "import PIL, pillow_heif" >nul 2>nul
if errorlevel 1 (
  echo First run: installing the picture libraries ^(one time, about a minute^)...
  %PY% -m pip install --quiet -r "%HERE%requirements.txt"
)

rem --- remember where the photos are ---
set "SRC="
if exist "%SRCFILE%" set /p SRC=<"%SRCFILE%"
if not defined SRC call :findsrc

rem --- where pulled clips land; option 9 shows this folder on your phone over home Wi-Fi (free, no cloud storage) ---
set "PHONE="
if exist "%LIB%\phone.txt" set /p PHONE=<"%LIB%\phone.txt"
if not defined PHONE (
  set "PHONE=%LIB%\for-phone"
)

:menu
cls
echo ==============================================
echo   PRESKI LIBRARY   -   nothing is ever moved,
echo   renamed or deleted in your camera roll
echo ==============================================
echo   Photos folder : %SRC%
echo   Library folder: %LIB%
echo.
echo   1  Health check            ^(is everything installed?^)
echo   2  Where am I up to?       ^(counts, tagged, cloud-only^)
echo   3  Scan my library         ^(indexes clips; safe to repeat^)
echo   4  Overnight batch         ^(pulls 50 cloud clips, makes thumbnails, frees space^)
echo   5  Find clips              ^(type a topic: "boxing", "lean", "talking head"^)
echo   6  Send SHOWCASE clips to my phone ^(most impressive, tagged^)
echo   7  Send clips on a topic to my phone ^(e.g. talking head, jogging^)
echo   8  Change photos folder
echo   9  OPEN CLIPS ON MY PHONE   ^(shows the link; phone must be on the same Wi-Fi^)
echo  10  MAKE A VIDEO from my voiceover ^(uses my tagged clips, adds captions + graphics^)
echo  11  SELF-TEST everything ^(2 min, made-up clips; proves it all works on this laptop^)
echo   0  Exit
echo.
echo   Phone folder  : %PHONE%
echo   ^(menu 9 gives a link: open it on your phone, tap a clip, Download, Save to Photos^)
echo.
echo   Tagging ^(talking-head, cardio, lean...^) is done by Claude in a LOCAL
echo   session after step 3 or 4. Ask it: "tag the pending clips".
echo.
set "C="
set /p C=Choose a number:
if "%C%"=="1" call :run doctor
if "%C%"=="2" call :run report
if "%C%"=="3" call :scan
if "%C%"=="4" call :run harvest --limit 50 --max-mb 100
if "%C%"=="5" call :find
if "%C%"=="6" call :run collect "impressive" --min-score 7 --name showcase --dest "%PHONE%\showcase"
if "%C%"=="7" call :collect
if "%C%"=="8" call :findsrc
if "%C%"=="9" call :share
if "%C%"=="10" call :make
if "%C%"=="11" call :selftest
if "%C%"=="0" exit /b 0
echo.
pause
goto menu

:run
echo.
%PY% "%CLIL%" --lib "%LIB%" %*
if errorlevel 1 echo.& echo ^(That step reported a problem - copy the text above and send it to Claude.^)
exit /b 0

:scan
if not exist "%LIB%\test_passed.json" (
  echo No test yet - running the safe 40-clip test first...
  %PY% "%CLIL%" --lib "%LIB%" init
  %PY% "%CLIL%" --lib "%LIB%" scan --test "%SRC%"
  if errorlevel 1 (
    echo Test did not pass, so the full scan is not started. Send the text above to Claude.
    exit /b 0
  )
)
%PY% "%CLIL%" --lib "%LIB%" scan "%SRC%"
exit /b 0

:find
set "Q="
set /p Q=What are you looking for?
if defined Q call :run search "%Q%" --limit 10
exit /b 0

:make
echo.
echo Drag your voiceover or sit-down video file into this window, then press Enter.
set "V="
set /p V=File:
if not defined V exit /b 0
set "V=%V:"=%"
set "HOOK="
set /p HOOK=On-screen hook for the first 2 seconds ^(Enter to skip^):
set "CTA="
set /p CTA=Call-to-action at the end, e.g. COMMENT ABS FOR THE FREE PLAN ^(Enter to skip^):
set "SCR="
set /p SCR=Script text file for exact captions ^(Enter to let Whisper listen^):
set "STY="
echo Style:  shred = fast big word-by-word captions ^| explainer = calm talking head + cutaways ^| compare = LOSE FAT / BUILD MUSCLE graphics
set /p STY=Style ^(Enter = shred^):
if not defined STY set "STY=shred"
%PY% -c "import faster_whisper" >nul 2>nul
if errorlevel 1 if not defined SCR (
  echo Installing the speech-to-text library once ^(a few minutes^)...
  %PY% -m pip install --quiet faster-whisper
)
set "ARGS="
if defined HOOK set ARGS=%ARGS% --hook "%HOOK%"
if defined CTA set ARGS=%ARGS% --cta "%CTA%"
if defined SCR set ARGS=%ARGS% --script "%SCR:"=%"
set ARGS=%ARGS% --style %STY%
%PY% "%HERE%editor.py" make "%V%" --lib "%LIB%" %ARGS% --out "%PHONE%\finished\video_%RANDOM%.mp4"
echo.
echo Finished videos are in %PHONE%\finished - open menu 9 to watch them on your phone.
exit /b 0

:selftest
echo.
echo Running the full self-test with made-up clips. Your real footage is not touched.
%PY% "%HERE%selftest.py" --with-claude
echo.
echo If anything says FAIL, copy the lines above and send them to Claude. A copy is saved in %LIB%\selftest_report.txt
exit /b 0

:share
echo.
echo Leave this window open while you use your phone. Close it to stop sharing.
%PY% "%HERE%share_server.py" "%PHONE%"
exit /b 0

:collect
set "Q="
set /p Q=Topic to collect?
if defined Q call :run collect "%Q%" --limit 15 --dest "%PHONE%\%Q%"
exit /b 0

:findsrc
echo.
echo Looking for your photos...
%PY% "%CLIL%" --lib "%LIB%" detect
echo.
set "SRC=%USERPROFILE%\Pictures\iCloud Photos\Photos"
set "IN="
set /p IN=Paste the photos folder, or just press Enter to use "%SRC%":
if defined IN set "SRC=%IN:"=%"
>"%SRCFILE%" echo %SRC%
exit /b 0

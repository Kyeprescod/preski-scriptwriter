# Preski Content Library - Windows setup. Read-only on your photos/videos.
# Run from PowerShell:
#   powershell -ExecutionPolicy Bypass -File .\.claude\skills\content-library-intelligence\scripts\setup_windows.ps1
# Installs (if missing): Python 3, FFmpeg (via winget). Creates a private venv with Pillow + pillow-heif
# in the library folder and a launcher:  %USERPROFILE%\preski-library\clil.cmd
param([string]$Lib = (Join-Path $env:USERPROFILE "preski-library"))
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
function Have($n) { [bool](Get-Command $n -ErrorAction SilentlyContinue) }

# 1. Python (use the 'py' launcher; the Microsoft Store 'python' alias is not reliable)
$pyExe = $null
if (Have "py") { try { $pyExe = (& py -3 -c "import sys;print(sys.executable)").Trim() } catch {} }
if (-not $pyExe -and (Have "python")) {
    try { $c = & python -c "import sys;print(sys.executable)" 2>$null; if ($LASTEXITCODE -eq 0 -and $c) { $pyExe = $c.Trim() } } catch {}
}
if (-not $pyExe) {
    Write-Host "Python not found - installing Python 3.12 with winget..."
    winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    Write-Host "`nDONE. Now CLOSE this window, open a NEW PowerShell, and run this script again."
    exit 1
}
Write-Host "Python: $pyExe"

# 2. FFmpeg (video metadata + frame extraction)
if (-not (Have "ffprobe") -or -not (Have "ffmpeg")) {
    Write-Host "FFmpeg not found - installing with winget..."
    winget install -e --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
    Write-Host "`nDONE. Now CLOSE this window, open a NEW PowerShell, and run this script again (so PATH updates)."
    exit 1
}

# 3. Private Python environment with the image libraries (HEIC support lives in pillow-heif)
New-Item -ItemType Directory -Force -Path $Lib | Out-Null
$venv = Join-Path $Lib "venv"
$vpy = Join-Path $venv "Scripts\python.exe"
if (-not (Test-Path $vpy)) { & $pyExe -m venv $venv }
& $vpy -m pip install --upgrade pip --quiet
& $vpy -m pip install -r (Join-Path $here "requirements.txt") --quiet

# 4. Launcher so you never type long paths:  clil.cmd <command> ...
$clil = Join-Path $here "clil.py"
$cmd = Join-Path $Lib "clil.cmd"
Set-Content -Path $cmd -Encoding ASCII -Value @('@echo off', ('"%~dp0venv\Scripts\python.exe" "' + $clil + '" --lib "%~dp0." %*'))
Write-Host "Launcher: $cmd"

# 5. Verify + find the library
Write-Host "`n--- doctor ---"
& $cmd doctor
Write-Host "`n--- where is your media? ---"
& $cmd detect
Write-Host "`nNext (replace the folder with the one detect recommends):"
Write-Host "  $cmd scan --test `"$env:USERPROFILE\Pictures\iCloud Photos\Photos`""

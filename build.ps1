# One-click build script.
#
#   .\build.ps1              # onedir build (recommended, fast startup)
#   .\build.ps1 -OneFile     # single-file exe (slower startup, unpacks each run)
#   .\build.ps1 -SkipVlc     # skip VLC download (vendor\vlc already present)
#   .\build.ps1 -SkipDeps    # skip pip install
#
# NOTE: keep this file ASCII-only. Windows PowerShell 5.1 reads BOM-less .ps1
# as the ANSI code page, which corrupts non-ASCII string literals.

param(
    [switch]$OneFile,
    [switch]$SkipVlc,
    [switch]$SkipDeps
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root

$venvPy = Join-Path $root ".venv\Scripts\python.exe"

# ------------------------------------------------------------- virtualenv ---
if (-not (Test-Path $venvPy)) {
    Write-Host "[1/5] creating virtualenv .venv" -ForegroundColor Cyan
    python -m venv .venv
}
if (-not (Test-Path $venvPy)) { throw "venv creation failed - install Python 3.10+ and add it to PATH" }

if (-not $SkipDeps) {
    Write-Host "[2/5] installing dependencies" -ForegroundColor Cyan
    & $venvPy -m pip install --upgrade pip
    & $venvPy -m pip install -r requirements.txt pyinstaller
} else {
    Write-Host "[2/5] dependencies skipped" -ForegroundColor DarkGray
}

# ------------------------------------------------------------------- VLC ----
$vlcDll = Join-Path $root "vendor\vlc\libvlc.dll"
if ($SkipVlc) {
    Write-Host "[3/5] VLC download skipped" -ForegroundColor DarkGray
} elseif (Test-Path $vlcDll) {
    Write-Host "[3/5] reusing existing vendor\vlc" -ForegroundColor DarkGray
} else {
    Write-Host "[3/5] downloading and extracting VLC runtime" -ForegroundColor Cyan
    & $venvPy (Join-Path $root "tools\fetch_vlc.py")
}
if (-not (Test-Path $vlcDll)) { throw "vendor\vlc\libvlc.dll is missing - cannot build" }

# ------------------------------------------------------------------ icon ----
$icon = Join-Path $root "assets\multiview.ico"
if (-not (Test-Path $icon)) {
    Write-Host "[4/5] generating application icon" -ForegroundColor Cyan
    & $venvPy (Join-Path $root "tools\make_icon.py")
}
if (-not (Test-Path $icon)) { Write-Host "[4/5] icon generation failed, continuing without icon" -ForegroundColor Yellow }
else { Write-Host "[4/5] icon ready" -ForegroundColor DarkGray }

# ------------------------------------------------------------- PyInstaller --
Write-Host "[5/5] running PyInstaller" -ForegroundColor Cyan
foreach ($d in @("dist", "build")) {
    $p = Join-Path $root $d
    if (Test-Path $p) { Remove-Item $p -Recurse -Force }
}

if ($OneFile) { $env:MV_ONEFILE = "1" } else { Remove-Item Env:\MV_ONEFILE -ErrorAction SilentlyContinue }
& $venvPy -m PyInstaller --noconfirm --clean (Join-Path $root "MultiView.spec")
Remove-Item Env:\MV_ONEFILE -ErrorAction SilentlyContinue

if ($OneFile) {
    $out = Join-Path $root "dist\MultiView.exe"
} else {
    $out = Join-Path $root "dist\MultiView\MultiView.exe"
}
if (-not (Test-Path $out)) { throw "build failed: $out not found" }

$size = (Get-ChildItem (Split-Path $out) -Recurse -File | Measure-Object Length -Sum).Sum / 1MB
Write-Host ""
Write-Host "BUILD OK: $out" -ForegroundColor Green
Write-Host ("total size: {0:N1} MB" -f $size) -ForegroundColor Green
if (-not $OneFile) {
    Write-Host "distribute: copy the whole dist\MultiView folder, then run MultiView.exe" -ForegroundColor Green
}

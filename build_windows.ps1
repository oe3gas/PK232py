# PK232PY — Windows onefile build script
# Requires: .venv with nuitka installed, Python 3.x (CPython official build,
#           NOT the Microsoft Store Python — its sandbox breaks onefile).
# Output:   dist\pk232py.exe  (single self-contained executable)
#
# Usage:    .\build_windows.ps1            # builds v0.1.0
#           .\build_windows.ps1 -Version 0.2.0
#
# The C compiler (MinGW64) is downloaded and cached automatically by Nuitka on
# the first build (%LOCALAPPDATA%\Nuitka\Nuitka\Cache\downloads\gcc\), so no
# manual toolchain install is needed.

param(
    [string]$Version = "0.1.0"
)

$ErrorActionPreference = "Stop"
$RepoRoot = $PSScriptRoot
$DistDir  = Join-Path $RepoRoot "dist"

# Splash image embedded during the onefile unpack phase (Windows only).
# main.py deletes Nuitka's feedback file once MainWindow is painted, which
# dismisses it. Resolved against the repo root so the preflight check below
# works regardless of the caller's current directory.
$SplashPng = Join-Path $RepoRoot "assets\splash.png"

Write-Host "Building PK232PY v$Version for Windows (onefile)..."

# Fail fast if the splash asset is missing: Nuitka would otherwise abort with a
# less obvious error, or (worse) produce an EXE with no splash at all.
if (-not (Test-Path $SplashPng)) {
    Write-Error "Splash image not found: $SplashPng  (expected a 600x300 PNG)"
    exit 1
}

# Ensure output directory exists
New-Item -ItemType Directory -Force -Path $DistDir | Out-Null

# Activate the project venv (so `python` is the venv interpreter with Nuitka)
$Activate = Join-Path $RepoRoot ".venv\Scripts\Activate.ps1"
. $Activate

# Entry point: src/pk232py/__main__.py  ->  `python -m pk232py`
python -m nuitka `
    --onefile `
    --enable-plugin=pyqt6 `
    --include-qt-plugins=sensible,styles `
    --include-data-dir="src/pk232py/help=pk232py/help" `
    --include-package=serial `
    --include-package=markdown `
    --windows-console-mode=disable `
    --onefile-windows-splash-screen-image="$SplashPng" `
    --windows-product-name="PK232PY" `
    --windows-product-version="$Version.0" `
    --windows-company-name="OE3GAS" `
    --windows-file-description="Multimode Terminal for AEA PK-232MBX" `
    --output-dir="$DistDir" `
    --output-filename="pk232py.exe" `
    --assume-yes-for-downloads `
    --show-progress `
    src/pk232py/__main__.py

# $ErrorActionPreference="Stop" does NOT abort on a failed native process —
# it only governs PowerShell cmdlets. Check Nuitka's exit code explicitly so a
# failed build does not fall through to the "Build complete" message.
if ($LASTEXITCODE -ne 0) {
    Write-Error "Nuitka build failed (exit code $LASTEXITCODE)"
    exit 1
}

Write-Host ""
$Exe = Join-Path $DistDir "pk232py.exe"
Write-Host "Build complete: $Exe"
$SizeMB = [math]::Round((Get-Item $Exe).Length / 1MB, 1)
Write-Host "File size: $SizeMB MB"
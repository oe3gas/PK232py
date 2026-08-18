# build_portable.ps1 - Build a portable-Python Windows distribution of PK232PY
# Requires: a host Python whose major.minor matches $PythonVersion (for pip),
#           internet access (python.org download, cached after first run).
# Usage:    .\build_portable.ps1                    # builds v0.1.0
#           .\build_portable.ps1 -Version 0.2.0
#
# Output:   dist\PK232PY-<version>-portable-win64.zip  + .sha256

param(
    [string]$Version       = "0.1.0",
    [string]$PythonVersion = "3.12.10",   # embeddable runtime version
    [switch]$NoFax                          # skip numpy/scipy (smaller zip,
                                            # FAX smoothing falls back to raw)
)

$ErrorActionPreference = "Stop"

# --- Paths -------------------------------------------------------------------
$RepoRoot  = $PSScriptRoot
$DistName  = "PK232PY-$Version-portable-win64"
$DistDir   = Join-Path $RepoRoot "dist\$DistName"
$PyDir     = Join-Path $DistDir  "python"
$AppDir    = Join-Path $DistDir  "app"
$CacheDir  = Join-Path $RepoRoot "dist\.cache"

# Short version string "312" used in file names inside the embeddable package
$PyShort   = ($PythonVersion.Split('.')[0..1] -join '')

# --- 1. Sanity check: host Python must match the target minor version --------
# pip installs *into* the bundle from the host interpreter. Binary wheels
# (PyQt6!) are tagged cp312 etc., so host and target minor version must match,
# otherwise pip picks wheels the embedded runtime cannot import.
$hostVer = (python -c "import sys; print('%d.%d' % sys.version_info[:2])").Trim()
$wantVer = ($PythonVersion.Split('.')[0..1] -join '.')
if ($hostVer -ne $wantVer) {
    Write-Error "Host Python is $hostVer, need $wantVer (wheel tags must match)."
}

# --- 2. Download + unpack the embeddable runtime (cached) --------------------
New-Item -ItemType Directory -Force $CacheDir | Out-Null
$EmbedZip = Join-Path $CacheDir "python-$PythonVersion-embed-amd64.zip"
if (-not (Test-Path $EmbedZip)) {
    $url = "https://www.python.org/ftp/python/$PythonVersion/" +
           "python-$PythonVersion-embed-amd64.zip"
    Write-Host "Downloading $url"
    Invoke-WebRequest -Uri $url -OutFile $EmbedZip
}
if (Test-Path $DistDir) { Remove-Item -Recurse -Force $DistDir }
New-Item -ItemType Directory -Force $PyDir | Out-Null
Expand-Archive -Path $EmbedZip -DestinationPath $PyDir

# --- 3. Patch python3XX._pth -------------------------------------------------
# The embeddable package ignores PYTHONPATH and site-packages by design.
# The ._pth file is the ONLY search-path mechanism. We add:
#   Lib\site-packages   -> where pip --target puts the dependencies
#   ..\app\src          -> the pk232py package itself (relative to python\)
# We deliberately do NOT enable "import site": no user-site leakage, the
# bundle behaves identically on every machine.
$PthFile = Join-Path $PyDir "python$PyShort._pth"
@(
    "python$PyShort.zip"
    "."
    "Lib\site-packages"
    "..\app\src"
) | Set-Content -Path $PthFile -Encoding ascii

# --- 4. Install dependencies into the bundle ---------------------------------
# Core deps come from requirements.txt (single source of truth, kept in sync
# with pyproject.toml). numpy/scipy are NOT in requirements.txt - they are a
# build-script-only addition for FAX smoothing (scipy.ndimage.gaussian_filter,
# see CLAUDE.md FAX Gotchas) and stay gated behind -NoFax.
$SitePackages = Join-Path $PyDir "Lib\site-packages"
New-Item -ItemType Directory -Force $SitePackages | Out-Null
$ReqFile = Join-Path $RepoRoot "requirements.txt"
python -m pip install --target $SitePackages --no-compile -r $ReqFile
if ($LASTEXITCODE -ne 0) { Write-Error "pip install failed" }
if (-not $NoFax) {
    python -m pip install --target $SitePackages --no-compile numpy scipy
    if ($LASTEXITCODE -ne 0) { Write-Error "pip install (numpy/scipy) failed" }
}

# --- 5. Copy the application sources -----------------------------------------
# robocopy copies the whole tree including help/*.md (data files that a
# .py-only export would miss). Exit codes 0-7 are success for robocopy.
New-Item -ItemType Directory -Force $AppDir | Out-Null
robocopy (Join-Path $RepoRoot "src") (Join-Path $AppDir "src") /E `
    /XD __pycache__ .pytest_cache /XF *.pyc | Out-Null
if ($LASTEXITCODE -gt 7) { Write-Error "robocopy failed ($LASTEXITCODE)" }
Copy-Item (Join-Path $RepoRoot "LICENSE")   $DistDir
Copy-Item (Join-Path $RepoRoot "README.md") $DistDir

# --- 6. Generate the launcher ------------------------------------------------
# 'start ""' detaches pythonw.exe so the console window of the .cmd closes
# immediately; pythonw itself never opens a console. %~dp0 = folder of the
# .cmd, so the bundle works from any extraction path.
@'
@echo off
start "" "%~dp0python\pythonw.exe" -m pk232py
'@ | Set-Content -Path (Join-Path $DistDir "PK232PY.cmd") -Encoding ascii

@"
PK232PY $Version - portable beta
1. Extract this ZIP to a folder you own (e.g. C:\PK232PY or Desktop).
   Do NOT use C:\Program Files.
2. Double-click PK232PY.cmd.
3. Settings/logs live in %USERPROFILE%\.pk232py\
If Windows shows a security prompt on first start: right-click the
downloaded ZIP -> Properties -> Unblock, then extract again.
"@ | Set-Content -Path (Join-Path $DistDir "README-FIRST.txt") -Encoding ascii

# --- 7. Smoke test: can the bundled runtime import the app? ------------------
& (Join-Path $PyDir "python.exe") -c "import pk232py, PyQt6, serial; print('bundle OK')"
if ($LASTEXITCODE -ne 0) { Write-Error "Bundle smoke test failed" }

# --- 8. Zip + SHA-256 --------------------------------------------------------
$ZipPath = Join-Path $RepoRoot "dist\$DistName.zip"
if (Test-Path $ZipPath) { Remove-Item $ZipPath }
Compress-Archive -Path $DistDir -DestinationPath $ZipPath
$hash = (Get-FileHash $ZipPath -Algorithm SHA256).Hash.ToLower()
"$hash  $DistName.zip" | Set-Content "$ZipPath.sha256" -Encoding ascii
Write-Host "Done: $ZipPath"
Write-Host "SHA-256: $hash"
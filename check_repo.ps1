# check_repo.ps1 — PK232PY repository completeness check
# Usage: .\check_repo.ps1 [repo_root]
# Default repo root: current directory

param(
    [string]$RepoRoot = "."
)

$SRC = Join-Path $RepoRoot "src\pk232py"
$Pass = 0
$Fail = 0
$Warn = 0

function Ok($msg)   { Write-Host "  [OK]  $msg" -ForegroundColor Green;  $script:Pass++ }
function Fail($msg) { Write-Host "  [!!]  $msg" -ForegroundColor Red;    $script:Fail++ }
function Warn($msg) { Write-Host "  [??]  $msg" -ForegroundColor Yellow; $script:Warn++ }
function Hdr($msg)  { Write-Host "`n── $msg ──" -ForegroundColor Cyan }

function Check-File($path, $minBytes = 100) {
    $label = $path.Replace("$RepoRoot\", "").Replace("$RepoRoot/", "")
    if (-not (Test-Path $path)) {
        Fail "MISSING:  $label"
    } elseif ((Get-Item $path).Length -eq 0) {
        Fail "EMPTY:    $label"
    } elseif ((Get-Item $path).Length -lt $minBytes) {
        $size = (Get-Item $path).Length
        Warn "SMALL (${size}B): $label"
    } else {
        $size = (Get-Item $path).Length
        Ok "$label  (${size} B)"
    }
}

Write-Host "`nPK232PY Repository Check" -ForegroundColor White
Write-Host "Repo: $RepoRoot"
Write-Host "Date: $(Get-Date -Format 'yyyy-MM-dd HH:mm UTC')"

# ── Git Status ──────────────────────────────────────────────────────
Hdr "Git Status"
Push-Location $RepoRoot
$gitStatus = git status --short
if ($gitStatus) { $gitStatus | ForEach-Object { Write-Host "  $_" } }
$branch = git branch --show-current
$head   = git log --oneline -1
Write-Host "  Branch: $branch" -ForegroundColor Cyan
Write-Host "  HEAD:   $head"
$modified  = ($gitStatus | Where-Object { $_ -match '^[^?]' }).Count
$untracked = ($gitStatus | Where-Object { $_ -match '^\?' }).Count
if ($modified  -gt 0) { Warn "$modified uncommitted change(s)" }
if ($untracked -gt 0) { Warn "$untracked untracked file(s)" }
if ($modified -eq 0 -and $untracked -eq 0) { Ok "Working tree clean" }
Pop-Location

# ── Package root ────────────────────────────────────────────────────
Hdr "Package Root  (src/pk232py/)"
Check-File "$SRC\__init__.py"      50
Check-File "$SRC\__main__.py"      50
Check-File "$SRC\main.py"         200
Check-File "$SRC\config.py"       500
Check-File "$SRC\mode_manager.py" 500

# ── comm/ ───────────────────────────────────────────────────────────
Hdr "comm/"
Check-File "$SRC\comm\__init__.py"       10
Check-File "$SRC\comm\constants.py"     200
Check-File "$SRC\comm\frame.py"         500
Check-File "$SRC\comm\hostmode.py"      300
Check-File "$SRC\comm\autobaud.py"      300
Check-File "$SRC\comm\kiss.py"          300
Check-File "$SRC\comm\serial_manager.py" 500

# ── modes/ ──────────────────────────────────────────────────────────
Hdr "modes/  (v1.0)"
Check-File "$SRC\modes\__init__.py"      400
Check-File "$SRC\modes\base_mode.py"     200
Check-File "$SRC\modes\packet_hf.py"     500
Check-File "$SRC\modes\packet_vhf.py"    300
Check-File "$SRC\modes\pactor.py"        500
Check-File "$SRC\modes\amtor.py"         500
Check-File "$SRC\modes\rtty_baudot.py"   500
Check-File "$SRC\modes\rtty_ascii.py"    400

Hdr "modes/  (v1.1)"
Check-File "$SRC\modes\morse.py"         400
Check-File "$SRC\modes\navtex.py"        400

Hdr "modes/  (v1.2)"
Check-File "$SRC\modes\tdm.py"           300
Check-File "$SRC\modes\fax.py"           300
Check-File "$SRC\modes\signal_analysis.py" 300

# ── ui/ ─────────────────────────────────────────────────────────────
Hdr "ui/"
Check-File "$SRC\ui\__init__.py"              100
Check-File "$SRC\ui\main_window.py"          1000
Check-File "$SRC\ui\tnc_config_dialog.py"     500
Check-File "$SRC\ui\dialogs\__init__.py"       10
Check-File "$SRC\ui\dialogs\tnc_config.py"    500

# ── Infrastructure ───────────────────────────────────────────────────
Hdr "log/"
Check-File "$SRC\log\__init__.py"              10
Check-File "$SRC\log\qso_log.py"              500

Hdr "macros/"
Check-File "$SRC\macros\__init__.py"           10
Check-File "$SRC\macros\macro_manager.py"     500

Hdr "maildrop/"
Check-File "$SRC\maildrop\__init__.py"        100
Check-File "$SRC\maildrop\maildrop.py"        500
Check-File "$SRC\maildrop\message_store.py"   500

# ── tests/ ──────────────────────────────────────────────────────────
Hdr "tests/"
Check-File "$SRC\tests\__init__.py"            10
Check-File "$SRC\tests\test_hostmode.py"      500

# ── Project files ────────────────────────────────────────────────────
Hdr "Project files"
Check-File "$RepoRoot\pyproject.toml"         100
Check-File "$RepoRoot\README.md"              100
Check-File "$RepoRoot\.gitignore"              50

# ── Python syntax check ──────────────────────────────────────────────
Hdr "Python Syntax Check"
$pyFiles = Get-ChildItem -Path $SRC -Filter "*.py" -Recurse
$syntaxFail = 0
foreach ($f in $pyFiles) {
    $result = python -c "
import ast, sys
try:
    ast.parse(open(r'$($f.FullName)', encoding='utf-8').read())
except SyntaxError as e:
    print(f'SYNTAX ERROR: $($f.Name): {e}')
    sys.exit(1)
" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Fail $result
        $syntaxFail++
    }
}
if ($syntaxFail -eq 0) { Ok "All .py files parse without syntax errors" }

# ── Summary ──────────────────────────────────────────────────────────
Write-Host "`nSummary" -ForegroundColor White
Write-Host "  OK:       $Pass" -ForegroundColor Green
if ($Warn -gt 0) { Write-Host "  Warnings: $Warn" -ForegroundColor Yellow }
if ($Fail -gt 0) { Write-Host "  Failed:   $Fail" -ForegroundColor Red }

if ($Fail -eq 0) {
    Write-Host "`nRepository is complete." -ForegroundColor Green
    exit 0
} else {
    Write-Host "`nRepository has $Fail missing or empty file(s)." -ForegroundColor Red
    exit 1
}
#!/usr/bin/env bash
# check_repo.sh — PK232PY repository completeness check
# Usage: bash check_repo.sh [repo_root]
# Default repo root: current directory

set -euo pipefail

REPO="${1:-.}"
SRC="$REPO/src/pk232py"
PASS=0
FAIL=0
WARN=0

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

ok()   { echo -e "  ${GREEN}✓${NC}  $1"; ((PASS++)); }
fail() { echo -e "  ${RED}✗${NC}  $1"; ((FAIL++)); }
warn() { echo -e "  ${YELLOW}!${NC}  $1"; ((WARN++)); }
hdr()  { echo -e "\n${CYAN}${BOLD}── $1 ──${NC}"; }

check_file() {
    local path="$1"
    local min_bytes="${2:-100}"
    local label="${path#$REPO/}"
    if [ ! -f "$path" ]; then
        fail "MISSING:  $label"
    elif [ ! -s "$path" ]; then
        fail "EMPTY:    $label"
    else
        local size
        size=$(wc -c < "$path")
        if [ "$size" -lt "$min_bytes" ]; then
            warn "SMALL ($size B): $label"
        else
            ok "$label  ($size B)"
        fi
    fi
}

echo -e "\n${BOLD}PK232PY Repository Check${NC}"
echo -e "Repo: $REPO"
echo -e "Date: $(date -u '+%Y-%m-%d %H:%M UTC')"

# ── Git status ──────────────────────────────────────────────────────
hdr "Git Status"
cd "$REPO"
git status --short
echo ""
BRANCH=$(git branch --show-current)
HEAD=$(git log --oneline -1)
echo -e "  Branch: ${CYAN}$BRANCH${NC}"
echo -e "  HEAD:   $HEAD"
UNTRACKED=$(git status --short | grep '^?' | wc -l)
MODIFIED=$(git status --short | grep '^[^?]' | wc -l)
[ "$MODIFIED"  -gt 0 ] && warn "$MODIFIED uncommitted change(s)"
[ "$UNTRACKED" -gt 0 ] && warn "$UNTRACKED untracked file(s)"
[ "$MODIFIED"  -eq 0 ] && [ "$UNTRACKED" -eq 0 ] && ok "Working tree clean"

# ── Package root ────────────────────────────────────────────────────
hdr "Package Root  (src/pk232py/)"
check_file "$SRC/__init__.py"         50
check_file "$SRC/__main__.py"         50
check_file "$SRC/main.py"            200
check_file "$SRC/config.py"          500
check_file "$SRC/mode_manager.py"    500

# ── comm/ ───────────────────────────────────────────────────────────
hdr "comm/"
check_file "$SRC/comm/__init__.py"    10
check_file "$SRC/comm/constants.py"  200
check_file "$SRC/comm/frame.py"      500
check_file "$SRC/comm/hostmode.py"   300
check_file "$SRC/comm/autobaud.py"   300
check_file "$SRC/comm/kiss.py"       300
check_file "$SRC/comm/serial_manager.py" 500

# ── modes/ ──────────────────────────────────────────────────────────
hdr "modes/  (v1.0)"
check_file "$SRC/modes/__init__.py"  400
check_file "$SRC/modes/base_mode.py" 200
check_file "$SRC/modes/packet_hf.py" 500
check_file "$SRC/modes/packet_vhf.py" 300
check_file "$SRC/modes/pactor.py"    500
check_file "$SRC/modes/amtor.py"     500
check_file "$SRC/modes/rtty_baudot.py" 500
check_file "$SRC/modes/rtty_ascii.py"  400

hdr "modes/  (v1.1)"
check_file "$SRC/modes/morse.py"     400
check_file "$SRC/modes/navtex.py"    400

hdr "modes/  (v1.2)"
check_file "$SRC/modes/tdm.py"       300
check_file "$SRC/modes/fax.py"       300
check_file "$SRC/modes/signal_analysis.py" 300

# ── ui/ ─────────────────────────────────────────────────────────────
hdr "ui/"
check_file "$SRC/ui/__init__.py"     100
check_file "$SRC/ui/main_window.py"  1000
check_file "$SRC/ui/tnc_config_dialog.py" 500
check_file "$SRC/ui/dialogs/__init__.py"   10
check_file "$SRC/ui/dialogs/tnc_config.py" 500

# ── Infrastructure ───────────────────────────────────────────────────
hdr "log/"
check_file "$SRC/log/__init__.py"     10
check_file "$SRC/log/qso_log.py"     500

hdr "macros/"
check_file "$SRC/macros/__init__.py"  10
check_file "$SRC/macros/macro_manager.py" 500

hdr "maildrop/"
check_file "$SRC/maildrop/__init__.py"  100
check_file "$SRC/maildrop/maildrop.py"  500
check_file "$SRC/maildrop/message_store.py" 500

# ── tests/ ──────────────────────────────────────────────────────────
hdr "tests/"
check_file "$SRC/tests/__init__.py"   10
check_file "$SRC/tests/test_hostmode.py" 500

# ── Project files ────────────────────────────────────────────────────
hdr "Project files"
check_file "$REPO/pyproject.toml"    100
check_file "$REPO/README.md"         100
check_file "$REPO/.gitignore"         50

# ── Python syntax check ──────────────────────────────────────────────
hdr "Python Syntax Check"
SYNTAX_FAIL=0
while IFS= read -r -d '' pyfile; do
    label="${pyfile#$REPO/}"
    if python3 -c "
import ast, sys
try:
    ast.parse(open('$pyfile').read())
except SyntaxError as e:
    print(f'  SYNTAX ERROR in $label: {e}')
    sys.exit(1)
" 2>&1; then
        :  # silent on success
    else
        ((FAIL++)); ((SYNTAX_FAIL++))
    fi
done < <(find "$SRC" -name "*.py" -print0)
[ "$SYNTAX_FAIL" -eq 0 ] && ok "All .py files parse without syntax errors"

# ── Summary ──────────────────────────────────────────────────────────
echo -e "\n${BOLD}Summary${NC}"
echo -e "  ${GREEN}✓  $PASS passed${NC}"
[ "$WARN" -gt 0 ] && echo -e "  ${YELLOW}!  $WARN warnings${NC}"
[ "$FAIL" -gt 0 ] && echo -e "  ${RED}✗  $FAIL failed${NC}"

if [ "$FAIL" -eq 0 ]; then
    echo -e "\n${GREEN}${BOLD}Repository is complete.${NC}\n"
    exit 0
else
    echo -e "\n${RED}${BOLD}Repository has $FAIL missing or empty file(s).${NC}\n"
    exit 1
fi
#!/bin/bash
# ============================================================================
# run_tests.sh — Run all tests and save a timestamped report to tests/reports/
#
# Usage:
#   sh tests/run_tests.sh              # run all test suites
#   sh tests/run_tests.sh preflight    # preflight only
#   sh tests/run_tests.sh supply_chain # supply chain logic only
#   sh tests/run_tests.sh governance   # governance layer only
#   sh tests/run_tests.sh observability
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPORTS_DIR="$SCRIPT_DIR/reports"
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
SUITE="${1:-all}"

# Load env
if [ -f "$REPO_ROOT/.env" ]; then
    set -a && source "$REPO_ROOT/.env" && set +a
fi
export CHROMA_DB_PATH="${CHROMA_DB_PATH:-$REPO_ROOT/database/chroma_db}"
export GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT:-cloudassiciate}"

mkdir -p "$REPORTS_DIR"

REPORT_HTML="$REPORTS_DIR/report_${TIMESTAMP}.html"
REPORT_MD="$REPORTS_DIR/report_${TIMESTAMP}.md"
LATEST_HTML="$REPORTS_DIR/latest.html"
LATEST_MD="$REPORTS_DIR/latest.md"

echo ""
echo "╔════════════════════════════════════════════════════╗"
echo "║  Supply Chain — Test Suite                        ║"
echo "╠════════════════════════════════════════════════════╣"
echo "  Suite:   $SUITE"
echo "  Report:  tests/reports/report_${TIMESTAMP}.html"
echo "╚════════════════════════════════════════════════════╝"
echo ""

# ── Select test files ────────────────────────────────────────
case "$SUITE" in
    preflight)
        TEST_FILES="tests/test_preflight.py"
        SUITE_LABEL="Pre-flight Checks"
        ;;
    supply_chain)
        TEST_FILES="tests/test_supply_chain.py"
        SUITE_LABEL="Supply Chain Logic"
        ;;
    governance)
        TEST_FILES="tests/test_governance.py"
        SUITE_LABEL="Governance Layer"
        ;;
    observability)
        TEST_FILES="tests/test_observability.py"
        SUITE_LABEL="Observability"
        ;;
    all|*)
        TEST_FILES="tests/test_preflight.py tests/test_supply_chain.py"
        [ -f "$REPO_ROOT/tests/test_governance.py" ]    && TEST_FILES="$TEST_FILES tests/test_governance.py"
        [ -f "$REPO_ROOT/tests/test_observability.py" ] && TEST_FILES="$TEST_FILES tests/test_observability.py"
        SUITE_LABEL="Full Suite"
        ;;
esac

# ── Run pytest — capture output and exit code separately ─────
cd "$REPO_ROOT"
OUTPUT_FILE="/tmp/pytest_output_${TIMESTAMP}.txt"

python3 -m pytest $TEST_FILES \
    -v \
    --tb=short \
    --html="$REPORT_HTML" \
    --self-contained-html \
    2>&1 | tee "$OUTPUT_FILE"

EXIT_CODE=$?

# ── Parse counts from output ─────────────────────────────────
PASSED=$(grep -c " PASSED" "$OUTPUT_FILE" 2>/dev/null || true)
FAILED=$(grep -c " FAILED" "$OUTPUT_FILE" 2>/dev/null || true)
SKIPPED=$(grep -c " SKIPPED" "$OUTPUT_FILE" 2>/dev/null || true)
PASSED=${PASSED:-0}
FAILED=${FAILED:-0}
SKIPPED=${SKIPPED:-0}
TOTAL=$(( PASSED + FAILED + SKIPPED ))

if [ "$EXIT_CODE" -eq 0 ]; then
    STATUS_BADGE="✅ PASS"
    STATUS="PASS"
else
    STATUS_BADGE="❌ FAIL"
    STATUS="FAIL"
fi

# ── Write Markdown report ─────────────────────────────────────
cat > "$REPORT_MD" <<MDEOF
# Supply Chain Test Report

| Field    | Value |
|----------|-------|
| Suite    | ${SUITE_LABEL} |
| Run at   | ${TIMESTAMP} |
| Status   | ${STATUS_BADGE} |
| Passed   | ${PASSED} |
| Failed   | ${FAILED} |
| Skipped  | ${SKIPPED} |
| Total    | ${TOTAL} |

## Test Output

\`\`\`
$(cat "$OUTPUT_FILE")
\`\`\`
MDEOF

# ── Copy to latest ───────────────────────────────────────────
cp "$REPORT_HTML" "$LATEST_HTML"
cp "$REPORT_MD"   "$LATEST_MD"
rm -f "$OUTPUT_FILE"

# ── Serve report on port 9090 ────────────────────────────────
REPORT_PORT=9090
# Kill any existing report server on that port
lsof -ti:$REPORT_PORT | xargs kill -9 2>/dev/null || true
sleep 0.5

python3 -m http.server $REPORT_PORT \
    --directory "$REPORTS_DIR" \
    > /dev/null 2>&1 &
REPORT_SERVER_PID=$!

sleep 0.5

# Open browser to the latest report
if command -v open >/dev/null 2>&1; then
    open "http://localhost:$REPORT_PORT/latest.html"
elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "http://localhost:$REPORT_PORT/latest.html"
fi

# ── Summary ──────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════"
echo "  $STATUS_BADGE   $PASSED passed  |  $FAILED failed  |  $SKIPPED skipped  |  $TOTAL total"
echo "  Report : http://localhost:$REPORT_PORT/latest.html"
echo "  Saved  : tests/reports/report_${TIMESTAMP}.html"
echo "           tests/reports/report_${TIMESTAMP}.md"
echo "  Server : PID $REPORT_SERVER_PID (port $REPORT_PORT)"
echo "════════════════════════════════════════════════════"
echo ""

exit $EXIT_CODE

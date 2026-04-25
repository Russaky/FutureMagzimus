#!/bin/bash
# Run all 5 Day Zero connection tests from the project root.
# Usage: cd "/Users/user/AntiGravity/Editing archive" && bash tests/run_all_tests.sh

if [ -f "venv/bin/python3" ]; then
  PYTHON="venv/bin/python3"
elif [ -f "venv/bin/python" ]; then
  PYTHON="venv/bin/python"
else
  PYTHON="$(which python3)"
fi

PASS=0
FAIL=0
RESULTS=()

run_test() {
  local label="$1"
  local script="$2"
  output=$($PYTHON "$script" 2>&1)
  if echo "$output" | grep -q "^PASS"; then
    PASS=$((PASS+1))
    RESULTS+=("  ✅  $label: $output")
  else
    FAIL=$((FAIL+1))
    RESULTS+=("  ❌  $label: $output")
  fi
}

echo ""
echo "=== Day Zero — Connection Tests ==="
echo ""

run_test "GCS read/write"       "tests/test_gcs.py"
run_test "n8n API"              "tests/test_n8n_api.py"
run_test "n8n Webhook"          "tests/test_n8n_webhook.py"
run_test "Gemini API"           "tests/test_vertex.py"
run_test "Archive Drive"        "tests/test_archive_drive.py"

echo ""
for r in "${RESULTS[@]}"; do echo "$r"; done
echo ""
echo "=== $PASS/5 PASS | $FAIL/5 FAIL ==="
echo ""

if [ "$FAIL" -gt 0 ]; then exit 1; fi

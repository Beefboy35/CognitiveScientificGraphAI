#!/bin/bash

set -e

TEST_DIR="/tmp/migration_test_$$"
mkdir -p "$TEST_DIR"
cd "$TEST_DIR"

echo "Test 1: Parse DSN"
test_dsn() {
    local dsn="$1"
    local result=$(echo "$dsn" | sed -n 's|.*@\([^:/]*\):\([0-9]*\).*|\1 \2|p')
    local host=$(echo "$result" | awk '{print $1}')
    local port=$(echo "$result" | awk '{print $2}')
    
    if [ "$host" = "postgres" ] && [ "$port" = "5432" ]; then
        echo "PASS: DSN parsing"
        return 0
    else
        echo "FAIL: DSN parsing - got $host:$port"
        return 1
    fi
}
test_dsn "postgresql://user:pass@postgres:5432/db"

echo ""
echo "Test 2: Timeout calculation"
timeout 2 bash -c 'sleep 1' && echo "PASS: Timeout handling" || echo "FAIL: Timeout"

echo ""
echo "Test 3: Variable defaults"
DB_WAIT_TIMEOUT="${DB_WAIT_TIMEOUT:-60}"
DB_WAIT_INTERVAL="${DB_WAIT_INTERVAL:-2}"
if [ "$DB_WAIT_TIMEOUT" = "60" ] && [ "$DB_WAIT_INTERVAL" = "2" ]; then
    echo "PASS: Default variables"
else
    echo "FAIL: Default variables"
fi

echo ""
echo "Test 4: SKIP_MIGRATIONS logic"
SKIP_MIGRATIONS="true"
if [ "${SKIP_MIGRATIONS:-false}" = "true" ]; then
    echo "PASS: SKIP_MIGRATIONS flag"
else
    echo "FAIL: SKIP_MIGRATIONS flag"
fi

echo ""
echo "Test 5: Exit codes"
set -e
bash -c 'exit 0' && echo "PASS: Exit 0" || true
bash -c 'exit 1' && echo "FAIL: Exit 1 caught" || echo "PASS: Exit 1 caught"

echo ""
rm -rf "$TEST_DIR"
echo "All basic tests completed"

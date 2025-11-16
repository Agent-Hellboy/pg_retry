#!/bin/bash
# Run pgTAP tests for pg_retry extension

set -e

echo "🧪 Running pgTAP tests for pg_retry extension"

# Check if pgTAP is installed (skip installation since it's done by Makefile)
if ! psql -c "CREATE EXTENSION IF NOT EXISTS pgtap; SELECT plan(1); SELECT pass('test'); SELECT * FROM finish();" >/dev/null 2>&1; then
    echo "❌ pgTAP not working properly"
    exit 1
fi

# Check if pg_retry extension is available
if ! psql -c "CREATE EXTENSION IF NOT EXISTS pg_retry" >/dev/null 2>&1; then
    echo "❌ pg_retry extension not available"
    exit 1
fi

echo "📋 Running basic functionality tests..."
psql -f setup.sql

echo "📋 Running retry scenario tests..."
psql -f retry_scenarios.sql

echo "✅ pgTAP tests completed"

# Generate test report
echo "📊 Test Results Summary:"
echo "========================"
psql -c "
SELECT
    CASE WHEN passed THEN '✅ PASS' ELSE '❌ FAIL' END as status,
    test_name,
    diag
FROM tap_results
ORDER BY id;
" 2>/dev/null || echo "No detailed results available"


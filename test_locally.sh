#!/bin/bash

# Local testing script for pg_retry extension on macOS
# Run this from your pg_retry project directory

set -e

echo "🧪 Testing pg_retry extension locally on macOS"
echo

# Check if we're in the right directory
if [ ! -f "Makefile" ] || [ ! -d "system_tests" ]; then
    echo "❌ Error: Run this script from the pg_retry project root directory"
    exit 1
fi

echo "📋 Step 1: Checking PostgreSQL..."
if ! command -v pg_isready &> /dev/null; then
    echo "❌ PostgreSQL not found. Installing..."
    brew install postgresql
    brew services start postgresql
    sleep 3
fi

if ! pg_isready -q; then
    echo "❌ PostgreSQL is not running. Starting..."
    brew services start postgresql
    sleep 3
    if ! pg_isready -q; then
        echo "❌ Failed to start PostgreSQL"
        exit 1
    fi
fi

echo "✅ PostgreSQL is running"

echo
echo "📋 Step 1.5: Checking for optional test dependencies..."
# Check if pgreplay is available (user has it installed locally)
if command -v pgreplay --help >/dev/null 2>&1; then
    echo "✅ pgreplay is available"
else
    echo "⚠️  pgreplay not available - replay tests will skip"
fi

# Check if pgbench is available (usually comes with PostgreSQL)
if command -v pgbench &> /dev/null; then
    echo "✅ pgbench is available"
else
    echo "⚠️  pgbench not found - pgbench tests will skip"
fi

echo
echo "📋 Step 3: Installing Python dependencies..."
cd system_tests

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo "Installing psycopg and pytest..."
pip install psycopg-binary pytest

cd ..

echo
echo "📋 Step 4: Building extension..."
make clean
make

echo
echo "📋 Step 5: Installing extension..."
sudo make install

echo
echo "📋 Step 6: Running regression tests..."
make installcheck || {
    echo "❌ Regression tests failed"
    echo "Check regression.diffs for details"
    exit 1
}

echo
echo "📋 Step 7: Setting up system test environment..."

# Create test log for pgreplay
echo "Creating test log for pgreplay..."
echo "test log for pgreplay testing" > /tmp/test_pg_log.log

echo
echo "📋 Step 8: Running system tests..."

# Set environment variables for system tests
export SYSTEMTEST_PYTEST_FLAGS="--all"
export PGREPLAY_LOG="/tmp/test_pg_log.log"
export PG_FAULT_SQL="SELECT retry.execute_failure_plan('test_fault')"
export PG_FAULT_SQLSTATE="40001"
export PG_FAULT_EXPECT_SUCCESS="false"
export PG_FAULT_MAX_TRIES="1"
export PG_FAULT_BASE_DELAY_MS="10"
export PG_FAULT_MAX_DELAY_MS="100"

echo "Environment variables set:"
echo "  SYSTEMTEST_PYTEST_FLAGS: $SYSTEMTEST_PYTEST_FLAGS"
echo "  PGREPLAY_LOG: $PGREPLAY_LOG"
echo "  PG_FAULT_SQL: $PG_FAULT_SQL"
echo

# Run system tests
make systemtest SYSTEMTEST_SKIP_INSTALL=1

echo
echo "🎉 All tests completed successfully!"
echo
echo "📊 Test Summary:"
echo "- ✅ Regression tests passed"
echo "- ✅ System tests completed"
echo "- ✅ Extension is working correctly"